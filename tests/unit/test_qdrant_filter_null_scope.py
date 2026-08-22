"""Null means company-wide, on both sides of the clause (FR-014a, SC-024, R4).

Three rules, and the third is the one a flat equality filter cannot express at all:

* A **document** with a null `country` or `department_id` is scoped **company-wide**.
* A caller **with** a value reaches documents matching it **or** company-wide ones.
* A caller **without** a value reaches **only** company-wide ones.

**Why `AccessContext` had to change.** The third rule describes a caller this codebase
could not construct: `department_id` and `country` were non-optional, so "a caller without
a department" did not exist as a value and the rule could never have been tested. They are
now `| None`, and every case below builds a **real** `AccessContext` rather than probing a
private helper — a semantics test that only exercises an internal function proves the
internal function, not the filter the search layer actually receives.

**The absent attribute narrows; it never disappears.** The tempting shortcut is to omit the
clause when the caller has no value. That widens the search to every department in the
tenant — the exact opposite of what an absent attribute means — so there is an explicit
test for it.
"""

from __future__ import annotations

import uuid
from typing import Any, Final

import pytest

from eaios_core.authz.filters import attribute_clause, qdrant_filter

from .authz_helpers import ENGINEERING
from .authz_helpers import context as build_context

pytestmark = pytest.mark.unit

ATTRIBUTES: Final[tuple[str, ...]] = ("department_id", "country")


def _clause_for(rendered: Any, key: str) -> dict[str, Any] | None:
    """The should-group governing one attribute, wherever it sits in the tree."""
    if isinstance(rendered, dict):
        branches = rendered.get("should")
        if isinstance(branches, list) and any(
            (b.get("key") == key or b.get("is_null", {}).get("key") == key)
            for b in branches
            if isinstance(b, dict)
        ):
            return rendered
        for value in rendered.values():
            found = _clause_for(value, key)
            if found is not None:
                return found
    elif isinstance(rendered, list):
        for item in rendered:
            found = _clause_for(item, key)
            if found is not None:
                return found
    return None


def _branch_kinds(clause: dict[str, Any], key: str) -> set[str]:
    """Which branch kinds the clause offers: `equals`, `null`, or both."""
    kinds: set[str] = set()
    for branch in clause.get("should", []):
        if not isinstance(branch, dict):
            continue
        if branch.get("is_null", {}).get("key") == key:
            kinds.add("null")
        elif branch.get("key") == key:
            kinds.add("equals")
    return kinds


class TestTheFourCallersAreConstructible:
    """The change that made this file possible; without it three cases do not exist."""

    def test_both_attributes_present(self) -> None:
        subject = build_context()
        assert subject.department_id is not None
        assert subject.country is not None

    def test_missing_department_only(self) -> None:
        subject = build_context(department_id=None)
        assert subject.department_id is None
        assert subject.country is not None

    def test_missing_country_only(self) -> None:
        subject = build_context(country=None)
        assert subject.country is None
        assert subject.department_id is not None

    def test_both_missing(self) -> None:
        subject = build_context(department_id=None, country=None)
        assert subject.department_id is None and subject.country is None


class TestACallerWithAValueReachesMatchingOrCompanyWide:
    @pytest.mark.parametrize("attribute", ATTRIBUTES)
    def test_the_clause_offers_both_branches(self, attribute: str) -> None:
        clause = _clause_for(qdrant_filter(build_context()), attribute)
        assert clause is not None, f"no clause governs `{attribute}`"
        assert _branch_kinds(clause, attribute) == {"equals", "null"}, (
            f"a caller with a `{attribute}` must reach matching **or** company-wide"
            f" documents; branches offered: {_branch_kinds(clause, attribute)}"
        )

    def test_the_equals_branch_carries_the_callers_value(self) -> None:
        subject = build_context(department_id=ENGINEERING)
        clause = _clause_for(qdrant_filter(subject), "department_id")
        assert clause is not None
        values = [
            b["match"]["value"]
            for b in clause["should"]
            if isinstance(b, dict) and b.get("key") == "department_id"
        ]
        assert values == [str(ENGINEERING)]


class TestACallerWithoutAValueReachesOnlyCompanyWide:
    @pytest.mark.parametrize(
        ("attribute", "override"),
        [("department_id", {"department_id": None}), ("country", {"country": None})],
    )
    def test_only_the_null_branch_remains(self, attribute: str, override: dict[str, Any]) -> None:
        clause = _clause_for(qdrant_filter(build_context(**override)), attribute)
        assert clause is not None, f"the `{attribute}` clause disappeared for a null caller"
        assert _branch_kinds(clause, attribute) == {"null"}, (
            f"a caller with no `{attribute}` must reach only company-wide documents;"
            f" branches offered: {_branch_kinds(clause, attribute)}"
        )

    def test_both_missing_leaves_both_clauses_null_only(self) -> None:
        rendered = qdrant_filter(build_context(department_id=None, country=None))
        for attribute in ATTRIBUTES:
            clause = _clause_for(rendered, attribute)
            assert clause is not None
            assert _branch_kinds(clause, attribute) == {"null"}


class TestAnAbsentAttributeNarrowsRatherThanDisappears:
    """The shortcut that would silently widen the search to the whole tenant."""

    @pytest.mark.parametrize(
        ("attribute", "override"),
        [("department_id", {"department_id": None}), ("country", {"country": None})],
    )
    def test_the_clause_is_still_present(self, attribute: str, override: dict[str, Any]) -> None:
        rendered = qdrant_filter(build_context(**override))
        assert _clause_for(rendered, attribute) is not None, (
            f"the `{attribute}` clause was omitted for a caller with no value. Omitting"
            " it does not narrow to company-wide — it widens to every value in the"
            " tenant, which is the opposite of what an absent attribute means"
        )

    @pytest.mark.parametrize("attribute", ATTRIBUTES)
    def test_a_null_caller_is_strictly_narrower_than_a_valued_one(self, attribute: str) -> None:
        valued = _clause_for(qdrant_filter(build_context()), attribute)
        absent = _clause_for(qdrant_filter(build_context(**{attribute: None})), attribute)
        assert valued is not None and absent is not None
        assert _branch_kinds(absent, attribute) < _branch_kinds(valued, attribute), (
            "a caller without the attribute must reach a strict subset of what a caller"
            " with it reaches"
        )


class TestTheClauseBuilderCarriesTheSemantics:
    """Directly, so the rule is pinned independently of how the filter assembles it."""

    def test_a_value_yields_equals_and_null(self) -> None:
        clause = attribute_clause("country", "EG")
        assert _branch_kinds(clause, "country") == {"equals", "null"}
        assert clause["min_should"] == 1

    def test_none_yields_null_only(self) -> None:
        clause = attribute_clause("country", None)
        assert _branch_kinds(clause, "country") == {"null"}
        assert clause["min_should"] == 1

    def test_a_uuid_is_rendered_as_a_string(self) -> None:
        identifier = uuid.uuid4()
        clause = attribute_clause("department_id", identifier)
        values = [b["match"]["value"] for b in clause["should"] if "match" in b]
        assert values == [str(identifier)], "the value must be a string, not a UUID object"
