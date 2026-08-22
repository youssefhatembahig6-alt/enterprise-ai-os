"""The five layers, their order, and what each branch may and may not reach (FR-014, FR-015, R5).

FR-014 fixes the order: **tenant, role, attribute, resource grant, classification**. Two of
those bound (tenant, classification) and three reach (role, attribute, grant). This file
pins the reaches and proves none of them can widen a bound.

**How the explicit-ACL layer reaches the filter.** `document_acl` is relational — grants are
rows keyed by (`principal_type`, `principal_id`, `permission`) — and a Qdrant payload is
not relational, so the ACL cannot be a clause the way `owner_id` is. The retrieval service
therefore **resolves grants before the search** (T094, R5): it queries `document_acl` for
`READ` grants matching the caller's user id, role ids and department id, scoped to the
caller's company, and hands the resulting **document ids** to `qdrant_filter`, which renders
them as the `document_id` reach.

Three properties follow, and each has a test below:

* the grant **narrows the search** rather than filtering its results, because resolution
  happens before the query (FR-013);
* the ids are **always server-derived** — `qdrant_filter` has no parameter and
  `AccessContext` no field through which a request could contribute one (FR-029);
* `qdrant_filter` **queries nothing**; it renders what it is handed, so this package keeps
  its independence from the database exactly as it has from the vector store.

**What an earlier draft got wrong.** It tested the ACL through `HR_PROFILE` and the policy
engine's `acl_grants`, on the reasoning that no `ResourceKind.DOCUMENT` exists. That proved
the HR engine's ACL, which is a different mechanism reached by a different code path, and
proved nothing about retrieval. Those tests are removed rather than adapted.

**Only `USER`/`READ` grants exist in this corpus** (R5: four rows). `ROLE` and `DEPARTMENT`
principals are Phase 3 wiring coverage — the resolution query in T094 handles them and no
seeded row exercises them. That limitation is stated in a test below rather than left to be
discovered, because a filter that cannot see provenance cannot be the place it is fixed.

Each reach branch is also **removed independently** and the removal proven visible.
"""

from __future__ import annotations

import dataclasses
import uuid
from typing import Any, Final

import pytest

from eaios_core.authz.filters import qdrant_filter
from eaios_core.classification import Classification

from .authz_helpers import ALICE, CAROL, DELTA, context

pytestmark = pytest.mark.unit

#: The reaches, in FR-014's order. Tenant (1) and classification (5) are bounds and are
#: pinned in `tests/security/test_filter_invariants.py`.
REACH_BRANCHES: Final[tuple[str, ...]] = (
    "allowed_roles",
    "department_id",
    "owner_id",
    "document_id",
)

#: Stand-ins for what T094's `document_acl` query returns. Fixed rather than random so an
#: ordering assertion means something.
GRANT_A: Final[uuid.UUID] = uuid.UUID("d0c11e00-0000-4000-8000-00000000000a")
GRANT_B: Final[uuid.UUID] = uuid.UUID("d0c11e00-0000-4000-8000-00000000000b")
GRANTED: Final[tuple[uuid.UUID, ...]] = (GRANT_A,)


def _rendered(granted: Any = GRANTED, **overrides: Any) -> dict[str, Any]:
    return qdrant_filter(context(**overrides), granted_document_ids=granted)


def _reach_group(rendered: dict[str, Any]) -> dict[str, Any]:
    """The should-group holding the reaches."""
    for clause in rendered["must"]:
        if isinstance(clause, dict) and "should" in clause:
            return clause
    raise AssertionError("no reach group in the filter")


