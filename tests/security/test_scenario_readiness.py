"""The dataset can express all eight blueprint scenarios (spec FR-047a, SC-013).

Decision D1 defers request-time authorization, so this feature cannot *enforce* the
blueprint's access-control scenarios. What it must guarantee is that the records
exist to express them — otherwise the next feature would build an authorization
engine with nothing to authorize against, and discover the gap late.

Each test below maps to one numbered scenario from the blueprint's acceptance table.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, text

pytestmark = pytest.mark.security

PERSONAS = (
    "employee.engineering",
    "manager.engineering",
    "employee.sales",
    "hr.generalist",
    "finance.analyst",
    "legal.counsel",
    "auditor.readonly",
    "admin.company",
    "comms.sender",
    "employee.delta",
)


@pytest.fixture(scope="module")
def personas(owner_engine: Engine) -> dict[str, dict]:
    with owner_engine.connect() as conn:
        rows = (
            conn.execute(
                text(
                    "SELECT u.persona_key, u.id, u.full_name, u.country, u.manager_id,"
                    " d.name AS department, c.slug AS company"
                    " FROM users u"
                    " JOIN departments d ON d.id = u.department_id"
                    " JOIN companies c ON c.id = u.company_id"
                    " WHERE u.persona_key IS NOT NULL"
                )
            )
            .mappings()
            .all()
        )
    return {row["persona_key"]: dict(row) for row in rows}


class TestPersonaSet:
    """FR-025b / SC-014 — the fixed persona set with stable identities."""

    def test_all_ten_personas_exist(self, personas: dict[str, dict]) -> None:
        missing = sorted(set(PERSONAS) - set(personas))
        assert missing == [], f"missing personas: {missing}"

    def test_each_persona_resolves_to_exactly_one_user(self, owner_engine: Engine) -> None:
        with owner_engine.connect() as conn:
            duplicates = conn.execute(
                text(
                    "SELECT persona_key FROM users WHERE persona_key IS NOT NULL"
                    " GROUP BY persona_key HAVING count(*) > 1"
                )
            ).all()
        assert duplicates == []

    @pytest.mark.parametrize(
        ("key", "company", "department"),
        [
            ("employee.engineering", "niletech", "Engineering"),
            ("manager.engineering", "niletech", "Engineering"),
            ("employee.sales", "niletech", "Sales"),
            ("hr.generalist", "niletech", "HR"),
            ("legal.counsel", "niletech", "Legal"),
            ("employee.delta", "delta-retail", "Sales"),
        ],
    )
    def test_persona_placement_is_documented(
        self, personas: dict[str, dict], key: str, company: str, department: str
    ) -> None:
        assert personas[key]["company"] == company
        assert personas[key]["department"] == department


class TestScenario1GeneralPolicy:
    """Employee asks for the general vacation policy → allow."""

    def test_an_internal_leave_policy_exists(self, owner_engine: Engine) -> None:
        with owner_engine.connect() as conn:
            count = conn.execute(
                text(
                    "SELECT count(*) FROM policy_documents p JOIN documents d ON d.id = p.document_id"
                    " WHERE p.policy_type = 'LEAVE' AND d.classification = 'INTERNAL'"
                )
            ).scalar_one()
        assert count == 2, "each tenant needs a readable leave policy"


class TestScenario2OwnData:
    """Employee asks for their own leave balance → allow."""

    def test_the_employee_persona_has_a_leave_balance(
        self, owner_engine: Engine, personas: dict[str, dict]
    ) -> None:
        with owner_engine.connect() as conn:
            count = conn.execute(
                text("SELECT count(*) FROM leave_balances WHERE user_id = :uid"),
                {"uid": personas["employee.engineering"]["id"]},
            ).scalar_one()
        assert count > 0


class TestScenario3AnotherSalary:
    """Employee asks for another employee's salary → deny."""

    def test_another_employees_salary_record_exists(
        self, owner_engine: Engine, personas: dict[str, dict]
    ) -> None:
        with owner_engine.connect() as conn:
            count = conn.execute(
                text("SELECT count(*) FROM employee_profiles WHERE user_id = :uid"),
                {"uid": personas["employee.sales"]["id"]},
            ).scalar_one()
        assert count == 1, "there must be a salary record to be denied"

    def test_a_restricted_payroll_document_exists(self, owner_engine: Engine) -> None:
        """FR-010c — RESTRICTED must be represented, and this is what it protects."""
        with owner_engine.connect() as conn:
            count = conn.execute(
                text("SELECT count(*) FROM documents WHERE classification = 'RESTRICTED'")
            ).scalar_one()
        assert count == 2


