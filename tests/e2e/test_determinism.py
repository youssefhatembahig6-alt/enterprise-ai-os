"""The dataset reproduces exactly from empty (spec FR-011, FR-017a, SC-002).

This is the project's central data guarantee: destroy everything, regenerate, and
get a byte-identical dataset. Without it a bug is not reproducible, a demo is not
re-runnable, and an evaluation metric is not comparable between weeks.

Two layers are asserted. The **in-process** checks run anywhere and are fast. The
**full lifecycle** check destroys and regenerates the live environment, so it is
marked e2e and skipped when no stack is running.

A committed known-good fingerprint (FR-017a) is deliberately included: without one,
verification only proves the dataset agrees with its own manifest, and a generator
change would produce a new dataset and a new manifest that match each other
perfectly.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from eaios_core.db import create_owner_engine
from eaios_seed.config import SeedConfig
from eaios_seed.manifest import compute_digests
from eaios_seed.pipeline import build_complete_dataset

from ..conftest import environment_profile, run_seed_cli

pytestmark = pytest.mark.e2e

#: Both profiles are real datasets with committed known-good values, so both are
#: asserted. `full` is the CLI default and therefore what `make seed` produces —
#: the dataset a demo actually runs on.
PROFILES = ("smoke", "full")


@pytest.fixture(scope="module")
def env_profile() -> str:
    """The profile the live environment holds.

    A fixture rather than a module constant, and deliberately so: resolving it at
    import time runs a query during collection, before the session fixture has
    pointed the store hostnames at localhost — which caches `Settings` against the
    in-container hostname and makes every database test in the run skip. Skips are
    silent, so the suite reports success while checking nothing.
    """
    return environment_profile()


#: Known-good fingerprints, computed 2026-08-01 with the committed seed. A
#: deliberate dataset change means bumping GENERATOR_VERSION and these values
#: together; an accidental one means the generator picked up a dependency it should
#: not have.
#:
#: **Both entries are asserted.** The `full` value sat here unread for several
#: revisions while every pinned check used `smoke` — so the dataset the volume
#: table describes, and the one a demo is seeded with, had a known-good value that
#: nothing compared against. `test_profiles_are_distinct_datasets` did not cover
#: it: two datasets stay distinct however far one of them drifts.
#:
#: Two defects were fixed while establishing these values. Faker instances were
#: being cached, and Faker is stateful — a second generation in the same process
#: continued where the first left off. Separately, the CLI and the test helper
#: computed the digest over *different* datasets, because only the CLI included the
#: seed's own audit rows; both now go through `build_complete_dataset`, so the two
#: paths cannot diverge again.
#: Re-pinned at GENERATOR_VERSION 0.1.6: every document now takes its
#: `department_id` from its owner, which gave a department to Delta Retail's 25
#: contracts and to both companies' public pages, where the name-based lookup had
#: been returning null (FR-010).
EXPECTED_FINGERPRINTS = {
    "smoke": "e9fe3dca0665747ec878e69e8c28736e53d5fdeb9e116027ed02c9b4c52be3ad",
    "full": "abc407d70e90672cf5696aaa6e020e4c5112ecef78c7d970d7626c75912147ba",
}


def _generate(profile: str, seed: str | None = None) -> str:
    config = (
        SeedConfig.build(profile=profile, seed=seed)  # type: ignore[arg-type]
        if seed
        else SeedConfig.build(profile=profile)  # type: ignore[arg-type]
    )
    dataset, ctx = build_complete_dataset(config)
    _families, _files, root = compute_digests(dataset, ctx.company_ids)
    return root


@pytest.fixture(scope="module", autouse=True)
def _ensure_seeded(env_profile: str) -> None:
    """Guarantee a seeded environment for the lifecycle tests.

    These tests previously skipped whenever an earlier module had left the
    environment empty — which made them silently absent from most runs, and a test
    that quietly does not run is worse than one that fails. Provisioning here makes
    the module independent of what ran before it.
    """
    if _stored_fingerprint() is not None:
        return
    result = run_seed_cli("reset", "--yes", "--profile", env_profile)
    if result.returncode != 0:
        pytest.skip(f"cannot provision an environment: {result.stderr[-400:]}")


def _stored_fingerprint() -> str | None:
    try:
        engine = create_owner_engine()
        with engine.connect() as conn:
            row = conn.execute(text("SELECT root_fingerprint FROM dataset_manifest")).first()
    except Exception:  # pragma: no cover - environment guard
        return None
    return row[0] if row else None


class TestInProcessDeterminism:
    """Fast checks — no stores required."""

    def test_two_generations_agree(self) -> None:
        assert _generate("smoke") == _generate("smoke")

    @pytest.mark.parametrize("profile", PROFILES)
    def test_matches_the_committed_fingerprint(self, profile: str) -> None:
        assert _generate(profile) == EXPECTED_FINGERPRINTS[profile]

    def test_a_different_seed_produces_a_different_dataset(self) -> None:
        """Confirms the fingerprint actually depends on its inputs — a value that
        never changes would satisfy the pinned check while proving nothing."""
        assert _generate("smoke", seed="a-different-seed") != _generate("smoke")

    def test_profiles_are_distinct_datasets(self) -> None:
        assert _generate("smoke") != _generate("full")

    def test_row_content_is_identical_not_merely_the_digest(self) -> None:
        first, _ = build_complete_dataset(SeedConfig.build(profile="smoke"))
        second, _ = build_complete_dataset(SeedConfig.build(profile="smoke"))
        assert first.rows.keys() == second.rows.keys()
        for table in first.rows:
            assert first.rows[table] == second.rows[table], f"{table} differs between runs"


class TestFingerprintCli:
    @pytest.mark.parametrize("profile", PROFILES)
    def test_fingerprint_command_agrees_with_the_library(self, profile: str) -> None:
        result = run_seed_cli("fingerprint", "--profile", profile)
        assert result.returncode == 0, result.stderr[-800:]
        assert result.stdout.strip() == EXPECTED_FINGERPRINTS[profile]

    def test_fingerprint_needs_no_database(self) -> None:
        """It generates in memory, so it works before an environment is seeded."""
        assert run_seed_cli("fingerprint", "--profile", "smoke").returncode == 0


class TestFullLifecycle:
    """Destroys and regenerates the live environment (FR-004, FR-014a)."""

    def test_reset_and_reseed_reproduce_the_same_fingerprint(self, env_profile: str) -> None:
        before = _stored_fingerprint()
        assert before is not None

        result = run_seed_cli("reset", "--yes", "--profile", env_profile)
        assert result.returncode == 0, result.stderr[-2000:]

        after = _stored_fingerprint()
        assert after == before, (
            "a full destroy-and-regenerate cycle produced a different dataset — "
            "generation is not deterministic (SC-002)"
        )

    def test_the_stored_fingerprint_matches_the_committed_value(self, env_profile: str) -> None:
        assert _stored_fingerprint() == EXPECTED_FINGERPRINTS[env_profile]

    def test_the_environment_holds_a_profile_we_have_a_known_good_value_for(
        self, env_profile: str
    ) -> None:
        """Otherwise the assertion above would KeyError rather than fail usefully,
        and a profile added without a pinned fingerprint would slip through."""
        assert env_profile in EXPECTED_FINGERPRINTS

    def test_verify_passes_after_a_reseed(self, env_profile: str) -> None:
        result = run_seed_cli("verify", "--profile", env_profile)
        assert result.returncode == 0, result.stdout + result.stderr
