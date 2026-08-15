"""Deterministic, sentence-aware document chunking (Feature 004, FR-007–FR-009).

This is the **canonical** chunker. The Phase 0 benchmark imports it rather than carrying
its own copy, so one determinism guarantee covers both the measurement and the production
ingestion path (FR-035p). A benchmark-only reimplementation would be a second procedure
producing chunks that look like the first one's and are not.

Nothing here touches PostgreSQL, MinIO, Qdrant, or the network. That is enforced, not
merely intended, by `tests/unit/test_phase0_bare_checkout.py`.
"""

from __future__ import annotations

from .chunker import Chunk, chunk_document, normalize
from .config import DEFAULT_CONFIG, ChunkerConfig
from .tokenizer import FixedVocabularyTokenizer, Tokenizer, load_bge_m3

__all__ = [
    "DEFAULT_CONFIG",
    "Chunk",
    "ChunkerConfig",
    "FixedVocabularyTokenizer",
    "Tokenizer",
    "chunk_document",
    "load_bge_m3",
    "normalize",
]
