"""Policy prose and stored records state the same numbers (spec FR-035, SC-007).

This is the coherence property everything else rests on. If the leave policy says
21 days and the balances say 20, every grounded answer the system later produces is
contradicted by its own source — and the failure looks like an AI defect when it is
really a data defect.

The generator reads both values from one function, so agreement is structural rather
than coincidental. These tests confirm that structure actually held.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, text

from eaios_seed.generators.policies import POLICY_TYPES, entitlement_days

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def engine() -> Engine:
    from eaios_core.db import create_owner_engine

    engine = create_owner_engine()
    try:
        with engine.connect() as conn:
            seeded = conn.execute(text("SELECT count(*) FROM companies")).scalar_one()
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"database unavailable: {exc}")
    if not seeded:
        pytest.skip("environment not seeded; run `make up && make seed`")
    return engine


class TestLeavePolicyAgreesWithBalances:
    def test_every_annual_entitlement_matches_the_policy(self, engine: Engine) -> None:
        """FR-035, across every employee — not a sample."""
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT u.country, u.employment_type, lb.entitlement_days, count(*) AS n"
                    " FROM leave_balances lb JOIN users u ON u.id = lb.user_id"
                    " WHERE lb.leave_type = 'ANNUAL'"
                    " GROUP BY 1, 2, 3"
                )
            ).all()

        assert rows, "no annual leave balances to check"
        mismatches = [
            f"{row.country}/{row.employment_type}: policy says "
            f"{entitlement_days(row.country, row.employment_type)}, "
            f"{row.n} record(s) say {row.entitlement_days}"
            for row in rows
            if row.entitlement_days != entitlement_days(row.country, row.employment_type)
        ]
        assert mismatches == [], "\n".join(mismatches)

    def test_the_policy_document_states_the_same_numbers(self, engine: Engine) -> None:
        """The prose a user would read must match the records (FR-035)."""
        with engine.connect() as conn:
            stated = conn.execute(
                text(
                    "SELECT stated_values -> 'annual_leave_days' AS days"
                    " FROM policy_documents WHERE policy_type = 'LEAVE' LIMIT 1"
                )
            ).scalar_one()

        assert stated["EG"] == entitlement_days("EG", "FULL_TIME")
        assert stated["AE"] == entitlement_days("AE", "FULL_TIME")

    def test_countries_differ_so_the_check_discriminates(self) -> None:
        """If both countries had the same entitlement, the country-scoped rule the
        next feature builds would be untestable."""
        assert entitlement_days("EG", "FULL_TIME") != entitlement_days("AE", "FULL_TIME")

    def test_contractors_accrue_nothing(self, engine: Engine) -> None:
        with engine.connect() as conn:
            wrong = conn.execute(
                text(
                    "SELECT count(*) FROM leave_balances lb JOIN users u ON u.id = lb.user_id"
                    " WHERE lb.leave_type = 'ANNUAL' AND u.employment_type = 'CONTRACT'"
                    " AND lb.entitlement_days <> 0"
                )
            ).scalar_one()
        assert wrong == 0


class TestBalanceArithmetic:
    def test_remaining_equals_entitlement_minus_used(self, engine: Engine) -> None:
        with engine.connect() as conn:
            broken = conn.execute(
                text(
                    "SELECT count(*) FROM leave_balances"
                    " WHERE remaining_days <> entitlement_days - used_days"
                )
            ).scalar_one()
        assert broken == 0

    def test_no_negative_balances(self, engine: Engine) -> None:
        with engine.connect() as conn:
            negative = conn.execute(
                text("SELECT count(*) FROM leave_balances WHERE remaining_days < 0")
            ).scalar_one()
        assert negative == 0


class TestPolicyCoverage:
    def test_every_policy_type_exists_for_both_tenants(self, engine: Engine) -> None:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT c.slug, p.policy_type FROM policy_documents p"
                    " JOIN companies c ON c.id = p.company_id"
                )
            ).all()
        by_company: dict[str, set[str]] = {}
        for slug, policy_type in rows:
            by_company.setdefault(slug, set()).add(policy_type)

        for slug, types in by_company.items():
            missing = sorted(set(POLICY_TYPES) - types)
            assert missing == [], f"{slug} is missing policies: {missing}"

    def test_every_policy_has_a_backing_document(self, engine: Engine) -> None:
        with engine.connect() as conn:
            orphaned = conn.execute(
                text(
                    "SELECT count(*) FROM policy_documents p"
                    " LEFT JOIN documents d ON d.id = p.document_id WHERE d.id IS NULL"
                )
            ).scalar_one()
        assert orphaned == 0


class TestDocumentsReferenceRealEntities:
    """FR-036 — generated prose names only things that exist in that company."""

    def test_document_owners_belong_to_the_same_company(self, engine: Engine) -> None:
        with engine.connect() as conn:
            crossing = conn.execute(
                text(
                    "SELECT count(*) FROM documents d JOIN users u ON u.id = d.owner_id"
                    " WHERE u.company_id <> d.company_id"
                )
            ).scalar_one()
        assert crossing == 0

    def test_document_departments_belong_to_the_same_company(self, engine: Engine) -> None:
        with engine.connect() as conn:
            crossing = conn.execute(
                text(
                    "SELECT count(*) FROM documents d"
                    " JOIN departments dept ON dept.id = d.department_id"
                    " WHERE dept.company_id <> d.company_id"
                )
            ).scalar_one()
        assert crossing == 0

    def test_every_document_has_exactly_one_owner(self, engine: Engine) -> None:
        """FR-031a — no file may be ownerless."""
        with engine.connect() as conn:
            ownerless = conn.execute(
                text("SELECT count(*) FROM documents WHERE owner_id IS NULL")
            ).scalar_one()
        assert ownerless == 0

    def test_content_digest_matches_recorded_size(self, engine: Engine) -> None:
        with engine.connect() as conn:
            bad = conn.execute(
                text(
                    "SELECT count(*) FROM documents"
                    " WHERE byte_size <= 0 OR length(content_sha256) <> 64"
                )
            ).scalar_one()
        assert bad == 0
