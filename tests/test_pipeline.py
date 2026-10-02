"""Tests for retrieval, metrics, the experiment runner and the HTTP API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.server import app
from chunking_lab.document import load_document, normalise
from chunking_lab.euri_client import EuriClient
from chunking_lab.experiment import (
    run_config,
    structural_metrics,
    summarise_chunks,
)
from chunking_lab.questions import QUESTIONS, span_in_text
from chunking_lab.report import render_report
from chunking_lab.retriever import VectorStore, build_prompt, score_retrieval
from chunking_lab.strategies import chunk_document


@pytest.fixture(scope="module")
def client() -> EuriClient:
    """Return a shared embedding client."""
    return EuriClient()


@pytest.fixture(scope="module")
def store(client):
    """Return a vector store over recursive 800/160 chunks."""
    document = load_document().text
    chunks = chunk_document(document, "recursive", 800, 160)
    return VectorStore(chunks, client.embed([c.text for c in chunks]))


def test_store_rejects_mismatched_vectors():
    chunks = chunk_document("a. b. c.", "fixed", 200, 0)
    with pytest.raises(ValueError, match="vectors"):
        VectorStore(chunks, [])


def test_search_returns_top_k_in_descending_score_order(store, client):
    results = store.search(client.embed_one("how are tables handled?"), top_k=4)
    assert len(results) == 4
    assert [r.rank for r in results] == [1, 2, 3, 4]
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_top_k_larger_than_the_index_is_clamped(client):
    chunks = chunk_document("One. Two. Three.", "sentence", 400, 0)
    small = VectorStore(chunks, client.embed([c.text for c in chunks]))
    assert len(small.search(client.embed_one("one"), top_k=50)) == len(chunks)


def test_identical_text_embeds_identically(client):
    first, second = client.embed(["repeatable input", "repeatable input"])
    assert first == second


def test_metrics_stay_in_range(store, client):
    for question in QUESTIONS:
        result = score_retrieval(question, store.search(client.embed_one(question.text), top_k=3))
        assert result.recall in (0.0, 1.0)
        assert 0.0 <= result.span_coverage <= 1.0
        assert 0.0 <= result.context_precision <= 1.0
        assert len(result.spans_found) + len(result.spans_missed) == len(question.gold_spans)


def test_recall_is_one_exactly_when_a_span_was_found(store, client):
    for question in QUESTIONS:
        result = score_retrieval(question, store.search(client.embed_one(question.text), top_k=3))
        assert (result.recall == 1.0) == bool(result.spans_found)


def test_span_matching_ignores_whitespace_differences():
    assert span_in_text("one two three", "ONE\n  TWO\tTHREE")
    assert not span_in_text("one two four", "one two three")
    assert normalise("a \n\n b   c") == "a b c"


def test_structural_metrics_report_chunks_needed():
    document = load_document().text
    chunks = chunk_document(document, "recursive", 800, 160)
    integrity, needed = structural_metrics(chunks)
    assert 0.0 <= integrity <= 1.0
    assert set(needed) == {q.qid for q in QUESTIONS}
    assert all(value == -1 or value >= 1 for value in needed.values())


def test_summarise_chunks_counts_boundary_damage():
    document = load_document().text
    stats = summarise_chunks(chunk_document(document, "fixed", 800, 160), 800)
    assert stats["n"] > 0
    assert stats["over_budget"] == 0
    assert stats["starts_mid_word"] > 0
    assert stats["redundancy"] > 1.0


def test_prompt_respects_its_character_budget(store, client):
    retrieved = store.search(client.embed_one("reranking latency"), top_k=5)
    assert len(build_prompt("q", retrieved, char_budget=300)) < len(
        build_prompt("q", retrieved, char_budget=9000)
    )
    assert "Question: q" in build_prompt("q", retrieved)


def test_prompt_handles_an_empty_result_set():
    assert "(no context retrieved)" in build_prompt("q", [])


def test_run_config_and_report_render(client):
    document = load_document()
    result = run_config(document, client, "recursive", 800, 160, top_k=2, generate=False)
    assert result.config_id == "recursive_800_160"
    assert len(result.question_results) == len(QUESTIONS)
    assert all(len(r.retrieved) == 2 for r in result.question_results)

    bundle = {
        "generated_at": "now",
        "mode": "offline",
        "embedding_model": client.embedding_model,
        "chat_model": client.chat_model,
        "top_k": 2,
        "document": document.to_dict(),
        "questions": [q.to_dict() for q in QUESTIONS],
        "strategies": {},
        "grid": [[800, 160]],
        "configs": [result.to_dict(include_chunks=False)],
    }
    report = render_report(bundle)
    assert "Chunk geometry" in report
    assert "recursive_800_160" in report
    assert "Which chunks each strategy retrieved" in report


def test_progress_callback_fires_for_every_stage(client):
    seen: list[str] = []
    run_config(
        load_document(),
        client,
        "fixed",
        600,
        0,
        top_k=1,
        generate=False,
        progress=lambda name, _payload: seen.append(name),
    )
    assert {"chunking_start", "chunking_done", "embedding_done", "config_done"} <= set(seen)
    assert seen.count("query_done") == len(QUESTIONS)


# --------------------------------------------------------------------------- API


@pytest.fixture(scope="module")
def api() -> TestClient:
    """Return a test client for the FastAPI app."""
    return TestClient(app)


def test_meta_endpoint_exposes_controls(api):
    body = api.get("/api/meta").json()
    assert set(body["strategies"]) == {"fixed", "recursive", "sentence", "semantic"}
    assert len(body["questions"]) == 5
    assert body["mode"] in {"live", "offline"}
    assert body["document"]["n_chars"] > 1000


def test_chunk_endpoint_returns_chunks_and_stats(api):
    params = {"strategy": "fixed", "chunk_size": 500, "chunk_overlap": 50}
    body = api.get("/api/chunk", params=params).json()
    assert body["stats"]["n"] == len(body["chunks"])
    assert body["chunks"][0]["strategy"] == "fixed"


def test_chunk_endpoint_validates_input(api):
    assert api.get("/api/chunk", params={"strategy": "nope"}).status_code == 400
    assert (
        api.get("/api/chunk", params={"chunk_size": 400, "chunk_overlap": 400}).status_code == 400
    )


def test_run_endpoint_streams_sse_events(api):
    with api.stream(
        "GET",
        "/api/run",
        params={"strategies": "fixed", "chunk_size": 800, "chunk_overlap": 160, "generate": False},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        payload = "".join(response.iter_text())
    for event in ("event: meta", "event: chunking_done", "event: strategy_done", "event: done"):
        assert event in payload


def test_run_endpoint_rejects_unknown_strategies(api):
    assert api.get("/api/run", params={"strategies": "bogus"}).status_code == 400


def test_index_serves_the_visualizer(api):
    response = api.get("/")
    assert response.status_code == 200
    assert "Chunking Lab" in response.text
