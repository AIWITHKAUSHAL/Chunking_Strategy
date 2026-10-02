"""FastAPI server backing the live chunking visualizer.

The visualizer is a single static HTML page that talks to this server over Server-Sent Events,
so a demo shows the pipeline actually happening -- chunks appearing one at a time, boundaries
being painted onto the document, embeddings being counted, then retrieval and generation per
question -- rather than replaying a precomputed recording.

Endpoints
---------
``GET /``
    The visualizer page.
``GET /api/meta``
    Document statistics, strategy catalogue, question set, active models and mode.
``GET /api/document``
    The raw source text, used by the page to paint chunk spans.
``GET /api/chunk``
    Synchronous chunk-only call for instant slider feedback (no embeddings, no retrieval).
``GET /api/run``
    The SSE stream: a full chunk -> embed -> retrieve -> generate run.
``GET /api/results``
    The saved sweep artefact from ``results/experiment_results.json``, when present.

Run it with::

    uvicorn app.server:app --reload --port 8000
"""

from __future__ import annotations

import json
import queue
import threading
from collections.abc import Iterator
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from chunking_lab.config import PROJECT_ROOT, get_settings
from chunking_lab.document import load_document
from chunking_lab.euri_client import EuriClient
from chunking_lab.experiment import SIZE_GRID, run_config, summarise_chunks
from chunking_lab.questions import QUESTIONS
from chunking_lab.strategies import STRATEGIES, chunk_document

VISUALIZER = PROJECT_ROOT / "docs" / "chunking_visualizer.html"
RESULTS_JSON = PROJECT_ROOT / "results" / "experiment_results.json"

app = FastAPI(
    title="Chunking Strategies Live Lab",
    description="Live comparison of four chunking strategies over one document.",
    version="1.0.0",
)


def _sse(event: str, data: dict[str, Any]) -> str:
    """Format one Server-Sent Event frame.

    Args:
        event: Event name the browser listens for.
        data: JSON-serialisable payload.

    Returns:
        The wire-format SSE frame, terminated by a blank line.
    """
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    """Serve the visualizer page.

    Returns:
        The HTML file response.

    Raises:
        HTTPException: If the visualizer file is missing.
    """
    if not VISUALIZER.exists():
        raise HTTPException(status_code=404, detail="Visualizer HTML not found")
    return FileResponse(VISUALIZER, media_type="text/html")


@app.get("/api/meta")
def meta() -> JSONResponse:
    """Return everything the page needs to render its controls before any run.

    Returns:
        Document statistics, strategy catalogue, questions, grid and active models.
    """
    settings = get_settings()
    client = EuriClient(settings)
    document = load_document(settings.document_path)
    return JSONResponse(
        {
            "mode": settings.mode,
            "embedding_model": client.embedding_model,
            "chat_model": client.chat_model,
            "top_k": settings.top_k,
            "document": document.to_dict(),
            "grid": [list(pair) for pair in SIZE_GRID],
            "questions": [q.to_dict() for q in QUESTIONS],
            "strategies": {
                key: {
                    "key": key,
                    "label": spec.label,
                    "blurb": spec.blurb,
                    "separators": list(spec.separators) if spec.separators else None,
                    "needs_embeddings": spec.needs_embeddings,
                    "pros": list(spec.pros),
                    "cons": list(spec.cons),
                }
                for key, spec in STRATEGIES.items()
            },
            "has_saved_results": RESULTS_JSON.exists(),
        }
    )


@app.get("/api/document")
def document_text() -> JSONResponse:
    """Return the raw source document text.

    Returns:
        The document text and its filename.
    """
    document = load_document(get_settings().document_path)
    return JSONResponse({"name": document.path.name, "text": document.text})


@app.get("/api/chunk")
def chunk_only(
    strategy: str = Query("recursive"),
    chunk_size: int = Query(800, ge=100, le=4000),
    chunk_overlap: int = Query(160, ge=0, le=2000),
) -> JSONResponse:
    """Chunk the document and return the chunks without embedding or retrieving.

    Backs the instant feedback the page gives while the size and overlap sliders are dragged.

    Args:
        strategy: Strategy key.
        chunk_size: Maximum chunk size in characters.
        chunk_overlap: Overlap in characters.

    Returns:
        The chunks plus their summary statistics.

    Raises:
        HTTPException: On an unknown strategy or an invalid size/overlap pair.
    """
    if strategy not in STRATEGIES:
        raise HTTPException(status_code=400, detail=f"Unknown strategy {strategy!r}")
    if chunk_overlap >= chunk_size:
        raise HTTPException(status_code=400, detail="chunk_overlap must be < chunk_size")

    settings = get_settings()
    document = load_document(settings.document_path)
    client = EuriClient(settings)
    chunks = chunk_document(
        document.text,
        strategy,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        embed_fn=client.embed,
    )
    return JSONResponse(
        {
            "strategy": strategy,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "stats": summarise_chunks(chunks, chunk_size),
            "chunks": [c.to_dict() for c in chunks],
        }
    )


