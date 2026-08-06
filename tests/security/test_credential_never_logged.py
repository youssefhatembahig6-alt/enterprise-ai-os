"""No credential reaches a log, a response, or the audit trail (spec 003 FR-018, FR-002).

FR-018 forbids audit entries containing credentials, session tokens, or any value from
which either could be reconstructed. The same reasoning applies to logs, which are read
far more casually than the database and are shipped to places nobody reviews.

The hard part is that this is an assertion about *absence*, and absence is the easiest
thing in the world to prove by accident. A test that captures no log records at all
finds no passwords in them. So the first class here proves the capture works before any
other class relies on it.

**What counts as a leak.** Not just the plaintext password: the Argon2 encoding, the
token, and the token's *signature segment* all qualify. The signature is the part that
would let a leaked entry be replayed, so a log line carrying only that is a full
compromise of the session it names.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from eaios_core.db import create_owner_engine

from .auth_helpers import DEMO_PASSWORD, EMPLOYEE, auth, load_person, sign_in, token_for

pytestmark = pytest.mark.security


class _Capture(logging.Handler):
    """Everything logged while attached, rendered as it would be written."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.lines.append(self.format(record))
        except Exception:  # pragma: no cover - a broken record is still a record
            self.lines.append(repr(record.__dict__))

    @property
    def blob(self) -> str:
        return "\n".join(self.lines)


@pytest.fixture
def captured_logs() -> Iterator[_Capture]:
    """Attach to the root logger, so nothing escapes by using its own logger name."""
    handler = _Capture()
    root = logging.getLogger()
    previous = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        yield handler
    finally:
        root.removeHandler(handler)
        root.setLevel(previous)


class TestTheCaptureWorks:
    """Without this, every "the password is not in the logs" assertion below is
    satisfied by a handler that captured nothing."""

    def test_it_records_a_log_line(self, captured_logs: _Capture) -> None:
        logging.getLogger("eaios.test").warning("a marker line")
        assert "a marker line" in captured_logs.blob

    def test_it_would_find_the_password_if_it_were_logged(
        self, captured_logs: _Capture
    ) -> None:
        """The direct control for the search term. If `DEMO_PASSWORD` could not be
        found even when deliberately logged, none of the assertions below mean
        anything."""
        logging.getLogger("eaios.test").warning("deliberate: %s", DEMO_PASSWORD)
        assert DEMO_PASSWORD in captured_logs.blob

    def test_a_request_produces_log_output(
        self, client: TestClient, captured_logs: _Capture
    ) -> None:
        token = token_for(client, EMPLOYEE)
        client.get("/me", headers=auth(token))
        assert captured_logs.lines, "a full request cycle logged nothing at all"


class TestSignInLogsNoCredential:
    def test_a_successful_sign_in_logs_no_password(
        self, client: TestClient, captured_logs: _Capture
    ) -> None:
        person = load_person(EMPLOYEE)
        response = sign_in(client, person.email)
        assert response.status_code == 200, response.text
        assert DEMO_PASSWORD not in captured_logs.blob

    def test_a_failed_sign_in_logs_no_password(
        self, client: TestClient, captured_logs: _Capture
    ) -> None:
        """The likelier leak. A failure is what someone reaches for a debug log line
        over, and "why was this rejected?" is answered far too easily by printing the
        input."""
        person = load_person(EMPLOYEE)
        sign_in(client, person.email, "a-very-distinctive-wrong-password")
        assert "a-very-distinctive-wrong-password" not in captured_logs.blob

    def test_no_argon2_encoding_is_logged(
        self, client: TestClient, captured_logs: _Capture
    ) -> None:
        person = load_person(EMPLOYEE)
        sign_in(client, person.email)
        assert "$argon2" not in captured_logs.blob, (
            "a stored hash reached the logs — it is not the password, but it is the"
            " material an offline attack runs against"
        )

    def test_the_issued_token_is_not_logged(
        self, client: TestClient, captured_logs: _Capture
    ) -> None:
        person = load_person(EMPLOYEE)
        token = str(sign_in(client, person.email).json()["access_token"])
        signature = token.rsplit(".", 1)[-1]

        assert token not in captured_logs.blob
        assert signature not in captured_logs.blob, (
            "the token's signature segment reached the logs; that is the part that"
            " makes a leaked line replayable"
        )