class TestScenario4ManagerTeam:
    """Manager asks for direct reports' leave summary → allow, reports only."""

    def test_the_manager_persona_has_at_least_three_reports(
        self, owner_engine: Engine, personas: dict[str, dict]
    ) -> None:
        with owner_engine.connect() as conn:
            count = conn.execute(
                text("SELECT count(*) FROM users WHERE manager_id = :uid"),
                {"uid": personas["manager.engineering"]["id"]},
            ).scalar_one()
        assert count >= 3, f"manager.engineering has {count} reports, needs >= 3"

    def test_those_reports_have_leave_balances(
        self, owner_engine: Engine, personas: dict[str, dict]
    ) -> None:
        with owner_engine.connect() as conn:
            count = conn.execute(
                text(
                    "SELECT count(*) FROM leave_balances WHERE user_id IN"
                    " (SELECT id FROM users WHERE manager_id = :uid)"
                ),
                {"uid": personas["manager.engineering"]["id"]},
            ).scalar_one()
        assert count > 0


class TestScenario5CrossDepartment:
    """Manager asks for another department's records → deny."""

    def test_a_user_exists_outside_the_managers_department(self, personas: dict[str, dict]) -> None:
        manager = personas["manager.engineering"]
        outsider = personas["employee.sales"]
        assert manager["company"] == outsider["company"]
        assert manager["department"] != outsider["department"]

    def test_the_outsider_is_not_a_direct_report(
        self, owner_engine: Engine, personas: dict[str, dict]
    ) -> None:
        assert personas["employee.sales"]["manager_id"] != personas["manager.engineering"]["id"]


class TestScenario6ContractComparison:
    """Legal compares two assigned contracts → allow, with citations."""

    def test_a_matched_contract_pair_exists(self, owner_engine: Engine) -> None:
        with owner_engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT notice_period_days, liability_cap_amount, payment_terms"
                    " FROM contracts WHERE counterparty_name IN"
                    " ('Helios Logistics Group', 'Zenith Manufacturing Ltd')"
                    " AND company_id = (SELECT id FROM companies WHERE slug = 'niletech')"
                    " ORDER BY counterparty_name"
                )
            ).all()
        assert len(rows) == 2, "the comparison pair is missing"

        notices = {row.notice_period_days for row in rows}
        caps = {row.liability_cap_amount for row in rows}
        terms = {row.payment_terms for row in rows}

        assert notices == {30, 90}, "notice periods must differ for a comparison to be meaningful"
        assert None in caps and len(caps) == 2, "one contract must be uncapped"
        assert len(terms) == 1, "payment terms must agree, so the answer has an agreement too"

    def test_legal_persona_holds_an_explicit_grant(
        self, owner_engine: Engine, personas: dict[str, dict]
    ) -> None:
        """The resource-ACL layer above role and attribute rules."""
        with owner_engine.connect() as conn:
            count = conn.execute(
                text(
                    "SELECT count(*) FROM document_acl"
                    " WHERE principal_type = 'USER' AND principal_id = :uid"
                    " AND permission = 'READ'"
                ),
                {"uid": personas["legal.counsel"]["id"]},
            ).scalar_one()
        assert count >= 2, "legal.counsel needs explicit READ on both contracts"


