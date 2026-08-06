"""The audit trail says what happened, and nothing it must not (FR-017, FR-017a/b, FR-018, SC-006).

Two rules with opposite failure modes, which is why they are tested together:

* **every denial is recorded** — a missing entry means an attack left no trace;
* **an ordinary self-read is not** — and an *absence* is a dangerous thing to assert,
  because a broken audit writer and a correctly-quiet one look identical from outside.

So every test that asserts nothing was written sits beside one asserting something was,
in the same run. And every count is a **delta**: `audit_logs` is never empty — the seed
writes to it — so "the table has rows" proves nothing at all.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from eaios_core.db import create_owner_engine

from .auth_helpers import (
    EMPLOYEE,
    HR,
    MANAGER,
    auth,
    direct_report_ids,
    load_person,
    token_for,
    unrelated_colleague,
)

pytestmark = pytest.mark.security


@dataclass(frozen=True, slots=True)
class Entry:
    action: str
    actor_user_id: object
    company_id: object
    resource_type: str
    resource_id: str | None
    decision: str
    reason: str


class _Trail:
    """Entries written between construction and `since()`."""

    def __init__(self) -> None:
        with create_owner_engine().connect() as conn:
            self.mark = int(
                conn.execute(text("SELECT count(*) FROM audit_logs")).scalar_one()
            )

    def since(self, action: str | None = None) -> list[Entry]:
        sql = (
            "SELECT action, actor_user_id, company_id, resource_type, resource_id,"
            "       decision, reason"
            " FROM audit_logs ORDER BY created_at DESC, action LIMIT 200"
        )
        with create_owner_engine().connect() as conn:
            total = int(conn.execute(text("SELECT count(*) FROM audit_logs")).scalar_one())
            rows = conn.execute(text(sql)).all()
        fresh = rows[: max(0, total - self.mark)]
        entries = [Entry(*row) for row in fresh]
        if action is not None:
            entries = [e for e in entries if e.action == action]
        return entries


@pytest.fixture
def trail() -> Iterator[_Trail]:
    yield _Trail()


class TestEveryDenialIsRecorded:
    def test_a_forbidden_profile_read_writes_one_entry(
        self, client: TestClient, trail: _Trail
    ) -> None:
        token = token_for(client, EMPLOYEE)
        manager = load_person(MANAGER)

        response = client.get(f"/hr/profiles/{manager.user_id}", headers=auth(token))
        assert response.status_code == 403

        denials = trail.since("authz.denied")
        assert len(denials) == 1, f"expected exactly one denial entry, got {len(denials)}"

    def test_the_entry_carries_everything_principle_x_requires(
        self, client: TestClient, trail: _Trail
    ) -> None:
        person = load_person(EMPLOYEE)
        token = token_for(client, EMPLOYEE)
        manager = load_person(MANAGER)

        client.get(f"/hr/profiles/{manager.user_id}", headers=auth(token))
        entry = trail.since("authz.denied")[0]

        assert entry.actor_user_id == person.user_id, "no actor"
        assert entry.company_id == person.company_id, "no tenant"
        assert entry.resource_type == "HR_PROFILE", entry.resource_type
        assert entry.resource_id == str(manager.user_id), "no resource identifier"
        assert entry.decision == "DENY"
        assert entry.reason, "no reason"

    def test_the_reason_names_the_rule_that_fired(
        self, client: TestClient, trail: _Trail
    ) -> None:
        """A reason of "denied" would satisfy "carries a reason" and tell an auditor
        nothing. The stable reason codes exist so the trail distinguishes "no such
        permission" from "not your report"."""
        token = token_for(client, EMPLOYEE)
        manager = load_person(MANAGER)
        client.get(f"/hr/profiles/{manager.user_id}", headers=auth(token))

        reason = trail.since("authz.denied")[0].reason
        assert "ATTRIBUTE_MISMATCH" in reason or "NOT_IN_REPORTING_LINE" in reason, reason
        assert "layer" in reason, f"the reason does not say which layer decided: {reason}"

    def test_a_compensation_denial_is_recorded(
        self, client: TestClient, trail: _Trail
    ) -> None:
        manager = load_person(MANAGER)
        reports = direct_report_ids(manager.user_id)
        if not reports:
            pytest.skip("no direct reports seeded")

        token = token_for(client, MANAGER)
        client.get(f"/hr/profiles/{reports[0]}/compensation", headers=auth(token))

        denials = trail.since("authz.denied")
        assert len(denials) == 1
        assert denials[0].resource_type == "HR_COMPENSATION"


