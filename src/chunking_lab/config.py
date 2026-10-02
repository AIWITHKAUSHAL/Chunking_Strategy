"""Runtime configuration for the chunking lab.

Every tunable lives here so that the CLI, the FastAPI server and the notebooks all read the
same values. Settings come from environment variables (optionally via a local ``.env`` file)
and fall back to the documented defaults below.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
"""Repository root, derived from this file's location rather than the process CWD."""

DEFAULT_DOCUMENT = PROJECT_ROOT / "data" / "vector_search_handbook.md"
RESULTS_DIR = PROJECT_ROOT / "results"
CACHE_DIR = PROJECT_ROOT / ".cache"


@dataclass(frozen=True)
class Settings:
    """Resolved configuration for one process.

    Attributes:
        api_key: Euron gateway key. Empty string means offline mode.
        base_url: OpenAI-compatible base URL for the Euron gateway.
        embedding_model: Embedding model identifier.
        chat_model: Chat/generation model identifier.
        embed_batch_size: Number of inputs sent per embedding request.
        max_retries: Attempts per API call before giving up.
        retry_base_delay: Base seconds for exponential backoff between retries.
        temperature: Sampling temperature used for answer generation.
        top_k: Number of chunks retrieved per question.
        document_path: Path to the source document shared by every strategy.
        results_dir: Directory experiment artefacts are written to.
        cache_dir: Directory holding the on-disk embedding cache.
        offline: True when no API key is available, enabling the deterministic fallback embedder.
    """

    api_key: str = ""
    base_url: str = "https://api.euron.one/api/v1/euri"
    embedding_model: str = "gemini-embedding-001"
    chat_model: str = "gemini-3.5-flash-lite"
    embed_batch_size: int = 64
    max_retries: int = 5
    retry_base_delay: float = 0.8
    temperature: float = 0.2
    top_k: int = 3
    document_path: Path = DEFAULT_DOCUMENT
    results_dir: Path = RESULTS_DIR
    cache_dir: Path = CACHE_DIR
    offline: bool = field(default=False)

    @property
    def mode(self) -> str:
        """Return ``"offline"`` or ``"live"`` for display in logs and the UI."""
        return "offline" if self.offline else "live"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Build :class:`Settings` from the environment, loading ``.env`` if present.

    The result is cached for the lifetime of the process, so mutating the environment after
    the first call has no effect.

    Returns:
        The resolved settings object.
    """
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    api_key = os.environ.get("EURI_API_KEY", "").strip()
    return Settings(
        api_key=api_key,
        base_url=os.environ.get("EURI_BASE_URL", "https://api.euron.one/api/v1/euri").strip(),
        embedding_model=os.environ.get("EMBEDDING_MODEL", "gemini-embedding-001").strip(),
        chat_model=os.environ.get("CHAT_MODEL", "gemini-3.5-flash-lite").strip(),
        top_k=int(os.environ.get("TOP_K", "3")),
        offline=not api_key,
    )