class TestScenario7CrossTenant:
    """NileTech user searches a Delta phrase → nothing.

    The probe itself lives in test_cross_tenant_probe.py; this asserts the bait
    exists so that probe is not vacuous.
    """

    def test_delta_content_exists_to_be_searched_for(self, owner_engine: Engine) -> None:
        with owner_engine.connect() as conn:
            count = conn.execute(
                text(
                    "SELECT count(*) FROM documents"
                    " WHERE company_id = (SELECT id FROM companies WHERE slug = 'delta-retail')"
                )
            ).scalar_one()
        assert count > 0


class TestScenario8ApprovalGate:
    """Authorized agent proposes sending a report → pause for confirmation."""

    def test_a_send_capable_persona_exists(self, personas: dict[str, dict]) -> None:
        assert "comms.sender" in personas

    def test_the_send_permission_is_in_the_catalog(self, owner_engine: Engine) -> None:
        with owner_engine.connect() as conn:
            codes = {
                row[0]
                for row in conn.execute(
                    text("SELECT code FROM permissions WHERE code LIKE 'communications:%'")
                )
            }
        assert codes == {"communications:draft", "communications:send"}

    def test_a_report_document_exists_to_be_sent(self, owner_engine: Engine) -> None:
        with owner_engine.connect() as conn:
            count = conn.execute(
                text("SELECT count(*) FROM documents WHERE document_type = 'REPORT'")
            ).scalar_one()
        assert count > 0


class TestAllEightAreCovered:
    def test_scenario_count(self) -> None:
        """SC-013 — 8 of 8, with none quietly dropped."""
        scenario_classes = [name for name in globals() if name.startswith("TestScenario")]
        assert len(scenario_classes) == 8, sorted(scenario_classes)


class TestLiveDataMatchesTheFrozenPersonas:
    """The generator's persona table is pinned in `tests/unit/test_persona_identity.py`.
    This confirms the *loaded* environment agrees with it, which the unit test cannot
    see — a loader that dropped or reordered users would satisfy the pin and still
    leave the demo pointing at the wrong people.
    """

    def test_live_personas_match_the_frozen_identities(self, owner_engine: Engine) -> None:
        from tests.unit.test_persona_identity import FROZEN

        with owner_engine.connect() as conn:
            profile = conn.execute(text("SELECT profile FROM dataset_manifest")).scalar_one()
            rows = (
                conn.execute(
                    text(
                        "SELECT u.persona_key, u.email, u.full_name, u.country,"
                        " d.name AS department, c.slug AS company,"
                        " m.email AS manager_email"
                        " FROM users u"
                        " JOIN departments d ON d.id = u.department_id"
                        " JOIN companies c ON c.id = u.company_id"
                        " LEFT JOIN users m ON m.id = u.manager_id"
                        " WHERE u.persona_key IS NOT NULL"
                    )
                )
                .mappings()
                .all()
            )

        expected = FROZEN[profile]
        drifted = []
        for row in rows:
            frozen = expected[row["persona_key"]]
            observed = (
                frozen.company == row["company"]
                and frozen.department == row["department"]
                and frozen.country == row["country"]
                and frozen.email == row["email"]
                and frozen.full_name == row["full_name"]
                and frozen.manager_email == row["manager_email"]
            )
            if not observed:
                drifted.append((row["persona_key"], frozen, dict(row)))

        assert drifted == [], f"loaded personas differ from the frozen table: {drifted}"

    def test_the_profile_has_a_frozen_table(self, owner_engine: Engine) -> None:
        """Otherwise the lookup above would KeyError instead of failing usefully."""
        from tests.unit.test_persona_identity import FROZEN

        with owner_engine.connect() as conn:
            profile = conn.execute(text("SELECT profile FROM dataset_manifest")).scalar_one()
        assert profile in FROZEN
