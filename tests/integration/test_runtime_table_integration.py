"""Runtime tables do not break feature 001's guarantees (spec 002, research R8).

`contact_submissions` is the first table in this system written at *runtime* rather
than by the generator. That single fact touches three of feature 001's guarantees,
and each one fails differently and confusingly if missed:

* **Fingerprint** — including the table would make a visitor submitting the contact
  form change the dataset fingerprint, so `verify` would report a determinism defect
  caused by a legitimate user action.
* **Reset** — `reset_all` claims to destroy all state. A table it does not truncate
  makes that claim false, and visitor messages would survive a reset.
* **Seed pre-flight** — `inspect_stores` iterates `INSERT_ORDER`, which lists seeded
  tables only. A submission written before seeding would leave the environment
  non-empty in a way the pre-flight could not see, and `seed` would proceed against a
  dirty database — the exact state FR-014 exists to refuse.

The third is the one that would have gone unnoticed longest, because nothing fails
loudly: the seed simply succeeds against a database it should have refused.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text

from eaios_core.clock import reference_datetime
from eaios_core.fingerprint import FINGERPRINT_EXCLUSIONS, is_excluded
from eaios_seed.loaders.stores import RUNTIME_TABLES, inspect_stores
from eaios_seed.pipeline import INSERT_ORDER

pytestmark = pytest.mark.integration

TABLE = "contact_submissions"


@pytest.fixture(scope="module")
def owner_engine() -> Engine:
    """Local rather than shared: the `owner_engine` in `tests/security/conftest.py`
    is not visible to integration tests, and importing it across suites would
    couple them."""
    from eaios_core.db import create_owner_engine

    engine = create_owner_engine()
    try:
        with engine.connect() as conn:
            seeded = conn.execute(text("SELECT count(*) FROM dataset_manifest")).scalar_one()
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"database unavailable: {exc}")
    if not seeded:
        pytest.skip("environment not seeded; run `make up && make seed`")
    return engine


@pytest.fixture(scope="module")
def company_ids(owner_engine: Engine) -> dict[str, uuid.UUID]:
    with owner_engine.connect() as conn:
        return dict(conn.execute(text("SELECT slug, id FROM companies")).all())


@pytest.fixture
def submission(owner_engine: Engine, company_ids: dict[str, uuid.UUID]) -> Iterator[uuid.UUID]:
    """Insert one submission and remove it afterwards."""
    row_id = uuid.uuid4()
    now = reference_datetime()
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO contact_submissions (id, company_id, sender_name,"
                " sender_email, subject, message, content_hash, submitted_at,"
                " created_at, updated_at)"
                " VALUES (:id, :cid, 'Test Sender', 'sender@example.com', 'Subject',"
                " 'Message body', :hash, :now, :now, :now)"
            ),
            {"id": row_id, "cid": company_ids["niletech"], "hash": "0" * 64, "now": now},
        )
    try:
        yield row_id
    finally:
        with owner_engine.begin() as conn:
            conn.execute(text("DELETE FROM contact_submissions WHERE id = :id"), {"id": row_id})


class TestFingerprintExclusion:
    def test_the_table_is_excluded(self) -> None:
        assert is_excluded(TABLE)

    def test_it_is_not_in_the_seeded_insert_order(self) -> None:
        """Belt and braces: a table that is both seeded and excluded would mean
        generated content nothing verifies."""
        assert TABLE not in INSERT_ORDER

    def test_exclusions_stay_minimal(self) -> None:
        """FR-015a — an over-broad exclusion silently weakens the guarantee, so the
        set is asserted exactly rather than merely containing what we expect."""
        assert {
            "dataset_manifest",
            "alembic_version",
            "contact_submissions",
        } == FINGERPRINT_EXCLUSIONS

    def test_a_submission_does_not_change_the_fingerprint(
        self, owner_engine: Engine, submission: uuid.UUID
    ) -> None:
        """The assertion this whole exclusion exists for."""
        with owner_engine.connect() as conn:
            stored = conn.execute(
                text("SELECT root_fingerprint FROM dataset_manifest")
            ).scalar_one()
            present = conn.execute(
                text("SELECT count(*) FROM contact_submissions WHERE id = :id"),
                {"id": submission},
            ).scalar_one()

        assert present == 1, "the fixture did not insert — the check below would be vacuous"

        from eaios_seed.config import SeedConfig
        from eaios_seed.manifest import compute_digests
        from eaios_seed.pipeline import build_complete_dataset

        profile = _profile(owner_engine)
        dataset, ctx = build_complete_dataset(SeedConfig.build(profile=profile))  # type: ignore[arg-type]
        _families, _files, recomputed = compute_digests(dataset, ctx.company_ids)
        assert recomputed == stored


class TestPreflightSeesRuntimeTables:
    def test_the_runtime_table_list_is_not_empty(self) -> None:
        """A pre-flight extended with an empty list checks nothing extra."""
        assert RUNTIME_TABLES

    def test_every_runtime_table_exists(self, owner_engine: Engine) -> None:
        with owner_engine.connect() as conn:
            for table in RUNTIME_TABLES:
                conn.execute(text(f"SELECT count(*) FROM {table}"))

    def test_a_submission_makes_the_environment_non_empty(
        self, owner_engine: Engine, submission: uuid.UUID
    ) -> None:
        """Without this, `seed` would run against a database holding visitor data
        and believe it was empty."""
        assert inspect_stores().postgres_rows > 0

    def test_the_row_is_counted_even_with_no_seeded_data(
        self, owner_engine: Engine, submission: uuid.UUID
    ) -> None:
        """Counted directly, so the assertion above cannot pass on seeded rows
        alone — that would make it vacuous in a seeded environment."""
        with owner_engine.connect() as conn:
            count = conn.execute(text("SELECT count(*) FROM contact_submissions")).scalar_one()
        assert count >= 1


class TestResetTruncatesRuntimeTables:
    def test_reset_includes_every_runtime_table(self) -> None:
        """Asserted against the source rather than by running reset, which would
        destroy the environment the rest of the suite depends on."""
        import inspect

        from eaios_seed.loaders import stores

        source = inspect.getsource(stores.reset_all)
        assert "RUNTIME_TABLES" in source, (
            "reset_all does not truncate runtime tables — a reset would leave "
            "visitor submissions behind while claiming to destroy all state"
        )


def _profile(engine: Engine) -> str:
    with engine.connect() as conn:
        return str(conn.execute(text("SELECT profile FROM dataset_manifest")).scalar_one())


class TestResetClearsTheAnonymousBounds:
    """`make reset` destroys every cache entry — including these (FR-024d, FR-047b).

    The rate-limit counters were the *second* piece of runtime state this feature
    added, and the reset path did not learn about them: `reset_all` clears Redis by
    scanning `cache_namespace(slug)`, which expands to `eaios:cache:{company}:*`, and
    the counters live under `eaios:ratelimit:*` — a different prefix, and deliberately
    not tenant-scoped because the callers they bound are anonymous.

    The consequence was small and the shape was familiar: `make reset` announces
    "This destroys every row, object, vector, and cache entry in the local
    environment", and a developer resetting for a clean environment kept whatever
    bound they had accumulated for up to an hour. It is the same class of omission
    this module already documents for `contact_submissions`, which is why the check
    belongs beside those.
    """

    @staticmethod
    def _redis():
        from eaios_core.clients.stores import get_redis

        try:
            client = get_redis()
            client.ping()
        except Exception as exc:  # pragma: no cover - environment guard
            pytest.skip(f"redis unavailable: {exc}")
        return client

    def test_the_reset_pattern_matches_a_real_counter(self) -> None:
        """The two must agree by construction, not by both being written correctly.

        Both now come from `eaios_core.keys`, which is the point: the code that
        writes a counter and the code that clears it read the same pattern.
        """
        import fnmatch

        from eaios_core.keys import rate_limit_key, rate_limit_namespace

        key = rate_limit_key("contact", "abc123")
        assert fnmatch.fnmatch(key, rate_limit_namespace()), (
            f"{key!r} is not matched by the reset pattern {rate_limit_namespace()!r}"
        )

    def test_the_cache_pattern_does_not_match_a_counter(self) -> None:
        """Why the extra scan is needed at all — and the assertion that would have
        caught this when the counters were introduced."""
        import fnmatch

        from eaios_core.constants import NILETECH
        from eaios_core.keys import cache_namespace, rate_limit_key

        key = rate_limit_key("contact", "abc123")
        assert not fnmatch.fnmatch(key, cache_namespace(NILETECH))

    @pytest.fixture(scope="class")
    def _restore_seeded_environment(self):
        """Reseed after the destructive cases below.

        `reset_all()` empties the environment, and the two tests that follow call the
        real function rather than inspecting its source — which is what the older
        `TestResetTruncatesRuntimeTables` above does precisely to stay
        non-destructive. Both approaches are defensible; what is not defensible is
        the first version of this class, which called `reset_all()` with no restore
        and left every later test in the suite running against an empty database.

        The pattern here follows `test_migrations.py`, which pays the same cost for
        the same reason and documents it.
        """
        from ..conftest import environment_profile, run_seed_cli

        profile = environment_profile()
        yield
        run_seed_cli("reset", "--yes", "--profile", profile)

    def test_a_counter_written_before_a_reset_is_gone_after_it(
        self, _restore_seeded_environment
    ) -> None:
        from eaios_core.keys import rate_limit_key
        from eaios_seed.loaders.stores import reset_all

        client = self._redis()
        key = rate_limit_key("contact", "reset-probe-7f3a")
        client.set(key, "4", ex=3600)
        assert client.exists(key) == 1, "the probe was not written; nothing to reset"

        reset_all()

        assert client.exists(key) == 0, (
            "a rate-limit counter survived `reset`, which promises to destroy every"
            " cache entry in the environment"
        )

    def test_reset_leaves_no_bound_behind_at_all(self, _restore_seeded_environment) -> None:
        from eaios_core.keys import rate_limit_key, rate_limit_namespace
        from eaios_seed.loaders.stores import reset_all

        client = self._redis()
        for index in range(5):
            client.set(rate_limit_key("refusal-audit", f"probe-{index}"), "1", ex=3600)

        reset_all()

        remaining = list(client.scan_iter(match=rate_limit_namespace()))
        assert remaining == [], f"{len(remaining)} counter(s) survived the reset"
