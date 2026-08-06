"""Credentials survive the full destroy-and-rebuild cycle (spec 003 FR-002a, SC-014).

Two claims, and both are about the seam between a *generated* dataset and *runtime*
state written after it.

**SC-014, first half.** Establishing credentials leaves the committed dataset
fingerprint unchanged. That is the entire argument for FR-002a's post-seed provisioning
step: the fingerprint is computed from the in-process generated rows, not from the
database, so a row written afterwards cannot reach it. Generating hashes inside the seed
would have needed a fixed salt — weakening the hash by construction — *and* changed the
generated row set, invalidating both committed values.

**SC-014, second half.** "A reset followed by re-provisioning restores a working
sign-in." `reset` truncates `user_credentials` along with every other runtime table, so
a reset environment has a complete dataset and nobody who can get in. The recovery is
one documented command, and this proves it is the *only* one needed.

**This module is destructive** — it runs `reset`, which regenerates the whole dataset.
It restores credentials on the way out so the rest of the suite is not left unable to
sign in, the same courtesy `test_migrations.py` extends after its downgrade.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text

from eaios_core.passwords import verify_password
from eaios_core.settings import get_settings

from ..conftest import environment_profile, run_seed_cli

pytestmark = pytest.mark.e2e

DEMO_PASSWORD = "eaios-demo-local-only"


def _engine():  # type: ignore[no-untyped-def]
    return create_engine(get_settings().postgres.url(as_owner=True))


def _scalar(sql: str) -> int:
    with _engine().connect() as conn:
        return int(conn.execute(text(sql)).scalar_one())


def _first_hash() -> str | None:
    with _engine().connect() as conn:
        return conn.execute(
            text("SELECT password_hash FROM user_credentials ORDER BY user_id LIMIT 1")
        ).scalar_one_or_none()


@pytest.fixture(scope="module", autouse=True)
def _restore_a_usable_environment() -> Iterator[None]:
    """Leave the environment signable-into, whatever happened in between."""
    try:
        seeded = _scalar("SELECT count(*) FROM users")
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"database unavailable: {exc}")
    if not seeded:
        pytest.skip("environment not seeded; run `make up && make seed`")

    yield

    result = run_seed_cli("credentials")
    assert result.returncode == 0, (
        "failed to restore credentials after the destructive lifecycle tests; the rest"
        f" of the suite cannot sign in: {result.stderr[-800:]}"
    )


class TestTheFingerprintDoesNotMove:
    def test_provisioning_leaves_it_byte_identical(self) -> None:
        before = run_seed_cli("fingerprint")
        assert before.returncode == 0, before.stderr

        provisioned = run_seed_cli("credentials")
        assert provisioned.returncode == 0, provisioned.stderr

        after = run_seed_cli("fingerprint")
        assert after.returncode == 0, after.stderr

        assert before.stdout.strip() == after.stdout.strip(), (
            "establishing credentials moved the dataset fingerprint (SC-014) — the"
            " committed known-good value is no longer valid"
        )

    def test_the_fingerprint_is_a_real_value(self) -> None:
        """Without this, the equality above holds just as well when both runs print
        nothing at all."""
        assert len(run_seed_cli("fingerprint").stdout.strip()) == 64

    def test_credentials_actually_existed_during_that_comparison(self) -> None:
        assert _scalar("SELECT count(*) FROM user_credentials") > 0, (
            "the fingerprint was compared across a database with no credentials in it,"
            " which proves nothing about whether credentials move it"
        )


class TestResetAndReprovision:
    """The documented recovery, end to end."""

    def test_reset_clears_credentials_and_reprovisioning_restores_sign_in(self) -> None:
        profile = environment_profile()

        # --- before ---------------------------------------------------------
        assert run_seed_cli("credentials").returncode == 0
        users_before = _scalar("SELECT count(*) FROM users WHERE is_active")
        creds_before = _scalar("SELECT count(*) FROM user_credentials")
        assert creds_before == users_before > 0
        hash_before = _first_hash()

        # --- destroy and regenerate -----------------------------------------
        reset = run_seed_cli("reset", "--yes", "--profile", profile)
        assert reset.returncode == 0, reset.stderr[-1200:]

        # The dataset is back...
        assert _scalar("SELECT count(*) FROM users WHERE is_active") == users_before
        # ...and nobody can sign in. This is the state a developer lands in after
        # `make reset`, and the reason the command says so in its output.
        assert _scalar("SELECT count(*) FROM user_credentials") == 0, (
            "reset left credentials behind; they point at users it has just recreated"
        )

        # --- recover --------------------------------------------------------
        again = run_seed_cli("credentials")
        assert again.returncode == 0, again.stderr

        assert _scalar("SELECT count(*) FROM user_credentials") == users_before
        restored = _first_hash()
        assert restored is not None
        assert verify_password(DEMO_PASSWORD, restored), (
            "the documented password does not work after reset → re-provision (SC-014)"
        )
        assert restored != hash_before, (
            "the same stored bytes came back — a fresh salt per hash is the property"
            " that makes one precomputation useless against every account"
        )

    def test_the_fingerprint_survives_the_whole_cycle(self) -> None:
        """The two halves of SC-014 together: a reset regenerates the identical
        dataset, and re-provisioning on top of it still does not move the value."""
        assert run_seed_cli("credentials").returncode == 0
        assert len(run_seed_cli("fingerprint").stdout.strip()) == 64
        verify = run_seed_cli("verify", "--profile", environment_profile())
        assert verify.returncode == 0, (
            "the environment no longer verifies against its committed fingerprint after"
            f" a reset and re-provision:\n{verify.stdout[-1500:]}"
        )


class TestTheResetOutputSaysWhatToDoNext:
    def test_it_names_the_credentials_command(self) -> None:
        """A reset that silently leaves the portal unusable is the shape of failure this
        project keeps finding: correct behaviour, invisible consequence."""
        result = run_seed_cli("reset", "--yes", "--profile", environment_profile())
        assert result.returncode == 0, result.stderr[-800:]

        combined = result.stdout + result.stderr
        assert "credentials" in combined.lower(), (
            "reset does not tell the operator that credentials must be re-provisioned:\n"
            f"{combined[-800:]}"
        )
