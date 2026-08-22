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
        widened = context(permission_codes=EMPLOYEE | {"hr:read_team"}).permission_fingerprint
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

    def test_it_does_not_depend_on_identity_office_or_role_names(self) -> None:
        """User, session, office, employment type and role names move nothing.

        **Narrowed from "anything but tenant and permissions" in feature 004.** The
        original invariant was correct while `qdrant_filter` did not narrow by
        department or country. It now does (FR-014a): two callers holding identical
        permission codes in different departments reach genuinely different document
        sets, so a fingerprint blind to those two fields would give them the same cache
        key for the same question and serve one the other's answer — the cross-scope
        leak FR-018 exists to prevent.

        The fields listed here are the ones that still change nothing about *what is
        reachable*, and they remain excluded for the original reason: fragmenting the
        cache per user would stop it being a cache.
        """
        base = context(permission_codes=MANAGER).permission_fingerprint
        from .authz_helpers import ident

        varied = context(
            permission_codes=MANAGER,
            user_id=ident("user:someone-else"),
            session_id=ident("session:another"),
            office_id=ident("office:dxb"),
            employment_type="CONTRACT",
            role_names=frozenset({"Auditor"}),
        ).permission_fingerprint
        assert base == varied

    def test_it_does_depend_on_department_and_country(self) -> None:
        """The other half of the narrowing, stated so it cannot be reverted silently."""
        from .authz_helpers import SALES, ident

        base = context(permission_codes=MANAGER)
        assert (
            base.permission_fingerprint
            != context(permission_codes=MANAGER, department_id=SALES).permission_fingerprint
        ), "two departments shared a fingerprint"
        assert (
            base.permission_fingerprint
            != context(permission_codes=MANAGER, country="AE").permission_fingerprint
        ), "two countries shared a fingerprint"
        del ident

    def test_a_missing_attribute_cannot_collide_with_a_real_one(self) -> None:
        """`None` is rendered `<null>`, which no UUID or ISO country code can produce."""
        from eaios_core.authz.context import NULL_SENTINEL

        absent = context(permission_codes=MANAGER, department_id=None).permission_fingerprint
        present = context(permission_codes=MANAGER).permission_fingerprint
        assert absent != present
        assert "<" in NULL_SENTINEL, "the sentinel must be unproducible by a real value"

    def test_the_cache_fan_out_stays_bounded(self) -> None:
        """The original concern, checked rather than dismissed.

        Adding two attributes multiplies entries by department × country **per company**,
        not per user — the fields that would have fragmented it one-per-user are still
        excluded above.
        """
        from .authz_helpers import SALES
        from .authz_helpers import ident as _ident

        distinct = {
            context(permission_codes=MANAGER, user_id=_ident(f"user:{n}")).permission_fingerprint
            for n in range(5)
        }
        assert len(distinct) == 1, "identity still fragments the cache"
        scoped = {
            context(permission_codes=MANAGER).permission_fingerprint,
            context(permission_codes=MANAGER, department_id=SALES).permission_fingerprint,
        }
        assert len(scoped) == 2


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