def _run_stream(
    strategies: list[str],
    chunk_size: int,
    chunk_overlap: int,
    top_k: int,
    generate: bool,
) -> Iterator[str]:
    """Drive one live run and yield SSE frames as it progresses.

    Each configuration is executed on a worker thread while this generator drains a queue, so
    frames reach the browser as the work happens instead of after it finishes.

    Args:
        strategies: Strategy keys to run, in order.
        chunk_size: Maximum chunk size in characters.
        chunk_overlap: Overlap in characters.
        top_k: Chunks retrieved per question.
        generate: Whether to call the chat model per question.

    Yields:
        SSE frames.
    """
    settings = get_settings()
    client = EuriClient(settings)
    document = load_document(settings.document_path)

    yield _sse(
        "meta",
        {
            "mode": settings.mode,
            "embedding_model": client.embedding_model,
            "chat_model": client.chat_model,
            "strategies": strategies,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "top_k": top_k,
            "generate": generate,
            "document": document.to_dict(),
            "n_questions": len(QUESTIONS),
        },
    )

    for position, strategy in enumerate(strategies, start=1):
        events: queue.Queue[tuple[str, dict[str, Any]] | None] = queue.Queue()
        holder: dict[str, Any] = {}

        def worker(
            strategy: str = strategy,
            events: queue.Queue = events,
            holder: dict[str, Any] = holder,
        ) -> None:
            """Execute one configuration, pushing progress events onto the queue."""
            try:
                result = run_config(
                    document=document,
                    client=client,
                    strategy=strategy,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                    top_k=top_k,
                    generate=generate,
                    progress=lambda event, data: events.put((event, data)),
                )
                holder["result"] = result
            except Exception as exc:  # noqa: BLE001 - surfaced to the browser as an event
                events.put(("error", {"message": str(exc), "strategy": strategy}))  # noqa: B023
            finally:
                events.put(None)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        yield _sse(
            "strategy_start",
            {
                "strategy": strategy,
                "label": STRATEGIES[strategy].label,
                "position": position,
                "total": len(strategies),
            },
        )

        while True:
            item = events.get()
            if item is None:
                break
            name, payload = item
            yield _sse(name, {"strategy": strategy, **payload})

        thread.join(timeout=1.0)
        result = holder.get("result")
        if result is not None:
            yield _sse(
                "strategy_done",
                {
                    "strategy": strategy,
                    "summary": result.to_dict(include_chunks=True),
                },
            )

    yield _sse("done", {"client_stats": client.stats()})


@app.get("/api/run")
def run(
    strategies: str = Query("fixed,recursive,sentence,semantic"),
    chunk_size: int = Query(800, ge=100, le=4000),
    chunk_overlap: int = Query(160, ge=0, le=2000),
    top_k: int = Query(3, ge=1, le=10),
    generate: bool = Query(True),
) -> StreamingResponse:
    """Stream a full live run over Server-Sent Events.

    Args:
        strategies: Comma-separated strategy keys.
        chunk_size: Maximum chunk size in characters.
        chunk_overlap: Overlap in characters.
        top_k: Chunks retrieved per question.
        generate: Whether to call the chat model per question.

    Returns:
        A ``text/event-stream`` response.

    Raises:
        HTTPException: On unknown strategies or an invalid size/overlap pair.
    """
    keys = [s.strip() for s in strategies.split(",") if s.strip()]
    unknown = [k for k in keys if k not in STRATEGIES]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown strategies: {unknown}")
    if not keys:
        raise HTTPException(status_code=400, detail="No strategies requested")
    if chunk_overlap >= chunk_size:
        raise HTTPException(status_code=400, detail="chunk_overlap must be < chunk_size")

    return StreamingResponse(
        _run_stream(keys, chunk_size, chunk_overlap, top_k, generate),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/results")
def saved_results() -> JSONResponse:
    """Return the saved sweep artefact.

    Returns:
        The contents of ``results/experiment_results.json``.

    Raises:
        HTTPException: If the artefact has not been generated yet.
    """
    if not RESULTS_JSON.exists():
        raise HTTPException(
            status_code=404,
            detail="No saved results. Run: python -m chunking_lab.cli experiment",
        )
    return JSONResponse(json.loads(RESULTS_JSON.read_text(encoding="utf-8")))
