"""The seed refuses to run against a non-empty environment (spec FR-014).

Exit code `2` is deliberately distinct from `1`. A refusal is a *correct* outcome —
the tool protected the environment — and CI must be able to tell that apart from
the tool being broken. This test asserts the distinction rather than merely
asserting non-zero.

Requires a seeded environment: `make up && make seed`.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from eaios_core.db import create_owner_engine

from ..conftest import environment_profile, run_seed_cli

pytestmark = pytest.mark.integration

EXIT_REFUSED = 2
EXIT_NEEDS_CONFIRMATION = 4


def _fingerprint_in_db() -> str | None:
    try:
        engine = create_owner_engine()
        with engine.connect() as conn:
            row = conn.execute(text("SELECT root_fingerprint FROM dataset_manifest")).first()
    except Exception:  # pragma: no cover - environment guard
        return None
    return row[0] if row else None


@pytest.fixture(scope="module")
def seeded() -> str:
    fingerprint = _fingerprint_in_db()
    if fingerprint is None:
        pytest.skip("environment not seeded; run `make up && make seed`")
    return fingerprint


class TestRefusal:
    def test_seeding_a_populated_environment_exits_2(self, seeded: str) -> None:
        result = run_seed_cli("seed", "--profile", environment_profile())
        assert result.returncode == EXIT_REFUSED, result.stderr[-1500:]

    def test_refusal_is_distinguishable_from_a_crash(self, seeded: str) -> None:
        """Exit 1 would mean the tool broke; exit 2 means it did its job."""
        result = run_seed_cli("seed", "--profile", environment_profile())
        assert result.returncode != 1

    def test_refusal_names_the_remedy(self, seeded: str) -> None:
        result = run_seed_cli("seed", "--profile", environment_profile())
        assert "make reset" in result.stderr

    def test_refusal_reports_what_it_found(self, seeded: str) -> None:
        """An operator needs to know *why* it refused, per contracts/seed-cli.md."""
        combined = run_seed_cli("seed", "--profile", environment_profile()).stderr
        assert "not empty" in combined.lower()
        for store in ("postgres", "minio", "qdrant", "redis"):
            assert store in combined.lower()

    def test_refusal_changes_nothing(self, seeded: str) -> None:
        """The important guarantee: a refused run must not be a partial run."""
        before = _fingerprint_in_db()
        run_seed_cli("seed", "--profile", environment_profile())
        assert _fingerprint_in_db() == before


class TestResetGate:
    def test_reset_without_yes_exits_4(self, seeded: str) -> None:
        result = run_seed_cli("reset")
        assert result.returncode == EXIT_NEEDS_CONFIRMATION, result.stderr[-800:]

    def test_reset_without_yes_destroys_nothing(self, seeded: str) -> None:
        before = _fingerprint_in_db()
        run_seed_cli("reset")
        assert _fingerprint_in_db() == before

    def test_reset_refuses_a_non_local_environment(self, seeded: str, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        """FR-014a — the environment gate holds regardless of --yes."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        result = run_seed_cli("reset", "--yes")
        assert result.returncode == EXIT_REFUSED
        assert "production" in result.stderr
        assert _fingerprint_in_db() is not None  # still there


class TestUnknownProfile:
    def test_unknown_profile_is_refused(self) -> None:
        result = run_seed_cli("seed", "--profile", "enormous")
        assert result.returncode == EXIT_REFUSED
        assert "profile" in result.stderr.lower()
