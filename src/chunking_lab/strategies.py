"""The four chunking strategies, each returning a uniform list of :class:`Chunk` objects.

Every strategy takes the *same* document text and the *same* ``chunk_size`` / ``chunk_overlap``
pair, so differences in the resulting chunks are attributable purely to the segmentation rule.

Strategies
----------
``fixed``
    Blind character windows. Respects nothing.
``recursive``
    Descends an ordered separator list, splitting on the coarsest separator that fits.
``sentence``
    Packs whole sentences (grouped by paragraph) up to the size budget; overlap is in sentences.
``semantic``
    Embeds each sentence and cuts where the cosine distance between neighbours spikes.

Each returned chunk carries its character offsets into the original document, which is what
lets the live visualizer paint chunk boundaries directly onto the source text.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

EmbedFn = Callable[[Sequence[str]], list[list[float]]]
"""Signature of the embedding callback required by the semantic strategy."""

DEFAULT_SEPARATORS: tuple[str, ...] = ("\n\n", "\n", ". ", " ", "")
"""Separator ladder used by the recursive strategy, coarsest first."""

_ABBREVIATIONS = (
    "e.g.",
    "i.e.",
    "etc.",
    "vs.",
    "Fig.",
    "No.",
    "Dr.",
    "Mr.",
    "Mrs.",
    "Ms.",
    "approx.",
)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")


@dataclass
class Chunk:
    """One unit of retrievable text produced by a chunking strategy.

    Attributes:
        index: Zero-based position of this chunk in the strategy's output.
        text: The chunk's text, exactly as it will be embedded.
        start: Inclusive character offset of the chunk in the source document.
        end: Exclusive character offset of the chunk in the source document.
        strategy: Name of the strategy that produced it.
        n_chars: Character length of ``text``.
        n_tokens_est: Rough token estimate (``n_chars / 4``), used for cost talk only.
        starts_mid_sentence: True when the chunk begins partway through a sentence.
        ends_mid_sentence: True when the chunk stops before its final sentence ends.
        starts_mid_word: True when the chunk begins partway through a word.
        meta: Strategy-specific extras (separator used, sentence count, breakpoint distance...).
    """

    index: int
    text: str
    start: int
    end: int
    strategy: str = ""
    n_chars: int = 0
    n_tokens_est: int = 0
    starts_mid_sentence: bool = False
    ends_mid_sentence: bool = False
    starts_mid_word: bool = False
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation of the chunk."""
        return asdict(self)

    @property
    def preview(self) -> str:
        """Return a single-line, length-capped preview for log output."""
        flat = " ".join(self.text.split())
        return flat if len(flat) <= 120 else flat[:117] + "..."


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def split_sentences(text: str) -> list[str]:
    """Split text into sentences without pulling in a heavyweight NLP dependency.

    Splits on whitespace that follows ``.``, ``!`` or ``?``, then re-joins fragments whose
    left-hand side ended in a known abbreviation or a single initial, which are the two cases
    a naive regex gets wrong most often.

    Args:
        text: Raw text to split.

    Returns:
        Non-empty, whitespace-stripped sentences in document order.
    """
    raw = _SENTENCE_END.split(text.strip())
    merged: list[str] = []
    for piece in raw:
        if not piece:
            continue
        if merged and (
            merged[-1].endswith(_ABBREVIATIONS)
            or re.search(r"\b[A-Z]\.$", merged[-1])
            or re.search(r"\b\d+\.$", merged[-1])
        ):
            merged[-1] = f"{merged[-1]} {piece}"
        else:
            merged.append(piece)
    return [s.strip() for s in merged if s.strip()]


def split_paragraphs(text: str) -> list[str]:
    """Split text on blank lines into non-empty paragraphs.

    Args:
        text: Raw text to split.

    Returns:
        Whitespace-stripped paragraphs in document order.
    """
    return [p.strip() for p in _PARAGRAPH_SPLIT.split(text) if p.strip()]


