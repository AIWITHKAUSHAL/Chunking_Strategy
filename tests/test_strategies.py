"""Tests for the four chunking strategies and their shared invariants.

The invariants matter more than the exact chunk counts: a strategy that silently exceeds its
size budget, loses document text, or reports offsets that do not line up with the source would
invalidate every number in the experiment.
"""

from __future__ import annotations

import pytest

from chunking_lab.document import load_document
from chunking_lab.euri_client import EuriClient
from chunking_lab.questions import QUESTIONS, validate_gold_spans
from chunking_lab.strategies import (
    STRATEGIES,
    chunk_document,
    split_paragraphs,
    split_sentences,
)

SIZES = [(400, 40), (800, 160), (1200, 300)]


@pytest.fixture(scope="module")
def document() -> str:
    """Return the shared source document text."""
    return load_document().text


@pytest.fixture(scope="module")
def embed_fn():
    """Return an embedding callback (offline unless a key is configured)."""
    return EuriClient().embed


@pytest.mark.parametrize("strategy", list(STRATEGIES))
@pytest.mark.parametrize(("size", "overlap"), SIZES)
def test_chunks_respect_size_budget(document, embed_fn, strategy, size, overlap):
    chunks = chunk_document(document, strategy, size, overlap, embed_fn=embed_fn)
    assert chunks, "strategy produced no chunks"
    oversized = [c for c in chunks if c.n_chars > size]
    # Only the sentence-aware strategies may exceed the budget, and only for a single
    # indivisible sentence that is longer than the budget itself.
    for chunk in oversized:
        assert strategy in {"sentence", "semantic"}
        assert len(split_sentences(chunk.text)) == 1


@pytest.mark.parametrize("strategy", list(STRATEGIES))
def test_offsets_point_into_the_document(document, embed_fn, strategy):
    chunks = chunk_document(document, strategy, 800, 160, embed_fn=embed_fn)
    for chunk in chunks:
        assert 0 <= chunk.start <= chunk.end <= len(document)
    assert [c.index for c in chunks] == list(range(len(chunks)))
    assert all(a.start <= b.start for a, b in zip(chunks, chunks[1:], strict=False))


@pytest.mark.parametrize("strategy", list(STRATEGIES))
def test_full_document_is_covered(document, embed_fn, strategy):
    """Every strategy must emit enough text to account for the whole document."""
    chunks = chunk_document(document, strategy, 800, 160, embed_fn=embed_fn)
    assert sum(c.n_chars for c in chunks) >= 0.85 * len(document)
    assert chunks[-1].end >= 0.95 * len(document)


def test_fixed_size_steps_by_size_minus_overlap(document):
    chunks = chunk_document(document, "fixed", 500, 100)
    starts = [c.meta["window_start"] for c in chunks]
    steps = {b - a for a, b in zip(starts, starts[1:], strict=False)}
    assert steps == {400}


def test_fixed_size_is_the_only_strategy_that_cuts_words(document):
    fixed = chunk_document(document, "fixed", 800, 160)
    recursive = chunk_document(document, "recursive", 800, 160)
    sentence = chunk_document(document, "sentence", 800, 160)
    assert sum(c.starts_mid_word for c in fixed) > 5
    assert sum(c.starts_mid_word for c in recursive) == 0
    assert sum(c.starts_mid_word for c in sentence) == 0


def test_zero_overlap_produces_no_repeated_text(document):
    chunks = chunk_document(document, "fixed", 600, 0)
    for previous, current in zip(chunks, chunks[1:], strict=False):
        assert current.start >= previous.end - 1


def test_more_overlap_means_more_total_characters(document):
    low = chunk_document(document, "fixed", 800, 0)
    high = chunk_document(document, "fixed", 800, 400)
    assert sum(c.n_chars for c in high) > sum(c.n_chars for c in low)
    assert len(high) > len(low)


def test_overlap_must_be_smaller_than_size(document):
    with pytest.raises(ValueError, match="chunk_overlap"):
        chunk_document(document, "fixed", 400, 400)
    with pytest.raises(ValueError, match="chunk_overlap"):
        chunk_document(document, "recursive", 400, 500)


def test_semantic_requires_an_embedder(document):
    with pytest.raises(ValueError, match="embed_fn"):
        chunk_document(document, "semantic", 800, 160, embed_fn=None)


def test_recursive_records_the_separator_it_used(document):
    chunks = chunk_document(document, "recursive", 800, 160)
    separators = {c.meta["separator_used"] for c in chunks}
    assert separators, "no separator metadata recorded"
    assert separators <= {repr(s) for s in ("\n\n", "\n", ". ", " ", "")}


def test_sentence_strategy_never_crosses_a_paragraph(document):
    chunks = chunk_document(document, "sentence", 1200, 0)
    indices = [c.meta["paragraph_index"] for c in chunks]
    assert indices == sorted(indices)
    assert len(set(indices)) == len(split_paragraphs(document))


def test_semantic_records_why_each_boundary_was_placed(document, embed_fn):
    chunks = chunk_document(document, "semantic", 800, 160, embed_fn=embed_fn)
    reasons = {c.meta.get("boundary_reason") for c in chunks}
    assert reasons <= {"topic_shift", "size_cap", "document_end"}
    assert "topic_shift" in reasons


def test_unknown_strategy_raises():
    with pytest.raises(KeyError, match="Unknown strategy"):
        chunk_document("text", "nonexistent")


def test_sentence_splitter_keeps_abbreviations_together():
    sentences = split_sentences("Use e.g. this one. Then stop.")
    assert sentences == ["Use e.g. this one.", "Then stop."]


def test_every_gold_span_exists_in_the_document(document):
    assert validate_gold_spans(document) == []
    assert len(QUESTIONS) == 5
    assert sum(len(q.gold_spans) for q in QUESTIONS) == 14
