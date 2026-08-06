"""Both session bounds, enforced by the server (spec 003 FR-005, SC-002).

FR-005 names two numbers — 30 minutes idle, 8 hours absolute — and says both are
required because they cover different risks: the idle timeout protects an unattended
machine, and the absolute cap limits how long a stolen credential stays useful. Without
the second, a credential taken from an active session can be kept alive indefinitely
simply by using it.

That last sentence is the test this file exists for, and it is the one an
implementation with a single moving expiry silently fails.

**Time is advanced by writing the session row's timestamps, never by sleeping.** A test
that waits eight hours is a test nobody runs, and a test that waits thirty minutes is
one somebody eventually deletes.
"""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from eaios_core.db import create_owner_engine
from eaios_core.settings import get_settings

from ..security.auth_helpers import EMPLOYEE, auth, token_for

pytestmark = pytest.mark.integration

PROTECTED = "/me"


def _session_id(token: str):  # type: ignore[no-untyped-def]
    from eaios_api.auth.tokens import verify_access_token

    return verify_access_token(token).session_id


def _age_session(session_id, **shift: float) -> None:  # type: ignore[no-untyped-def]
    """Move a session's timestamps backwards, as though time had passed.

    Writing the row rather than sleeping. The behaviour under test is the server's
    comparison against those columns, and a comparison is not made more real by having
    waited for it.
    """
    delta = dt.timedelta(**shift)
    with create_owner_engine().begin() as conn:
        conn.execute(
            text(
                "UPDATE sessions SET"
                "  issued_at = issued_at - :d,"
                "  last_seen_at = last_seen_at - :d,"
                "  absolute_expires_at = absolute_expires_at - :d"
                " WHERE id = :s"
            ),
            {"d": delta, "s": session_id},
        )


def _idle_session(session_id, **shift: float) -> None:  # type: ignore[no-untyped-def]
    """Age only `last_seen_at`, leaving the absolute cap in the future."""
    with create_owner_engine().begin() as conn:
        conn.execute(
            text("UPDATE sessions SET last_seen_at = last_seen_at - :d WHERE id = :s"),
            {"d": dt.timedelta(**shift), "s": session_id},
        )


def _row(session_id):  # type: ignore[no-untyped-def]
    with create_owner_engine().connect() as conn:
        return conn.execute(
            text(
                "SELECT ended_at, ended_reason, last_seen_at, absolute_expires_at"
                " FROM sessions WHERE id = :s"
            ),
            {"s": session_id},
        ).first()


class TestTheBoundsAreConfigured:
    def test_both_are_set_and_the_cap_is_the_longer(self) -> None:
        auth_settings = get_settings().auth
        assert auth_settings.idle_timeout_seconds == 30 * 60
        assert auth_settings.absolute_lifetime_seconds == 8 * 3600
        assert auth_settings.absolute_lifetime_seconds > auth_settings.idle_timeout_seconds


class TestAFreshSessionWorks:
    """The control. Every test below asserts a refusal."""

    def test_a_new_session_reaches_a_protected_endpoint(self, client: TestClient) -> None:
        token = token_for(client, EMPLOYEE)
        assert client.get(PROTECTED, headers=auth(token)).status_code == 200

    def test_the_absolute_cap_is_eight_hours_from_sign_in(self, client: TestClient) -> None:
        token = token_for(client, EMPLOYEE)
        row = _row(_session_id(token))
        assert row is not None
        span = row.absolute_expires_at - (
            row.last_seen_at - dt.timedelta(0)
        )
        assert abs(span.total_seconds() - 8 * 3600) < 60, span


class TestTheIdleBound:
    def test_a_session_idle_past_thirty_minutes_is_refused(self, client: TestClient) -> None:
        token = token_for(client, EMPLOYEE)
        session_id = _session_id(token)
        _idle_session(session_id, minutes=31)

        assert client.get(PROTECTED, headers=auth(token)).status_code == 401

    def test_the_row_records_why(self, client: TestClient) -> None:
        token = token_for(client, EMPLOYEE)
        session_id = _session_id(token)
        _idle_session(session_id, minutes=31)
        client.get(PROTECTED, headers=auth(token))

        row = _row(session_id)
        assert row is not None
        assert row.ended_at is not None
        assert row.ended_reason == "IDLE"

    def test_a_session_idle_for_twenty_nine_minutes_still_works(
        self, client: TestClient
    ) -> None:
        """The boundary from the other side. Without this, an implementation that
        refused *every* session would pass every idle test above."""
        token = token_for(client, EMPLOYEE)
        _idle_session(_session_id(token), minutes=29)
        assert client.get(PROTECTED, headers=auth(token)).status_code == 200

    def test_activity_renews_the_idle_bound(self, client: TestClient) -> None:
        """`last_seen_at` advances on each accepted request, which is what makes the
        idle bound a bound on *inactivity* rather than a second, shorter cap."""
        token = token_for(client, EMPLOYEE)
        session_id = _session_id(token)

        _idle_session(session_id, minutes=29)
        before = _row(session_id)
        assert client.get(PROTECTED, headers=auth(token)).status_code == 200
        after = _row(session_id)

        assert before is not None and after is not None
        assert after.last_seen_at > before.last_seen_at, "last_seen_at did not advance"

        # And now the session survives another 29 minutes of idleness.
        _idle_session(session_id, minutes=29)
        assert client.get(PROTECTED, headers=auth(token)).status_code == 200