def _locate(document: str, pieces: Sequence[str]) -> list[tuple[int, int]]:
    """Map each chunk's text back to its character span in the source document.

    Uses a forward-only cursor so that repeated text (common when overlap is enabled) resolves
    to successive occurrences rather than always matching the first one. Falls back to a global
    search, then to a zero-width span, when a piece cannot be found verbatim -- which happens
    when a strategy re-joins text with a normalised separator.

    Args:
        document: The original document text.
        pieces: Chunk texts in document order.

    Returns:
        One ``(start, end)`` tuple per piece.
    """
    spans: list[tuple[int, int]] = []
    cursor = 0
    for piece in pieces:
        needle = piece.strip()
        if not needle:
            spans.append((cursor, cursor))
            continue
        found = document.find(needle, cursor)
        if found == -1:
            # Overlap can push the cursor past a chunk's true start; retry from the top.
            found = document.find(needle)
        if found == -1:
            # Re-joined text: anchor on the chunk's first line instead.
            head = needle.split("\n", 1)[0][:60]
            found = document.find(head, cursor) if head else -1
            if found == -1:
                spans.append((cursor, min(cursor + len(needle), len(document))))
                continue
        spans.append((found, found + len(needle)))
        cursor = found + 1
    return spans


def _carry_sentences(
    buffer: Sequence[str],
    chunk_overlap: int,
    next_len: int,
    chunk_size: int,
) -> list[str]:
    """Choose which trailing sentences to repeat at the start of the next chunk.

    Sentence-level overlap cannot honour both "whole sentences only" and a hard character cap
    at the same time, so the carry is bounded twice: first to the ``chunk_overlap`` budget, and
    then further until the incoming sentence provably still fits inside ``chunk_size``. Without
    the second bound a single long carried sentence pushes the next chunk over budget.

    Args:
        buffer: Sentences of the chunk just emitted, in order.
        chunk_overlap: Character budget for the repeated tail.
        next_len: Length of the sentence about to be appended.
        chunk_size: Hard character cap for the next chunk.

    Returns:
        The sentences to carry forward; empty when overlap is disabled or nothing fits.
    """
    if chunk_overlap <= 0:
        return []
    carry: list[str] = []
    carry_len = 0
    for sentence in reversed(buffer):
        if carry and carry_len + len(sentence) > chunk_overlap:
            break
        carry.insert(0, sentence)
        carry_len += len(sentence) + 1
    # Drop carried sentences from the front until the incoming sentence fits the budget.
    while carry and carry_len + next_len > chunk_size:
        carry_len -= len(carry.pop(0)) + 1
    return carry


def _finalise(
    document: str,
    texts: Sequence[str],
    strategy: str,
    metas: Sequence[dict[str, Any]] | None = None,
) -> list[Chunk]:
    """Turn raw chunk strings into fully annotated :class:`Chunk` objects.

    Computes character spans and the boundary-quality flags that make the strategies
    comparable: whether a chunk starts or ends mid-sentence, and whether it starts mid-word.

    Args:
        document: The original document text.
        texts: Chunk texts in document order.
        strategy: Name recorded on every chunk.
        metas: Optional per-chunk metadata, aligned with ``texts``.

    Returns:
        The annotated chunks, with empty ones dropped.
    """
    cleaned = [t for t in texts if t.strip()]
    metas = list(metas or [{} for _ in cleaned])
    spans = _locate(document, cleaned)
    chunks: list[Chunk] = []
    terminators = (".", "!", "?", ":", '"', ")", "`")
    for i, (text, (start, end)) in enumerate(zip(cleaned, spans, strict=False)):
        stripped = text.strip()
        before = document[:start]
        # A chunk starts cleanly at the document head, after a line break (a heading or a new
        # paragraph) or after sentence-ending punctuation. Anything else is a mid-sentence cut.
        starts_clean = (
            not before.strip()
            or before.rstrip(" \t").endswith("\n")
            or before.rstrip().endswith(terminators)
        )
        # A chunk ends cleanly on sentence-ending punctuation, at a line break, or at EOF.
        after = document[end : end + 1]
        ends_clean = stripped.endswith(terminators) or after in ("", "\n")
        chunks.append(
            Chunk(
                index=i,
                text=stripped,
                start=start,
                end=end,
                strategy=strategy,
                n_chars=len(stripped),
                n_tokens_est=max(1, round(len(stripped) / 4)),
                starts_mid_sentence=not starts_clean,
                ends_mid_sentence=not ends_clean,
                starts_mid_word=start > 0 and document[start - 1].isalnum(),
                meta=metas[i] if i < len(metas) else {},
            )
        )
    return chunks


