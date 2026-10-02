"""The strategy x chunk_size x chunk_overlap sweep and its artefacts.

One run holds the document, the embedding model, the generation model, the index and the
question set constant, and varies **only** the chunking configuration. Anything that differs in
the output is therefore caused by chunking.

Metrics fall into two families:

*Structural* metrics depend on chunking alone and need no retrieval:

``span_integrity``
    Fraction of gold spans that survive chunking intact inside at least one chunk. A span cut
    across a boundary is unretrievable in principle -- no embedding model can recover it.
``chunks_needed``
    Minimum number of chunks required to cover all of a question's gold spans. When this
    exceeds ``top_k``, the question is unanswerable completely however good the embedder is.

*Retrieval* metrics depend on the embedder as well, and are reported at the configured ``top_k``:
``recall``, ``span_coverage`` and ``context_precision`` (see :mod:`chunking_lab.retriever`).
"""

from __future__ import annotations

import json
import logging
import statistics
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from chunking_lab.config import Settings, get_settings
from chunking_lab.document import SourceDocument, load_document
from chunking_lab.euri_client import EuriClient
from chunking_lab.questions import QUESTIONS, Question, span_in_text, validate_gold_spans
from chunking_lab.retriever import (
    ANSWER_SYSTEM_PROMPT,
    QuestionResult,
    VectorStore,
    build_prompt,
    score_retrieval,
)
from chunking_lab.strategies import STRATEGIES, Chunk, chunk_document

LOGGER = logging.getLogger(__name__)

SIZE_GRID: tuple[tuple[int, int], ...] = (
    (400, 40),
    (800, 160),
    (1200, 300),
)
"""The three (chunk_size, chunk_overlap) pairs swept by default: 10%, 20% and 25% overlap."""

OVERLAP_GRID: tuple[tuple[int, int], ...] = (
    (800, 0),
    (800, 160),
    (800, 400),
)
"""A second sweep holding size at 800 and varying overlap only: 0%, 20% and 50%."""

FULL_GRID: tuple[tuple[int, int], ...] = (
    (400, 40),
    (800, 160),
    (1200, 300),
    (800, 0),
    (800, 400),
)
"""Union of both sweeps: three sizes at 10/20/25% overlap, plus 0% and 50% overlap at 800."""

ProgressFn = Callable[[str, dict[str, Any]], None]
"""Callback signature for streaming progress events to a console or an SSE stream."""


@dataclass
class ConfigResult:
    """Everything measured for one (strategy, chunk_size, chunk_overlap) configuration.

    Attributes:
        strategy: Strategy key.
        chunk_size: Configured maximum chunk size in characters.
        chunk_overlap: Configured overlap in characters.
        n_chunks: Number of chunks produced.
        chunk_stats: Size distribution and boundary-damage counters.
        span_integrity: Fraction of gold spans surviving intact in some chunk.
        chunks_needed: Per-question minimum chunk count to cover all gold spans.
        question_results: Per-question retrieval and generation outcomes.
        elapsed_s: Wall-clock seconds spent on this configuration.
        chunks: The chunks themselves, retained for the visualizer.
    """

    strategy: str
    chunk_size: int
    chunk_overlap: int
    n_chunks: int
    chunk_stats: dict[str, Any]
    span_integrity: float
    chunks_needed: dict[str, int]
    question_results: list[QuestionResult]
    elapsed_s: float
    chunks: list[Chunk] = field(default_factory=list)

    @property
    def config_id(self) -> str:
        """Return a stable identifier such as ``recursive_800_160``."""
        return f"{self.strategy}_{self.chunk_size}_{self.chunk_overlap}"

    @property
    def mean_recall(self) -> float:
        """Return mean recall across the question set."""
        return statistics.fmean(r.recall for r in self.question_results)

    @property
    def mean_coverage(self) -> float:
        """Return mean gold-span coverage across the question set."""
        return statistics.fmean(r.span_coverage for r in self.question_results)

    @property
    def mean_precision(self) -> float:
        """Return mean context precision across the question set."""
        return statistics.fmean(r.context_precision for r in self.question_results)

    def to_dict(self, include_chunks: bool = True) -> dict[str, Any]:
        """Return a JSON-serialisable representation.

        Args:
            include_chunks: When False, omit the chunk texts to keep the payload small.

        Returns:
            The serialised configuration result.
        """
        payload: dict[str, Any] = {
            "config_id": self.config_id,
            "strategy": self.strategy,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "overlap_pct": round(100 * self.chunk_overlap / self.chunk_size, 1),
            "n_chunks": self.n_chunks,
            "chunk_stats": self.chunk_stats,
            "span_integrity": round(self.span_integrity, 4),
            "chunks_needed": self.chunks_needed,
            "mean_recall": round(self.mean_recall, 4),
            "mean_span_coverage": round(self.mean_coverage, 4),
            "mean_context_precision": round(self.mean_precision, 4),
            "elapsed_s": round(self.elapsed_s, 2),
            "questions": [r.to_dict() for r in self.question_results],
        }
        if include_chunks:
            payload["chunks"] = [c.to_dict() for c in self.chunks]
        return payload


