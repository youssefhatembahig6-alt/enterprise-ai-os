"""Establishing demo credentials (spec 003 FR-002a, SC-014).

The step that makes sign-in possible, and the one that must not disturb anything
feature 001 guarantees. Three properties, each of which has a way of quietly not
holding:

* **One credential per active user.** Not "some rows appeared" — the count has to match
  the users, or a subset of people can sign in and nobody notices which.
* **Re-running is safe.** Not byte-identical, which is impossible: Argon2 salts are
  random per hash, so two runs necessarily store different bytes. What must hold is the
  *observable* outcome — the same password still signs in and the row count is
  unchanged.
* **The fingerprint does not move.** It is computed from the in-process generated rows,
  not from the database, so a post-seed write cannot reach it. That is the whole
  argument for FR-002a and it is worth measuring rather than asserting.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text

from eaios_core.settings import get_settings

from ..conftest import SEED_PYTHONPATH, run_seed_cli

pytestmark = pytest.mark.integration

DEMO_PASSWORD = "eaios-demo-local-only"


def _owner_engine():  # type: ignore[no-untyped-def]
    return create_engine(get_settings().postgres.url(as_owner=True))


def _scalar(sql: str) -> int:
    with _owner_engine().connect() as conn:
        return int(conn.execute(text(sql)).scalar_one())


@pytest.fixture(scope="module", autouse=True)
def _requires_a_seeded_environment() -> Iterator[None]:
    """Skip loudly rather than pass vacuously.

    Every assertion below compares credentials against users. Against an empty
    database "one row per user" is 0 == 0 and the whole module reports success while
    checking nothing — the exact shape of vacuous pass this project keeps finding.
    """
    try:
        users = _scalar("SELECT count(*) FROM users")
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"database unavailable: {exc}")
    if users == 0:
        pytest.skip("no users seeded; run `make seed` first (nothing to provision against)")
    yield


def _provision(*extra: str) -> subprocess.CompletedProcess[str]:
    return run_seed_cli("credentials", *extra)


def _provisioned(*extra: str) -> int:
    """Provision, and refuse to continue unless rows actually exist.

    Every content assertion below is of the form "no row is wrong". Against an empty
    table that is `0 == 0` and passes — which is how a broken provisioning step would
    have reported four green checks while writing nothing. This turns each of them into
    a claim about real rows.

    **Costly on purpose, so called sparingly.** One run hashes every active user with
    Argon2id at m=64MiB/t=3, which is tens of milliseconds each by design — the whole
    point of the algorithm. At 240 users that is ~20 seconds per call, and a first draft
    of this file called it a dozen times and took nearly nine minutes. The content
    assertions now share one run through `provisioned_once`; only the tests that are
    *about* re-running pay for a second.
    """
    result = _provision(*extra)
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    rows = _scalar("SELECT count(*) FROM user_credentials")
    assert rows > 0, "provisioning reported success and wrote nothing"
    return rows


@pytest.fixture(scope="module")
def provisioned_once() -> int:
    """One provisioning run, shared by every test that only inspects the result."""
    return _provisioned()


class TestTheProvisioningStepHasSubjects:
    def test_there_are_active_users_to_provision(self) -> None:
        active = _scalar("SELECT count(*) FROM users WHERE is_active")
        assert active > 0, "nothing to provision; every later assertion would be vacuous"

    def test_both_tenants_have_users(self) -> None:
        """Sign-in resolves the tenant by looking the email up under each company in
        turn (research R4). One tenant's worth of users would let a broken resolver
        pass."""
        companies = _scalar("SELECT count(DISTINCT company_id) FROM users")
        assert companies == 2, f"expected both tenants, found {companies}"


class TestOneCredentialPerActiveUser:
    def test_the_row_count_matches_the_active_users(self, provisioned_once: int) -> None:
        users = _scalar("SELECT count(*) FROM users WHERE is_active")
        assert provisioned_once == users, (
            f"{provisioned_once} credentials for {users} active users — a mismatch means"
            " some people silently cannot sign in"
        )

    def test_every_credential_carries_its_users_company(self, provisioned_once: int) -> None:
        """The tenant column is not decorative: RLS reads it, and a credential written
        under the wrong company would be invisible to its own owner's sign-in."""
        assert provisioned_once > 0
        mismatched = _scalar(
            "SELECT count(*) FROM user_credentials c"
            " JOIN users u ON u.id = c.user_id"
            " WHERE c.company_id <> u.company_id"
        )
        assert mismatched == 0

    def test_the_command_reports_what_it_did(self, provisioned_once: int) -> None:
        """A provisioning step whose result is invisible is one nobody notices
        failing. Re-runs the command because the *output* is what is under test — the
        one extra run this file pays for outside the re-run tests."""
        result = _provision()
        assert str(provisioned_once) in result.stdout
        assert DEMO_PASSWORD in result.stdout, "the demo password must be discoverable"