# ---------------------------------------------------------------------------
# Strategy 1 -- fixed-size character windows
# ---------------------------------------------------------------------------


def chunk_fixed_size(
    document: str,
    chunk_size: int = 800,
    chunk_overlap: int = 160,
    **_: Any,
) -> list[Chunk]:
    """Cut the document into blind character windows.

    The window advances by ``chunk_size - chunk_overlap`` characters. No linguistic or
    structural boundary is consulted, so words and sentences are routinely severed. This is the
    cheapest and most predictable strategy and the baseline every other strategy is measured
    against.

    Args:
        document: Source text.
        chunk_size: Window width in characters.
        chunk_overlap: Characters of the previous window repeated at the start of the next.
        **_: Ignored; keeps the signature uniform across strategies.

    Returns:
        The resulting chunks.

    Raises:
        ValueError: If ``chunk_overlap`` is not smaller than ``chunk_size``.
    """
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")
    step = chunk_size - chunk_overlap
    texts: list[str] = []
    metas: list[dict[str, Any]] = []
    for start in range(0, len(document), step):
        window = document[start : start + chunk_size]
        if not window.strip():
            continue
        texts.append(window)
        metas.append({"window_start": start, "window_end": start + len(window)})
        if start + chunk_size >= len(document):
            break
    return _finalise(document, texts, "fixed", metas)


# ---------------------------------------------------------------------------
# Strategy 2 -- recursive character splitting
# ---------------------------------------------------------------------------


def _merge_splits(
    splits: Sequence[str],
    separator: str,
    chunk_size: int,
    chunk_overlap: int,
) -> list[str]:
    """Greedily pack separator-delimited pieces into size-bounded chunks.

    Mirrors the merge step of LangChain's ``RecursiveCharacterTextSplitter``: accumulate pieces
    until the next one would overflow ``chunk_size``, emit, then retain a tail of the previous
    buffer worth up to ``chunk_overlap`` characters.

    Args:
        splits: Pieces to pack, already small enough individually.
        separator: String used to re-join pieces.
        chunk_size: Maximum characters per emitted chunk.
        chunk_overlap: Characters of tail context carried into the next chunk.

    Returns:
        The packed chunk strings.
    """
    joiner_len = len(separator)
    chunks: list[str] = []
    buffer: list[str] = []
    buffer_len = 0

    for piece in splits:
        addition = len(piece) + (joiner_len if buffer else 0)
        if buffer and buffer_len + addition > chunk_size:
            chunks.append(separator.join(buffer).strip())
            # Shed from the front until the retained tail is within the overlap budget *and*
            # the incoming piece provably fits. Without the second condition the carried
            # overlap plus the new piece can push a chunk past chunk_size.
            while buffer and (
                buffer_len > chunk_overlap
                or (buffer_len + len(piece) + joiner_len > chunk_size and buffer_len > 0)
            ):
                removed = buffer.pop(0)
                buffer_len -= len(removed) + (joiner_len if buffer else 0)
            addition = len(piece) + (joiner_len if buffer else 0)
        buffer.append(piece)
        buffer_len += addition

    if buffer:
        tail = separator.join(buffer).strip()
        if tail:
            chunks.append(tail)
    return [c for c in chunks if c]


def _recursive_split(
    text: str,
    separators: Sequence[str],
    chunk_size: int,
    chunk_overlap: int,
    used: list[str],
) -> list[str]:
    """Recursively split ``text`` using the coarsest separator that produces fitting pieces.

    Args:
        text: Text to split.
        separators: Remaining separator ladder, coarsest first.
        chunk_size: Maximum characters per chunk.
        chunk_overlap: Overlap budget handed to the merge step.
        used: Accumulator recording which separator each emitted chunk was split on.

    Returns:
        Chunk strings for this subtree, in document order.
    """
    separator = separators[-1]
    remainder: Sequence[str] = []
    for i, candidate in enumerate(separators):
        if candidate == "":
            separator = candidate
            remainder = separators[i + 1 :]
            break
        if candidate in text:
            separator = candidate
            remainder = separators[i + 1 :]
            break

    pieces = list(text) if separator == "" else text.split(separator)
    good: list[str] = []
    out: list[str] = []
    for piece in pieces:
        if len(piece) < chunk_size:
            good.append(piece)
            continue
        if good:
            merged = _merge_splits(good, separator, chunk_size, chunk_overlap)
            out.extend(merged)
            used.extend([separator] * len(merged))
            good = []
        if remainder:
            out.extend(_recursive_split(piece, remainder, chunk_size, chunk_overlap, used))
        else:
            out.append(piece)
            used.append(separator)
    if good:
        merged = _merge_splits(good, separator, chunk_size, chunk_overlap)
        out.extend(merged)
        used.extend([separator] * len(merged))
    return out


