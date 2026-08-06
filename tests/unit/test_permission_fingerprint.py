"""The permission fingerprint (spec 003 FR-016, Constitution Principle III).

``eaios_core.keys.cache_key`` has required a ``permission_fingerprint`` since feature
001 and nothing has ever produced one — the parameter existed, unfilled, waiting for
the feature where a permission set first exists. This is that feature.

Principle III's requirement is precise: an HR-scoped answer must never be served to an
ordinary employee. The fingerprint is the component of the cache key that carries
that, so it has to satisfy two properties that pull against each other:

* **different permission sets must never collide** — a collision is a cross-permission
  cache hit, which is the leak the key exists to prevent;
* **the same permission set must produce the same value every time**, including across
  processes and across whatever order the rows came back from the database in.

Nothing in this feature reads a cache. The value is defined and proven here so feature
004 consumes a definition rather than inventing a second one.
"""

from __future__ import annotations

import pytest

from eaios_core.keys import cache_key

from .authz_helpers import DELTA, NILETECH, context

pytestmark = pytest.mark.unit

EMPLOYEE = frozenset({"documents:read", "hr:read_self"})
MANAGER = frozenset({"documents:read", "hr:read_self", "hr:read_team", "actions:approve"})
HR = frozenset({"documents:read", "hr:read_self", "hr:read_all", "hr:update"})


class TestDistinctSetsDoNotCollide:
    def test_different_permission_sets_differ(self) -> None:
        prints = {
            name: context(permission_codes=codes).permission_fingerprint
            for name, codes in (("employee", EMPLOYEE), ("manager", MANAGER), ("hr", HR))
        }
        assert len(set(prints.values())) == 3, f"fingerprints collided: {prints}"

    def test_one_extra_permission_changes_it(self) -> None:
        """The narrowest case that matters. A manager differs from an employee by
        `hr:read_team` — precisely the permission that decides whether someone else's
        HR record is reachable — so a fingerprint insensitive to a single added code
        would serve an employee a manager's cached answer."""
        base = context(permission_codes=EMPLOYEE).permission_fingerprint
        widened = context(
            permission_codes=EMPLOYEE | {"hr:read_team"}
        ).permission_fingerprint
        assert base != widened

    def test_the_same_permissions_in_different_tenants_differ(self) -> None:
        """Tenant is already a separate component of `cache_key`, so this is defence in
        depth. It costs one field and removes any dependence on callers assembling the
        key correctly."""
        niletech = context(company_id=NILETECH, permission_codes=MANAGER)
        delta = context(company_id=DELTA, permission_codes=MANAGER)
        assert niletech.permission_fingerprint != delta.permission_fingerprint


class TestTheSameSetIsAlwaysTheSameValue:
    def test_order_does_not_matter(self) -> None:
        """A `frozenset` has no order, but the *iteration* order of one varies with
        insertion and with the process's hash seed. Hashing the iteration order
        directly would produce a value that changes between runs — a cache that misses
        every restart, and a fingerprint that means nothing."""
        forwards = context(
            permission_codes=frozenset(["a:read", "b:read", "c:read"])
        ).permission_fingerprint
        backwards = context(
            permission_codes=frozenset(["c:read", "b:read", "a:read"])
        ).permission_fingerprint
        assert forwards == backwards

    def test_it_is_stable_across_repeated_construction(self) -> None:
        values = {context(permission_codes=MANAGER).permission_fingerprint for _ in range(5)}
        assert len(values) == 1, f"unstable across construction: {values}"

    def test_it_does_not_depend_on_anything_but_tenant_and_permissions(self) -> None:
        """Department, office, session, and roles all change without moving it. If they
        did move it, every user would get their own cache entry and the cache would
        stop being one."""
        base = context(permission_codes=MANAGER).permission_fingerprint
        from .authz_helpers import SALES, ident

        varied = context(
            permission_codes=MANAGER,
            user_id=ident("user:someone-else"),
            session_id=ident("session:another"),
            department_id=SALES,
            office_id=ident("office:dxb"),
            country="AE",
            employment_type="CONTRACT",
            role_names=frozenset({"Auditor"}),
        ).permission_fingerprint
        assert base == varied


class TestTheShapeIsUsableAsAKeyComponent:
    def test_it_is_a_hex_digest(self) -> None:
        value = context(permission_codes=MANAGER).permission_fingerprint
        assert value, "empty fingerprint"
        assert all(character in "0123456789abcdef" for character in value), value

    def test_it_carries_no_permission_name(self) -> None:
        """Cache keys are visible to anyone who can run `KEYS *`. A fingerprint that
        embedded the codes would publish each user's exact permission set to whoever
        can list keys."""
        value = context(permission_codes=MANAGER).permission_fingerprint
        for code in MANAGER:
            assert code not in value

    def test_an_empty_permission_set_still_produces_one(self) -> None:
        """The spec's edge case — a user with no roles at all. A `None` or empty
        fingerprint here would make `cache_key` unbuildable for exactly the user whose
        answers must be narrowest."""
        value = context(permission_codes=frozenset()).permission_fingerprint
        assert value

    def test_it_composes_with_the_existing_cache_key_builder(self) -> None:
        """The point of the whole exercise: `cache_key` takes this parameter and has
        never been given a real one."""
        subject = context(permission_codes=MANAGER)
        key = cache_key(
            company_slug=subject.company_slug,
            permission_fingerprint=subject.permission_fingerprint,
            normalized_question="how many annual leave days do i have",
            data_version="abc407d7",
        )
        assert subject.permission_fingerprint in key
        assert key.startswith("eaios:cache:niletech:")