class TestTheStoredValueIsNotThePassword:
    def test_no_stored_value_contains_the_plaintext(self, provisioned_once: int) -> None:
        assert provisioned_once > 0
        leaked = _scalar(
            "SELECT count(*) FROM user_credentials"
            f" WHERE password_hash LIKE '%{DEMO_PASSWORD}%'"
        )
        assert leaked == 0

    def test_every_hash_is_argon2id(self, provisioned_once: int) -> None:
        assert provisioned_once > 0
        wrong = _scalar(
            "SELECT count(*) FROM user_credentials WHERE password_hash NOT LIKE '$argon2id$%'"
        )
        assert wrong == 0, "a stored value that is not an Argon2id encoding (FR-002)"

    def test_two_users_with_the_same_password_have_different_hashes(
        self, provisioned_once: int
    ) -> None:
        """Per-hash random salt. Identical hashes would mean a shared salt, which makes
        one precomputation break every account at once."""
        distinct = _scalar("SELECT count(DISTINCT password_hash) FROM user_credentials")
        assert distinct == provisioned_once, (
            f"{provisioned_once - distinct} duplicated hashes — the salt is not per-hash"
        )


def _first_hash() -> str:
    with _owner_engine().connect() as conn:
        return str(
            conn.execute(
                text("SELECT password_hash FROM user_credentials ORDER BY user_id LIMIT 1")
            ).scalar_one()
        )


class TestRerunningIsSafe:
    """Three claims about re-running, proven with two extra provisioning runs rather
    than six. The class is deliberately one test: each claim depends on the state the
    previous run left, and splitting them would multiply the cost for no isolation
    that matters."""

    def test_rerunning_changes_the_bytes_and_not_the_outcome(
        self, provisioned_once: int
    ) -> None:
        from eaios_core.passwords import verify_password

        before = _first_hash()

        # --- a second run with a *different* password --------------------------
        # Rewrite-not-skip: skipping rows that already have a hash would make
        # `--password` silently not apply, which is a worse failure than the rewrite
        # because the operator would believe they had changed something.
        changed = _provisioned("--password", "a-different-local-password")
        assert changed == provisioned_once, "the row count moved on a re-run"

        stored = _first_hash()
        assert verify_password("a-different-local-password", stored)
        assert not verify_password(DEMO_PASSWORD, stored), (
            "the old password still verifies — the row was skipped, not rewritten"
        )

        # --- back to the documented default ------------------------------------
        restored = _provisioned()
        assert restored == provisioned_once

        final = _first_hash()
        assert verify_password(DEMO_PASSWORD, final)

        # Idempotence here is about the *outcome*, not the bytes. Everywhere else in
        # this project idempotent means byte-identical; it cannot here, and that is the
        # point — a fresh random salt per run is what the hashes are worth anything for.
        assert final != before, "same bytes twice would mean a fixed salt"


class TestTheGuards:
    def test_it_refuses_outside_a_local_environment(self) -> None:
        """The same outer guard `reset` already applies. Local-only placeholder
        credentials must be impossible to write into anything production-shaped."""
        result = subprocess.run(
            [sys.executable, "-m", "eaios_seed.cli", "credentials"],
            capture_output=True,
            text=True,
            check=False,
            env={
                **os.environ,
                "ENVIRONMENT": "staging",
                "PYTHONPATH": SEED_PYTHONPATH,
                "PYTHONIOENCODING": "utf-8",
            },
            timeout=120,
        )
        assert result.returncode != 0, "provisioning ran outside a local environment"
        assert "local" in (result.stdout + result.stderr).lower()

    def test_no_email_is_shared_across_tenants(self) -> None:
        """Sign-in resolves the tenant by email (research R4), and a duplicate would
        make that ambiguous. The provisioning step asserts it so the ambiguity is
        impossible in the data rather than handled at the sign-in form."""
        duplicates = _scalar(
            "SELECT count(*) FROM ("
            "  SELECT lower(email) FROM users GROUP BY lower(email) HAVING count(*) > 1"
            ") AS d"
        )
        assert duplicates == 0, (
            f"{duplicates} email(s) exist in more than one tenant; sign-in could not"
            " resolve them unambiguously"
        )


class TestTheFingerprintDoesNotMove:
    def test_provisioning_leaves_the_dataset_fingerprint_unchanged(
        self, provisioned_once: int
    ) -> None:
        """SC-014. The fingerprint is computed from the in-process generated rows, not
        from the database, so a row written afterwards cannot reach it. Measured rather
        than argued."""
        assert provisioned_once > 0
        before = run_seed_cli("fingerprint")
        assert before.returncode == 0, before.stderr
        _provisioned()
        after = run_seed_cli("fingerprint")
        assert after.returncode == 0, after.stderr
        assert before.stdout.strip() == after.stdout.strip(), (
            "establishing credentials moved the dataset fingerprint (SC-014)"
        )

    def test_the_fingerprint_is_a_real_value(self) -> None:
        """Without this, the equality above holds just as well when both runs print an
        empty string."""
        result = run_seed_cli("fingerprint")
        assert len(result.stdout.strip()) == 64, repr(result.stdout)