def chunk_recursive(
    document: str,
    chunk_size: int = 800,
    chunk_overlap: int = 160,
    separators: Sequence[str] = DEFAULT_SEPARATORS,
    **_: Any,
) -> list[Chunk]:
    r"""Split the document by descending an ordered separator ladder.

    Tries ``"\n\n"`` (paragraphs), then ``"\\n"``, then ``". "`` (sentences), then ``" "``
    (words), then raw characters. Coarse boundaries are preserved wherever a piece already fits
    the size budget, and finer separators are reached for only when a piece is still too large.
    This is the production default: near-paragraph quality at character-splitter cost.

    Args:
        document: Source text.
        chunk_size: Maximum characters per chunk.
        chunk_overlap: Characters of tail context repeated in the next chunk.
        separators: Separator ladder, coarsest first.
        **_: Ignored; keeps the signature uniform across strategies.

    Returns:
        The resulting chunks, each tagged with the separator it was split on.

    Raises:
        ValueError: If ``chunk_overlap`` is not smaller than ``chunk_size``.
    """
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")
    used: list[str] = []
    texts = _recursive_split(document, list(separators), chunk_size, chunk_overlap, used)
    metas = [
        {"separator_used": repr(used[i]) if i < len(used) else "?", "separators": list(separators)}
        for i in range(len(texts))
    ]
    return _finalise(document, texts, "recursive", metas)


# ---------------------------------------------------------------------------
# Strategy 3 -- sentence / paragraph packing
# ---------------------------------------------------------------------------


def chunk_sentence_paragraph(
    document: str,
    chunk_size: int = 800,
    chunk_overlap: int = 160,
    **_: Any,
) -> list[Chunk]:
    """Pack whole sentences into chunks, never crossing a paragraph boundary.

    The document is split into paragraphs first, then sentences are accumulated until one more
    would exceed ``chunk_size``. ``chunk_overlap`` is interpreted in characters but applied in
    whole sentences: trailing sentences are repeated until the overlap budget is met. Every
    chunk is therefore grammatically complete, which is what makes retrieved context readable.

    Args:
        document: Source text.
        chunk_size: Soft maximum characters per chunk; a single over-long sentence is kept whole.
        chunk_overlap: Character budget for repeated trailing sentences.
        **_: Ignored; keeps the signature uniform across strategies.

    Returns:
        The resulting chunks, each tagged with its sentence count.
    """
    texts: list[str] = []
    metas: list[dict[str, Any]] = []

    for para_index, paragraph in enumerate(split_paragraphs(document)):
        sentences = split_sentences(paragraph)
        buffer: list[str] = []
        length = 0
        for sentence in sentences:
            if buffer and length + len(sentence) + 1 > chunk_size:
                texts.append(" ".join(buffer))
                metas.append(
                    {"sentence_count": len(buffer), "paragraph_index": para_index, "complete": True}
                )
                # Carry whole trailing sentences forward, bounded so the next chunk still fits.
                buffer = _carry_sentences(buffer, chunk_overlap, len(sentence), chunk_size)
                length = sum(len(s) + 1 for s in buffer)
            buffer.append(sentence)
            length += len(sentence) + 1
        if buffer:
            texts.append(" ".join(buffer))
            metas.append(
                {"sentence_count": len(buffer), "paragraph_index": para_index, "complete": True}
            )
    return _finalise(document, texts, "sentence", metas)


# ---------------------------------------------------------------------------
# Strategy 4 -- semantic (embedding-distance) chunking
# ---------------------------------------------------------------------------


