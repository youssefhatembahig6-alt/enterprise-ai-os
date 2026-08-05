"""An interrupted seed is reported as *incomplete*, not as a mismatch (FR-014b/c).

These are different failures needing different responses: "the seed died, run it
again" versus "the data drifted, investigate the generator". Collapsing them would
send an operator hunting a determinism bug that does not exist.

The interruption is simulated by clearing the completion marker rather than by
killing a process mid-run — the marker *is* the mechanism under test, and clearing
it reproduces exactly the state a crash leaves behind, without a race.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import text

from eaios_core.db import create_owner_engine

from ..conftest import environment_profile, run_seed_cli

pytestmark = pytest.mark.integration

EXIT_VERIFY_FAILED = 3


def _manifest_exists() -> bool:
    try:
        engine = create_owner_engine()
        with engine.connect() as conn:
            return conn.execute(text("SELECT count(*) FROM dataset_manifest")).scalar_one() > 0
    except Exception:  # pragma: no cover - environment guard
        return False


@pytest.fixture
def interrupted_seed() -> Iterator[None]:
    """Clear the completion marker, then restore it."""
    if not _manifest_exists():
        pytest.skip("environment not seeded; run `make up && make seed`")

    engine = create_owner_engine()
    with engine.begin() as conn:
        saved = conn.execute(
            text("SELECT completed_at, duration_seconds FROM dataset_manifest LIMIT 1")
        ).first()
        conn.execute(
            text("UPDATE dataset_manifest SET completed_at = NULL, duration_seconds = NULL")
        )
    try:
        yield
    finally:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE dataset_manifest SET completed_at = :completed_at,"
                    " duration_seconds = :duration_seconds"
                ),
                {"completed_at": saved[0], "duration_seconds": saved[1]},
            )


class TestIncompleteDetection:
    def test_verify_fails_when_the_marker_is_missing(self, interrupted_seed: None) -> None:
        result = run_seed_cli("verify", "--profile", environment_profile())
        assert result.returncode == EXIT_VERIFY_FAILED, result.stdout + result.stderr

    def test_verify_reports_incomplete_not_mismatch(self, interrupted_seed: None) -> None:
        """The distinction FR-014c exists to preserve."""
        combined = (run_seed_cli("verify", "--profile", environment_profile()).stderr).lower()
        assert "incomplete" in combined
        assert "mismatch" not in combined

    def test_verify_explains_the_cause(self, interrupted_seed: None) -> None:
        combined = run_seed_cli("verify", "--profile", environment_profile()).stderr.lower()
        assert "did not finish" in combined or "completion marker" in combined

    def test_an_incomplete_environment_is_still_not_empty(self, interrupted_seed: None) -> None:
        """So `seed` still refuses — the remedy is `reset`, not a top-up (FR-014)."""
        result = run_seed_cli("seed", "--profile", environment_profile())
        assert result.returncode == 2
        assert "make reset" in result.stderr


class TestCompleteAfterRestore:
    def test_verify_passes_once_the_marker_is_back(self) -> None:
        if not _manifest_exists():
            pytest.skip("environment not seeded")
        result = run_seed_cli("verify", "--profile", environment_profile())
        assert result.returncode == 0, result.stdout + result.stderr
        assert "manifest complete" in result.stdout.lower()
