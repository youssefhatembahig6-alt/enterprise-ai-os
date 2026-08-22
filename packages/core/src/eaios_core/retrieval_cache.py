"""The retrieval cache accessor (FR-018, FR-018a, R2, R23).

This is a thin object over `cache_key`, and thin is the point. `cache_key` has carried the
right four components since feature 001 and nothing had ever supplied a real
`permission_fingerprint` or `data_version`; this class supplies both, from the verified
access context and from a `CorpusVersionProvider`. **`cache_key` itself is unchanged** —
rewriting the key builder to serve a new caller is how two subtly different key formats
come to exist.

**Entitlement lives in the key.** Two callers with different permissions, departments,
countries or tenants derive different keys, so one cannot read the other's entry. That
makes the leak unconstructible rather than merely detected: a check applied *after* the
lookup runs when the answer has already come back out of the cache.

**Retirement lives in the key too.** A permission change or a corpus republish changes the
key, so the previous entry becomes unreachable **without anything being deleted**. No sweep
over `eaios:cache:*`, no window in which the stale or over-broad answer is still served,
and no correctness that depends on a cleanup job having run. The old entries expire on
their own TTL, and re-activating a previous corpus version makes its entries reachable
again — a rollback that costs nothing, which a delete-on-publish design would have thrown
away.

**Verified by** `tests/security/test_cache_isolation.py` and
`tests/security/test_cache_data_version.py`, both pure and in-memory: an isolation test
that mutated a real Redis namespace would be the one artefact in the suite capable of
causing the incident it describes.
"""

from __future__ import annotations

from typing import Any, Final, Protocol

from .authz.context import AccessContext
from .corpus_version import CorpusVersionProvider
from .keys import cache_key

__all__ = ["DEFAULT_COLLECTION", "CacheBackend", "RetrievalCache"]

#: The collection retrieval searches. A parameter on the accessor rather than a constant
#: inside the key builder, so a second collection does not need a second key format.
DEFAULT_COLLECTION: Final[str] = "documents"

#: Keys that may never appear in a cached value. Passage and question text are the two
#: things FR-037 forbids recording, and a cache is a recording.
_FORBIDDEN_VALUE_KEYS: Final[frozenset[str]] = frozenset(
    {"passages", "passage", "text", "content", "body", "excerpt", "question"}
)


class CacheBackend(Protocol):
    """The two operations this accessor needs, so the tests can supply a dict."""

    def get(self, key: str) -> Any: ...

    def set(self, key: str, value: Any, *, ttl_seconds: int | None = None) -> None: ...


class RetrievalCache:
    """Permission- and corpus-aware access to cached answers."""

    def __init__(
        self,
        backend: CacheBackend,
        corpus_versions: CorpusVersionProvider,
        *,
        collection: str = DEFAULT_COLLECTION,
    ) -> None:
        self._backend = backend
        self._corpus_versions = corpus_versions
        self._collection = collection

    def key_for(self, subject: AccessContext, normalized_question: str) -> str:
        """The cache key for one caller's question, right now.

        The corpus checksum is read **per call**, not captured in `__init__`: a provider
        consulted once would keep serving the retired version for the lifetime of the
        process.
        """
        return cache_key(
            company_slug=subject.company_slug,
            permission_fingerprint=subject.permission_fingerprint,
            normalized_question=normalized_question,
            data_version=self._corpus_versions.active_checksum(
                subject.company_id, self._collection
            ),
        )

    def get(self, subject: AccessContext, normalized_question: str) -> Any:
        """The cached answer, or `None`.

        A miss returns `None` and **mutates nothing**. That is worth stating: if a miss
        cleaned up the entries it stepped over, unreachability would depend on someone
        having missed first.
        """
        return self._backend.get(self.key_for(subject, normalized_question))

    def set(
        self,
        subject: AccessContext,
        normalized_question: str,
        value: Any,
        *,
        ttl_seconds: int | None = None,
    ) -> None:
        """Cache an answer under this caller's entitlement and the active corpus version.

        Raises:
            ValueError: The value carries passage or question text. A cache that stored
                passage bodies would put unauthorized content one key-collision away from
                a reader, and FR-037 forbids recording it at all.
        """
        _refuse_passage_bodies(value)
        self._backend.set(
            self.key_for(subject, normalized_question), value, ttl_seconds=ttl_seconds
        )


def _refuse_passage_bodies(value: Any, *, depth: int = 0) -> None:
    """Reject a value that carries verbatim text, however deeply it is nested."""
    if depth > 6:
        return
    if isinstance(value, dict):
        offending = sorted(
            str(key) for key in value if str(key).lower() in _FORBIDDEN_VALUE_KEYS
        )
        if offending:
            raise ValueError(
                f"refusing to cache a value carrying passage or question text: {offending}."
                " The cache holds answers and digests; passage bodies are never recorded"
                " (FR-037)"
            )
        for item in value.values():
            _refuse_passage_bodies(item, depth=depth + 1)
    elif isinstance(value, list | tuple):
        for item in value:
            _refuse_passage_bodies(item, depth=depth + 1)
