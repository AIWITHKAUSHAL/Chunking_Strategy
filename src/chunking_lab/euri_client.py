"""Access to ``gemini-embedding-001`` and ``gemini-3.5-flash-lite`` via the Euron gateway.

The gateway is OpenAI-compatible, so the official ``openai`` client is pointed at it:

    client = OpenAI(api_key=os.environ["EURI_API_KEY"], base_url="https://api.euron.one/api/v1/euri")
    client.embeddings.create(model="gemini-embedding-001", input=[...])
    client.chat.completions.create(model="gemini-3.5-flash-lite", messages=[...])

Two features matter for this project:

* **Content-hash caching.** Chunking configurations overlap heavily -- most chunks are
  byte-identical across runs -- so every embedding is cached on disk by ``sha256(model + text)``.
  A full sweep therefore costs a fraction of its nominal embedding volume.
* **Offline fallback.** With no ``EURI_API_KEY`` the client switches to a deterministic hashed
  bag-of-words embedder. Retrieval rankings are weaker but the pipeline, the experiments and the
  live visualizer all still run, which keeps the demo reproducible without network access.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import random
import re
import time
from collections.abc import Sequence
from typing import Any

from chunking_lab.config import Settings, get_settings

LOGGER = logging.getLogger(__name__)

OFFLINE_DIM = 256
"""Dimensionality of the deterministic fallback embedder."""

_WORD = re.compile(r"[a-z0-9]+")


class EuriClient:
    """Embedding and chat-completion client with caching and an offline fallback.

    Args:
        settings: Resolved settings; defaults to :func:`chunking_lab.config.get_settings`.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialise the client and load any previously cached embeddings.

        Args:
            settings: Resolved settings; defaults to the process-wide settings.
        """
        self.settings = settings or get_settings()
        self._cache_path = self.settings.cache_dir / "embeddings.jsonl"
        self._cache: dict[str, list[float]] = {}
        self._client: Any | None = None
        self.api_calls = 0
        self.cache_hits = 0
        self.tokens_embedded = 0
        self._load_cache()

    # -- properties ---------------------------------------------------------

    @property
    def offline(self) -> bool:
        """True when no API key is configured and the fallback embedder is in use."""
        return self.settings.offline

    @property
    def embedding_model(self) -> str:
        """Identifier of the embedding model actually in use."""
        return "offline-hash-256" if self.offline else self.settings.embedding_model

    @property
    def chat_model(self) -> str:
        """Identifier of the chat model actually in use."""
        return "offline-extractive" if self.offline else self.settings.chat_model

    def stats(self) -> dict[str, Any]:
        """Return call-accounting counters for display in the UI and the report."""
        return {
            "mode": self.settings.mode,
            "embedding_model": self.embedding_model,
            "chat_model": self.chat_model,
            "api_calls": self.api_calls,
            "cache_hits": self.cache_hits,
            "cached_vectors": len(self._cache),
        }

    # -- cache --------------------------------------------------------------

    def _load_cache(self) -> None:
        """Load the on-disk embedding cache into memory, ignoring corrupt lines."""
        if not self._cache_path.exists():
            return
        with self._cache_path.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                    self._cache[record["key"]] = record["vector"]
                except (json.JSONDecodeError, KeyError):
                    continue
        LOGGER.debug("Loaded %d cached embeddings", len(self._cache))

    def _append_cache(self, key: str, vector: list[float]) -> None:
        """Append one embedding to the in-memory and on-disk caches.

        Args:
            key: Content hash key.
            vector: The embedding to persist.
        """
        self._cache[key] = vector
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        with self._cache_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"key": key, "vector": vector}) + "\n")

    def _cache_key(self, text: str) -> str:
        """Return the cache key for a text under the current embedding model.

        Args:
            text: Text to be embedded.

        Returns:
            A hex digest keyed on both the model name and the text.
        """
        digest = hashlib.sha256(f"{self.embedding_model}\x00{text}".encode()).hexdigest()
        return digest[:32]

    # -- embeddings ---------------------------------------------------------

    def _ensure_client(self) -> Any:
        """Lazily construct the OpenAI-compatible client pointed at the Euron gateway.

        Returns:
            The live ``OpenAI`` client instance.

        Raises:
            RuntimeError: If the ``openai`` package is not installed.
        """
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:  # pragma: no cover - dependency is declared
                raise RuntimeError("pip install openai to use live mode") from exc
            self._client = OpenAI(
                api_key=self.settings.api_key,
                base_url=self.settings.base_url,
                timeout=60.0,
            )
        return self._client

    def _offline_embed(self, text: str) -> list[float]:
        """Produce a deterministic, L2-normalised lexical embedding without any network call.

        Hashes word unigrams and bigrams into a fixed-width vector with sub-linear term
        weighting. This is a bag-of-words sketch, not a semantic model: it ranks by lexical
        overlap, which is enough to exercise retrieval end-to-end offline.

        Args:
            text: Text to embed.

        Returns:
            An ``OFFLINE_DIM``-dimensional unit vector.
        """
        vector = [0.0] * OFFLINE_DIM
        words = _WORD.findall(text.lower())
        grams = words + [f"{a}_{b}" for a, b in zip(words, words[1:], strict=False)]
        for gram in grams:
            slot = int(hashlib.md5(gram.encode()).hexdigest()[:8], 16) % OFFLINE_DIM
            vector[slot] += 1.0
        vector = [math.log1p(v) for v in vector]
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    def _embed_batch_live(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed one batch through the gateway, retrying with exponential backoff.

        Args:
            texts: Batch of texts, at most ``settings.embed_batch_size`` long.

        Returns:
            One vector per input, in input order.

        Raises:
            RuntimeError: If every retry attempt fails.
        """
        client = self._ensure_client()
        last_error: Exception | None = None
        for attempt in range(self.settings.max_retries):
            try:
                response = client.embeddings.create(
                    model=self.settings.embedding_model,
                    input=list(texts),
                )
                self.api_calls += 1
                return [item.embedding for item in response.data]
            except Exception as exc:  # noqa: BLE001 - gateway raises many error types
                last_error = exc
                delay = self.settings.retry_base_delay * (2**attempt)
                delay += random.random() * 0.3  # noqa: S311 - jitter only, not security
                LOGGER.warning(
                    "Embedding attempt %d/%d failed (%s); retrying in %.1fs",
                    attempt + 1,
                    self.settings.max_retries,
                    exc,
                    delay,
                )
                time.sleep(delay)
        raise RuntimeError(f"Embedding failed after {self.settings.max_retries} attempts") from (
            last_error
        )

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed texts, serving what it can from cache and batching the remainder.

        Args:
            texts: Texts to embed, in any order.

        Returns:
            One vector per input text, aligned with ``texts``.
        """
        if not texts:
            return []
        vectors: list[list[float] | None] = [None] * len(texts)
        pending: list[tuple[int, str]] = []

        for i, text in enumerate(texts):
            key = self._cache_key(text)
            cached = self._cache.get(key)
            if cached is not None:
                vectors[i] = cached
                self.cache_hits += 1
            else:
                pending.append((i, text))

        if pending and self.offline:
            for i, text in pending:
                vector = self._offline_embed(text)
                self._append_cache(self._cache_key(text), vector)
                vectors[i] = vector
        elif pending:
            batch_size = self.settings.embed_batch_size
            for offset in range(0, len(pending), batch_size):
                batch = pending[offset : offset + batch_size]
                results = self._embed_batch_live([text for _, text in batch])
                for (i, text), vector in zip(batch, results, strict=False):
                    self.tokens_embedded += max(1, len(text) // 4)
                    self._append_cache(self._cache_key(text), vector)
                    vectors[i] = vector

        return [v if v is not None else [0.0] * OFFLINE_DIM for v in vectors]

    def embed_one(self, text: str) -> list[float]:
        """Embed a single text.

        Args:
            text: Text to embed.

        Returns:
            The embedding vector.
        """
        return self.embed([text])[0]

    # -- chat ---------------------------------------------------------------

    def complete(self, system: str, user: str, temperature: float | None = None) -> str:
        """Generate an answer with the chat model, or extractively when offline.

        Args:
            system: System prompt.
            user: User prompt, normally the retrieved context plus the question.
            temperature: Sampling temperature; defaults to the configured value.

        Returns:
            The generated answer text, or an offline extractive stand-in.
        """
        if self.offline:
            return self._offline_complete(user)
        client = self._ensure_client()
        for attempt in range(self.settings.max_retries):
            try:
                response = client.chat.completions.create(
                    model=self.settings.chat_model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=(self.settings.temperature if temperature is None else temperature),
                )
                self.api_calls += 1
                return (response.choices[0].message.content or "").strip()
            except Exception as exc:  # noqa: BLE001 - gateway raises many error types
                delay = self.settings.retry_base_delay * (2**attempt)
                LOGGER.warning("Chat attempt %d failed (%s)", attempt + 1, exc)
                if attempt == self.settings.max_retries - 1:
                    return f"[generation failed after {self.settings.max_retries} attempts: {exc}]"
                time.sleep(delay)
        return ""

    @staticmethod
    def _offline_complete(user_prompt: str) -> str:
        """Return an extractive stand-in answer built from the supplied context.

        Picks the context sentences with the highest word overlap against the question, which
        makes the offline answer a faithful readout of what retrieval actually supplied -- the
        thing this project is measuring -- rather than a fabrication.

        Args:
            user_prompt: The full user prompt containing both context and question.

        Returns:
            A short extractive answer.
        """
        question = user_prompt.rsplit("Question:", 1)[-1].strip()
        context = user_prompt.split("Question:")[0]
        q_words = set(_WORD.findall(question.lower())) - {
            "the",
            "a",
            "an",
            "what",
            "which",
            "how",
            "does",
            "is",
            "are",
            "and",
            "of",
            "to",
            "in",
        }
        scored: list[tuple[float, str]] = []
        for raw in re.split(r"(?<=[.!?])\s+", context):
            sentence = raw.strip()
            if len(sentence) < 30:
                continue
            words = set(_WORD.findall(sentence.lower()))
            if not words:
                continue
            overlap = len(q_words & words) / (len(q_words) or 1)
            scored.append((overlap, sentence))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        best = [s for score, s in scored[:3] if score > 0]
        if not best:
            return "[offline mode] The retrieved context does not appear to contain the answer."
        return "[offline extractive answer] " + " ".join(best)


def get_embed_fn(client: EuriClient) -> Any:
    """Adapt a client into the ``embed_fn`` callback the semantic strategy expects.

    Args:
        client: The client to wrap.

    Returns:
        A callable taking a sequence of texts and returning a list of vectors.
    """
    return client.embed
