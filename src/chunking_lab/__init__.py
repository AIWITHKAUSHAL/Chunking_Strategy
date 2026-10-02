"""Chunking Lab: four chunking strategies benchmarked on a single document.

The package is organised so that each concern lives in exactly one module:

* :mod:`chunking_lab.config` -- runtime settings, read once from the environment.
* :mod:`chunking_lab.document` -- loading and light structural analysis of the source text.
* :mod:`chunking_lab.strategies` -- the four chunking strategies, all returning ``Chunk`` objects.
* :mod:`chunking_lab.euri_client` -- embedding and chat access via the Euron OpenAI-compatible API.
* :mod:`chunking_lab.retriever` -- an in-memory cosine-similarity vector store.
* :mod:`chunking_lab.questions` -- the five fixed evaluation questions.
* :mod:`chunking_lab.experiment` -- the strategy x chunk-size x overlap sweep.
* :mod:`chunking_lab.report` -- Markdown rendering of experiment results.
"""

from chunking_lab.config import Settings, get_settings
from chunking_lab.strategies import STRATEGIES, Chunk, chunk_document, get_strategy

__all__ = [
    "STRATEGIES",
    "Chunk",
    "Settings",
    "chunk_document",
    "get_settings",
    "get_strategy",
]
__version__ = "1.0.0"
