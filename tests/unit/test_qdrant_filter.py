"""Every filter clause is present, and removing any one is detected (FR-014b, R1, CHK025).

**Why one named test per clause.** A single "the filter has the right keys" assertion fails
as one line whatever is missing, so the failure says *something* changed rather than *what*.
These seven say which clause went, because the consequences differ enormously: dropping
`company_id` is a cross-tenant leak, dropping `classification` exposes material above the
caller's ceiling, and dropping `owner_id` merely hides documents someone owns.

**Seven, not six.** `document_id` carries the resource-grant reach (R5): the retrieval
service resolves READ grants from `document_acl` *before* the search and hands the
resulting ids to `qdrant_filter`. It was previously indexed and idle. Because that reach
only exists when a grant was resolved, the filters built here supply one — a caller with no
grants has six clauses, and that is the negative twin in
`tests/unit/test_qdrant_filter_grants.py`, not a missing clause.

**Non-vacuity is proven per clause, not asserted.** Each test induces the exact defect —
strips that one clause from a real filter — and requires the detector to fire. A test that
cannot fail is worse than no test here, because the whole point of a pre-search filter is
that nothing downstream re-checks it (FR-013).
"""

from __future__ import annotations

import uuid
from typing import Any, Final

import pytest

from eaios_core.authz.filters import FILTER_KEYS, qdrant_filter

from .authz_helpers import context as build_context

pytestmark = pytest.mark.unit

#: The seven clauses FR-014b enumerates. Named here so a clause added to the filter
#: without a test is a failure rather than an omission nobody notices.
EXPECTED_CLAUSES: Final[tuple[str, ...]] = (
    "company_id",
    "classification",
    "department_id",
    "country",
    "allowed_roles",
    "owner_id",
    "document_id",
)

#: One internally resolved READ-granted document id. Every filter below is built with it,
#: because the grant reach is rendered only when resolution produced something.
GRANTED: Final[tuple[uuid.UUID, ...]] = (uuid.UUID("d0c11e00-0000-4000-8000-000000000001"),)


def _rendered(**overrides: Any) -> dict[str, Any]:
    """A complete seven-clause filter for a caller with one resolved grant."""
    return qdrant_filter(build_context(**overrides), granted_document_ids=GRANTED)


def _keys_in(clause: Any) -> set[str]:
    """Every payload key referenced anywhere in a structured filter."""
    found: set[str] = set()
    if isinstance(clause, dict):
        if "key" in clause and isinstance(clause["key"], str):
            found.add(clause["key"])
        for value in clause.values():
            found |= _keys_in(value)
    elif isinstance(clause, list):
        for item in clause:
            found |= _keys_in(item)
    return found


def _strip(clause: Any, key: str) -> Any:
    """The same filter with every reference to `key` removed — the induced defect."""
    if isinstance(clause, dict):
        if clause.get("key") == key:
            return None
        rebuilt = {k: _strip(v, key) for k, v in clause.items()}
        return {k: v for k, v in rebuilt.items() if v is not None}
    if isinstance(clause, list):
        return [item for item in (_strip(i, key) for i in clause) if item is not None]
    return clause


class TestTheFilterHasSubstance:
    """A key-set assertion over an empty filter passes exactly like a correct one."""

    def test_the_filter_is_not_empty(self) -> None:
        assert _rendered(), "qdrant_filter returned nothing"

    def test_it_references_several_payload_keys(self) -> None:
        keys = _keys_in(_rendered())
        assert len(keys) >= 7, f"only {len(keys)} payload keys referenced: {sorted(keys)}"

    def test_the_declared_key_set_matches_the_expectation(self) -> None:
        """`FILTER_KEYS` is what T043 derives its index list from, so it must be right."""
        assert set(FILTER_KEYS) == set(EXPECTED_CLAUSES), (
            f"FILTER_KEYS={sorted(FILTER_KEYS)} does not match the seven clauses FR-014b"
            f" enumerates: {sorted(EXPECTED_CLAUSES)}"
        )


class TestEveryClauseIsPresent:
    @pytest.mark.parametrize("clause", EXPECTED_CLAUSES)
    def test_the_clause_appears_in_the_filter(self, clause: str) -> None:
        keys = _keys_in(_rendered())
        assert clause in keys, (
            f"`{clause}` is not referenced by the filter. Every clause is a narrowing the"
            f" search would otherwise not apply, and nothing downstream re-checks it"
        )


class TestRemovingAClauseIsDetected:
    """Falsification, one induced defect per clause."""

    @pytest.mark.parametrize("clause", EXPECTED_CLAUSES)
    def test_stripping_the_clause_is_visible(self, clause: str) -> None:
        complete = _rendered()
        damaged = _strip(complete, clause)

        assert clause in _keys_in(complete)
        assert clause not in _keys_in(damaged), (
            f"stripping `{clause}` left it still referenced, so this file's detector"
            " cannot see the defect it exists to catch"
        )

    @pytest.mark.parametrize("clause", EXPECTED_CLAUSES)
    def test_the_damaged_filter_would_fail_the_presence_check(self, clause: str) -> None:
        damaged = _strip(_rendered(), clause)
        assert not set(EXPECTED_CLAUSES) <= _keys_in(damaged)


class TestTheTenantClauseIsUnconditional:
    """`company_id` is the boundary, not a narrowing (Principle I)."""

    def test_it_is_present_for_the_narrowest_caller_there_is(self) -> None:
        """No roles, no department, no country, no grants — nothing left to narrow by,
        and the tenant clause is still there. The full null-caller semantics live in
        `test_qdrant_filter_null_scope.py`."""
        subject = build_context(role_ids=frozenset(), department_id=None, country=None)
        assert "company_id" in _keys_in(qdrant_filter(subject))

    def test_it_carries_the_callers_company(self) -> None:
        company = uuid.uuid4()
        rendered = repr(_rendered(company_id=company))
        assert str(company) in rendered, "the filter does not carry the caller's company id"

    def test_two_callers_from_different_companies_get_different_filters(self) -> None:
        first = _rendered(company_id=uuid.uuid4())
        second = _rendered(company_id=uuid.uuid4())
        assert first != second, (
            "two tenants produced an identical filter, so the tenant boundary is not in it"
        )
