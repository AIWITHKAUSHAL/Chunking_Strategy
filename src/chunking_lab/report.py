"""Markdown rendering of experiment results.

Produces ``results/OBSERVATIONS.md``: the chunk-geometry table, the structural metrics, the
retrieval metrics, and a per-question breakdown of exactly which chunks each strategy retrieved.
Every number in the generated document comes from the result bundle, so the write-up cannot
drift away from the measurements.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from chunking_lab.config import get_settings


def _table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    """Render a Markdown table.

    Args:
        headers: Column headers.
        rows: Row values; each row must match the header count.

    Returns:
        The table as a Markdown string.
    """
    lines = [
        "| " + " | ".join(str(h) for h in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(str(c) for c in row) + " |" for row in rows)
    return "\n".join(lines)


def _pct(value: float) -> str:
    """Format a 0-1 ratio as a percentage string.

    Args:
        value: Ratio in ``[0, 1]``.

    Returns:
        The percentage, to one decimal place.
    """
    return f"{100 * value:.1f}%"


def render_geometry(bundle: dict[str, Any]) -> str:
    """Render the chunk-geometry comparison table.

    Args:
        bundle: An experiment result bundle.

    Returns:
        A Markdown section.
    """
    rows = []
    for cfg in bundle["configs"]:
        stats = cfg["chunk_stats"]
        rows.append(
            [
                cfg["strategy"],
                cfg["chunk_size"],
                f"{cfg['chunk_overlap']} ({cfg['overlap_pct']}%)",
                cfg["n_chunks"],
                stats.get("mean_chars", "-"),
                f"{stats.get('min_chars', '-')}-{stats.get('max_chars', '-')}",
                stats.get("stdev_chars", "-"),
                stats.get("starts_mid_word", "-"),
                f"{stats.get('pct_broken_boundaries', '-')}%",
                stats.get("redundancy", "-"),
            ]
        )
    return "## Chunk geometry\n\n" + _table(
        [
            "strategy",
            "size",
            "overlap",
            "chunks",
            "mean chars",
            "min-max",
            "stdev",
            "mid-word cuts",
            "broken boundaries",
            "redundancy",
        ],
        rows,
    )


def render_structural(bundle: dict[str, Any]) -> str:
    """Render the structural-metrics table, which is independent of the embedding model.

    Args:
        bundle: An experiment result bundle.

    Returns:
        A Markdown section.
    """
    qids = [q["qid"] for q in bundle["questions"]]
    rows = []
    for cfg in bundle["configs"]:
        needed = cfg["chunks_needed"]
        rows.append(
            [
                cfg["config_id"],
                _pct(cfg["span_integrity"]),
                *[("severed" if needed.get(q, -1) < 0 else needed.get(q, "-")) for q in qids],
            ]
        )
    return (
        "## Structural metrics (chunking only -- no embedding model involved)\n\n"
        "`span integrity` is the share of gold answer spans that survive chunking inside a "
        "single chunk. `chunks needed` is how many chunks must be retrieved to cover all of a "
        f"question's gold spans; anything above top_k={bundle['top_k']} cannot be answered "
        "completely no matter how good the embedder is.\n\n"
        + _table(["config", "span integrity", *[f"{q} chunks needed" for q in qids]], rows)
    )


def render_retrieval(bundle: dict[str, Any]) -> str:
    """Render the retrieval-metrics table.

    Args:
        bundle: An experiment result bundle.

    Returns:
        A Markdown section.
    """
    rows = []
    for cfg in bundle["configs"]:
        rows.append(
            [
                cfg["config_id"],
                cfg["n_chunks"],
                _pct(cfg["mean_recall"]),
                _pct(cfg["mean_span_coverage"]),
                f"{cfg['mean_context_precision']:.4f}",
                f"{cfg['elapsed_s']}s",
            ]
        )
    return (
        f"## Retrieval metrics at top_k={bundle['top_k']}\n\n"
        f"Embedding model `{bundle['embedding_model']}`, generation model "
        f"`{bundle['chat_model']}`, identical for every row. Only the chunking changes.\n\n"
        + _table(
            ["config", "chunks", "recall", "span coverage", "context precision", "time"],
            rows,
        )
    )


def render_per_question(bundle: dict[str, Any]) -> str:
    """Render, for each question, which chunks each configuration retrieved.

    This is the section that answers the assignment's "compare which chunks each strategy
    retrieves" requirement directly.

    Args:
        bundle: An experiment result bundle.

    Returns:
        A Markdown section.
    """
    out = ["## Which chunks each strategy retrieved"]
    questions = {q["qid"]: q for q in bundle["questions"]}

    for qid, question in questions.items():
        out.append(f"\n### {qid}. {question['text']}")
        out.append(f"\n*Designed to probe:* {question['probes']}")
        out.append(f"\n*Gold spans ({len(question['gold_spans'])}):*")
        out.extend(f"\n{i}. `{span}`" for i, span in enumerate(question["gold_spans"], start=1))
        out.append("")
        rows = []
        for cfg in bundle["configs"]:
            result = next((q for q in cfg["questions"] if q["qid"] == qid), None)
            if result is None:
                continue
            ranks = ", ".join(f"#{r['index']}({r['score']:.3f})" for r in result["retrieved"])
            rows.append(
                [
                    cfg["config_id"],
                    ranks or "-",
                    f"{len(result['spans_found'])}/{len(question['gold_spans'])}",
                    f"{result['context_precision']:.4f}",
                    "yes" if result["recall"] else "**no**",
                ]
            )
        out.append(
            _table(
                ["config", "retrieved chunk ids (score)", "spans found", "precision", "hit"],
                rows,
            )
        )
    return "\n".join(out)


def render_answers(bundle: dict[str, Any], qid: str | None = None) -> str:
    """Render the generated answers so retrieval differences can be read as answer differences.

    Args:
        bundle: An experiment result bundle.
        qid: Restrict to a single question; defaults to the first question in the set.

    Returns:
        A Markdown section, or an empty string when generation was not run.
    """
    target = qid or bundle["questions"][0]["qid"]
    blocks: list[str] = []
    for cfg in bundle["configs"]:
        result = next((q for q in cfg["questions"] if q["qid"] == target), None)
        if not result or not result.get("answer"):
            continue
        blocks.append(f"**`{cfg['config_id']}`**\n\n> {result['answer']}\n")
    if not blocks:
        return ""
    question = next(q for q in bundle["questions"] if q["qid"] == target)
    return (
        f"## Generated answers for {target}\n\n"
        f"*{question['text']}*\n\n"
        "Same question, same generation model, same prompt template. The only difference is "
        "which chunks retrieval supplied.\n\n" + "\n".join(blocks)
    )


def render_leaderboard(bundle: dict[str, Any]) -> str:
    """Render a ranked summary of configurations by span coverage then precision.

    Args:
        bundle: An experiment result bundle.

    Returns:
        A Markdown section.
    """
    ranked = sorted(
        bundle["configs"],
        key=lambda c: (-c["mean_span_coverage"], -c["mean_recall"], -c["mean_context_precision"]),
    )
    rows = [
        [
            i,
            cfg["config_id"],
            _pct(cfg["mean_span_coverage"]),
            _pct(cfg["mean_recall"]),
            f"{cfg['mean_context_precision']:.4f}",
            cfg["n_chunks"],
        ]
        for i, cfg in enumerate(ranked, start=1)
    ]
    return (
        "## Leaderboard\n\nRanked by mean gold-span coverage, then recall, then precision.\n\n"
        + _table(["#", "config", "span coverage", "recall", "context precision", "chunks"], rows)
    )


def render_report(bundle: dict[str, Any]) -> str:
    """Render the complete observations document.

    Args:
        bundle: An experiment result bundle.

    Returns:
        The full Markdown document.
    """
    document = bundle["document"]
    header = (
        "# Experiment Results and Observations\n\n"
        f"Generated {bundle['generated_at']} in **{bundle['mode']}** mode.\n\n"
        f"- Source document: `{document['path']}` -- {document['n_chars']:,} chars, "
        f"{document['n_words']:,} words, {document['n_sentences']} sentences, "
        f"{document['n_paragraphs']} paragraphs, {document['n_headings']} headings\n"
        f"- Embedding model: `{bundle['embedding_model']}`\n"
        f"- Generation model: `{bundle['chat_model']}`\n"
        f"- Retrieval depth: top_k = {bundle['top_k']}\n"
        f"- Configurations: {len(bundle['configs'])} "
        f"({len(bundle['strategies'])} strategies x {len(bundle['grid'])} size/overlap pairs)\n"
        f"- Questions: {len(bundle['questions'])}, carrying "
        f"{sum(len(q['gold_spans']) for q in bundle['questions'])} span-level gold labels\n\n"
        "> The document, the embedding model, the generation model, the vector index and the "
        "question set are **identical across every row below**. The only independent variable "
        "is how the document was cut into chunks.\n"
    )
    sections = [
        header,
        render_leaderboard(bundle),
        render_geometry(bundle),
        render_structural(bundle),
        render_retrieval(bundle),
        render_per_question(bundle),
        render_answers(bundle),
    ]
    return "\n\n".join(s for s in sections if s) + "\n"


def save_report(bundle: dict[str, Any], path: Path | None = None) -> Path:
    """Render and write the observations document.

    Args:
        bundle: An experiment result bundle.
        path: Destination path; defaults to ``results/OBSERVATIONS.md``.

    Returns:
        The path written to.
    """
    target = path or (get_settings().results_dir / "OBSERVATIONS.md")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_report(bundle), encoding="utf-8")
    return target
