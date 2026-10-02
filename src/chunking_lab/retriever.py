"""An in-memory cosine-similarity vector store plus the span-level retrieval metrics.

The store is intentionally minimal -- a dense matrix and an ``argsort`` -- because the variable
under study is the chunking strategy, not the index. Holding the index, the embedding model and
the generation model constant is what makes the comparison in :mod:`chunking_lab.experiment`
attributable to chunking alone.

Three metrics are computed per question:

``recall``
    Did any retrieved chunk contain a gold span? (Binary, the headline number.)
``span_coverage``
    What fraction of the question's gold spans were recovered across the whole top-k window?
``context_precision``
    What fraction of the retrieved characters belong to a gold span? Punishes oversized chunks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from chunking_lab.document import normalise
from chunking_lab.questions import Question, span_in_text
from chunking_lab.strategies import Chunk

ANSWER_SYSTEM_PROMPT = (
    "You answer strictly from the provided context. If the context does not contain the "
    "answer, reply exactly: 'The provided context does not contain this information.' "
    "Never use outside knowledge. Keep the answer under 80 words."
)
"""System prompt used for generation, written so that retrieval gaps surface as refusals."""


@dataclass
class RetrievedChunk:
    """One chunk returned by the retriever, with its score and gold-span overlap.

    Attributes:
        chunk: The underlying chunk.
        score: Cosine similarity against the query embedding.
        rank: One-based position in the result list.
        gold_spans_hit: Gold spans fully contained in this chunk.
    """

    chunk: Chunk
    score: float
    rank: int
    gold_spans_hit: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation, including the chunk."""
        return {
            "rank": self.rank,
            "score": round(self.score, 4),
            "gold_spans_hit": list(self.gold_spans_hit),
            **self.chunk.to_dict(),
        }


@dataclass
class QuestionResult:
    """Retrieval and generation outcome for one question under one configuration.

    Attributes:
        qid: Question identifier.
        question: The question text.
        retrieved: The top-k retrieved chunks.
        recall: 1.0 when at least one gold span was retrieved, else 0.0.
        span_coverage: Fraction of the question's gold spans present in the top-k window.
        context_precision: Fraction of retrieved characters belonging to a gold span.
        answer: The generated answer, when generation was run.
        spans_found: Gold spans recovered anywhere in the top-k window.
        spans_missed: Gold spans absent from the top-k window.
    """

    qid: str
    question: str
    retrieved: list[RetrievedChunk]
    recall: float
    span_coverage: float
    context_precision: float
    answer: str = ""
    spans_found: list[str] = field(default_factory=list)
    spans_missed: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation of the result."""
        return {
            "qid": self.qid,
            "question": self.question,
            "recall": self.recall,
            "span_coverage": round(self.span_coverage, 4),
            "context_precision": round(self.context_precision, 4),
            "spans_found": self.spans_found,
            "spans_missed": self.spans_missed,
            "answer": self.answer,
            "retrieved": [r.to_dict() for r in self.retrieved],
        }


class VectorStore:
    """A dense vector index over the chunks of one chunking configuration.

    Args:
        chunks: The chunks to index.
        vectors: One embedding per chunk, in the same order.

    Raises:
        ValueError: If the chunk and vector counts disagree.
    """

    def __init__(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        """Build the index, pre-normalising vectors so search is a plain dot product.

        Args:
            chunks: The chunks to index.
            vectors: One embedding per chunk, in the same order.

        Raises:
            ValueError: If the chunk and vector counts disagree.
        """
        if len(chunks) != len(vectors):
            raise ValueError(f"{len(chunks)} chunks but {len(vectors)} vectors")
        self.chunks = chunks
        matrix = np.asarray(vectors, dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self.matrix = matrix / norms  # Pre-normalised, so similarity is a plain dot product.

    def __len__(self) -> int:
        """Return the number of indexed chunks."""
        return len(self.chunks)

    def search(self, query_vector: list[float], top_k: int = 3) -> list[RetrievedChunk]:
        """Return the ``top_k`` most similar chunks to a query vector.

        Args:
            query_vector: The embedded query.
            top_k: Number of chunks to return.

        Returns:
            Retrieved chunks ordered by descending cosine similarity.
        """
        if not self.chunks:
            return []
        query = np.asarray(query_vector, dtype=np.float32)
        norm = float(np.linalg.norm(query)) or 1.0
        scores = self.matrix @ (query / norm)
        k = min(top_k, len(self.chunks))
        top = np.argpartition(-scores, k - 1)[:k]
        top = top[np.argsort(-scores[top])]
        return [
            RetrievedChunk(chunk=self.chunks[int(i)], score=float(scores[int(i)]), rank=rank + 1)
            for rank, i in enumerate(top)
        ]


def score_retrieval(
    question: Question,
    retrieved: list[RetrievedChunk],
) -> QuestionResult:
    """Compute span-level retrieval metrics for one question.

    Args:
        question: The question, carrying its gold spans.
        retrieved: The retriever's output for that question.

    Returns:
        A :class:`QuestionResult` with recall, span coverage and context precision filled in.
    """
    for item in retrieved:
        item.gold_spans_hit = tuple(
            span for span in question.gold_spans if span_in_text(span, item.chunk.text)
        )

    window = " ".join(item.chunk.text for item in retrieved)
    found = [span for span in question.gold_spans if span_in_text(span, window)]
    missed = [span for span in question.gold_spans if span not in found]

    retrieved_chars = len(normalise(window)) or 1
    gold_chars = sum(len(normalise(span)) for span in found)

    return QuestionResult(
        qid=question.qid,
        question=question.text,
        retrieved=retrieved,
        recall=1.0 if found else 0.0,
        span_coverage=len(found) / max(1, len(question.gold_spans)),
        context_precision=min(1.0, gold_chars / retrieved_chars),
        spans_found=found,
        spans_missed=missed,
    )


def build_prompt(question: str, retrieved: list[RetrievedChunk], char_budget: int = 8000) -> str:
    """Assemble the generation prompt from the retrieved chunks.

    Context is truncated at ``char_budget`` characters, mirroring the production template
    described in the handbook, so an over-large top-k silently loses its tail exactly as it
    would in the real system.

    Args:
        question: The question to answer.
        retrieved: Retrieved chunks, in rank order.
        char_budget: Maximum characters of context to include.

    Returns:
        The user-role prompt string.
    """
    parts: list[str] = []
    used = 0
    for item in retrieved:
        block = f"[chunk {item.chunk.index} | score {item.score:.3f}]\n{item.chunk.text}"
        if used + len(block) > char_budget:
            break
        parts.append(block)
        used += len(block)
    context = "\n\n".join(parts) if parts else "(no context retrieved)"
    return f"Context:\n{context}\n\nQuestion: {question}"
