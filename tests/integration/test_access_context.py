"""The access context is built from current records (spec 003 FR-004, FR-008, FR-011).

FR-011 exists so what the server believes about a caller is *observable* rather than
inferred from which requests happened to succeed. That makes this file unusually
direct: it compares the endpoint's answer against the database, field by field.

FR-004 is the harder claim — attributes are re-read **per request**, not carried in the
credential. The two tests that matter change something in the database mid-session and
assert the *next* request sees it, each with a control asserting the previous request
did not. Without the control, "access was refused after deactivation" is satisfied by a
session that was never working.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from eaios_core.db import create_owner_engine

from ..security.auth_helpers import (
    EMPLOYEE,
    MANAGER,
    auth,
    direct_report_ids,
    load_person,
    token_for,
)

pytestmark = pytest.mark.integration


def _context(client: TestClient, token: str) -> dict[str, object]:
    response = client.get("/me/access-context", headers=auth(token))
    assert response.status_code == 200, response.text
    return dict(response.json())


class TestItDescribesTheSeededPerson:
    def test_every_identity_field_matches_the_database(self, client: TestClient) -> None:
        person = load_person(EMPLOYEE)
        body = _context(client, token_for(client, EMPLOYEE))

        assert body["user_id"] == str(person.user_id)
        assert body["company_id"] == str(person.company_id)
        assert body["department_id"] == str(person.department_id)
        assert body["manager_id"] == (str(person.manager_id) if person.manager_id else None)

    def test_office_country_and_employment_type_are_present(
        self, client: TestClient
    ) -> None:
        person = load_person(EMPLOYEE)
        body = _context(client, token_for(client, EMPLOYEE))

        with create_owner_engine().connect() as conn:
            row = conn.execute(
                text(
                    "SELECT office_id, country, employment_type FROM users WHERE id = :u"
                ),
                {"u": person.user_id},
            ).one()

        assert body["office_id"] == str(row.office_id)
        assert body["country"] == row.country
        assert body["employment_type"] == row.employment_type

    def test_both_manager_directions_are_carried(self, client: TestClient) -> None:
        """FR-008 names both. They answer different questions — `manager_id` is "whose
        team am I on", `direct_report_ids` is "whose records may I read" — and only the
        second decides anything in this feature."""
        person = load_person(MANAGER)
        body = _context(client, token_for(client, MANAGER))

        expected = {str(uid) for uid in direct_report_ids(person.user_id)}
        assert expected, "the seeded manager has no direct reports; the field is untested"
        assert set(body["direct_report_ids"]) == expected  # type: ignore[arg-type]

    def test_permissions_come_from_roles(self, client: TestClient) -> None:
        person = load_person(EMPLOYEE)
        body = _context(client, token_for(client, EMPLOYEE))

        with create_owner_engine().connect() as conn:
            expected = {
                row.code
                for row in conn.execute(
                    text(
                        "SELECT DISTINCT p.code FROM permissions p"
                        " JOIN role_permissions rp ON rp.permission_id = p.id"
                        " JOIN user_roles ur ON ur.role_id = rp.role_id"
                        " WHERE ur.user_id = :u"
                    ),
                    {"u": person.user_id},
                )
            }

        assert expected, "the seeded employee holds no permissions; the field is untested"
        assert set(body["permissions"]) == expected  # type: ignore[arg-type]

    def test_it_carries_no_credential_token_or_session(self, client: TestClient) -> None:
        """FR-011 says what the context contains; this asserts what it does not. An
        endpoint whose purpose is showing internals is the one most likely to show one
        too many."""
        body = _context(client, token_for(client, EMPLOYEE))
        for forbidden in ("password", "password_hash", "token", "access_token", "session_id"):
            assert forbidden not in body, f"the access context exposes {forbidden}"


class TestAttributesAreRereadPerRequest:
    """FR-004. The expensive property, and the one the whole design rests on."""

    def test_a_deactivated_user_loses_access_on_the_next_request(
        self, client: TestClient
    ) -> None:
        person = load_person(EMPLOYEE)
        token = token_for(client, EMPLOYEE)

        # Control: it worked a moment ago, with this exact credential.
        assert client.get("/me", headers=auth(token)).status_code == 200

        with _deactivated(person.user_id):
            refused = client.get("/me", headers=auth(token))
            assert refused.status_code == 401, (
                "a deactivated user kept access — active status is being read from the"
                " credential rather than from current records (FR-004)"
            )

        # And access returns when they do, without a new sign-in.
        assert client.get("/me", headers=auth(token)).status_code == 200

    def test_a_role_change_takes_effect_without_a_new_token(
        self, client: TestClient
    ) -> None:
        """The other half of FR-004, and the one the specification calls out: a
        permission change must not have to wait for a stale token to expire."""
        person = load_person(EMPLOYEE)
        token = token_for(client, EMPLOYEE)

        before = set(_context(client, token)["permissions"])  # type: ignore[arg-type]
        assert "hr:read_all" not in before, "the fixture already holds the widened code"

        with _granted_role(person.user_id, person.company_id, "HR"):
            after = set(_context(client, token)["permissions"])  # type: ignore[arg-type]
            assert "hr:read_all" in after, (
                "a role granted mid-session did not reach the access context"
            )

        restored = set(_context(client, token)["permissions"])  # type: ignore[arg-type]
        assert restored == before


class TestTheContextIsImmutable:
    def test_repeated_reads_agree(self, client: TestClient) -> None:
        """FR-009 is about the object within one request, which a black-box test cannot
        reach directly. What it *can* check is the observable consequence: two reads in
        a row describe the same caller, so nothing downstream is mutating it."""
        token = token_for(client, EMPLOYEE)
        assert _context(client, token) == _context(client, token)

    def test_the_permission_fingerprint_follows_the_permissions(
        self, client: TestClient
    ) -> None:
        person = load_person(EMPLOYEE)
        token = token_for(client, EMPLOYEE)

        before = _context(client, token)["permission_fingerprint"]
        with _granted_role(person.user_id, person.company_id, "HR"):
            widened = _context(client, token)["permission_fingerprint"]
        after = _context(client, token)["permission_fingerprint"]

        assert widened != before, (
            "the fingerprint did not change when the permission set did — a cache keyed"
            " on it would serve an HR-scoped answer to an employee (Principle III)"
        )
        assert after == before


@pytest.fixture(autouse=True)
def _no_leftover_grants() -> Iterator[None]:
    """A grant left behind would widen the fixture user for every later test in the
    suite — and the failures would appear somewhere else entirely."""
    yield
    person = load_person(EMPLOYEE)
    with create_owner_engine().begin() as conn:
        conn.execute(
            text(
                "DELETE FROM user_roles WHERE user_id = :u AND role_id IN"
                " (SELECT id FROM roles WHERE name = 'HR' AND company_id = :c)"
            ),
            {"u": person.user_id, "c": person.company_id},
        )
        conn.execute(
            text("UPDATE users SET is_active = true WHERE id = :u"), {"u": person.user_id}
        )


class _deactivated:  # noqa: N801 - reads as a statement at the call site
    def __init__(self, user_id: object) -> None:
        self.user_id = user_id

    def __enter__(self) -> None:
        with create_owner_engine().begin() as conn:
            conn.execute(
                text("UPDATE users SET is_active = false WHERE id = :u"),
                {"u": self.user_id},
            )

    def __exit__(self, *exc: object) -> None:
        with create_owner_engine().begin() as conn:
            conn.execute(
                text("UPDATE users SET is_active = true WHERE id = :u"),
                {"u": self.user_id},
            )


class _granted_role:  # noqa: N801 - reads as a statement at the call site
    def __init__(self, user_id: object, company_id: object, role_name: str) -> None:
        self.user_id = user_id
        self.company_id = company_id
        self.role_name = role_name

    def __enter__(self) -> None:
        with create_owner_engine().begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO user_roles"
                    " (id, company_id, user_id, role_id, is_primary, created_at, updated_at)"
                    " SELECT gen_random_uuid(), :c, :u, r.id, false, now(), now()"
                    " FROM roles r WHERE r.name = :n AND r.company_id = :c"
                    " ON CONFLICT (user_id, role_id) DO NOTHING"
                ),
                {"c": self.company_id, "u": self.user_id, "n": self.role_name},
            )

    def __exit__(self, *exc: object) -> None:
        with create_owner_engine().begin() as conn:
            conn.execute(
                text(
                    "DELETE FROM user_roles WHERE user_id = :u AND role_id IN"
                    " (SELECT id FROM roles WHERE name = :n AND company_id = :c)"
                ),
                {"u": self.user_id, "n": self.role_name, "c": self.company_id},
            )