def summarise_chunks(chunks: Sequence[Chunk], chunk_size: int) -> dict[str, Any]:
    """Compute the size distribution and boundary-damage counters for a chunk set.

    Args:
        chunks: The chunks to summarise.
        chunk_size: The configured budget, used to count over-budget chunks.

    Returns:
        A dictionary of summary statistics.
    """
    if not chunks:
        return {"n": 0}
    sizes = [c.n_chars for c in chunks]
    return {
        "n": len(chunks),
        "min_chars": min(sizes),
        "max_chars": max(sizes),
        "mean_chars": round(statistics.fmean(sizes), 1),
        "median_chars": round(statistics.median(sizes), 1),
        "stdev_chars": round(statistics.pstdev(sizes), 1) if len(sizes) > 1 else 0.0,
        "total_chars": sum(sizes),
        "mean_tokens_est": round(statistics.fmean(c.n_tokens_est for c in chunks), 1),
        "over_budget": sum(1 for s in sizes if s > chunk_size),
        "starts_mid_sentence": sum(c.starts_mid_sentence for c in chunks),
        "ends_mid_sentence": sum(c.ends_mid_sentence for c in chunks),
        "starts_mid_word": sum(c.starts_mid_word for c in chunks),
        "pct_broken_boundaries": round(
            100
            * sum(1 for c in chunks if c.starts_mid_sentence or c.ends_mid_sentence)
            / len(chunks),
            1,
        ),
        "redundancy": round(sum(sizes) / max(1, chunks[-1].end), 3),
    }


def structural_metrics(
    chunks: Sequence[Chunk],
    questions: Sequence[Question] = QUESTIONS,
) -> tuple[float, dict[str, int]]:
    """Compute span integrity and per-question minimum chunk coverage.

    These depend only on how the document was cut, so they isolate the chunking effect from
    the embedding model entirely.

    Args:
        chunks: The chunks produced by one configuration.
        questions: The question set.

    Returns:
        A tuple of (span integrity in ``[0, 1]``, mapping of question id to chunks needed).
    """
    total = 0
    intact = 0
    needed: dict[str, int] = {}
    for question in questions:
        holders: set[int] = set()
        for span in question.gold_spans:
            total += 1
            hits = [c.index for c in chunks if span_in_text(span, c.text)]
            if hits:
                intact += 1
                holders.add(hits[0])
        # -1 marks a question whose spans cannot all be covered, because one was severed.
        covered_all = sum(
            1 for span in question.gold_spans if any(span_in_text(span, c.text) for c in chunks)
        )
        needed[question.qid] = len(holders) if covered_all == len(question.gold_spans) else -1
    return (intact / total if total else 0.0), needed


