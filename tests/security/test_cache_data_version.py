"""A cached answer dies with the corpus it was computed from (FR-018a, R23).

The permission fingerprint stops the wrong *person* reading an entry. This file covers the
other axis: the right person reading a **stale** entry. When a document is re-ingested, the
answers computed from the old passages are wrong — not unauthorized, simply untrue — and an
answer that is confidently wrong is the failure mode a grounded RAG system exists to avoid.

**Retirement by key, not by sweep.** The corpus version's checksum is a key component, so
publishing a new version means every caller derives a new key. The old entries are not
found, not deleted, and expire on their own TTL. There is no scan over `eaios:cache:*`, no
window during which the stale answer is still served, and no dependence on a cleanup that
might not run — which matters most in exactly the case where it is hardest to test.

**Rollback is free, and that is a consequence worth having.** Re-activating a previous
corpus version restores its checksum, so its still-live cache entries become reachable
again. A design that deleted on publish would have thrown them away.

Pure and in-memory, for the same reason as `test_cache_isolation.py`.
"""

from __future__ import annotations

from typing import Any, Final

import pytest

from eaios_core.retrieval_cache import RetrievalCache
from tests.unit.authz_helpers import context as build_context

pytestmark = pytest.mark.security

QUESTION: Final[str] = "what is the remote work policy"
V1: Final[str] = "abc407d7"
V2: Final[str] = "9f2b1c04"

MANAGER: Final[frozenset[str]] = frozenset({"documents:read", "hr:read_team"})


class FakeCache:
    def __init__(self) -> None:
        self.store: dict[str, Any] = {}

    def get(self, key: str) -> Any:
        return self.store.get(key)

    def set(self, key: str, value: Any, *, ttl_seconds: int | None = None) -> None:
        self.store[key] = value


class MutableCorpusVersion:
    """The T052 protocol, stubbed so a publish is one assignment.

    Phase 1 must not wait on Phase 2's real provider — and a stub whose checksum can be
    changed mid-test is exactly what proves the retirement property.
    """

    def __init__(self, checksum: str = V1) -> None:
        self.checksum = checksum
        self.calls: list[tuple[Any, str]] = []

    def active_checksum(self, company_id: Any, collection: str) -> str:
        self.calls.append((company_id, collection))
        return self.checksum


def cache_for(versions: MutableCorpusVersion) -> tuple[RetrievalCache, FakeCache]:
    backend = FakeCache()
    return RetrievalCache(backend, versions), backend


class TestTwoCorpusVersionsDoNotShare:
    def test_different_checksums_yield_different_keys(self) -> None:
        subject = build_context(permission_codes=MANAGER)
        first, _ = cache_for(MutableCorpusVersion(V1))
        second, _ = cache_for(MutableCorpusVersion(V2))
        assert first.key_for(subject, QUESTION) != second.key_for(subject, QUESTION)

    def test_the_same_checksum_yields_the_same_key(self) -> None:
        """The other half: a cache that never hits is not a cache."""
        subject = build_context(permission_codes=MANAGER)
        first, _ = cache_for(MutableCorpusVersion(V1))
        second, _ = cache_for(MutableCorpusVersion(V1))
        assert first.key_for(subject, QUESTION) == second.key_for(subject, QUESTION)

    def test_the_checksum_is_read_per_call_not_captured_once(self) -> None:
        """A provider consulted once at construction would keep serving the old version
        for the lifetime of the process — the staleness bug, one level up."""
        versions = MutableCorpusVersion(V1)
        cache, _ = cache_for(versions)
        subject = build_context(permission_codes=MANAGER)

        before = cache.key_for(subject, QUESTION)
        versions.checksum = V2
        after = cache.key_for(subject, QUESTION)
        assert before != after, "the provider was consulted once and cached"


