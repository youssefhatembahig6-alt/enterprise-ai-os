"""A cached answer is reachable only by a caller entitled to it (FR-018, R2, CHK022, CHK023).

A retrieval cache is a store of answers computed under one person's permissions. The whole
risk of having one is that a second person reads the first person's entry — so the key,
not a check after the lookup, is what has to carry the entitlement. If the key is right the
leak is *unconstructible*; if the key is wrong, no amount of post-lookup filtering helps,
because by then the answer has already been read out of Redis.

**Unreachable, not invalidated.** The tempting design is to delete a user's cache entries
when their permissions change. That is a distributed cleanup, it runs late, it can fail
silently, and until it completes the old answer is live. Keying on the permission
fingerprint instead means the moment permissions change the caller **derives a different
key** — the old entry is not deleted, it is simply never asked for again. The correctness
does not depend on a cleanup job running.

**Pure and in-memory.** No Redis, no shared namespace: an isolation test that mutated a
real cache would be the one artefact in the suite capable of causing the incident it
describes. The fake below is a dict with the same two operations the accessor uses.

**Scope is part of entitlement.** Since FR-014a, `qdrant_filter` narrows by department and
country, so two callers with identical permission codes in different departments reach
genuinely different document sets. The fingerprint carries both; the tests here prove it,
because a fingerprint blind to them would give those two callers one key for one question.
"""

from __future__ import annotations

from typing import Any, Final

import pytest

from eaios_core.retrieval_cache import RetrievalCache
from tests.unit.authz_helpers import DELTA, ENGINEERING, NILETECH, SALES
from tests.unit.authz_helpers import context as build_context

pytestmark = pytest.mark.security

QUESTION: Final[str] = "how many annual leave days do i have"
CHECKSUM: Final[str] = "abc407d7"

EMPLOYEE: Final[frozenset[str]] = frozenset({"documents:read", "hr:read_self"})
MANAGER: Final[frozenset[str]] = frozenset(
    {"documents:read", "hr:read_self", "hr:read_team", "actions:approve"}
)
HR: Final[frozenset[str]] = frozenset(
    {"documents:read", "hr:read_self", "hr:read_all", "hr:update"}
)


class FakeCache:
    """A dict with a get/set surface and a log of what was asked for."""

    def __init__(self) -> None:
        self.store: dict[str, Any] = {}
        self.reads: list[str] = []

    def get(self, key: str) -> Any:
        self.reads.append(key)
        return self.store.get(key)

    def set(self, key: str, value: Any, *, ttl_seconds: int | None = None) -> None:
        self.store[key] = value


class StubCorpusVersion:
    """The T052 protocol, stubbed. Phase 1 must not depend on Phase 2's real provider."""

    def __init__(self, checksum: str = CHECKSUM) -> None:
        self.checksum = checksum
        self.calls: list[tuple[Any, str]] = []

    def active_checksum(self, company_id: Any, collection: str) -> str:
        self.calls.append((company_id, collection))
        return self.checksum


def cache_for(versions: StubCorpusVersion | None = None) -> tuple[RetrievalCache, FakeCache]:
    backend = FakeCache()
    return RetrievalCache(backend, versions or StubCorpusVersion()), backend


