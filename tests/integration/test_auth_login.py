"""User Story 1: an employee signs in, is recognised, and signs out (spec 003 FR-001, FR-006).

The vertical slice's happy path. The security suites cover what must *not* happen —
this covers what must, using **seeded** people rather than invented ones, because a
sign-in that only works for a fixture is a sign-in that works for nobody.

Both tenants are exercised. Delta Retail exists so cross-tenant isolation can be
demonstrated by an authenticated caller rather than asserted structurally, and that
only means anything if a Delta Retail user can actually sign in.
"""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from ..security.auth_helpers import (
    DELTA_EMPLOYEE,
    DEMO_PASSWORD,
    EMPLOYEE,
    HR,
    MANAGER,
    auth,
    load_person,
    sign_in,
)

pytestmark = pytest.mark.integration


class TestASeededEmployeeCanSignIn:
    def test_valid_credentials_are_accepted(self, client: TestClient) -> None:
        person = load_person(EMPLOYEE)
        response = sign_in(client, person.email)
        assert response.status_code == 200, response.text

    def test_the_response_carries_a_usable_token(self, client: TestClient) -> None:
        person = load_person(EMPLOYEE)
        body = sign_in(client, person.email).json()

        assert body["token_type"] == "bearer"
        assert body["access_token"]
        # The token works, which is the only property worth asserting about it here.
        assert client.get("/me", headers=auth(body["access_token"])).status_code == 200

    def test_the_expiry_is_the_eight_hour_cap(self, client: TestClient) -> None:
        """FR-005's absolute bound, surfaced so the portal can show it. Not the idle
        bound — that moves, and an interface must not try to track it."""
        person = load_person(EMPLOYEE)
        body = sign_in(client, person.email).json()

        expires = dt.datetime.fromisoformat(body["expires_at"])
        remaining = (expires - dt.datetime.now(tz=dt.UTC)).total_seconds()
        assert 8 * 3600 - 120 < remaining <= 8 * 3600, remaining

    def test_the_response_carries_no_credential(self, client: TestClient) -> None:
        person = load_person(EMPLOYEE)
        body = sign_in(client, person.email).text
        assert DEMO_PASSWORD not in body
        assert "$argon2" not in body


class TestBothTenantsAuthenticate:
    """FR-001 says "both tenants". Delta Retail signing in is the precondition for
    every cross-tenant test — an isolation suite where the second tenant cannot get a
    session proves nothing."""

    @pytest.mark.parametrize("persona", [EMPLOYEE, MANAGER, HR, DELTA_EMPLOYEE])
    def test_each_seeded_persona_can_sign_in(
        self, client: TestClient, persona: str
    ) -> None:
        person = load_person(persona)
        response = sign_in(client, person.email)
        assert response.status_code == 200, f"{persona} ({person.email}): {response.text}"

    def test_each_caller_is_recognised_as_themselves(self, client: TestClient) -> None:
        for persona in (EMPLOYEE, DELTA_EMPLOYEE):
            person = load_person(persona)
            token = sign_in(client, person.email).json()["access_token"]
            body = client.get("/me", headers=auth(token)).json()
            assert body["user_id"] == str(person.user_id), persona
            assert body["email"] == person.email

    def test_the_two_tenants_are_different_companies(self, client: TestClient) -> None:
        """Guards the parametrised test above from passing on a dataset where both
        personas happen to be in the same company."""
        niletech = load_person(EMPLOYEE)
        delta = load_person(DELTA_EMPLOYEE)
        assert niletech.company_id != delta.company_id


class TestTheCurrentUserResponse:
    def test_it_names_the_person_and_their_placement(self, client: TestClient) -> None:
        person = load_person(EMPLOYEE)
        token = sign_in(client, person.email).json()["access_token"]
        body = client.get("/me", headers=auth(token)).json()

        assert body["full_name"] == person.full_name
        assert body["company_name"], "no company name to greet them with"
        assert body["department"], "no department"
        assert body["office"], "no office"

    def test_it_carries_permission_codes_for_navigation(self, client: TestClient) -> None:
        """FR-028's input. Role-aware navigation is built from these, never from role
        names — so the portal needs them present and non-empty for an ordinary user."""
        person = load_person(EMPLOYEE)
        token = sign_in(client, person.email).json()["access_token"]
        body = client.get("/me", headers=auth(token)).json()

        assert body["permissions"], "an employee holds no permission codes at all"
        assert "hr:read_self" in body["permissions"]

    def test_it_carries_role_names_for_display_only(self, client: TestClient) -> None:
        person = load_person(MANAGER)
        token = sign_in(client, person.email).json()["access_token"]
        body = client.get("/me", headers=auth(token)).json()
        assert body["roles"], "no role names to display"


class TestSigningOut:
    def test_sign_out_succeeds_and_ends_access(self, client: TestClient) -> None:
        """The full arc of the story: in, recognised, out, refused."""
        person = load_person(EMPLOYEE)
        token = sign_in(client, person.email).json()["access_token"]

        assert client.get("/me", headers=auth(token)).status_code == 200
        assert client.post("/auth/logout", headers=auth(token)).status_code == 204
        assert client.get("/me", headers=auth(token)).status_code == 401


class TestTheSessionEndpoint:
    def test_it_reports_both_bounds(self, client: TestClient) -> None:
        """The portal needs both to tell "expired" from "never signed in", and to say
        which of the two bounds ended a session (FR-027, FR-029)."""
        person = load_person(EMPLOYEE)
        token = sign_in(client, person.email).json()["access_token"]

        body = client.get("/auth/session", headers=auth(token)).json()
        issued = dt.datetime.fromisoformat(body["issued_at"])
        absolute = dt.datetime.fromisoformat(body["absolute_expires_at"])
        idle = dt.datetime.fromisoformat(body["idle_expires_at"])

        assert absolute > idle, "the absolute cap must be the later of the two bounds"
        assert abs((absolute - issued).total_seconds() - 8 * 3600) < 120
        assert 0 < (idle - dt.datetime.now(tz=dt.UTC)).total_seconds() <= 30 * 60

    def test_it_is_refused_without_a_session(self, client: TestClient) -> None:
        assert client.get("/auth/session").status_code == 401


class TestThePublicSurfaceStaysAnonymous:
    """FR-031. The sign-in surface arriving must not change what an anonymous visitor
    can reach — asserted here rather than left to feature 002's suite, because this is
    the file that would notice if `/auth/login` had been mounted under `/public`."""

    @pytest.mark.parametrize(
        "path", ["/health/live", "/health/ready", "/dataset/manifest", "/public/company"]
    )
    def test_it_needs_no_credential(self, client: TestClient, path: str) -> None:
        assert client.get(path).status_code == 200, path

    def test_sign_in_itself_needs_no_credential(self, client: TestClient) -> None:
        """The one authenticated-surface endpoint that must stay open, or nobody could
        ever obtain a session."""
        assert sign_in(client, "nobody@niletech.example").status_code == 401
