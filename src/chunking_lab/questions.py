"""The five fixed evaluation questions and their span-level gold labels.

Labels are **spans of the source document**, not chunk identifiers. That distinction is the
whole reason two chunking strategies can be compared at all: a chunk-level label would be
invalidated the moment ``chunk_size`` changed, whereas a span survives every reconfiguration.

Each question is deliberately engineered to stress a different chunking failure:

====  ======================================================================================
 Q1   A recommendation and its justification sit in adjacent sentences -- tests overlap.
 Q2   A three-item enumeration spread over three long paragraphs -- tests completeness.
 Q3   A procedure that runs across a paragraph boundary -- tests boundary respect.
 Q4   A number in one paragraph, its consequence in the next -- tests overlap again.
 Q5   A fact in section 4 whose consequence is in section 6 -- tests multi-chunk retrieval.
====  ======================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from chunking_lab.document import normalise


@dataclass(frozen=True)
class Question:
    """One evaluation question with its gold answer spans.

    Attributes:
        qid: Stable short identifier.
        text: The question as asked of the retriever and the LLM.
        gold_spans: Verbatim document substrings that a correct answer must be grounded in.
        probes: What chunking weakness this question is designed to expose.
    """

    qid: str
    text: str
    gold_spans: tuple[str, ...]
    probes: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation of the question."""
        return {
            "qid": self.qid,
            "text": self.text,
            "gold_spans": list(self.gold_spans),
            "probes": self.probes,
        }


QUESTIONS: tuple[Question, ...] = (
    Question(
        qid="Q1",
        text=(
            "What chunk size and chunk overlap does the handbook recommend for technical "
            "manuals, and why is the overlap set that high?"
        ),
        gold_spans=(
            "chunk size of eight hundred characters with a chunk overlap of one hundred and "
            "sixty characters",
            "a step separated from its precondition retrieves as a confidently wrong answer",
        ),
        probes=(
            "The parameter values and the reason for them sit in neighbouring sentences. A "
            "strategy that cuts between them returns the number without the justification."
        ),
    ),
    Question(
        qid="Q2",
        text="What are the three failure modes of hybrid retrieval described in the handbook?",
        gold_spans=(
            "The first failure mode is score-scale mismatch",
            "The second failure mode is vocabulary collapse on short chunks",
            "The third failure mode is duplicate amplification",
        ),
        probes=(
            "A three-item enumeration spanning three long paragraphs. Small chunks cannot hold "
            "all three, so the answer's completeness depends directly on chunk size."
        ),
    ),
    Question(
        qid="Q3",
        text="How does the ingestion pipeline handle tables found inside PDF files?",
        gold_spans=(
            "reconstructs each table into a row-major Markdown table",
            "segmentation is forbidden from splitting inside it",
            "Tables wider than forty columns are the single exception",
        ),
        probes=(
            "A multi-step procedure with its exception at the very end of the paragraph. "
            "A mid-paragraph cut drops the exception silently."
        ),
    ),
    Question(
        qid="Q4",
        text=(
            "How many milliseconds are budgeted for reranking, and what does the platform do "
            "when that budget is exceeded?"
        ),
        gold_spans=(
            "Reranking is allotted 450 milliseconds",
            "falls back to returning the raw vector-search ordering",
            "rerank_degraded",
        ),
        probes=(
            "The allocation is stated in one paragraph and the timeout behaviour in the next. "
            "This is the clearest test of whether chunk_overlap is doing its job."
        ),
    ),
    Question(
        qid="Q5",
        text=(
            "What embedding dimensionality does the platform use, and how does that dimension "
            "affect the index memory footprint?"
        ),
        gold_spans=(
            "vectors of three thousand and seventy-two dimensions",
            "a single vector occupies twelve thousand two hundred and eighty-eight bytes",
            "chunk count, not corpus size, drives your memory bill",
        ),
        probes=(
            "The dimension is in section 4 and its memory consequence is in section 6. No "
            "single chunk can contain both, so the top-k list must span two sections."
        ),
    ),
)
"""The frozen question set. Identical across every strategy and every configuration."""


def span_in_text(span: str, text: str) -> bool:
    """Test whether a gold span appears in text, ignoring whitespace differences.

    Args:
        span: The gold span to look for.
        text: Text to search, typically one chunk or a concatenated context window.

    Returns:
        True when the normalised span is a substring of the normalised text.
    """
    return normalise(span).lower() in normalise(text).lower()


def validate_gold_spans(document: str) -> list[str]:
    """Check that every gold span really occurs in the source document.

    Guards against a label drifting out of sync with the document after an edit.

    Args:
        document: The source document text.

    Returns:
        Human-readable descriptions of any spans that could not be found; empty when all match.
    """
    missing: list[str] = []
    for question in QUESTIONS:
        for span in question.gold_spans:
            if not span_in_text(span, document):
                missing.append(f"{question.qid}: {span!r}")
    return missing