class TestDifferentPermissionsCannotShareAnEntry:
    def test_three_permission_sets_yield_three_keys(self) -> None:
        cache, _ = cache_for()
        keys = {
            name: cache.key_for(build_context(permission_codes=codes), QUESTION)
            for name, codes in (("employee", EMPLOYEE), ("manager", MANAGER), ("hr", HR))
        }
        assert len(set(keys.values())) == 3, f"cache keys collided: {keys}"

    def test_one_extra_permission_changes_the_key(self) -> None:
        """The narrowest case that matters: `hr:read_team` is exactly the permission
        deciding whether someone else's HR record is reachable."""
        cache, _ = cache_for()
        base = cache.key_for(build_context(permission_codes=EMPLOYEE), QUESTION)
        widened = cache.key_for(
            build_context(permission_codes=EMPLOYEE | {"hr:read_team"}), QUESTION
        )
        assert base != widened

    def test_an_employee_cannot_read_a_managers_cached_answer(self) -> None:
        """The leak itself, attempted rather than reasoned about."""
        cache, backend = cache_for()
        manager = build_context(permission_codes=MANAGER)
        employee = build_context(permission_codes=EMPLOYEE)

        cache.set(manager, QUESTION, "you have 20 days, and your team has 4 pending")
        assert cache.get(employee, QUESTION) is None, (
            "an employee read an answer computed under a manager's permissions"
        )
        assert cache.get(manager, QUESTION) is not None, "the owner lost their own entry"

    def test_the_same_permissions_in_two_tenants_do_not_share(self) -> None:
        cache, _ = cache_for()
        here = build_context(company_id=NILETECH, permission_codes=MANAGER)
        there = build_context(company_id=DELTA, permission_codes=MANAGER)
        assert cache.key_for(here, QUESTION) != cache.key_for(there, QUESTION)

    def test_a_cross_tenant_read_returns_nothing(self) -> None:
        cache, _ = cache_for()
        here = build_context(company_id=NILETECH, permission_codes=MANAGER)
        there = build_context(company_id=DELTA, permission_codes=MANAGER)
        cache.set(here, QUESTION, "niletech answer")
        assert cache.get(there, QUESTION) is None


class TestScopeIsPartOfEntitlement:
    """FR-014a made department and country narrow the search; the key must follow."""

    def test_two_departments_do_not_share(self) -> None:
        cache, _ = cache_for()
        engineering = build_context(permission_codes=MANAGER, department_id=ENGINEERING)
        sales = build_context(permission_codes=MANAGER, department_id=SALES)
        assert cache.key_for(engineering, QUESTION) != cache.key_for(sales, QUESTION), (
            "two departments shared a cache key. They reach different document sets, so"
            " one would be served the other's answer for the same question"
        )

    def test_two_countries_do_not_share(self) -> None:
        cache, _ = cache_for()
        egypt = build_context(permission_codes=MANAGER, country="EG")
        emirates = build_context(permission_codes=MANAGER, country="AE")
        assert cache.key_for(egypt, QUESTION) != cache.key_for(emirates, QUESTION)

    def test_a_caller_without_a_department_does_not_share_with_one_who_has_it(self) -> None:
        """A null scope reaches only company-wide documents — strictly less — so it must
        not collide with any real department."""
        cache, _ = cache_for()
        scoped = build_context(permission_codes=MANAGER, department_id=ENGINEERING)
        unscoped = build_context(permission_codes=MANAGER, department_id=None)
        assert cache.key_for(scoped, QUESTION) != cache.key_for(unscoped, QUESTION)


class TestAPermissionChangeMakesTheOldEntryUnreachable:
    """Without deleting anything — the property that makes correctness independent of a
    cleanup job."""

    def test_the_old_answer_is_not_returned_after_a_demotion(self) -> None:
        cache, backend = cache_for()
        before = build_context(permission_codes=HR)
        cache.set(before, QUESTION, "every employee's leave balance")

        after = build_context(permission_codes=EMPLOYEE)
        assert cache.get(after, QUESTION) is None

    def test_nothing_was_deleted_to_achieve_that(self) -> None:
        """The distinction this whole design rests on. If unreachability required a
        deletion, there would be a window in which the old answer was still live."""
        cache, backend = cache_for()
        before = build_context(permission_codes=HR)
        cache.set(before, QUESTION, "every employee's leave balance")
        stored = dict(backend.store)

        after = build_context(permission_codes=EMPLOYEE)
        cache.get(after, QUESTION)

        assert backend.store == stored, (
            "the cache mutated on a miss. Unreachability must come from the key, not"
            " from an invalidation that can fail, lag, or be skipped"
        )
        assert len(backend.store) == 1, "the old entry should still be sitting there"

    def test_a_promotion_does_not_expose_the_narrower_answer_either(self) -> None:
        """Both directions. A promoted caller must not inherit their old, narrower entry
        and believe it complete."""
        cache, _ = cache_for()
        narrow = build_context(permission_codes=EMPLOYEE)
        cache.set(narrow, QUESTION, "your own balance only")
        assert cache.get(build_context(permission_codes=HR), QUESTION) is None


