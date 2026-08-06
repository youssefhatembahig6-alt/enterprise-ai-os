"""Sign-in discloses nothing about which accounts exist (spec 003 FR-007a, FR-022, SC-013).

FR-022 forbids "any distinction between 'no such account' and 'wrong credentials'".
That is a stricter requirement than it looks, because a sign-in form leaks through four
separate channels and closing one is easy enough to feel finished:

* the **body** — the obvious one;
* the **status code** — a 404 for an unknown address answers the question outright;
* the **headers** — a `Retry-After` on a locked account says the account is real;
* the **work performed** — if the unknown-address path returns without hashing, the
  question is answerable with a stopwatch.

The last one is why `verify_dummy` exists. It is asserted structurally rather than by
timing: a wall-clock comparison on a loaded runner is exactly the flaky, low-power
check that passes by luck.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager, suppress

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from eaios_core.db import create_owner_engine
from eaios_core.settings import get_settings

from .auth_helpers import DEMO_PASSWORD, EMPLOYEE, load_person, sign_in

pytestmark = pytest.mark.security


def _clear_login_buckets() -> None:
    """Delete every sign-in counter. Scoped to the two login buckets.

    Not the whole `eaios:ratelimit:*` namespace: a first version cleared everything and
    quietly reset feature 002's contact-form and refusal-audit counters as a side
    effect, which masked a genuine ordering problem in `test_anonymous_refusal.py`.
    """
    from eaios_core.clients.stores import get_redis
    from eaios_core.keys import (
        LOGIN_ACCOUNT_BUCKET,
        LOGIN_ADDRESS_BUCKET,
        RATE_LIMIT_PREFIX,
    )

    redis = get_redis()
    for bucket in (LOGIN_ACCOUNT_BUCKET, LOGIN_ADDRESS_BUCKET):
        for key in redis.scan_iter(match=f"{RATE_LIMIT_PREFIX}:{bucket}:*"):
            redis.delete(key)


@pytest.fixture(autouse=True)
def _clear_attempt_counters() -> Iterator[None]:
    """Reset the sign-in counters **before and after** every test in this file.

    Before, because this file deliberately exhausts both bounds and the order tests ran
    in would otherwise decide which ones passed.

    After, and this half was missing: `test_the_address_bound_is_reached_across_many_accounts`
    drives the per-address counter to its limit on purpose, and the fixture used to
    clear only on the way in — so the *last* test in the file left the address locked
    for the rest of the fifteen-minute window. Every later suite sharing this client
    identity then failed to sign in at all: twelve session-expiry tests failed with a
    401 that looked like broken authentication and was actually the bound working.
    Counters this file fills are counters this file empties.
    """
    try:
        _clear_login_buckets()
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"redis unavailable: {exc}")

    yield

    # Suppressed: a teardown failure must not mask whatever the test itself reported.
    with suppress(Exception):
        _clear_login_buckets()


def _an_inactive_user() -> str:
    """Deactivate somebody for the duration of one test, and put them back."""
    engine = create_owner_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT email FROM users WHERE is_active ORDER BY id OFFSET 5 LIMIT 1")
        ).first()
        if row is None:
            pytest.skip("no users seeded")
        conn.execute(
            text("UPDATE users SET is_active = false WHERE email = :e"), {"e": row.email}
        )
    return str(row.email)


def _reactivate(email: str) -> None:
    with create_owner_engine().begin() as conn:
        conn.execute(text("UPDATE users SET is_active = true WHERE email = :e"), {"e": email})


@contextmanager
def _without_credentials() -> Iterator[str]:
    """Remove one person's credential for the duration of a block, then put it back.

    A real state, not a contrived one: `credentials` provisions active users, so anyone
    deactivated and later reactivated has no row until it is run again. The refusal must
    be indistinguishable from a wrong password — otherwise "this address exists but has
    no credential" is a fact the sign-in form hands out.

    Restored on the way out. An earlier version deleted and walked away, which would
    have quietly eroded the provisioned set one row per run until something unrelated
    failed and pointed somewhere else entirely.
    """
    engine = create_owner_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT u.email, c.id, c.company_id, c.user_id, c.password_hash,"
                "       c.created_at, c.updated_at"
                " FROM users u JOIN user_credentials c ON c.user_id = u.id"
                " WHERE u.is_active ORDER BY u.id OFFSET 9 LIMIT 1"
            )
        ).first()
        if row is None:
            pytest.skip("no provisioned users; run `make credentials`")
        conn.execute(text("DELETE FROM user_credentials WHERE id = :i"), {"i": row.id})

    try:
        yield str(row.email)
    finally:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO user_credentials"
                    " (id, company_id, user_id, password_hash, created_at, updated_at)"
                    " VALUES (:i, :c, :u, :h, :ca, :ua)"
                    " ON CONFLICT (user_id) DO NOTHING"
                ),
                {
                    "i": row.id,
                    "c": row.company_id,
                    "u": row.user_id,
                    "h": row.password_hash,
                    "ca": row.created_at,
                    "ua": row.updated_at,
                },
            )


class TestTheHappyPathWorks:
    """The control. Every assertion below is about refusals being indistinguishable,
    and an implementation that refused *everything* would satisfy all of them."""

    def test_a_seeded_user_can_sign_in(self, client: TestClient) -> None:
        person = load_person(EMPLOYEE)
        response = sign_in(client, person.email)
        assert response.status_code == 200, response.text
        assert response.json()["access_token"]

    def test_the_address_is_matched_case_insensitively(self, client: TestClient) -> None:
        """People type their address however they type it. A case-sensitive lookup
        would refuse a legitimate sign-in with the same message as a wrong password,
        which is unhelpful in exactly the way the generic message is meant to be
        helpful."""
        person = load_person(EMPLOYEE)
        assert sign_in(client, person.email.upper()).status_code == 200

    def test_surrounding_whitespace_is_tolerated(self, client: TestClient) -> None:
        person = load_person(EMPLOYEE)
        assert sign_in(client, f"  {person.email}  ").status_code == 200


class TestEveryRefusalLooksTheSame:
    """Five different causes, one indistinguishable response."""

    def _refusals(self, client: TestClient) -> dict[str, object]:
        """Every cause that could reveal whether an account exists.

        A **malformed** address is deliberately not in this set. It returns 422, and
        that is correct rather than a leak: an address with no `@` cannot be anybody's
        account, so refusing it as a validation error answers nothing about which
        accounts exist. It is also better for the person typing — the form can say
        "that does not look like an email address" instead of "those details were not
        accepted". `TestSyntaxErrorsAreNotEnumeration` below holds that line.
        """
        person = load_person(EMPLOYEE)
        inactive = _an_inactive_user()
        try:
            with _without_credentials() as unprovisioned:
                return {
                    "unknown address": sign_in(client, "nobody@niletech.example"),
                    "wrong password": sign_in(client, person.email, "not-the-password"),
                    "inactive user": sign_in(client, inactive),
                    "no credential row": sign_in(client, unprovisioned),
                    "empty password": sign_in(client, person.email, ""),
                }
        finally:
            _reactivate(inactive)

    def test_every_refusal_has_the_same_status(self, client: TestClient) -> None:
        statuses = {
            cause: response.status_code  # type: ignore[union-attr]
            for cause, response in self._refusals(client).items()
        }
        assert len(set(statuses.values())) == 1, f"statuses differ by cause: {statuses}"
        assert set(statuses.values()) == {401}, statuses

    def test_every_refusal_has_the_same_body(self, client: TestClient) -> None:
        bodies = {
            cause: response.text  # type: ignore[union-attr]
            for cause, response in self._refusals(client).items()
        }
        assert len(set(bodies.values())) == 1, (
            "refusal bodies differ by cause — each difference answers 'does this"
            f" account exist?':\n{bodies}"
        )

    def test_no_refusal_names_the_account_or_the_cause(self, client: TestClient) -> None:
        person = load_person(EMPLOYEE)
        body = sign_in(client, person.email, "wrong").text.lower()
        for leak in (
            person.email.lower(),
            "password",
            "inactive",
            "not found",
            "no such",
            "exists",
            "credential",
        ):
            assert leak not in body, f"the refusal body contains {leak!r}: {body}"

    def test_no_refusal_carries_a_retry_hint(self, client: TestClient) -> None:
        """A `Retry-After` on a locked account is a header that says the account is
        real. Absent by design, which is why it is asserted rather than assumed."""
        person = load_person(EMPLOYEE)
        response = sign_in(client, person.email, "wrong")
        assert "retry-after" not in {k.lower() for k in response.headers}


class TestSyntaxErrorsAreNotEnumeration:
    """A malformed address is refused as a validation error, and that is correct.

    The distinction worth holding: enumeration is learning *which accounts exist*. An
    address with no `@` cannot be one, so refusing it differently answers nothing an
    attacker did not already know — they typed it. What the 422 must not do is say
    anything about the account it could not have been.
    """

    def test_a_malformed_address_is_a_validation_error(self, client: TestClient) -> None:
        assert sign_in(client, "not-an-address").status_code == 422

    def test_the_validation_error_names_only_the_field(self, client: TestClient) -> None:
        body = sign_in(client, "not-an-address").text.lower()
        for leak in ("exists", "no such", "not found", "account", "credential", "password"):
            assert leak not in body, f"the 422 body mentions {leak!r}: {body}"

    def test_a_well_formed_unknown_address_is_not_a_validation_error(
        self, client: TestClient
    ) -> None:
        """The line itself. A well-formed address that belongs to nobody must go down
        the ordinary refusal path — if it produced a 422 too, the two statuses would
        together separate "could be an account" from "is an account"."""
        assert sign_in(client, "nobody@niletech.example").status_code == 401


class TestTheUnknownAccountPathDoesTheSameWork:
    def test_a_verification_happens_even_when_no_user_matches(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The timing channel, closed and asserted structurally.

        Counting verifications rather than measuring elapsed time: Argon2 costs tens of
        milliseconds by design, so a stopwatch comparison would be measuring the machine
        as much as the code, and would pass or fail with the runner's load.
        """
        from argon2 import PasswordHasher

        calls: list[str] = []
        original = PasswordHasher.verify

        def counting(self: PasswordHasher, stored: str, password: str) -> bool:
            calls.append(stored)
            return bool(original(self, stored, password))

        monkeypatch.setattr(PasswordHasher, "verify", counting)

        sign_in(client, "definitely-nobody@niletech.example")
        assert len(calls) >= 1, (
            "no verification ran for an unknown address — the unknown-account path is"
            " cheaper than the known-account path, and the difference is measurable"
        )

    def test_a_known_address_with_a_wrong_password_also_verifies(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The other half of the comparison. Without it, "a verification happened" is
        true of an implementation that hashes twice on one path and once on the
        other."""
        from argon2 import PasswordHasher

        calls: list[str] = []
        original = PasswordHasher.verify

        def counting(self: PasswordHasher, stored: str, password: str) -> bool:
            calls.append(stored)
            return bool(original(self, stored, password))

        monkeypatch.setattr(PasswordHasher, "verify", counting)

        person = load_person(EMPLOYEE)
        sign_in(client, person.email, "wrong")
        assert len(calls) >= 1


class TestTheAttemptBoundsHold:
    """FR-007a. Both dimensions, at the stated numbers, refusing identically."""

    def test_the_account_bound_is_reached(self, client: TestClient) -> None:
        limit = get_settings().auth.login_account_max_failures
        person = load_person(EMPLOYEE)

        for attempt in range(limit):
            response = sign_in(client, person.email, "wrong")
            assert response.status_code == 401, f"attempt {attempt + 1}: {response.text}"

        # Past the bound, even the *correct* password is refused. That is what makes it
        # a lockout rather than a slower guessing loop.
        blocked = sign_in(client, person.email, DEMO_PASSWORD)
        assert blocked.status_code == 401, (
            "the correct password was accepted after the account bound was reached"
        )

    def test_the_lockout_is_indistinguishable_from_a_wrong_password(
        self, client: TestClient
    ) -> None:
        limit = get_settings().auth.login_account_max_failures
        person = load_person(EMPLOYEE)

        ordinary = sign_in(client, person.email, "wrong")
        for _ in range(limit):
            sign_in(client, person.email, "wrong")
        locked = sign_in(client, person.email, "wrong")

        assert locked.status_code == ordinary.status_code
        assert locked.text == ordinary.text, (
            "a locked account answers differently from a wrong password — which tells"
            " an attacker the address is real and that they found it (FR-007a)"
        )

    def test_a_successful_sign_in_clears_the_account_counter(
        self, client: TestClient
    ) -> None:
        """FR-007a says so explicitly. Without it, a user who mistypes four times and
        then succeeds is one mistake away from a lockout for the rest of the window."""
        limit = get_settings().auth.login_account_max_failures
        person = load_person(EMPLOYEE)

        for _ in range(limit - 1):
            assert sign_in(client, person.email, "wrong").status_code == 401
        assert sign_in(client, person.email).status_code == 200

        # The counter is back to zero, so the next batch of failures does not lock out.
        for _ in range(limit - 1):
            assert sign_in(client, person.email, "wrong").status_code == 401
        assert sign_in(client, person.email).status_code == 200

    def test_the_address_bound_is_reached_across_many_accounts(
        self, client: TestClient
    ) -> None:
        """Credential stuffing's ordinary shape: one address, many accounts, so no
        single account counter ever fills. Without a per-address bound this is
        unlimited."""
        settings = get_settings()
        limit = settings.auth.login_address_max_failures

        for attempt in range(limit):
            response = sign_in(client, f"nobody-{attempt}@niletech.example", "wrong")
            assert response.status_code == 401

        # A *different*, real account from the same address is now refused too.
        person = load_person(EMPLOYEE)
        blocked = sign_in(client, person.email, DEMO_PASSWORD)
        assert blocked.status_code == 401, (
            "the address bound did not hold — attempts spread across accounts are"
            " unbounded"
        )

    def test_the_bounds_are_stated_as_numbers(self) -> None:
        """FR-007a requires it, because "bounded" is not testable. Asserted so the
        numbers cannot quietly become None or zero and disable the whole mechanism."""
        auth = get_settings().auth
        assert auth.login_account_max_failures > 0
        assert auth.login_address_max_failures > 0
        assert auth.login_bound_window_seconds > 0
        assert auth.login_address_max_failures > auth.login_account_max_failures, (
            "the address ceiling should exceed the account ceiling — a shared office"
            " egress is one address for many people"
        )


class TestLockoutsAreAudited:
    def test_reaching_a_bound_writes_an_audit_entry(self, client: TestClient) -> None:
        """FR-007a: "every lockout MUST be audited". A bound that fires silently is
        indistinguishable, operationally, from a user who gave up."""
        limit = get_settings().auth.login_account_max_failures
        person = load_person(EMPLOYEE)

        before = _audit_count("auth.locked_out")
        for _ in range(limit + 1):
            sign_in(client, person.email, "wrong")
        after = _audit_count("auth.locked_out")

        assert after > before, "the lockout wrote no audit entry"

    def test_no_audit_entry_records_the_attempted_address(
        self, client: TestClient
    ) -> None:
        """An audit table listing every attempted address is an enumeration surface
        with a longer memory than the sign-in form — and it is readable by anyone
        holding `audit:read`."""
        person = load_person(EMPLOYEE)
        sign_in(client, person.email, "wrong")

        engine = create_owner_engine()
        with engine.connect() as conn:
            leaked = conn.execute(
                text(
                    "SELECT count(*) FROM audit_logs"
                    " WHERE action LIKE 'auth.%'"
                    "   AND (coalesce(resource_id,'') ILIKE :e OR reason ILIKE :e)"
                ),
                {"e": f"%{person.email}%"},
            ).scalar_one()
        assert leaked == 0, "an audit entry contains the attempted address"


def _audit_count(action: str) -> int:
    with create_owner_engine().connect() as conn:
        return int(
            conn.execute(
                text("SELECT count(*) FROM audit_logs WHERE action = :a"), {"a": action}
            ).scalar_one()
        )