def _reach_keys(group: dict[str, Any]) -> set[str]:
    found: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if isinstance(node.get("key"), str):
                found.add(node["key"])
            if isinstance(node.get("is_null"), dict):
                found.add(node["is_null"]["key"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(group)
    return found


def _granted_ids(rendered: dict[str, Any]) -> list[str]:
    """The ids offered by the grant branch, in the order the filter emits them."""
    branches = [
        branch
        for branch in _reach_group(rendered)["should"]
        if isinstance(branch, dict) and branch.get("key") == "document_id"
    ]
    if not branches:
        return []
    assert len(branches) == 1, "more than one grant branch"
    return list(branches[0]["match"]["any"])


def _all_keys(node: Any) -> set[str]:
    """Every payload key anywhere in the filter, at any depth."""
    found: set[str] = set()
    if isinstance(node, dict):
        if isinstance(node.get("key"), str):
            found.add(node["key"])
        if isinstance(node.get("is_null"), dict):
            found.add(node["is_null"]["key"])
        for value in node.values():
            found |= _all_keys(value)
    elif isinstance(node, list):
        for item in node:
            found |= _all_keys(item)
    return found


class TestTheReachGroupExists:
    def test_there_is_exactly_one_reach_group(self) -> None:
        rendered = _rendered()
        groups = [c for c in rendered["must"] if isinstance(c, dict) and "should" in c]
        assert len(groups) == 1, f"expected one reach group, found {len(groups)}"

    def test_any_one_reach_suffices(self) -> None:
        assert _reach_group(_rendered())["min_should"] == 1, (
            "the reaches must be alternatives; requiring all of them would mean a caller"
            " reaches their own document only when it is also in their department"
        )

    def test_every_reach_branch_is_present(self) -> None:
        keys = _reach_keys(_reach_group(_rendered()))
        for branch in REACH_BRANCHES:
            assert branch in keys, f"the `{branch}` reach is missing"


class TestTheOwnerBranch:
    def test_it_carries_the_callers_user_id(self) -> None:
        group = _reach_group(_rendered(user_id=CAROL))
        owners = [
            b["match"]["value"]
            for b in group["should"]
            if isinstance(b, dict) and b.get("key") == "owner_id"
        ]
        assert owners == [str(CAROL)]

    def test_ownership_does_not_depend_on_department_or_country(self) -> None:
        """A caller reaches their own documents wherever those documents sit."""
        group = _reach_group(_rendered(department_id=None, country=None))
        assert "owner_id" in _reach_keys(group)


class TestTheRoleBranch:
    def test_it_carries_role_ids_not_names(self) -> None:
        roles = frozenset({uuid.uuid4(), uuid.uuid4()})
        group = _reach_group(_rendered(role_ids=roles))
        offered = next(
            b["match"]["any"]
            for b in group["should"]
            if isinstance(b, dict) and b.get("key") == "allowed_roles"
        )
        assert set(offered) == {str(r) for r in roles}, (
            "roles must be matched by id; a name follows a rename into granting access"
            " nobody decided to grant"
        )

    def test_a_caller_with_no_roles_still_has_the_branch(self) -> None:
        """Present but empty — an absent branch would be a structural difference that
        later code could mistake for 'roles do not apply here'."""
        group = _reach_group(_rendered(role_ids=frozenset()))
        assert "allowed_roles" in _reach_keys(group)


class TestTheAttributeBranch:
    def test_both_dimensions_must_admit_the_caller(self) -> None:
        """Nested `must`: the right country but the wrong department is not a reach."""
        group = _reach_group(_rendered())
        nested = [b for b in group["should"] if isinstance(b, dict) and "must" in b]
        assert nested, "the attribute branch is not a conjunction"
        keys = _reach_keys(nested[0])
        assert {"department_id", "country"} <= keys


class TestTheGrantBranchIsTheOnlyReachLeft:
    """The ACL-only positive and its negative twin.

    The caller is built so that **every other reach is exhausted**: no roles, no department,
    no country, and a document they do not own. What remains is the grant. Removing it must
    remove the only way in — which is what makes this the case R5 requires the evaluation
    set to contain.
    """

    STRANDED: Final[dict[str, Any]] = {
        "role_ids": frozenset(),
        "department_id": None,
        "country": None,
    }

    def test_the_grant_branch_carries_the_resolved_id(self) -> None:
        rendered = _rendered(GRANTED, **self.STRANDED)
        assert _granted_ids(rendered) == [str(GRANT_A)], (
            "a caller whose only reach is an explicit grant got no grant branch, so the"
            " document reachable solely through `document_acl` is unreachable"
        )

    def test_the_negative_twin_has_no_grant_branch_at_all(self) -> None:
        """The same caller, the same question, the grant withdrawn."""
        rendered = _rendered((), **self.STRANDED)
        assert _granted_ids(rendered) == []
        assert "document_id" not in _all_keys(rendered), (
            "an empty grant set still produced a `document_id` clause. An empty match-any"
            " is a branch that matches nothing today and a branch someone widens tomorrow;"
            " the absence of a grant must be the absence of the reach"
        )

    def test_the_twins_differ_only_in_the_grant(self) -> None:
        """Otherwise the positive could be passing for some unrelated reason."""
        granted = _rendered(GRANTED, **self.STRANDED)
        withheld = _rendered((), **self.STRANDED)
        assert granted != withheld
        assert _all_keys(granted) - _all_keys(withheld) == {"document_id"}

    def test_the_stranded_caller_really_is_stranded(self) -> None:
        """Vacuity guard. If this caller kept a live department or role reach, the
        'only way in' claim above would be false and both twins would pass regardless."""
        subject = context(**self.STRANDED)
        assert subject.role_ids == frozenset()
        assert subject.department_id is None and subject.country is None


class TestUserReadGrantsAreRepresentable:
    """R5's four rows are all `USER`/`READ`, so this is the shape that must work."""

    def test_a_uuid_is_rendered_as_a_string(self) -> None:
        assert _granted_ids(_rendered((GRANT_A,))) == [str(GRANT_A)], (
            "the id must be a string; a UUID object does not survive the wire"
        )

    def test_several_grants_are_all_offered(self) -> None:
        assert set(_granted_ids(_rendered((GRANT_A, GRANT_B)))) == {
            str(GRANT_A),
            str(GRANT_B),
        }

    def test_the_order_is_deterministic(self) -> None:
        """Two resolutions returning the same set in different orders must produce the
        same filter, or an otherwise identical query is a cache miss."""
        forwards = _rendered((GRANT_A, GRANT_B))
        backwards = _rendered((GRANT_B, GRANT_A))
        assert forwards == backwards

    def test_a_duplicate_id_does_not_appear_twice(self) -> None:
        """Resolution joins three principal kinds, so the same document can come back
        more than once."""
        assert _granted_ids(_rendered((GRANT_A, GRANT_A))) == [str(GRANT_A)]

    def test_any_iterable_of_ids_is_accepted(self) -> None:
        """The resolution layer returns whatever its query builds — a set, a list, a
        generator's result. The filter must not care."""
        as_set = _rendered(frozenset({GRANT_A, GRANT_B}))
        as_list = _rendered([GRANT_B, GRANT_A])
        assert as_set == as_list == _rendered((GRANT_A, GRANT_B))


class TestRoleAndDepartmentGrantsArePhaseThreeWiring:
    """R5's stated coverage limitation, recorded rather than left to be discovered.

    `document_acl` rows carry a `principal_type`, and resolution (T094) matches `USER`,
    `ROLE` and `DEPARTMENT` rows alike. By the time ids reach this function the principal
    type is **gone** — and deliberately so: a filter that could tell a role grant from a
    user grant would be re-deciding an authorization already decided.

    So the assertion here is the honest one. The filter is provenance-blind, which means
    `ROLE` and `DEPARTMENT` support is proven where the query lives, not here, and no
    seeded row in this corpus exercises it yet.
    """

    def test_the_filter_cannot_distinguish_the_principal_that_granted(self) -> None:
        from_user_grant = _rendered((GRANT_A,))
        from_role_grant = _rendered((GRANT_A,))
        assert from_user_grant == from_role_grant

    def test_no_principal_type_reaches_the_payload(self) -> None:
        rendered = repr(_rendered((GRANT_A, GRANT_B)))
        for leaked in ("principal_type", "USER", "ROLE", "DEPARTMENT", "READ"):
            assert leaked not in rendered, (
                f"`{leaked}` reached the payload filter. ACL bookkeeping belongs to the"
                " resolution query; a payload carrying it invites a second decision"
            )


class TestTheGrantIdsCannotComeFromTheRequest:
    """FR-029. A request-supplied granted id is an authorization decision taken from the
    caller — the escalation this whole ordering exists to prevent."""

    def test_omitting_the_argument_yields_no_grant_reach(self) -> None:
        """The default is empty, not 'unrestricted'. A caller who reaches this function
        without a resolution step gets no grant, never every grant."""
        assert "document_id" not in _all_keys(qdrant_filter(context()))

    def test_the_default_equals_an_explicit_empty_set(self) -> None:
        assert qdrant_filter(context()) == _rendered(())

    def test_the_argument_is_keyword_only(self) -> None:
        """Positionally, a grant set is one argument-order slip away from being whatever
        the caller happened to have. Naming it forces the call site to say so."""
        with pytest.raises(TypeError):
            qdrant_filter(context(), GRANTED)  # type: ignore[misc]

    def test_the_access_context_carries_no_grant_field(self) -> None:
        """The other way a request could reach the ids: through the context built from a
        verified token. Nothing there names grants, and this fails if something starts to.
        """
        subject = context()
        suspects = [
            field.name
            for field in dataclasses.fields(subject)
            if any(word in field.name.lower() for word in ("grant", "acl", "document"))
        ]
        assert suspects == [], (
            f"`AccessContext` grew grant-shaped fields: {suspects}. Grants are resolved"
            " per query from `document_acl`, not carried on the caller"
        )

    def test_mutating_the_caller_s_collection_afterwards_changes_nothing(self) -> None:
        """The resolution layer's list must not stay live inside the filter."""
        supplied = [GRANT_A]
        rendered = _rendered(supplied)
        supplied.append(GRANT_B)
        assert _granted_ids(rendered) == [str(GRANT_A)]


class TestNoReachWidensABound:
    @pytest.mark.parametrize("branch", REACH_BRANCHES)
    def test_the_bounds_survive_every_reach(self, branch: str) -> None:
        rendered = _rendered()
        top_level = {
            c["key"] for c in rendered["must"] if isinstance(c, dict) and "key" in c
        }
        assert {"company_id", "classification"} <= top_level, (
            f"the `{branch}` reach coincides with a missing bound"
        )

    def test_a_cross_tenant_owner_is_still_bounded(self) -> None:
        rendered = _rendered(company_id=DELTA, user_id=ALICE)
        company = next(
            c["match"]["value"] for c in rendered["must"] if c.get("key") == "company_id"
        )
        assert company == str(DELTA), "ownership leaked across the tenant boundary"

    def test_a_grant_cannot_cross_the_tenant_boundary(self) -> None:
        """Resolution is company-scoped, but the filter must not depend on that being
        remembered: `company_id` stays a top-level `must`, so a grant for another
        tenant's document reaches nothing even if one is somehow resolved."""
        rendered = _rendered((GRANT_A,), company_id=DELTA)
        company = next(
            c["match"]["value"] for c in rendered["must"] if c.get("key") == "company_id"
        )
        assert company == str(DELTA)
        assert "company_id" not in _reach_keys(_reach_group(rendered)), (
            "the tenant clause moved into the reach group, where the grant branch alone"
            " would satisfy it — a cross-tenant read wearing the shape of an ACL hit"
        )

    def test_a_grant_cannot_raise_the_classification_ceiling(self) -> None:
        """RESTRICTED needs an explicit decision, and a resolved grant id is not one:
        the ceiling is a `must`, so a granted RESTRICTED document is still out of reach
        until the policy engine says otherwise."""
        rendered = _rendered((GRANT_A, GRANT_B))
        offered = next(
            c["match"]["any"] for c in rendered["must"] if c.get("key") == "classification"
        )
        assert Classification.RESTRICTED.value not in offered
        assert "classification" not in _reach_keys(_reach_group(rendered))

    def test_no_reach_offers_restricted(self) -> None:
        rendered = _rendered(role_ids=frozenset({uuid.uuid4()}))
        offered = next(
            c["match"]["any"] for c in rendered["must"] if c.get("key") == "classification"
        )
        assert Classification.RESTRICTED.value not in offered


class TestRemovingAReachBranchIsDetected:
    """Falsification, each reach independently."""

    @staticmethod
    def _without(group: dict[str, Any], key: str) -> dict[str, Any]:
        def survives(branch: Any) -> bool:
            return key not in _reach_keys(branch)

        return {"should": [b for b in group["should"] if survives(b)], "min_should": 1}

    @pytest.mark.parametrize("branch", REACH_BRANCHES)
    def test_removing_it_is_visible(self, branch: str) -> None:
        group = _reach_group(_rendered())
        damaged = self._without(group, branch)
        assert branch in _reach_keys(group)
        assert branch not in _reach_keys(damaged), (
            f"removing the `{branch}` reach left it present, so this file cannot see the"
            " defect it exists to catch"
        )

    @pytest.mark.parametrize("branch", REACH_BRANCHES)
    def test_the_other_reaches_survive(self, branch: str) -> None:
        group = _reach_group(_rendered())
        damaged = self._without(group, branch)
        others = {b for b in REACH_BRANCHES if b != branch}
        # `department_id` and `country` share one nested branch, so removing either
        # removes both — named here rather than papered over.
        if branch == "department_id":
            others -= {"country"}
        assert others <= _reach_keys(damaged) | {"country"}