class TestOnlySensitiveAllowsAreRecorded:
    """The pairs. Each absence is asserted beside a presence, in the same run."""

    def test_reading_your_own_profile_writes_nothing(
        self, client: TestClient, trail: _Trail
    ) -> None:
        token = token_for(client, EMPLOYEE)
        response = client.get("/me/hr-profile", headers=auth(token))
        assert response.status_code == 200, response.text

        allows = trail.since("authz.allowed")
        assert allows == [], (
            "an ordinary self-read wrote an audit entry — FR-017a excludes it precisely"
            f" so one page view does not write dozens of rows: {allows}"
        )

    def test_reading_someone_elses_profile_writes_exactly_one(
        self, client: TestClient, trail: _Trail
    ) -> None:
        """The presence half of the pair above. Together they show the rule
        distinguishes cases rather than the writer being broken."""
        manager = load_person(MANAGER)
        reports = direct_report_ids(manager.user_id)
        if not reports:
            pytest.skip("no direct reports seeded")

        token = token_for(client, MANAGER)
        response = client.get(f"/hr/profiles/{reports[0]}", headers=auth(token))
        assert response.status_code == 200, response.text

        allows = trail.since("authz.allowed")
        assert len(allows) == 1, f"expected one allow entry, got {len(allows)}"
        assert allows[0].resource_type == "HR_PROFILE"

    def test_reading_your_own_compensation_is_recorded(
        self, client: TestClient, trail: _Trail
    ) -> None:
        """FR-017a clause 2: compensation "of any kind, including the requester's own".
        The clause that does not follow from ownership, and the one a natural
        implementation gets wrong."""
        person = load_person(HR)
        token = token_for(client, HR)

        response = client.get(
            f"/hr/profiles/{person.user_id}/compensation", headers=auth(token)
        )
        assert response.status_code == 200, response.text

        allows = trail.since("authz.allowed")
        assert len(allows) == 1, "an own-compensation read was not audited"
        assert allows[0].resource_type == "HR_COMPENSATION"

    def test_reading_your_own_access_context_writes_nothing(
        self, client: TestClient, trail: _Trail
    ) -> None:
        token = token_for(client, EMPLOYEE)
        client.get("/me/access-context", headers=auth(token))
        assert trail.since("authz.allowed") == []


class TestNoEntryCarriesACredential:
    def test_no_entry_contains_a_password_or_hash(self, client: TestClient) -> None:
        """FR-018. Searched across the whole table rather than the recent window: an
        entry written months ago is just as readable to anyone holding `audit:read`."""
        token = token_for(client, EMPLOYEE)
        client.get("/me", headers=auth(token))

        with create_owner_engine().connect() as conn:
            leaked = int(
                conn.execute(
                    text(
                        "SELECT count(*) FROM audit_logs"
                        " WHERE coalesce(resource_id,'') LIKE '%$argon2%'"
                        "    OR reason LIKE '%$argon2%'"
                        "    OR coalesce(resource_id,'') LIKE '%eaios-demo%'"
                        "    OR reason LIKE '%eaios-demo%'"
                    )
                ).scalar_one()
            )
        assert leaked == 0, "an audit entry contains a credential or a password hash"

    def test_no_entry_contains_a_json_web_token(self, client: TestClient) -> None:
        with create_owner_engine().connect() as conn:
            leaked = int(
                conn.execute(
                    text(
                        "SELECT count(*) FROM audit_logs"
                        " WHERE coalesce(resource_id,'') LIKE 'eyJ%'"
                        "    OR reason LIKE '%eyJ%'"
                    )
                ).scalar_one()
            )
        assert leaked == 0, "an audit entry contains a token"


class TestCrossTenantAttribution:
    def test_the_entry_is_written_under_the_actors_company(
        self, client: TestClient, trail: _Trail
    ) -> None:
        """Research F3. Writing a NileTech action into Delta Retail's trail would itself
        be a cross-tenant leak — and FR-030 makes it coherent: at layer 1 the other
        tenant's resource is absent, so there is nothing of theirs to attribute."""
        from .auth_helpers import DELTA_EMPLOYEE

        delta = load_person(DELTA_EMPLOYEE)
        niletech = load_person(EMPLOYEE)
        token = token_for(client, DELTA_EMPLOYEE)

        client.get(f"/hr/profiles/{niletech.user_id}", headers=auth(token))

        for entry in trail.since():
            assert entry.company_id != niletech.company_id, (
                "an entry for a Delta Retail action was written under NileTech"
            )
            if entry.actor_user_id is not None:
                assert entry.company_id == delta.company_id


class TestTheTrailHelperWorks:
    """Without this, a `since()` that always returned an empty list would satisfy every
    "wrote nothing" assertion above."""

    def test_it_sees_a_new_entry(self, client: TestClient, trail: _Trail) -> None:
        token = token_for(client, EMPLOYEE)
        manager = load_person(MANAGER)
        client.get(f"/hr/profiles/{manager.user_id}", headers=auth(token))
        assert trail.since(), "the trail helper reported no new entries after a denial"

    def test_it_ignores_older_entries(self, client: TestClient) -> None:
        token = token_for(client, EMPLOYEE)
        manager = load_person(MANAGER)
        client.get(f"/hr/profiles/{manager.user_id}", headers=auth(token))
        # Marked *after* the denial above, so it must see none of it.
        later = _Trail()
        assert later.since() == []


class TestUnrelatedDenialsAreAlsoRecorded:
    def test_a_cross_department_denial_appears(
        self, client: TestClient, trail: _Trail
    ) -> None:
        manager = load_person(MANAGER)
        outsider = unrelated_colleague(manager)
        token = token_for(client, MANAGER)

        client.get(f"/hr/profiles/{outsider.user_id}", headers=auth(token))
        assert len(trail.since("authz.denied")) == 1
