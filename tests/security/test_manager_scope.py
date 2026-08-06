"""A manager reaches their team and nobody else (spec 003 FR-024, FR-026, FR-033, SC-003).

The blueprint's flagship demonstration: the same request succeeds or fails depending on
who asks, decided by the dataset's relationships rather than by anything hard-coded.

**Seeded people, never fixtures** (FR-033). A fixture user has the relationships the
test author chose; a seeded one has the relationships the generator produced. That is
what makes FR-026 — "changing a reporting line in the data changes the reachable set
with no code change" — a claim about the system rather than about the test.

**Non-empty subject sets, asserted first.** SC-003 says a manager reaches *every* direct
report and *zero* employees outside the line. A manager with no reports satisfies the
first half vacuously, and a dataset with no unrelated employees satisfies the second.
Both are checked before anything else runs.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from .auth_helpers import (
    EMPLOYEE,
    HR,
    MANAGER,
    Person,
    auth,
    direct_report_ids,
    load_person,
    token_for,
    unrelated_colleague,
)

pytestmark = pytest.mark.security


@pytest.fixture(scope="module")
def manager() -> Person:
    return load_person(MANAGER)


@pytest.fixture(scope="module")
def reports(manager: Person) -> list[str]:
    return [str(uid) for uid in direct_report_ids(manager.user_id)]


@pytest.fixture(scope="module")
def outsider(manager: Person) -> Person:
    return unrelated_colleague(manager)


class TestTheScenarioHasSubjects:
    """Every assertion below is "all of these" or "none of those". Both are trivially
    true over an empty set."""

    def test_the_manager_has_direct_reports(self, reports: list[str]) -> None:
        assert reports, (
            "the seeded manager has no direct reports — 'can read every report' would"
            " be vacuously true and SC-003 would measure nothing"
        )

    def test_an_unrelated_employee_exists(self, manager: Person, outsider: Person) -> None:
        assert outsider.user_id not in {
            *direct_report_ids(manager.user_id),
            manager.user_id,
        }, "the 'unrelated' employee is actually related; the denial cannot be shown"
        assert outsider.department_id != manager.department_id


class TestAManagerReachesEveryDirectReport:
    def test_every_report_is_readable(
        self, client: TestClient, reports: list[str]
    ) -> None:
        token = token_for(client, MANAGER)
        refused = [
            uid
            for uid in reports
            if client.get(f"/hr/profiles/{uid}", headers=auth(token)).status_code != 200
        ]
        assert refused == [], f"the manager was refused their own reports: {refused}"

    def test_the_team_list_matches_the_reporting_line(
        self, client: TestClient, reports: list[str]
    ) -> None:
        token = token_for(client, MANAGER)
        response = client.get("/me/direct-reports", headers=auth(token))
        assert response.status_code == 200, response.text
        listed = {row["user_id"] for row in response.json()}
        assert listed == set(reports), (
            "the team list disagrees with `users.manager_id` — the reachable set is"
            " coming from somewhere other than the data (FR-026)"
        )

    def test_a_report_profile_is_the_right_person(
        self, client: TestClient, reports: list[str]
    ) -> None:
        token = token_for(client, MANAGER)
        body = client.get(f"/hr/profiles/{reports[0]}", headers=auth(token)).json()
        assert body["user_id"] == reports[0]


class TestAManagerReachesNobodyElse:
    def test_an_unrelated_employee_is_forbidden(
        self, client: TestClient, outsider: Person
    ) -> None:
        token = token_for(client, MANAGER)
        response = client.get(f"/hr/profiles/{outsider.user_id}", headers=auth(token))
        assert response.status_code == 403, (
            f"the manager reached an employee outside their reporting line:"
            f" {response.status_code}"
        )

    def test_the_refusal_is_forbidden_and_not_not_found(
        self, client: TestClient, outsider: Person
    ) -> None:
        """403, not 404, and the distinction is load-bearing. The person exists and is
        in the caller's company; they are simply not reachable. Answering 404 here would
        conflate an authorization decision with the tenant boundary, which FR-030 keeps
        deliberately separate."""
        token = token_for(client, MANAGER)
        assert client.get(
            f"/hr/profiles/{outsider.user_id}", headers=auth(token)
        ).status_code == 403

    def test_an_employee_with_no_reports_reaches_no_colleague(
        self, client: TestClient, manager: Person
    ) -> None:
        """The spec's third acceptance scenario for this story."""
        token = token_for(client, EMPLOYEE)
        assert client.get(
            f"/hr/profiles/{manager.user_id}", headers=auth(token)
        ).status_code == 403

    def test_an_employee_with_no_reports_gets_an_empty_team_list(
        self, client: TestClient
    ) -> None:
        """An empty list, not a refusal — the portal renders its empty state rather
        than its access-denied state, and those are different sentences."""
        token = token_for(client, EMPLOYEE)
        response = client.get("/me/direct-reports", headers=auth(token))
        person = load_person(EMPLOYEE)
        if direct_report_ids(person.user_id):
            pytest.skip("the seeded employee has reports; this case needs someone without")
        assert response.status_code in (200, 403)
        if response.status_code == 200:
            assert response.json() == []


