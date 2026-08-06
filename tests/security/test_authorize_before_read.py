"""Authorization precedes retrieval (spec 003 FR-015, FR-025, FR-036, SC-007).

FR-036 is unusually explicit about method: an automated check must prove a denied
request performs **no read** of the protected data, and "a check that only inspects the
response cannot establish this". It is right to insist. A denied request and a
successful one for an empty record produce the same absence of data in the response;
only the statement log distinguishes "we refused before looking" from "we looked and
then withheld".

So this file records the SQL a request actually executes and asserts on it — in **both**
directions. The denied path must not touch `employee_profiles.salary_amount`; the
allowed path must. Without the second half, every assertion here is satisfied by a
recorder that captured nothing at all, which is the exact failure mode this project has
found again and again.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from .auth_helpers import EMPLOYEE, HR, MANAGER, auth, direct_report_ids, load_person, token_for
from .conftest import StatementRecorder

pytestmark = pytest.mark.security

#: The column FR-025 protects. Searched for in the recorded statements rather than in
#: the response, because a response that omits it proves only that it was omitted.
SALARY = "salary_amount"


@pytest.fixture(scope="module")
def a_direct_report(client: TestClient) -> str:
    person = load_person(MANAGER)
    reports = direct_report_ids(person.user_id)
    if not reports:
        pytest.skip("the seeded manager has no direct reports; the scenario is untestable")
    return str(reports[0])


class TestTheRecorderWorks:
    """The harness needs its own control before anything it reports means anything.

    Every assertion in this file has the form "no statement mentioned X". A recorder
    attached to the wrong engine, or removed too early, satisfies all of them while
    watching nothing.
    """

    def test_it_records_statements_at_all(
        self, client: TestClient, recorded_sql: StatementRecorder
    ) -> None:
        token = token_for(client, EMPLOYEE)
        client.get("/me", headers=auth(token))
        assert len(recorded_sql) > 0, "the recorder captured nothing on a working request"

    def test_it_sees_the_tables_a_request_touches(
        self, client: TestClient, recorded_sql: StatementRecorder
    ) -> None:
        token = token_for(client, EMPLOYEE)
        client.get("/me", headers=auth(token))
        assert "users" in recorded_sql, "the recorder missed the users query"

    def test_it_can_distinguish_a_column(
        self, client: TestClient, recorded_sql: StatementRecorder
    ) -> None:
        """Proves the needle is findable when it is genuinely there — the direct
        control for every `SALARY not in recorded_sql` assertion below."""
        token = token_for(client, HR)
        person = load_person(HR)
        response = client.get(
            f"/hr/profiles/{person.user_id}/compensation", headers=auth(token)
        )
        assert response.status_code == 200, response.text
        assert SALARY in recorded_sql, (
            "an allowed compensation read executed no statement mentioning"
            f" {SALARY} — the search term is wrong, and every denial assertion in this"
            " file is therefore vacuous"
        )


class TestTheDeniedPathNeverReadsTheData:
    def test_a_manager_denied_compensation_runs_no_salary_query(
        self, client: TestClient, recorded_sql: StatementRecorder, a_direct_report: str
    ) -> None:
        """FR-025's flagship denial, proven at the query level.

        The manager is allowed to read this person's *profile* — they are a direct
        report — so the refusal is specifically about compensation, and the record is
        one the caller can otherwise reach. That makes it a real test of the boundary
        rather than of the tenant.
        """
        token = token_for(client, MANAGER)
        response = client.get(
            f"/hr/profiles/{a_direct_report}/compensation", headers=auth(token)
        )

        assert response.status_code == 403, response.text
        offenders = recorded_sql.touched(SALARY)
        assert offenders == [], (
            "a denied request executed a statement selecting the protected column:\n  "
            + "\n  ".join(offenders)
        )

    def test_an_employee_denied_a_colleagues_profile_runs_no_profile_query(
        self, client: TestClient, recorded_sql: StatementRecorder
    ) -> None:
        """The same property for the profile read. The descriptor query runs — it must,
        it is how the decision is made — but the payload join does not."""
        token = token_for(client, EMPLOYEE)
        manager = load_person(MANAGER)

        response = client.get(f"/hr/profiles/{manager.user_id}", headers=auth(token))
        assert response.status_code == 403, response.text

        # `employee_profiles` appears only in the payload query; the descriptor selects
        # from `users` alone.
        offenders = recorded_sql.touched("employee_profiles")
        assert offenders == [], (
            "a denied profile request read the payload table:\n  " + "\n  ".join(offenders)
        )

    def test_the_denied_request_did_run_the_decision_queries(
        self, client: TestClient, recorded_sql: StatementRecorder
    ) -> None:
        """The counterpart, and the reason the two assertions above are not vacuous:
        the denied request *did* execute the queries that made the decision. It refused
        after looking at access attributes and before looking at content — which is what
        FR-015 actually asks for."""
        token = token_for(client, EMPLOYEE)
        manager = load_person(MANAGER)

        client.get(f"/hr/profiles/{manager.user_id}", headers=auth(token))

        assert "users" in recorded_sql, "the descriptor query did not run either"
        assert len(recorded_sql) > 1


class TestTheAllowedPathDoesRead:
    def test_hr_reading_compensation_executes_the_salary_query(
        self, client: TestClient, recorded_sql: StatementRecorder
    ) -> None:
        token = token_for(client, HR)
        person = load_person(EMPLOYEE)

        response = client.get(
            f"/hr/profiles/{person.user_id}/compensation", headers=auth(token)
        )
        assert response.status_code == 200, response.text
        assert SALARY in recorded_sql

    def test_a_manager_reading_a_direct_reports_profile_executes_the_payload_query(
        self, client: TestClient, recorded_sql: StatementRecorder, a_direct_report: str
    ) -> None:
        token = token_for(client, MANAGER)
        response = client.get(f"/hr/profiles/{a_direct_report}", headers=auth(token))
        assert response.status_code == 200, response.text
        assert "employee_profiles" in recorded_sql


class TestTheProfileResponseCarriesNoCompensation:
    """Belt and braces beside the query-level proof. FR-025 is satisfied by the rule,
    not by the response shape — but a profile that leaked a salary field would make the
    rule pointless, and the schema forbids it, so this pins it."""

    def test_no_profile_response_contains_a_salary_field(
        self, client: TestClient, a_direct_report: str
    ) -> None:
        for caller, subject in (
            (EMPLOYEE, str(load_person(EMPLOYEE).user_id)),
            (MANAGER, a_direct_report),
            (HR, str(load_person(EMPLOYEE).user_id)),
        ):
            token = token_for(client, caller)
            body = client.get(f"/hr/profiles/{subject}", headers=auth(token)).json()
            for field in ("salary", "salary_amount", "salary_band", "compensation"):
                assert field not in body, f"{caller} received {field} on a profile read"