class TestARetiredChecksumIsUnreachableWithoutDeletion:
    def test_the_old_answer_is_not_served_after_a_publish(self) -> None:
        versions = MutableCorpusVersion(V1)
        cache, _ = cache_for(versions)
        subject = build_context(permission_codes=MANAGER)

        cache.set(subject, QUESTION, "the old policy: three days on site")
        versions.checksum = V2
        assert cache.get(subject, QUESTION) is None, (
            "a re-ingested corpus still served the answer computed from the old passages"
        )

    def test_no_key_was_deleted_to_achieve_that(self) -> None:
        versions = MutableCorpusVersion(V1)
        cache, backend = cache_for(versions)
        subject = build_context(permission_codes=MANAGER)

        cache.set(subject, QUESTION, "the old policy")
        stored = dict(backend.store)

        versions.checksum = V2
        cache.get(subject, QUESTION)

        assert backend.store == stored, (
            "publishing swept the cache. Retirement must come from the key: a sweep runs"
            " late, can fail, and leaves the stale answer live until it finishes"
        )
        assert len(backend.store) == 1

    def test_rolling_back_makes_the_old_entry_reachable_again(self) -> None:
        """A consequence of retiring by key rather than by deletion, asserted so a future
        change to sweeping is visible as a behaviour change and not just a refactor."""
        versions = MutableCorpusVersion(V1)
        cache, _ = cache_for(versions)
        subject = build_context(permission_codes=MANAGER)

        cache.set(subject, QUESTION, "the old policy")
        versions.checksum = V2
        assert cache.get(subject, QUESTION) is None

        versions.checksum = V1
        assert cache.get(subject, QUESTION) == "the old policy"

    def test_both_versions_coexist(self) -> None:
        versions = MutableCorpusVersion(V1)
        cache, backend = cache_for(versions)
        subject = build_context(permission_codes=MANAGER)

        cache.set(subject, QUESTION, "old answer")
        versions.checksum = V2
        cache.set(subject, QUESTION, "new answer")

        assert len(backend.store) == 2, "one version overwrote the other's entry"
        assert cache.get(subject, QUESTION) == "new answer"
        versions.checksum = V1
        assert cache.get(subject, QUESTION) == "old answer"


class TestBothAxesActTogether:
    """Permission and corpus version are independent components, and a key must carry
    both — a change in either has to be enough on its own."""

    def test_a_permission_change_alone_retires_the_entry(self) -> None:
        versions = MutableCorpusVersion(V1)
        cache, _ = cache_for(versions)
        cache.set(build_context(permission_codes=MANAGER), QUESTION, "answer")
        other = build_context(permission_codes=frozenset({"documents:read"}))
        assert cache.get(other, QUESTION) is None

    def test_a_corpus_change_alone_retires_the_entry(self) -> None:
        versions = MutableCorpusVersion(V1)
        cache, _ = cache_for(versions)
        subject = build_context(permission_codes=MANAGER)
        cache.set(subject, QUESTION, "answer")
        versions.checksum = V2
        assert cache.get(subject, QUESTION) is None


class TestTheProviderIsAskedCorrectly:
    def test_it_is_scoped_by_company_and_collection(self) -> None:
        """A checksum that ignored the tenant would let one company's re-ingestion retire
        another's cache — noisy rather than unsafe, but wrong."""
        versions = MutableCorpusVersion(V1)
        cache, _ = cache_for(versions)
        subject = build_context(permission_codes=MANAGER)
        cache.key_for(subject, QUESTION)

        assert versions.calls, "the corpus-version provider was never consulted"
        company_id, collection = versions.calls[-1]
        assert company_id == subject.company_id
        assert collection == "documents"


class TestTheFakeIsRealEnough:
    def test_a_hit_is_possible(self) -> None:
        versions = MutableCorpusVersion(V1)
        cache, _ = cache_for(versions)
        subject = build_context(permission_codes=MANAGER)
        cache.set(subject, QUESTION, "an answer")
        assert cache.get(subject, QUESTION) == "an answer"