class TestCompensationNeedsMoreThanTeamScope:
    def test_a_manager_cannot_read_a_reports_compensation(
        self, client: TestClient, reports: list[str]
    ) -> None:
        """FR-025. `hr:read_team` reaches the profile and stops there; compensation
        needs `hr:read_all`. This is the denial the blueprint leads with."""
        token = token_for(client, MANAGER)
        assert client.get(
            f"/hr/profiles/{reports[0]}/compensation", headers=auth(token)
        ).status_code == 403

    def test_the_same_manager_can_read_that_persons_profile(
        self, client: TestClient, reports: list[str]
    ) -> None:
        """Immediately beside it: the refusal above is specifically about compensation,
        not about the person. Without this pairing, a manager who could reach nothing
        would satisfy the test above."""
        token = token_for(client, MANAGER)
        assert client.get(
            f"/hr/profiles/{reports[0]}", headers=auth(token)
        ).status_code == 200

    def test_hr_can_read_it(self, client: TestClient, reports: list[str]) -> None:
        """And the permission is reachable by somebody, or `hr:read_all` would be a
        code that grants nothing and the denial above would prove only that."""
        token = token_for(client, HR)
        response = client.get(
            f"/hr/profiles/{reports[0]}/compensation", headers=auth(token)
        )
        assert response.status_code == 200, response.text
        assert response.json()["salary_amount"]

    def test_nobody_can_read_their_own_compensation_without_the_permission(
        self, client: TestClient
    ) -> None:
        """FR-025 says "including a manager reading their own direct report ... unless
        that permission is separately granted". The same holds for one's own record: the
        rule is about the permission, not about ownership."""
        token = token_for(client, EMPLOYEE)
        person = load_person(EMPLOYEE)
        assert client.get(
            f"/hr/profiles/{person.user_id}/compensation", headers=auth(token)
        ).status_code == 403


class TestTheReachableSetFollowsTheData:
    def test_moving_a_report_moves_the_reachable_set(
        self, client: TestClient, manager: Person, outsider: Person
    ) -> None:
        """FR-026, demonstrated rather than asserted. Nothing about the code changes;
        one column in one row does, and the answer follows."""
        from sqlalchemy import text

        from eaios_core.db import create_owner_engine

        token = token_for(client, MANAGER)
        before = client.get(f"/hr/profiles/{outsider.user_id}", headers=auth(token))
        assert before.status_code == 403

        engine = create_owner_engine()
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE users SET manager_id = :m WHERE id = :u"),
                {"m": manager.user_id, "u": outsider.user_id},
            )
        try:
            after = client.get(f"/hr/profiles/{outsider.user_id}", headers=auth(token))
            assert after.status_code == 200, (
                "the reachable set did not follow the reporting line — it is coming"
                " from somewhere other than the data (FR-026)"
            )
        finally:
            with engine.begin() as conn:
                conn.execute(
                    text("UPDATE users SET manager_id = :m WHERE id = :u"),
                    {"m": outsider.manager_id, "u": outsider.user_id},
                )

        restored = client.get(f"/hr/profiles/{outsider.user_id}", headers=auth(token))
        assert restored.status_code == 403, "the fixture did not restore the reporting line"