def run_config(
    document: SourceDocument,
    client: EuriClient,
    strategy: str,
    chunk_size: int,
    chunk_overlap: int,
    top_k: int = 3,
    generate: bool = False,
    questions: Sequence[Question] = QUESTIONS,
    progress: ProgressFn | None = None,
    **strategy_kwargs: Any,
) -> ConfigResult:
    """Chunk, embed, retrieve and optionally generate for one configuration.

    Args:
        document: The shared source document.
        client: Embedding and chat client.
        strategy: Strategy key.
        chunk_size: Maximum chunk size in characters.
        chunk_overlap: Overlap in characters.
        top_k: Number of chunks retrieved per question.
        generate: When True, call the chat model for each question.
        questions: The question set.
        progress: Optional callback receiving ``(event_name, payload)`` as work proceeds.
        **strategy_kwargs: Extra options forwarded to the strategy.

    Returns:
        The populated :class:`ConfigResult`.
    """
    started = time.perf_counter()

    def emit(event: str, **payload: Any) -> None:
        """Forward one progress event to the callback, if one was supplied."""
        if progress:
            progress(event, payload)

    emit("chunking_start", strategy=strategy, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunks = chunk_document(
        document.text,
        strategy,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        embed_fn=client.embed,
        **strategy_kwargs,
    )
    stats = summarise_chunks(chunks, chunk_size)
    emit(
        "chunking_done",
        n_chunks=len(chunks),
        stats=stats,
        chunks=[c.to_dict() for c in chunks],
    )

    emit("embedding_start", n_chunks=len(chunks))
    vectors = client.embed([c.text for c in chunks])
    emit("embedding_done", n_chunks=len(chunks), dims=len(vectors[0]) if vectors else 0)

    store = VectorStore(chunks, vectors)
    integrity, needed = structural_metrics(chunks, questions)

    results: list[QuestionResult] = []
    for question in questions:
        emit("query_start", qid=question.qid, question=question.text)
        retrieved = store.search(client.embed_one(question.text), top_k=top_k)
        result = score_retrieval(question, retrieved)
        if generate:
            result.answer = client.complete(
                ANSWER_SYSTEM_PROMPT,
                build_prompt(question.text, retrieved),
            )
        results.append(result)
        emit("query_done", qid=question.qid, result=result.to_dict())

    elapsed = time.perf_counter() - started
    emit("config_done", config_id=f"{strategy}_{chunk_size}_{chunk_overlap}", elapsed_s=elapsed)

    return ConfigResult(
        strategy=strategy,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        n_chunks=len(chunks),
        chunk_stats=stats,
        span_integrity=integrity,
        chunks_needed=needed,
        question_results=results,
        elapsed_s=elapsed,
        chunks=chunks,
    )


def iter_grid(
    strategies: Sequence[str] = tuple(STRATEGIES),
    grid: Sequence[tuple[int, int]] = SIZE_GRID,
) -> Iterator[tuple[str, int, int]]:
    """Yield every (strategy, chunk_size, chunk_overlap) combination in the sweep.

    Args:
        strategies: Strategy keys to include.
        grid: ``(chunk_size, chunk_overlap)`` pairs to include.

    Yields:
        One configuration tuple at a time.
    """
    for strategy in strategies:
        for chunk_size, chunk_overlap in grid:
            yield strategy, chunk_size, chunk_overlap


def run_experiment(
    strategies: Sequence[str] = tuple(STRATEGIES),
    grid: Sequence[tuple[int, int]] = SIZE_GRID,
    top_k: int = 3,
    generate: bool = True,
    settings: Settings | None = None,
    progress: ProgressFn | None = None,
) -> dict[str, Any]:
    """Run the full sweep and return a JSON-serialisable result bundle.

    Args:
        strategies: Strategy keys to sweep.
        grid: ``(chunk_size, chunk_overlap)`` pairs to sweep.
        top_k: Chunks retrieved per question.
        generate: Whether to call the chat model for each question.
        settings: Settings override.
        progress: Optional progress callback.

    Returns:
        The complete result bundle, ready to be written to JSON.

    Raises:
        ValueError: If any gold span no longer occurs in the source document.
    """
    resolved = settings or get_settings()
    document = load_document(resolved.document_path)
    missing = validate_gold_spans(document.text)
    if missing:
        raise ValueError(f"Gold spans missing from the document: {missing}")

    client = EuriClient(resolved)
    configs: list[ConfigResult] = []
    combos = list(iter_grid(strategies, grid))

    for i, (strategy, chunk_size, chunk_overlap) in enumerate(combos, start=1):
        LOGGER.info(
            "[%d/%d] %s size=%d overlap=%d", i, len(combos), strategy, chunk_size, chunk_overlap
        )
        if progress:
            progress("config_start", {"index": i, "total": len(combos), "strategy": strategy})
        configs.append(
            run_config(
                document=document,
                client=client,
                strategy=strategy,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                top_k=top_k,
                generate=generate,
                progress=progress,
            )
        )

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "mode": resolved.mode,
        "embedding_model": client.embedding_model,
        "chat_model": client.chat_model,
        "top_k": top_k,
        "document": document.to_dict(),
        "questions": [q.to_dict() for q in QUESTIONS],
        "strategies": {
            key: {
                "label": spec.label,
                "blurb": spec.blurb,
                "separators": list(spec.separators) if spec.separators else None,
                "needs_embeddings": spec.needs_embeddings,
                "pros": list(spec.pros),
                "cons": list(spec.cons),
            }
            for key, spec in STRATEGIES.items()
        },
        "grid": [list(pair) for pair in grid],
        "client_stats": client.stats(),
        "configs": [c.to_dict(include_chunks=False) for c in configs],
        "chunks_by_config": {c.config_id: [ch.to_dict() for ch in c.chunks] for c in configs},
    }


def save_results(bundle: dict[str, Any], path: Path | None = None) -> Path:
    """Write a result bundle to JSON.

    Args:
        bundle: The bundle returned by :func:`run_experiment`.
        path: Destination path; defaults to ``results/experiment_results.json``.

    Returns:
        The path written to.
    """
    target = path or (get_settings().results_dir / "experiment_results.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    LOGGER.info("Wrote %s (%.1f KB)", target, target.stat().st_size / 1024)
    return target