class TestProtectedRequestsLogNoCredential:
    def test_the_bearer_token_is_not_logged(
        self, client: TestClient, captured_logs: _Capture
    ) -> None:
        token = token_for(client, EMPLOYEE)
        client.get("/me/access-context", headers=auth(token))
        assert token.rsplit(".", 1)[-1] not in captured_logs.blob

    def test_a_rejected_token_is_not_logged(
        self, client: TestClient, captured_logs: _Capture
    ) -> None:
        """A forged credential is exactly what an operator would want to see in full,
        and exactly what must not be written down: it may be a *valid* token for
        somebody else that simply failed one check."""
        token = token_for(client, EMPLOYEE)
        tampered = token[:-4] + "AAAA"
        client.get("/me", headers=auth(tampered))
        assert tampered.rsplit(".", 1)[-1] not in captured_logs.blob


class TestNoCredentialIsEverReturned:
    def test_no_endpoint_returns_a_password_hash(self, client: TestClient) -> None:
        person = load_person(EMPLOYEE)
        token = token_for(client, EMPLOYEE)

        for path in (
            "/me",
            "/me/access-context",
            "/me/hr-profile",
            f"/hr/profiles/{person.user_id}",
        ):
            body = client.get(path, headers=auth(token)).text
            assert "$argon2" not in body, f"{path} returned a password hash"
            assert "password" not in body.lower(), f"{path} returned a password field"


class TestTheAuditTrailCarriesNoCredential:
    def test_no_entry_anywhere_contains_a_hash_password_or_token(
        self, client: TestClient
    ) -> None:
        """Across the whole table, not a recent window: an entry written months ago is
        just as readable to anyone holding `audit:read`."""
        person = load_person(EMPLOYEE)
        sign_in(client, person.email)
        sign_in(client, person.email, "wrong")

        with create_owner_engine().connect() as conn:
            leaked = int(
                conn.execute(
                    text(
                        "SELECT count(*) FROM audit_logs"
                        " WHERE coalesce(resource_id,'') LIKE '%$argon2%'"
                        "    OR reason LIKE '%$argon2%'"
                        "    OR coalesce(resource_id,'') LIKE :pw"
                        "    OR reason LIKE :pw"
                        "    OR coalesce(resource_id,'') LIKE 'eyJ%'"
                        "    OR reason LIKE '%eyJ%'"
                    ),
                    {"pw": f"%{DEMO_PASSWORD}%"},
                ).scalar_one()
            )
        assert leaked == 0, "an audit entry contains a credential, hash, or token"

    def test_the_leak_patterns_match_when_the_value_is_really_there(self) -> None:
        """The control for the SQL above. A `LIKE` with a typo finds nothing and reports
        success, so the pattern has to be proven against a value that genuinely contains
        what it is looking for.

        Evaluated against **literals**, not against a planted row. A first version
        inserted a fake entry containing the demo password and tried to delete it
        afterwards — and could not: `audit_logs_append_only` blocks DELETE for the table
        owner too, not just the application role, which is stronger than assumed and
        exactly right for an audit table. The row survived, and it contained the very
        string the test above searches for, so the two tests in this class were left
        contradicting each other.

        A test for "no credential is in this table" must not put one there to check.
        """
        with create_owner_engine().connect() as conn:
            row = conn.execute(
                text(
                    "SELECT"
                    "  (:planted_pw LIKE :pw) AS finds_password,"
                    "  (:planted_hash LIKE '%$argon2%') AS finds_hash,"
                    "  (:planted_jwt LIKE '%eyJ%') AS finds_token,"
                    "  (:clean LIKE :pw) AS false_positive"
                ),
                {
                    "pw": f"%{DEMO_PASSWORD}%",
                    "planted_pw": f"prefix {DEMO_PASSWORD} suffix",
                    "planted_hash": "$argon2id$v=19$m=65536,t=3,p=4$abc$def",
                    "planted_jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.sig",
                    "clean": "an ordinary reason with no credential in it",
                },
            ).one()

        assert row.finds_password, "the password pattern does not match a real password"
        assert row.finds_hash, "the hash pattern does not match a real Argon2 encoding"
        assert row.finds_token, "the token pattern does not match a real JWT"
        assert not row.false_positive, "the pattern matches text containing no credential"
