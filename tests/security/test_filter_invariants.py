"""Tenant and classification are boundaries, not narrowings (FR-013, Principle I, CHK006).

The filter has two kinds of clause and confusing them is the whole risk. `company_id` and
`classification` are **must** clauses: they bound what is reachable at all. Everything else
— department, country, role, ownership — is a **reach**, and reaches sit in a should-group
where any one suffices.

The dangerous mistake is putting a boundary in that should-group. It reads as a small
refactor and it is a cross-tenant leak: a document owned by the caller would then be
reachable *regardless of company*, because ownership alone would satisfy the group. So
these tests fix the two invariants against every branch that could plausibly widen them —
owner, role, ACL, department, country, and the null-caller cases the nullable
`AccessContext` now makes constructible.

Each invariant is also **removed independently** and the removal proven visible. An
invariant test that cannot fail is the most dangerous artefact in a security suite: it
reports a boundary that nothing is checking.
"""

from __future__ import annotations

import uuid
from typing import Any, Final

import pytest

from eaios_core.authz.filters import MAX_ANONYMOUS_CLASSIFICATION, qdrant_filter
from eaios_core.classification import Classification
from tests.unit.authz_helpers import ENGINEERING, NILETECH
from tests.unit.authz_helpers import context as build_context

pytestmark = pytest.mark.security

#: The two clauses that must never move out of `must`.
INVARIANTS: Final[tuple[str, ...]] = ("company_id", "classification")

#: Every caller shape that might plausibly widen them.
CALLER_SHAPES: Final[dict[str, dict[str, Any]]] = {
    "ordinary": {},
    "owner-heavy": {"user_id": uuid.uuid4()},
    "many-roles": {"role_ids": frozenset(uuid.uuid4() for _ in range(4))},
    "no-roles": {"role_ids": frozenset()},
    "other-department": {"department_id": uuid.uuid4()},
    "other-country": {"country": "AE"},
    "null-department": {"department_id": None},
    "null-country": {"country": None},
    "null-both": {"department_id": None, "country": None},
    "null-both-no-roles": {"department_id": None, "country": None, "role_ids": frozenset()},
}


def _must_keys(rendered: dict[str, Any]) -> set[str]:
    """Payload keys constrained at the **top level** `must` — the boundary position."""
    return {
        clause["key"]
        for clause in rendered.get("must", [])
        if isinstance(clause, dict) and isinstance(clause.get("key"), str)
    }


def _should_keys(rendered: dict[str, Any]) -> set[str]:
    """Payload keys reachable through any should-group, at any depth."""
    found: set[str] = set()

    def walk(node: Any, inside_should: bool) -> None:
        if isinstance(node, dict):
            if inside_should and isinstance(node.get("key"), str):
                found.add(node["key"])
            for name, value in node.items():
                walk(value, inside_should or name == "should")
        elif isinstance(node, list):
            for item in node:
                walk(item, inside_should)

    walk(rendered, False)
    return found


class TestTheInvariantsAreTopLevelMustClauses:
    @pytest.mark.parametrize("shape", sorted(CALLER_SHAPES))
    @pytest.mark.parametrize("invariant", INVARIANTS)
    def test_the_invariant_is_a_must_clause(self, shape: str, invariant: str) -> None:
        rendered = qdrant_filter(build_context(**CALLER_SHAPES[shape]))
        assert invariant in _must_keys(rendered), (
            f"`{invariant}` is not a top-level must clause for the {shape!r} caller."
            " A boundary in a should-group is satisfied by any sibling branch, so"
            " ownership alone would reach documents in another tenant"
        )

    @pytest.mark.parametrize("shape", sorted(CALLER_SHAPES))
    @pytest.mark.parametrize("invariant", INVARIANTS)
    def test_the_invariant_is_not_reachable_through_a_should_group(
        self, shape: str, invariant: str
    ) -> None:
        rendered = qdrant_filter(build_context(**CALLER_SHAPES[shape]))
        assert invariant not in _should_keys(rendered), (
            f"`{invariant}` appears inside a should-group for the {shape!r} caller,"
            " which makes it optional"
        )


