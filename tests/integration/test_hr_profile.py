"""The HR profile an employee reads about themselves (spec 003 FR-023, SC-001).

FR-023 names the fields: department, office, manager, employment type, and leave
balance, "at minimum". This checks each one is present *and* matches the database,
because a field that renders as an empty string satisfies "present" and tells the
employee nothing.

The compensation absence is checked here too. `tests/security/test_authorize_before_read.py`
proves the denial happens before the query — the stronger property — but this pins the
response shape, so a future change that added a salary field to the profile model would
fail here rather than silently making the denial pointless.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from eaios_core.db import create_owner_engine

from ..security.auth_helpers import (
    DELTA_EMPLOYEE,
    EMPLOYEE,
    MANAGER,
    auth,
    load_person,
    token_for,
)

pytestmark = pytest.mark.integration


def _own_profile(client: TestClient, persona: str) -> dict[str, object]:
    token = token_for(client, persona)
    response = client.get("/me/hr-profile", headers=auth(token))
    assert response.status_code == 200, response.text
    return dict(response.json())


class TestEveryRequiredFieldIsPresent:
    @pytest.mark.parametrize(
        "field",
        [
            "user_id",
            "full_name",
            "email",
            "department",
            "office",
            "country",
            "employment_type",
            "job_title",
            "hire_date",
            "leave_balance",
        ],
    )
    def test_the_field_is_present(self, client: TestClient, field: str) -> None:
        body = _own_profile(client, EMPLOYEE)
        assert field in body, f"FR-023 requires {field}"

    def test_no_required_field_is_blank(self, client: TestClient) -> None:
        """Present and empty is the failure this catches. A profile page rendering
        blanks satisfies "the field exists" and satisfies nobody reading it."""
        body = _own_profile(client, EMPLOYEE)
        blank = [
            key
            for key in ("full_name", "email", "department", "office", "job_title")
            if not str(body.get(key) or "").strip()
        ]
        assert blank == [], f"blank fields on an employee's own profile: {blank}"

    def test_the_manager_is_named(self, client: TestClient) -> None:
        """Null only for the one manager-less user per company. The seeded employee is
        not that person, so a null here means the join failed."""
        person = load_person(EMPLOYEE)
        assert person.manager_id is not None, "fixture chose the manager-less executive"
        assert _own_profile(client, EMPLOYEE)["manager_name"]


class TestItMatchesTheDatabase:
    def test_identity_and_placement_agree_with_the_records(
        self, client: TestClient
    ) -> None:
        person = load_person(EMPLOYEE)
        body = _own_profile(client, EMPLOYEE)

        with create_owner_engine().connect() as conn:
            row = conn.execute(
                text(
                    "SELECT u.full_name, u.email, u.country, u.employment_type,"
                    "       d.name AS department, o.city AS office,"
                    "       p.job_title, p.hire_date, m.full_name AS manager_name"
                    " FROM users u"
                    " JOIN departments d ON d.id = u.department_id"
                    " JOIN offices o ON o.id = u.office_id"
                    " JOIN employee_profiles p ON p.user_id = u.id"
                    " LEFT JOIN users m ON m.id = u.manager_id"
                    " WHERE u.id = :u"
                ),
                {"u": person.user_id},
            ).one()

        assert body["full_name"] == row.full_name
        assert body["email"] == row.email
        assert body["department"] == row.department
        assert body["office"] == row.office
        assert body["country"] == row.country
        assert body["employment_type"] == row.employment_type
        assert body["job_title"] == row.job_title
        assert body["hire_date"] == row.hire_date.isoformat()
        assert body["manager_name"] == row.manager_name

    def test_the_leave_balance_agrees_with_the_records(self, client: TestClient) -> None:
        """Feature 001's FR-035 makes the leave policy and the balances coherent — a
        handbook stating 21 days matches the rows. This is where an employee actually
        sees that number, so it had better be the same one."""
        person = load_person(EMPLOYEE)
        balance = _own_profile(client, EMPLOYEE)["leave_balance"]
        assert balance is not None, "no annual leave balance for a seeded employee"
        assert isinstance(balance, dict)

        with create_owner_engine().connect() as conn:
            row = conn.execute(
                text(
                    "SELECT leave_type, year, entitlement_days, used_days, remaining_days"
                    " FROM leave_balances WHERE user_id = :u AND leave_type = 'ANNUAL'"
                    " ORDER BY year DESC LIMIT 1"
                ),
                {"u": person.user_id},
            ).one()

        assert balance["leave_type"] == row.leave_type
        assert balance["year"] == row.year
        assert balance["entitlement_days"] == row.entitlement_days
        assert balance["used_days"] == row.used_days
        assert balance["remaining_days"] == row.remaining_days
        assert (
            balance["remaining_days"] == balance["entitlement_days"] - balance["used_days"]
        ), "the arithmetic the database constraint enforces does not survive the API"


class TestItCarriesNoCompensation:
    def test_no_salary_field_appears(self, client: TestClient) -> None:
        body = _own_profile(client, EMPLOYEE)
        for forbidden in ("salary", "salary_amount", "salary_band", "currency", "compensation"):
            assert forbidden not in body, f"the profile leaked {forbidden}"

    def test_the_value_is_reachable_elsewhere_by_the_right_caller(
        self, client: TestClient
    ) -> None:
        """Without this, "no salary in the profile" is satisfied by a system where
        salary is unreachable full stop — and the denial in FR-025 would be proving
        nothing."""
        from ..security.auth_helpers import HR

        person = load_person(EMPLOYEE)
        token = token_for(client, HR)
        response = client.get(
            f"/hr/profiles/{person.user_id}/compensation", headers=auth(token)
        )
        assert response.status_code == 200, response.text
        assert response.json()["salary_amount"]

    def test_the_amount_is_a_string_not_a_float(self, client: TestClient) -> None:
        """Money is exact everywhere else — `Numeric(14,2)` in the database, `Decimal`
        in Python. JSON's number type is a double, so serialising it as one would
        reintroduce rounding error at the last boundary."""
        from ..security.auth_helpers import HR

        person = load_person(EMPLOYEE)
        token = token_for(client, HR)
        amount = client.get(
            f"/hr/profiles/{person.user_id}/compensation", headers=auth(token)
        ).json()["salary_amount"]
        assert isinstance(amount, str), f"salary serialised as {type(amount).__name__}"
        assert "." in amount and len(amount.split(".")[1]) == 2, amount


class TestTheSameShapeForEveryCaller:
    def test_a_manager_reading_a_report_gets_the_same_fields(
        self, client: TestClient
    ) -> None:
        """`/me/hr-profile` and `/hr/profiles/{id}` are the same read with the subject
        fixed differently. One shaping function serves both, and this is what would
        catch them drifting into describing the same person differently."""
        from ..security.auth_helpers import direct_report_ids

        manager = load_person(MANAGER)
        reports = direct_report_ids(manager.user_id)
        if not reports:
            pytest.skip("no direct reports seeded")

        token = token_for(client, MANAGER)
        own = client.get("/me/hr-profile", headers=auth(token)).json()
        theirs = client.get(f"/hr/profiles/{reports[0]}", headers=auth(token)).json()

        assert set(own) == set(theirs)
        assert own["user_id"] != theirs["user_id"]

    def test_a_delta_retail_employee_reads_their_own(self, client: TestClient) -> None:
        body = _own_profile(client, DELTA_EMPLOYEE)
        person = load_person(DELTA_EMPLOYEE)
        assert body["user_id"] == str(person.user_id)