class TestTheAbsoluteBound:
    def test_a_session_past_eight_hours_is_refused(self, client: TestClient) -> None:
        token = token_for(client, EMPLOYEE)
        session_id = _session_id(token)
        _age_session(session_id, hours=9)

        assert client.get(PROTECTED, headers=auth(token)).status_code == 401

    def test_the_row_records_why(self, client: TestClient) -> None:
        token = token_for(client, EMPLOYEE)
        session_id = _session_id(token)
        _age_session(session_id, hours=9)
        client.get(PROTECTED, headers=auth(token))

        row = _row(session_id)
        assert row is not None
        assert row.ended_reason == "ABSOLUTE"

    def test_continuous_activity_does_not_extend_the_cap(self, client: TestClient) -> None:
        """**The requirement's whole point.** A session used constantly for more than
        eight hours must still end.

        An implementation with one moving expiry passes every other test in this file
        and fails here — which is precisely why FR-005 insists on two bounds rather than
        one, and why this test exists rather than being implied by the two above.
        """
        token = token_for(client, EMPLOYEE)
        session_id = _session_id(token)

        # A full working day of steady use. Each step advances the clock by 25 minutes
        # — comfortably inside the 30-minute idle bound — and then makes a request, so
        # the session is never idle and `last_seen_at` is refreshed every time. Twenty
        # steps is over eight hours.
        #
        # The step must be shorter than the idle timeout or this stops testing what it
        # claims to: a first version used 55-minute steps, went idle on the first one,
        # and reported `IDLE` for a session it described as continuously used.
        for _ in range(21):
            _age_session(session_id, minutes=25)
            response = client.get(PROTECTED, headers=auth(token))
            if response.status_code == 401:
                break
        else:  # pragma: no cover - the loop must break
            pytest.fail("the session survived more than eight hours of continuous use")

        row = _row(session_id)
        assert row is not None
        assert row.ended_reason == "ABSOLUTE", (
            "an actively-used session ended for the wrong reason; the absolute cap is"
            f" what should have fired, got {row.ended_reason}"
        )

    def test_the_cap_is_never_pushed_forward(self, client: TestClient) -> None:
        """Directly: `absolute_expires_at` is set once and does not move. This is the
        column an implementation would quietly start updating alongside
        `last_seen_at`."""
        token = token_for(client, EMPLOYEE)
        session_id = _session_id(token)

        original = _row(session_id)
        assert original is not None
        for _ in range(3):
            assert client.get(PROTECTED, headers=auth(token)).status_code == 200
        after = _row(session_id)

        assert after is not None
        assert after.absolute_expires_at == original.absolute_expires_at


class TestExpiryIsEnforcedByTheServer:
    def test_an_ended_session_cannot_be_revived(self, client: TestClient) -> None:
        """Once ended, it stays ended. An implementation that re-checked the bounds and
        found them satisfied again — because the row was touched — would let an expired
        credential come back."""
        token = token_for(client, EMPLOYEE)
        session_id = _session_id(token)
        _idle_session(session_id, minutes=31)

        assert client.get(PROTECTED, headers=auth(token)).status_code == 401
        # Even with the clock apparently back to normal, the session stays ended.
        with create_owner_engine().begin() as conn:
            conn.execute(
                text("UPDATE sessions SET last_seen_at = now() WHERE id = :s"),
                {"s": session_id},
            )
        assert client.get(PROTECTED, headers=auth(token)).status_code == 401

    def test_expiry_is_audited(self, client: TestClient) -> None:
        before = _audit_count("auth.session_expired")
        token = token_for(client, EMPLOYEE)
        _idle_session(_session_id(token), minutes=31)
        client.get(PROTECTED, headers=auth(token))
        assert _audit_count("auth.session_expired") > before


def _audit_count(action: str) -> int:
    with create_owner_engine().connect() as conn:
        return int(
            conn.execute(
                text("SELECT count(*) FROM audit_logs WHERE action = :a"), {"a": action}
            ).scalar_one()
        )