class TestNoBranchWidensTheTenant:
    def test_every_caller_shape_carries_the_same_company(self) -> None:
        companies = set()
        for overrides in CALLER_SHAPES.values():
            rendered = qdrant_filter(build_context(**overrides))
            companies |= {
                clause["match"]["value"]
                for clause in rendered["must"]
                if isinstance(clause, dict) and clause.get("key") == "company_id"
            }
        assert companies == {str(NILETECH)}, (
            f"the tenant clause varied across caller shapes: {companies}"
        )

    def test_a_caller_owning_everything_still_cannot_cross_tenants(self) -> None:
        """Ownership is a reach, never a boundary override."""
        rendered = qdrant_filter(build_context(user_id=uuid.uuid4()))
        assert "company_id" in _must_keys(rendered)
        assert "owner_id" in _should_keys(rendered), "ownership must be a reach"


class TestNoBranchWidensTheClassificationCeiling:
    def test_restricted_is_never_offered(self) -> None:
        for overrides in CALLER_SHAPES.values():
            rendered = qdrant_filter(build_context(**overrides))
            levels = [
                clause["match"]["any"]
                for clause in rendered["must"]
                if isinstance(clause, dict) and clause.get("key") == "classification"
            ]
            assert levels, "no classification clause"
            for offered in levels:
                assert Classification.RESTRICTED.value not in offered, (
                    "RESTRICTED is reachable by payload filter; it requires an explicit"
                    " grant decided by the policy engine, not a filter"
                )

    def test_the_ceiling_matches_the_declared_maximum(self) -> None:
        rendered = qdrant_filter(build_context())
        offered = next(
            clause["match"]["any"]
            for clause in rendered["must"]
            if clause.get("key") == "classification"
        )
        expected = [
            level.value for level in Classification if level <= MAX_ANONYMOUS_CLASSIFICATION
        ]
        assert offered == expected


class TestRemovingAnInvariantIsDetected:
    """Falsification, each invariant independently."""

    @staticmethod
    def _without(rendered: dict[str, Any], key: str) -> dict[str, Any]:
        return {
            "must": [
                clause
                for clause in rendered["must"]
                if not (isinstance(clause, dict) and clause.get("key") == key)
            ]
        }

    @pytest.mark.parametrize("invariant", INVARIANTS)
    def test_removing_it_leaves_it_out_of_must(self, invariant: str) -> None:
        damaged = self._without(qdrant_filter(build_context()), invariant)
        assert invariant not in _must_keys(damaged), (
            f"removing `{invariant}` left it in the must set, so the assertions above"
            " cannot see the defect they exist to catch"
        )

    @pytest.mark.parametrize("invariant", INVARIANTS)
    def test_the_other_invariant_survives_its_removal(self, invariant: str) -> None:
        """One removal must not cascade, or the detector cannot say which went."""
        other = next(name for name in INVARIANTS if name != invariant)
        damaged = self._without(qdrant_filter(build_context()), invariant)
        assert other in _must_keys(damaged)

    @pytest.mark.parametrize("invariant", INVARIANTS)
    def test_moving_it_into_a_should_group_is_detected(self, invariant: str) -> None:
        """The realistic defect: not deletion, but demotion to a reach."""
        rendered = qdrant_filter(build_context())
        boundary = next(c for c in rendered["must"] if c.get("key") == invariant)
        demoted = {
            "must": [c for c in rendered["must"] if c.get("key") != invariant],
            "should": [boundary],
            "min_should": 1,
        }
        assert invariant not in _must_keys(demoted)
        assert invariant in _should_keys(demoted), "the demotion was not constructed"


class TestTheDetectorsSeeRealStructure:
    """Vacuity guards: helpers that find nothing pass every assertion above."""

    def test_must_keys_finds_the_boundaries(self) -> None:
        assert _must_keys(qdrant_filter(build_context())) >= set(INVARIANTS)

    def test_should_keys_finds_the_reaches(self) -> None:
        reaches = _should_keys(qdrant_filter(build_context(department_id=ENGINEERING)))
        assert {"owner_id", "allowed_roles", "department_id", "country"} <= reaches, (
            f"the should-walker missed reaches: {sorted(reaches)}"
        )
