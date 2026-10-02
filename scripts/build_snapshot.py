"""Bake an experiment bundle into the visualizer so the page works without a server.

The visualizer prefers a live FastAPI backend. When it cannot reach one -- opened straight from
disk, or viewed through GitHub's HTML preview -- it falls back to ``EMBEDDED_SNAPSHOT``, which
this script writes into ``docs/chunking_visualizer.html`` between the ``SNAPSHOT_START`` and
``SNAPSHOT_END`` markers.

Usage::

    python scripts/build_snapshot.py                      # from results/experiment_results.json
    python scripts/build_snapshot.py --run                # run a fresh sweep first
    python scripts/build_snapshot.py --sizes 800,160      # keep only these configurations
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from chunking_lab.experiment import FULL_GRID, run_experiment, save_results  # noqa: E402
from chunking_lab.report import save_report  # noqa: E402

VISUALIZER = PROJECT_ROOT / "docs" / "chunking_visualizer.html"
RESULTS = PROJECT_ROOT / "results" / "experiment_results.json"
MARKER = re.compile(r"/\*SNAPSHOT_START\*/.*?/\*SNAPSHOT_END\*/", re.DOTALL)

CHUNK_FIELDS = (
    "index",
    "text",
    "start",
    "end",
    "strategy",
    "n_chars",
    "n_tokens_est",
    "starts_mid_sentence",
    "ends_mid_sentence",
    "starts_mid_word",
    "meta",
)
"""Chunk fields kept in the snapshot; everything else is derivable in the browser."""


RETRIEVED_TEXT_CAP = 700
"""Characters of retrieved-chunk text kept in the snapshot; the UI truncates at 420 anyway."""


def _trim_retrieved(config: dict) -> dict:
    """Cap the retrieved-chunk text inside one configuration's question results.

    Retrieval results carry a copy of every retrieved chunk's text, which dominates the
    snapshot's size across 20 configurations. The visualizer truncates this text for display
    regardless, so capping it here costs nothing visible.

    Args:
        config: One serialised configuration result.

    Returns:
        A copy with retrieved-chunk text capped.
    """
    trimmed = dict(config)
    trimmed["questions"] = [
        {
            **question,
            "retrieved": [
                {
                    **item,
                    "text": (
                        item["text"]
                        if len(item["text"]) <= RETRIEVED_TEXT_CAP
                        else item["text"][:RETRIEVED_TEXT_CAP] + " …"
                    ),
                }
                for item in question["retrieved"]
            ],
        }
        for question in config.get("questions", [])
    ]
    return trimmed


def slim(bundle: dict, keep: set[str] | None, ribbon: set[str] | None) -> dict:
    """Reduce a result bundle to what the visualizer actually reads.

    Full chunk text is the bulk of the payload, so it is retained only for the configurations
    named by ``ribbon``. Every other configuration keeps its metrics -- enough for the
    scoreboard and the retrieval columns, which carry their own chunk text per question -- but
    not the chunk ribbon. Starting the server restores the ribbon for every configuration.

    Args:
        bundle: The full experiment bundle.
        keep: ``"{size}_{overlap}"`` keys to retain, or None to keep every configuration.
        ribbon: ``"{size}_{overlap}"`` keys whose full chunk text to retain, or None for all.

    Returns:
        A trimmed bundle suitable for inlining into the HTML.
    """
    configs = [
        _trim_retrieved(cfg)
        for cfg in bundle["configs"]
        if keep is None or f"{cfg['chunk_size']}_{cfg['chunk_overlap']}" in keep
    ]
    wanted = {
        cfg["config_id"]
        for cfg in configs
        if ribbon is None or f"{cfg['chunk_size']}_{cfg['chunk_overlap']}" in ribbon
    }
    chunks = {
        config_id: [{k: c[k] for k in CHUNK_FIELDS} for c in chunk_list]
        for config_id, chunk_list in bundle.get("chunks_by_config", {}).items()
        if config_id in wanted
    }
    return {
        "generated_at": bundle["generated_at"],
        "mode": bundle["mode"],
        "embedding_model": bundle["embedding_model"],
        "chat_model": bundle["chat_model"],
        "top_k": bundle["top_k"],
        "document": bundle["document"],
        "questions": bundle["questions"],
        "strategies": bundle["strategies"],
        "grid": bundle["grid"],
        "configs": configs,
        "chunks_by_config": chunks,
    }


def inject(snapshot: dict) -> int:
    """Write the snapshot into the visualizer between its markers.

    Args:
        snapshot: The trimmed bundle to inline.

    Returns:
        The byte size of the injected JSON.

    Raises:
        SystemExit: If the visualizer or its markers are missing.
    """
    if not VISUALIZER.exists():
        raise SystemExit(f"Visualizer not found: {VISUALIZER}")
    html = VISUALIZER.read_text(encoding="utf-8")
    if not MARKER.search(html):
        raise SystemExit("SNAPSHOT_START/END markers not found in the visualizer")
    payload = json.dumps(snapshot, separators=(",", ":"))
    # </script> inside the JSON would terminate the host script tag early.
    payload = payload.replace("</", "<\\/")
    block = f"/*SNAPSHOT_START*/\nconst EMBEDDED_SNAPSHOT = {payload};\n/*SNAPSHOT_END*/"
    VISUALIZER.write_text(MARKER.sub(lambda _: block, html, count=1), encoding="utf-8")
    return len(payload)


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, obtain a bundle and inject it.

    Args:
        argv: Argument vector; defaults to ``sys.argv[1:]``.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="run a fresh sweep before injecting")
    parser.add_argument("--no-generate", action="store_true", help="skip LLM calls when running")
    parser.add_argument(
        "--sizes",
        default="",
        help="semicolon-separated size,overlap pairs to keep (default: all)",
    )
    parser.add_argument(
        "--ribbon-for",
        default="800,160",
        help="size,overlap pairs that keep full chunk text; 'all' keeps every one (large)",
    )
    args = parser.parse_args(argv)

    if args.run:
        print("Running sweep...")
        bundle = run_experiment(grid=FULL_GRID, generate=not args.no_generate)
        save_results(bundle)
        save_report(bundle)
    else:
        if not RESULTS.exists():
            raise SystemExit(
                f"{RESULTS} not found. Run it first:\n"
                "  python -m chunking_lab.cli experiment\n"
                "or pass --run to do both at once."
            )
        bundle = json.loads(RESULTS.read_text(encoding="utf-8"))

    keep = (
        {pair.strip().replace(",", "_") for pair in args.sizes.split(";") if pair.strip()}
        if args.sizes
        else None
    )
    ribbon = (
        None
        if args.ribbon_for.strip().lower() == "all"
        else {pair.strip().replace(",", "_") for pair in args.ribbon_for.split(";") if pair.strip()}
    )
    snapshot = slim(bundle, keep, ribbon)
    size = inject(snapshot)
    print(
        f"Injected {len(snapshot['configs'])} configurations "
        f"({len(snapshot['chunks_by_config'])} with full chunk text, "
        f"{size / 1024:.0f} KB JSON) into {VISUALIZER.relative_to(PROJECT_ROOT)}"
    )
    print(f"Visualizer is now {VISUALIZER.stat().st_size / 1024:.0f} KB total.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
