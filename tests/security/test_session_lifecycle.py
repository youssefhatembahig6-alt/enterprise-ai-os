"""Signing out actually ends access (spec 003 FR-007, SC-002a).

SC-002a is worded with unusual care: after sign-out, protected requests presenting the
previous credential are refused — "demonstrated by **replaying that exact credential**,
not by observing that the interface stopped sending it".

That distinction is the whole requirement. A self-contained credential cannot be
withdrawn: without server-side session state, "sign out" deletes the client's copy and
leaves the credential valid until it expires. A test that signs out and then makes an
unauthenticated request proves nothing — an unauthenticated request was always refused.
So every test here keeps the token and presents it again.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from eaios_core.db import create_owner_engine

from .auth_helpers import EMPLOYEE, auth, load_person, token_for

pytestmark = pytest.mark.security

PROTECTED = "/me"


class TestATokenWorksBeforeSignOut:
    """The control, and it is not optional: every test below asserts a refusal, and an
    endpoint that refused everyone would satisfy all of them."""

    def test_a_fresh_token_reaches_a_protected_endpoint(self, client: TestClient) -> None:
        token = token_for(client, EMPLOYEE)
        response = client.get(PROTECTED, headers=auth(token))
        assert response.status_code == 200, response.text

    def test_the_response_is_the_signed_in_person(self, client: TestClient) -> None:
        person = load_person(EMPLOYEE)
        token = token_for(client, EMPLOYEE)
        body = client.get(PROTECTED, headers=auth(token)).json()
        assert body["user_id"] == str(person.user_id)


class TestSignOutRevokesTheCredential:
    def test_the_exact_token_is_refused_after_sign_out(self, client: TestClient) -> None:
        token = token_for(client, EMPLOYEE)
        assert client.get(PROTECTED, headers=auth(token)).status_code == 200

        assert client.post("/auth/logout", headers=auth(token)).status_code == 204

        replayed = client.get(PROTECTED, headers=auth(token))
        assert replayed.status_code == 401, (
            "the credential still works after sign-out — without server-side session"
            " state, signing out only deletes the client's copy (FR-007)"
        )

    def test_the_token_is_still_cryptographically_valid(self, client: TestClient) -> None:
        """Signing out does not and cannot invalidate the signature. This pins *why*
        the replay above fails: not because the token became malformed, but because the
        server withdrew the session it names. An implementation that relied on token
        expiry would pass the test above only after eight hours."""
        from eaios_api.auth.tokens import verify_access_token

        token = token_for(client, EMPLOYEE)
        client.post("/auth/logout", headers=auth(token))

        claims = verify_access_token(token)  # does not raise
        assert claims.session_id is not None

    def test_the_session_row_records_the_reason(self, client: TestClient) -> None:
        from eaios_api.auth.tokens import verify_access_token

        token = token_for(client, EMPLOYEE)
        session_id = verify_access_token(token).session_id
        client.post("/auth/logout", headers=auth(token))

        with create_owner_engine().connect() as conn:
            row = conn.execute(
                text("SELECT ended_at, ended_reason FROM sessions WHERE id = :s"),
                {"s": session_id},
            ).first()
        assert row is not None, "the session row disappeared instead of being ended"
        assert row.ended_at is not None
        assert row.ended_reason == "SIGN_OUT"

    def test_signing_out_twice_refuses_the_second_attempt(self, client: TestClient) -> None:
        """The second sign-out is **401**, and that is the correct answer.

        `/auth/logout` is itself a protected endpoint, so the credential it is
        presented with has to be live. After the first sign-out it is not. Accepting a
        dead credential here — even to perform an action that is already done — would
        carve an exception into the one rule this feature exists to enforce, in the
        single place it matters most.

        It costs nothing in the interface: the portal's logout route handler clears its
        cookies regardless of what the API answers (contracts/portal-routes.md), so a
        retried sign-out leaves the browser signed out either way.
        """
        token = token_for(client, EMPLOYEE)
        assert client.post("/auth/logout", headers=auth(token)).status_code == 204
        assert client.post("/auth/logout", headers=auth(token)).status_code == 401

    def test_the_second_sign_out_does_not_write_a_second_audit_entry(
        self, client: TestClient
    ) -> None:
        """The corollary. A refused retry is not a sign-out, and recording it as one
        would make the trail say a session ended twice."""
        token = token_for(client, EMPLOYEE)
        client.post("/auth/logout", headers=auth(token))
        before = _audit_count("auth.sign_out")
        client.post("/auth/logout", headers=auth(token))
        assert _audit_count("auth.sign_out") == before

    def test_signing_out_does_not_end_anybody_elses_session(
        self, client: TestClient
    ) -> None:
        """Two sessions for the same person. Ending one must not end the other — a
        person signed in on a phone and a laptop signs out of one of them."""
        first = token_for(client, EMPLOYEE)
        second = token_for(client, EMPLOYEE)
        assert first != second, "two sign-ins produced the same token"

        client.post("/auth/logout", headers=auth(first))

        assert client.get(PROTECTED, headers=auth(first)).status_code == 401
        assert client.get(PROTECTED, headers=auth(second)).status_code == 200, (
            "signing out of one session ended the other"
        )


class TestSignOutRefusals:
    def test_signing_out_without_a_credential_is_refused(self, client: TestClient) -> None:
        assert client.post("/auth/logout").status_code == 401

    def test_signing_out_with_a_garbage_credential_is_refused(
        self, client: TestClient
    ) -> None:
        assert client.post("/auth/logout", headers=auth("not-a-token")).status_code == 401


class TestSignOutIsAudited:
    def test_signing_in_and_out_both_write_entries(self, client: TestClient) -> None:
        before_in = _audit_count("auth.sign_in")
        before_out = _audit_count("auth.sign_out")

        token = token_for(client, EMPLOYEE)
        client.post("/auth/logout", headers=auth(token))

        assert _audit_count("auth.sign_in") == before_in + 1
        assert _audit_count("auth.sign_out") == before_out + 1

    def test_no_entry_contains_the_token(self, client: TestClient) -> None:
        """FR-018. A token in the audit log is a credential in a table that many people
        can read, surviving long after the session it belonged to."""
        token = token_for(client, EMPLOYEE)
        client.post("/auth/logout", headers=auth(token))

        # The signature segment is the part that would let a leaked entry be replayed.
        signature = token.rsplit(".", 1)[-1]
        with create_owner_engine().connect() as conn:
            leaked = conn.execute(
                text(
                    "SELECT count(*) FROM audit_logs"
                    " WHERE coalesce(resource_id,'') LIKE :t OR reason LIKE :t"
                ),
                {"t": f"%{signature}%"},
            ).scalar_one()
        assert leaked == 0, "an audit entry contains part of a session token"


def _audit_count(action: str) -> int:
    with create_owner_engine().connect() as conn:
        return int(
            conn.execute(
                text("SELECT count(*) FROM audit_logs WHERE action = :a"), {"a": action}
            ).scalar_one()
        )
