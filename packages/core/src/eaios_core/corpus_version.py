"""Which corpus a cached answer was computed from (FR-018a, R23).

An answer is only true of the passages it was built from. Re-ingest a document and the
cached answer is not unauthorized, it is simply **wrong** — and a confidently wrong answer
is the failure a grounded retrieval system exists to prevent. So the active corpus
version's checksum is a component of the cache key, and publishing a new version retires
every entry derived from the old one *by making them unaddressable*.

**Why a protocol and not a class.** The real provider reads the `corpus_versions` table,
which arrives in Phase 2 (T078). Phase 1 needs the cache key to be correct now, and waiting
would mean either shipping a key without the component or building the table early to serve
a cache. A protocol lets the cache depend on the *shape* of the answer; the table, the
query and the caching of it are Phase 2's business.

That also keeps `packages/core` free of a database dependency, which is the same line
`qdrant_filter` holds against the vector store: this package renders and derives, it does
not connect.
"""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

__all__ = ["CorpusVersionProvider"]


@runtime_checkable
class CorpusVersionProvider(Protocol):
    """Supplies the checksum of the corpus version currently serving a collection."""

    def active_checksum(self, company_id: uuid.UUID, collection: str) -> str:
        """The active corpus version's checksum for one tenant and collection.

        Args:
            company_id: The caller's tenant. Scoped per tenant because one company's
                re-ingestion must not retire another's cache.
            collection: The vector collection being searched, e.g. ``"documents"``.

        Returns:
            An opaque checksum, stable while that version stays active and different for
            every other version.

        Implementations must be cheap enough to call on **every** cache lookup. A value
        captured once at construction would keep serving the retired version for the life
        of the process, which is the staleness bug one level up from the one this exists
        to fix.
        """
        ...