def _cosine_distance(a: Sequence[float], b: Sequence[float]) -> float:
    """Return ``1 - cosine_similarity(a, b)``, clamped to ``[0, 2]``.

    Args:
        a: First vector.
        b: Second vector.

    Returns:
        The cosine distance; ``1.0`` when either vector has zero norm.
    """
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 1.0
    return max(0.0, min(2.0, 1.0 - dot / (na * nb)))


def _percentile(values: Sequence[float], pct: float) -> float:
    """Return the linear-interpolated percentile of ``values``.

    Args:
        values: Sample values; must be non-empty.
        pct: Percentile in ``[0, 100]``.

    Returns:
        The percentile value, or ``0.0`` for an empty sample.
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * pct / 100.0
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def chunk_semantic(
    document: str,
    chunk_size: int = 800,
    chunk_overlap: int = 160,
    embed_fn: EmbedFn | None = None,
    breakpoint_percentile: float = 90.0,
    **_: Any,
) -> list[Chunk]:
    """Cut the document where consecutive sentences stop talking about the same thing.

    Each sentence is embedded individually. The cosine distance between every adjacent pair is
    computed, and a boundary is placed wherever that distance exceeds the
    ``breakpoint_percentile`` of all distances in the document. ``chunk_size`` acts as a hard
    cap so a long run of similar sentences still gets divided, and ``chunk_overlap`` carries
    trailing sentences across a boundary.

    Args:
        document: Source text.
        chunk_size: Hard character cap applied on top of the semantic boundaries.
        chunk_overlap: Character budget for repeated trailing sentences.
        embed_fn: Callback that embeds a list of sentences. Required.
        breakpoint_percentile: Distance percentile above which a boundary is placed.
        **_: Ignored; keeps the signature uniform across strategies.

    Returns:
        The resulting chunks, each tagged with the distance that triggered its boundary.

    Raises:
        ValueError: If ``embed_fn`` is not supplied.
    """
    if embed_fn is None:
        raise ValueError("chunk_semantic requires an embed_fn to embed sentences")

    sentences = split_sentences(document)
    if len(sentences) < 2:
        return _finalise(document, [document], "semantic", [{"sentence_count": len(sentences)}])

    vectors = embed_fn(sentences)
    distances = [_cosine_distance(vectors[i], vectors[i + 1]) for i in range(len(vectors) - 1)]
    threshold = _percentile(distances, breakpoint_percentile)

    texts: list[str] = []
    metas: list[dict[str, Any]] = []
    buffer: list[str] = [sentences[0]]
    length = len(sentences[0])

    for i in range(1, len(sentences)):
        distance = distances[i - 1]
        sentence = sentences[i]
        topic_shift = distance > threshold
        size_exceeded = length + len(sentence) + 1 > chunk_size
        if buffer and (topic_shift or size_exceeded):
            texts.append(" ".join(buffer))
            metas.append(
                {
                    "sentence_count": len(buffer),
                    "boundary_reason": "topic_shift" if topic_shift else "size_cap",
                    "boundary_distance": round(distance, 4),
                    "threshold": round(threshold, 4),
                }
            )
            buffer = _carry_sentences(buffer, chunk_overlap, len(sentence), chunk_size)
            length = sum(len(s) + 1 for s in buffer)
        buffer.append(sentence)
        length += len(sentence) + 1

    if buffer:
        texts.append(" ".join(buffer))
        metas.append(
            {
                "sentence_count": len(buffer),
                "boundary_reason": "document_end",
                "threshold": round(threshold, 4),
            }
        )
    return _finalise(document, texts, "semantic", metas)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StrategySpec:
    """Display and dispatch metadata for one strategy.

    Attributes:
        key: Short identifier used in CLI arguments, JSON keys and the UI.
        label: Human-readable name.
        fn: The callable implementing the strategy.
        needs_embeddings: True when the strategy itself calls the embedding model.
        separators: Separator ladder, when the strategy uses one.
        blurb: One-line description shown in the visualizer.
        pros: Advantages, for the README and the UI.
        cons: Disadvantages, for the README and the UI.
    """

    key: str
    label: str
    fn: Callable[..., list[Chunk]]
    needs_embeddings: bool
    separators: tuple[str, ...] | None
    blurb: str
    pros: tuple[str, ...]
    cons: tuple[str, ...]


STRATEGIES: dict[str, StrategySpec] = {
    "fixed": StrategySpec(
        key="fixed",
        label="Fixed-size",
        fn=chunk_fixed_size,
        needs_embeddings=False,
        separators=None,
        blurb="Blind character windows stepping by chunk_size - chunk_overlap.",
        pros=(
            "Fastest possible: one pass, no parsing.",
            "Exactly predictable chunk count, so index size and cost are known in advance.",
            "Completely language- and format-agnostic.",
        ),
        cons=(
            "Severs words, sentences, tables and list items without hesitation.",
            "A fact split across a boundary becomes unretrievable by either half.",
            "Chunk embeddings mix the tail of one topic with the head of the next.",
        ),
    ),
    "recursive": StrategySpec(
        key="recursive",
        label="Recursive character",
        fn=chunk_recursive,
        needs_embeddings=False,
        separators=DEFAULT_SEPARATORS,
        blurb='Descends ["\\n\\n", "\\n", ". ", " ", ""], splitting on the coarsest fit.',
        pros=(
            "Keeps paragraphs and sentences intact whenever the size budget allows.",
            "Still cheap: no embedding calls, no NLP model.",
            "Separator list is tunable per format (Markdown headings, code, CSV rows).",
        ),
        cons=(
            "Size budget still wins over meaning: a long section is cut at an arbitrary point.",
            "Chunk sizes become uneven, which complicates cost forecasting.",
            "A badly ordered separator list silently degrades it to character splitting.",
        ),
    ),
    "sentence": StrategySpec(
        key="sentence",
        label="Sentence / paragraph",
        fn=chunk_sentence_paragraph,
        needs_embeddings=False,
        separators=("paragraph", "sentence"),
        blurb="Packs whole sentences, never crossing a paragraph boundary.",
        pros=(
            "Every chunk is grammatically complete and human-readable.",
            "Overlap in whole sentences keeps preconditions attached to their steps.",
            "Paragraph awareness naturally tracks the author's own topic structure.",
        ),
        cons=(
            "Depends on reliable sentence detection; abbreviations and lists break it.",
            "Short paragraphs become tiny chunks whose embeddings are weak and noisy.",
            "A single long paragraph on two subjects still yields one mixed chunk.",
        ),
    ),
    "semantic": StrategySpec(
        key="semantic",
        label="Semantic",
        fn=chunk_semantic,
        needs_embeddings=True,
        separators=("sentence", "cosine-distance breakpoint"),
        blurb="Embeds every sentence and cuts where adjacent-sentence distance spikes.",
        pros=(
            "Boundaries land where the topic actually changes, not where a counter runs out.",
            "High internal coherence raises the signal-to-noise ratio of every chunk.",
            "Adapts automatically to documents with no usable heading structure.",
        ),
        cons=(
            "One embedding call per sentence: the most expensive strategy to ingest.",
            "Threshold is corpus-sensitive; a wrong percentile over- or under-splits badly.",
            "Chunk sizes vary wildly, so some chunks blow past the prompt's context budget.",
        ),
    ),
}
"""Registry of every available strategy, keyed by short identifier."""


def get_strategy(key: str) -> StrategySpec:
    """Look up a strategy by key.

    Args:
        key: Short strategy identifier.

    Returns:
        The matching :class:`StrategySpec`.

    Raises:
        KeyError: If ``key`` is not a known strategy.
    """
    if key not in STRATEGIES:
        raise KeyError(f"Unknown strategy {key!r}. Known: {sorted(STRATEGIES)}")
    return STRATEGIES[key]


def chunk_document(
    document: str,
    strategy: str,
    chunk_size: int = 800,
    chunk_overlap: int = 160,
    embed_fn: EmbedFn | None = None,
    **kwargs: Any,
) -> list[Chunk]:
    """Chunk a document with the named strategy.

    Args:
        document: Source text.
        strategy: Strategy key (``fixed``, ``recursive``, ``sentence`` or ``semantic``).
        chunk_size: Maximum characters per chunk.
        chunk_overlap: Overlap budget in characters.
        embed_fn: Embedding callback, required only by the semantic strategy.
        **kwargs: Extra strategy-specific options (for example ``separators``).

    Returns:
        The resulting chunks.
    """
    spec = get_strategy(strategy)
    return spec.fn(
        document,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        embed_fn=embed_fn,
        **kwargs,
    )
