"""Loading and light structural analysis of the single source document.

Every strategy is evaluated on the *same* text, so loading is centralised here. The structural
statistics are used by the visualizer to show what the document looks like before any chunking
decision is made.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from chunking_lab.config import get_settings
from chunking_lab.strategies import split_paragraphs, split_sentences


def normalise(text: str) -> str:
    """Collapse all whitespace runs to single spaces.

    Used for substring matching so that a gold answer span still matches after a strategy has
    re-joined sentences with a different separator than the original document used.

    Args:
        text: Text to normalise.

    Returns:
        The text with every whitespace run collapsed to one space, stripped.
    """
    return " ".join(text.split())


@dataclass(frozen=True)
class SourceDocument:
    """The source document plus its precomputed structural statistics.

    Attributes:
        path: Filesystem path the text was read from.
        text: The full document text.
        n_chars: Character count.
        n_words: Whitespace-delimited word count.
        n_sentences: Sentence count per :func:`chunking_lab.strategies.split_sentences`.
        n_paragraphs: Blank-line-delimited paragraph count.
        headings: Markdown headings found, in document order.
    """

    path: Path
    text: str
    n_chars: int
    n_words: int
    n_sentences: int
    n_paragraphs: int
    headings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable summary, excluding the full text."""
        return {
            "path": str(self.path.name),
            "n_chars": self.n_chars,
            "n_words": self.n_words,
            "n_sentences": self.n_sentences,
            "n_paragraphs": self.n_paragraphs,
            "n_headings": len(self.headings),
            "headings": list(self.headings),
        }


def load_document(path: Path | str | None = None) -> SourceDocument:
    """Read the source document and compute its structural statistics.

    Args:
        path: Document path; defaults to the configured document.

    Returns:
        The loaded :class:`SourceDocument`.

    Raises:
        FileNotFoundError: If the document does not exist.
    """
    resolved = Path(path) if path else get_settings().document_path
    if not resolved.exists():
        raise FileNotFoundError(f"Source document not found: {resolved}")
    text = resolved.read_text(encoding="utf-8")
    headings = tuple(
        line.strip().lstrip("# ").strip()
        for line in text.splitlines()
        if line.strip().startswith("#")
    )
    return SourceDocument(
        path=resolved,
        text=text,
        n_chars=len(text),
        n_words=len(text.split()),
        n_sentences=len(split_sentences(text)),
        n_paragraphs=len(split_paragraphs(text)),
        headings=headings,
    )
