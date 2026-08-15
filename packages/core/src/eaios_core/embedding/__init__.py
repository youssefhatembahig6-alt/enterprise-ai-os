"""Local embedding with the pinned BGE-M3 revision (Feature 004, FR-011).

The **canonical** embedder. The Phase 0 benchmark imports it rather than carrying its own
copy, so one identity guarantee covers the measurement and the production ingestion path
alike (FR-035p).

Nothing here touches PostgreSQL, MinIO, Qdrant, or the network — enforced by
`tests/unit/test_phase0_bare_checkout.py`, not merely intended.
"""

from __future__ import annotations

from .bge_m3 import (
    EMBEDDING_DIMENSION,
    MODEL_REPOSITORY,
    PINNED_REVISION,
    WEIGHT_SHA256,
    BgeM3Embedder,
    EmbeddingIdentity,
    declared_identity,
    missing_runtime,
)

__all__ = [
    "EMBEDDING_DIMENSION",
    "MODEL_REPOSITORY",
    "PINNED_REVISION",
    "WEIGHT_SHA256",
    "BgeM3Embedder",
    "EmbeddingIdentity",
    "declared_identity",
    "missing_runtime",
]