class TestNoPassageBodyIsStored:
    """FR-037. The cache holds answers, and the key holds digests — never text."""

    def test_the_key_carries_no_question_text(self) -> None:
        cache, _ = cache_for()
        key = cache.key_for(build_context(permission_codes=MANAGER), QUESTION)
        assert QUESTION not in key
        # Words of three letters or more only: the key ends in hex digests, and every
        # single letter a–f occurs in one by chance. Asserting on those would fail for a
        # reason that has nothing to do with the question surviving into the key.
        for word in (w for w in QUESTION.split() if len(w) >= 3):
            assert word not in key, f"the question word {word!r} appears in the key {key!r}"

    def test_the_key_carries_no_permission_name(self) -> None:
        """Cache keys are visible to anyone who can run `KEYS *`."""
        cache, _ = cache_for()
        key = cache.key_for(build_context(permission_codes=MANAGER), QUESTION)
        for code in MANAGER:
            assert code not in key

    def test_storing_a_passage_body_is_refused(self) -> None:
        cache, _ = cache_for()
        subject = build_context(permission_codes=MANAGER)
        with pytest.raises(ValueError, match="passage"):
            cache.set(subject, QUESTION, {"passages": [{"text": "verbatim body"}]})

    @pytest.mark.parametrize(
        "value",
        [
            {"result": {"passages": [{"text": "body"}]}},
            {"answer": {"sources": {"excerpt": "body"}}},
            {"turns": [{"citations": [{"content": "body"}]}]},
            [{"question": "what did i ask"}],
        ],
        ids=["nested-dict", "twice-nested", "through-a-list", "top-level-list"],
    )
    def test_a_body_buried_anywhere_is_refused(self, value: object) -> None:
        """Only the top level was checked once, and a cached answer is a nested
        structure by nature — passages hang off it, not beside it."""
        cache, _ = cache_for()
        with pytest.raises(ValueError, match="passage"):
            cache.set(build_context(permission_codes=MANAGER), QUESTION, value)

    def test_an_ordinary_answer_is_still_cacheable(self) -> None:
        """Vacuity guard: a refusal that rejects everything is not a policy."""
        cache, _ = cache_for()
        cache.set(
            build_context(permission_codes=MANAGER),
            QUESTION,
            {"answer": "20 days", "citations": [{"document_id": "abc", "ordinal": 3}]},
        )


class TestTheFakeCacheIsRealEnough:
    """Vacuity guards. A fake that stored nothing would pass every miss assertion."""

    def test_a_hit_is_possible_at_all(self) -> None:
        cache, _ = cache_for()
        subject = build_context(permission_codes=MANAGER)
        cache.set(subject, QUESTION, "an answer")
        assert cache.get(subject, QUESTION) == "an answer", (
            "the fake never returns anything, so every 'cannot read' assertion above is"
            " vacuous"
        )

    def test_a_different_question_misses(self) -> None:
        cache, _ = cache_for()
        subject = build_context(permission_codes=MANAGER)
        cache.set(subject, QUESTION, "an answer")
        assert cache.get(subject, "something else entirely") is None

    def test_the_backend_actually_recorded_the_lookup(self) -> None:
        cache, backend = cache_for()
        cache.get(build_context(permission_codes=MANAGER), QUESTION)
        assert backend.reads, "no lookup reached the backend"
