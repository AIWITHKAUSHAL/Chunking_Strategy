"""Command-line entry point for the chunking lab.

Subcommands::

    python -m chunking_lab.cli doctor                 # check config, key and gold labels
    python -m chunking_lab.cli chunk --strategy fixed # inspect one configuration's chunks
    python -m chunking_lab.cli ask "question"         # one-off retrieval + generation
    python -m chunking_lab.cli experiment             # the full sweep, writes results/
    python -m chunking_lab.cli serve                  # start the live visualizer server
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any

from chunking_lab.config import get_settings
from chunking_lab.document import load_document
from chunking_lab.euri_client import EuriClient
from chunking_lab.experiment import (
    FULL_GRID,
    OVERLAP_GRID,
    SIZE_GRID,
    run_config,
    run_experiment,
    save_results,
)
from chunking_lab.questions import QUESTIONS, validate_gold_spans
from chunking_lab.report import save_report
from chunking_lab.retriever import (
    ANSWER_SYSTEM_PROMPT,
    VectorStore,
    build_prompt,
)
from chunking_lab.strategies import STRATEGIES, chunk_document

LOGGER = logging.getLogger("chunking_lab")


def _console_progress(event: str, payload: dict[str, Any]) -> None:
    """Print a one-line summary for the progress events worth showing on a terminal.

    Args:
        event: Event name.
        payload: Event payload.
    """
    if event == "chunking_done":
        print(f"    chunked -> {payload['n_chunks']} chunks")
    elif event == "embedding_done":
        print(f"    embedded {payload['n_chunks']} chunks ({payload['dims']}d)")
    elif event == "query_done":
        result = payload["result"]
        print(
            f"    {result['qid']}: recall={result['recall']:.0f} "
            f"coverage={result['span_coverage']:.2f} "
            f"precision={result['context_precision']:.4f}"
        )


def cmd_doctor(_: argparse.Namespace) -> int:
    """Verify configuration, API reachability and gold-label integrity.

    Args:
        _: Parsed arguments (unused).

    Returns:
        Process exit code.
    """
    settings = get_settings()
    client = EuriClient(settings)
    document = load_document(settings.document_path)

    print(f"mode              : {settings.mode}")
    print(f"embedding model   : {client.embedding_model}")
    print(f"chat model        : {client.chat_model}")
    print(f"document          : {document.path.name} ({document.n_chars:,} chars)")
    print(
        f"structure         : {document.n_paragraphs} paragraphs, {document.n_sentences} sentences"
    )
    print(f"strategies        : {', '.join(STRATEGIES)}")
    print(f"questions         : {len(QUESTIONS)}")

    missing = validate_gold_spans(document.text)
    print(f"gold labels       : {'OK' if not missing else f'{len(missing)} MISSING'}")
    for item in missing:
        print(f"  - {item}")

    if settings.offline:
        print("\nNo EURI_API_KEY found -- running with the deterministic offline embedder.")
        print("For a live run: cp .env.example .env and add your key.")
    else:
        print("\nProbing the gateway...")
        try:
            vector = client.embed_one("connectivity probe")
            print(f"  embeddings OK: {len(vector)} dimensions")
            reply = client.complete("Reply with the single word OK.", "Question: ready?")
            print(f"  chat OK: {reply[:60]}")
        except Exception as exc:  # noqa: BLE001 - diagnostic command, report anything
            print(f"  FAILED: {exc}")
            return 1
    return 0 if not missing else 1


def cmd_chunk(args: argparse.Namespace) -> int:
    """Chunk the document with one configuration and print the chunks.

    Args:
        args: Parsed arguments.

    Returns:
        Process exit code.
    """
    settings = get_settings()
    document = load_document(settings.document_path)
    client = EuriClient(settings)
    chunks = chunk_document(
        document.text,
        args.strategy,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        embed_fn=client.embed,
    )
    print(
        f"{args.strategy}  size={args.chunk_size}  overlap={args.chunk_overlap}  "
        f"-> {len(chunks)} chunks"
    )
    for chunk in chunks[: args.limit]:
        flags = "".join(
            [
                "W" if chunk.starts_mid_word else "-",
                "S" if chunk.starts_mid_sentence else "-",
                "E" if chunk.ends_mid_sentence else "-",
            ]
        )
        print(f"  [{chunk.index:3}] {chunk.n_chars:5}c [{flags}] {chunk.preview}")
    if len(chunks) > args.limit:
        print(f"  ... {len(chunks) - args.limit} more (flags: W=mid-word S=mid-sentence E=cut end)")
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    """Retrieve for an arbitrary question and generate an answer.

    Args:
        args: Parsed arguments.

    Returns:
        Process exit code.
    """
    settings = get_settings()
    document = load_document(settings.document_path)
    client = EuriClient(settings)
    chunks = chunk_document(
        document.text,
        args.strategy,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        embed_fn=client.embed,
    )
    store = VectorStore(chunks, client.embed([c.text for c in chunks]))
    retrieved = store.search(client.embed_one(args.question), top_k=args.top_k)

    print(f"\nQ: {args.question}\n")
    for item in retrieved:
        print(f"  #{item.chunk.index} score={item.score:.4f} {item.chunk.preview}")
    answer = client.complete(ANSWER_SYSTEM_PROMPT, build_prompt(args.question, retrieved))
    print(f"\nA: {answer}\n")
    return 0


def cmd_experiment(args: argparse.Namespace) -> int:
    """Run the full sweep and write the JSON and Markdown artefacts.

    Args:
        args: Parsed arguments.

    Returns:
        Process exit code.
    """
    grid = {"size": SIZE_GRID, "overlap": OVERLAP_GRID, "both": FULL_GRID}[args.grid]
    strategies = args.strategies.split(",") if args.strategies else list(STRATEGIES)
    print(
        f"Sweeping {len(strategies)} strategies x {len(grid)} configurations "
        f"({len(strategies) * len(grid)} runs), top_k={args.top_k}, "
        f"generate={not args.no_generate}"
    )
    bundle = run_experiment(
        strategies=strategies,
        grid=grid,
        top_k=args.top_k,
        generate=not args.no_generate,
        progress=_console_progress if args.verbose else None,
    )
    json_path = save_results(bundle)
    report_path = save_report(bundle)
    print(f"\nWrote {json_path}")
    print(f"Wrote {report_path}")

    ranked = sorted(bundle["configs"], key=lambda c: -c["mean_span_coverage"])
    print("\nTop configurations by gold-span coverage:")
    for cfg in ranked[:5]:
        print(
            f"  {cfg['config_id']:26} coverage={cfg['mean_span_coverage']:.2f} "
            f"recall={cfg['mean_recall']:.2f} precision={cfg['mean_context_precision']:.4f} "
            f"chunks={cfg['n_chunks']}"
        )
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    """Run every strategy at one size/overlap pair and print a compact comparison.

    Args:
        args: Parsed arguments.

    Returns:
        Process exit code.
    """
    settings = get_settings()
    document = load_document(settings.document_path)
    client = EuriClient(settings)
    print(f"size={args.chunk_size} overlap={args.chunk_overlap} top_k={args.top_k}\n")
    header = f"{'strategy':12} {'chunks':>6} {'integrity':>10} {'recall':>7} {'coverage':>9}"
    print(header)
    print("-" * len(header))
    for strategy in STRATEGIES:
        result = run_config(
            document=document,
            client=client,
            strategy=strategy,
            chunk_size=args.chunk_size,
            chunk_overlap=args.chunk_overlap,
            top_k=args.top_k,
            generate=False,
        )
        print(
            f"{strategy:12} {result.n_chunks:6} {result.span_integrity:9.0%} "
            f"{result.mean_recall:6.0%} {result.mean_coverage:8.0%}"
        )
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    """Start the live visualizer server.

    Args:
        args: Parsed arguments.

    Returns:
        Process exit code.
    """
    import uvicorn

    print(f"Live visualizer: http://127.0.0.1:{args.port}")
    uvicorn.run("app.server:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser.

    Returns:
        The configured parser.
    """
    parser = argparse.ArgumentParser(
        prog="chunking-lab",
        description="Compare four chunking strategies on one document.",
    )
    # --verbose lives on every subcommand (via a parent parser) rather than on the top-level
    # parser, so `cli experiment --verbose` works -- argparse would otherwise require it to
    # appear before the subcommand name.
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--verbose", "-v", action="store_true", help="stream progress events")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser(
        "doctor", parents=[shared], help="check configuration and gold labels"
    ).set_defaults(func=cmd_doctor)

    common = {"strategy": list(STRATEGIES)}
    chunk = sub.add_parser("chunk", parents=[shared], help="print the chunks for one configuration")
    chunk.add_argument("--strategy", default="recursive", choices=common["strategy"])
    chunk.add_argument("--chunk-size", type=int, default=800)
    chunk.add_argument("--chunk-overlap", type=int, default=160)
    chunk.add_argument("--limit", type=int, default=12)
    chunk.set_defaults(func=cmd_chunk)

    ask = sub.add_parser("ask", parents=[shared], help="retrieve and answer one question")
    ask.add_argument("question")
    ask.add_argument("--strategy", default="recursive", choices=common["strategy"])
    ask.add_argument("--chunk-size", type=int, default=800)
    ask.add_argument("--chunk-overlap", type=int, default=160)
    ask.add_argument("--top-k", type=int, default=3)
    ask.set_defaults(func=cmd_ask)

    compare = sub.add_parser(
        "compare", parents=[shared], help="compare all strategies at one size/overlap"
    )
    compare.add_argument("--chunk-size", type=int, default=800)
    compare.add_argument("--chunk-overlap", type=int, default=160)
    compare.add_argument("--top-k", type=int, default=3)
    compare.set_defaults(func=cmd_compare)

    experiment = sub.add_parser("experiment", parents=[shared], help="run the full sweep")
    experiment.add_argument(
        "--grid",
        choices=["size", "overlap", "both"],
        default="both",
        help="size: 3 sizes; overlap: 3 overlaps at size 800; both: the union (default)",
    )
    experiment.add_argument("--strategies", default="", help="comma-separated subset")
    experiment.add_argument("--top-k", type=int, default=3)
    experiment.add_argument("--no-generate", action="store_true", help="skip the LLM calls")
    experiment.set_defaults(func=cmd_experiment)

    serve = sub.add_parser("serve", parents=[shared], help="start the live visualizer server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    serve.set_defaults(func=cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch to the selected subcommand.

    Args:
        argv: Argument vector; defaults to ``sys.argv[1:]``.

    Returns:
        Process exit code.
    """
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
