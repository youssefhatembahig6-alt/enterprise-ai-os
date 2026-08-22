"""Migration reversibility (spec FR-007, FR-008).

"Reversible" is only meaningful if the downgrade is actually exercised. A migration
whose ``downgrade()`` has never run is a rollback plan nobody has tested.

**This module is destructive.** `alembic downgrade base` drops every table, so any
seeded data is gone. Pytest orders files alphabetically, which puts this one in the
middle of the integration suite — so without the restoring fixture below, every
test after it would find an empty environment and skip. The fixture reseeds once
the module finishes, keeping the file self-contained rather than depending on run
order.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

pytestmark = pytest.mark.integration

ALEMBIC_DIR = Path(__file__).resolve().parents[2] / "apps" / "api"


def _owner_url() -> str:
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_HOST_PORT", os.environ.get("POSTGRES_PORT", "5432"))
    user = os.environ.get("POSTGRES_OWNER_USER", "eaios_owner")
    password = os.environ.get("POSTGRES_OWNER_PASSWORD", "eaios_owner_local_only")
    db = os.environ.get("POSTGRES_DB", "eaios")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"


def _alembic(
    *args: str, database: str | None = None
) -> subprocess.CompletedProcess[str]:
    """Run alembic, optionally against a different database.

    Invoked as `python -m alembic` rather than the bare `alembic` shim: the console
    script is absent from some environments (and blocked outright by Windows App
    Control), and a missing executable would surface as an unrelated `FileNotFoundError`
    rather than as a migration failure.

    `database` overrides only `POSTGRES_DB`, which is what `alembic/env.py` reads through
    `get_settings()`. Everything else about the connection stays as configured.
    """
    environment = dict(os.environ)
    if database is not None:
        environment["POSTGRES_DB"] = database
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=ALEMBIC_DIR,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )


def _schema_snapshot() -> dict[str, list[str]]:
    """Table → sorted column names. Enough to detect a lossy round trip."""
    engine = create_engine(_owner_url())
    inspector = inspect(engine)
    return {
        table: sorted(col["name"] for col in inspector.get_columns(table))
        for table in sorted(inspector.get_table_names())
        if table != "alembic_version"
    }


@pytest.fixture(scope="module")
def at_head() -> None:
    result = _alembic("upgrade", "head")
    if result.returncode != 0:
        pytest.skip(f"database unavailable or migrations failed: {result.stderr[-400:]}")


@pytest.fixture(scope="module", autouse=True)
def _restore_seeded_environment() -> Iterator[None]:
    """Reseed after this module, because downgrading dropped everything.

    Only reseeds if the environment was seeded to begin with — running the
    migration tests against an intentionally empty environment must not
    surprise the caller with data.

    The profile is read **before** the downgrade, because the downgrade drops the
    manifest table it is stored in. Restoring at a hardcoded `smoke` used to turn a
    developer's full dataset into a smoke one without saying so, and every test
    after this module then agreed with the smaller manifest.
    """
    from ..conftest import environment_profile, run_seed_cli

    was_seeded = _has_manifest()
    profile = environment_profile()
    had_credentials = _has_credentials()
    yield
    _alembic("upgrade", "head")
    if was_seeded:
        # `reset`, not `seed`. Downgrading dropped the tables but left object
        # storage and the vector store populated, so the environment is in a mixed
        # state and `seed` would correctly refuse it as non-empty. `reset` is the
        # command for exactly this situation.
        result = run_seed_cli("reset", "--yes", "--profile", profile)
        assert result.returncode == 0, (
            "failed to restore the seeded environment after the destructive "
            f"migration tests: {result.stderr[-1200:]}"
        )
        assert environment_profile() == profile, (
            f"restored the environment at a different profile than it started with "
            f"(was {profile!r})"
        )

    if had_credentials:
        # `reset` truncates `user_credentials` along with every other runtime table, so
        # the restored environment has a complete dataset and nobody who can sign in.
        # Without this, every authentication test that runs after this module — and
        # pytest orders files alphabetically, so that is all of them — skips itself with
        # "no credentials provisioned" and the suite reports success having checked
        # none of them. Twelve tests were doing exactly that before this line existed.
        result = run_seed_cli("credentials")
        assert result.returncode == 0, (
            "failed to re-provision credentials after the destructive migration tests: "
            f"{result.stderr[-1200:]}"
        )
        assert _has_credentials(), "credentials command reported success and wrote none"


def _has_credentials() -> bool:
    try:
        engine = create_engine(_owner_url())
        with engine.connect() as conn:
            return bool(
                conn.execute(text("SELECT count(*) FROM user_credentials")).scalar_one()
            )
    except Exception:  # pragma: no cover - environment guard
        return False


def _has_manifest() -> bool:
    try:
        engine = create_engine(_owner_url())
        with engine.connect() as conn:
            return bool(
                conn.execute(text("SELECT count(*) FROM dataset_manifest")).scalar_one()
            )
    except Exception:
        return False


class TestReversibility:
    def test_upgrade_downgrade_upgrade_is_lossless(self, at_head: None) -> None:
        before = _schema_snapshot()
        assert before, "no tables after upgrade — migration did nothing"

        assert _alembic("downgrade", "base").returncode == 0
        assert _schema_snapshot() == {}, "downgrade left tables behind"

        assert _alembic("upgrade", "head").returncode == 0
        assert _schema_snapshot() == before, "schema differs after a round trip"

    def test_enum_type_is_dropped_and_recreated(self, at_head: None) -> None:
        """The classification enum is a separate object from the tables that use it,
        so a downgrade that forgets it leaves the database unable to re-upgrade."""
        engine = create_engine(_owner_url())

        _alembic("downgrade", "base")
        with engine.connect() as conn:
            remaining = conn.execute(
                text("SELECT 1 FROM pg_type WHERE typname = 'classification_level'")
            ).first()
        assert remaining is None, "classification_level enum survived the downgrade"

        assert _alembic("upgrade", "head").returncode == 0


class TestRowLevelSecurityIsApplied:
    def test_every_tenant_table_has_a_policy(self, at_head: None) -> None:
        """Migration 0002 derives its table list from the metadata, so a newly added
        model gets a policy automatically. This asserts that actually happened."""
        from eaios_core.models import tenant_tables

        engine = create_engine(_owner_url())
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT tablename FROM pg_policies WHERE policyname = 'tenant_isolation'")
            ).fetchall()

        with_policy = {row[0] for row in rows}
        missing = sorted(set(tenant_tables()) - with_policy)
        assert not missing, f"tenant tables without an RLS policy: {missing}"


class TestTheBaselineOwnsOnlyItsOwnTables:
    """Migration 0001 builds the schema from the declarative metadata, which is a
    shortcut with a delayed cost: the metadata is read when the migration *runs*, so
    a model added by a later feature is created twice — once by `create_all` and once
    by the migration that introduces it.

    That is not hypothetical. Adding `contact_submissions` in 0003 made a fresh
    `alembic upgrade head` fail with *relation "contact_submissions" already exists*,
    while every already-migrated database kept working. The schema could not be
    built from scratch and no check said so; `TestReversibility` above caught it only
    because the downgrade failed first.

    `POST_BASELINE_TABLES` is the register that keeps the shortcut safe, and a
    register nobody validates is a comment. These assertions validate it.
    """

    def test_every_registered_name_is_a_real_table(self) -> None:
        from eaios_core.models import POST_BASELINE_TABLES, Base

        unknown = sorted(POST_BASELINE_TABLES - set(Base.metadata.tables))
        assert unknown == [], f"registered but not in the metadata: {unknown}"

    def test_the_baseline_excludes_them(self) -> None:
        from eaios_core.models import POST_BASELINE_TABLES, baseline_tables

        assert not (set(baseline_tables()) & POST_BASELINE_TABLES)

    def test_the_baseline_is_not_empty(self) -> None:
        """Guards the assertion above from passing by excluding everything."""
        from eaios_core.models import baseline_tables

        assert len(baseline_tables()) > 25

    def test_rls_still_covers_the_later_tables(self) -> None:
        """The exclusion is about *when* a policy is applied, never whether. The
        unqualified list — the one `tests/security/test_rls.py` walks — must still
        contain them."""
        from eaios_core.models import POST_BASELINE_TABLES, tenant_tables

        full = set(tenant_tables())
        assert full >= POST_BASELINE_TABLES
        assert not (set(tenant_tables(baseline_only=True)) & POST_BASELINE_TABLES)

    def test_every_later_table_is_created_by_a_migration_of_its_own(self) -> None:
        """A table excluded from the baseline and created nowhere else would exist in
        the models and in no database."""
        versions = ALEMBIC_DIR / "alembic" / "versions"
        sources = "\n".join(
            path.read_text(encoding="utf-8")
            for path in versions.glob("*.py")
            if path.name != "0001_initial_schema.py"
        )
        from eaios_core.models import POST_BASELINE_TABLES

        for table in sorted(POST_BASELINE_TABLES):
            assert f'"{table}"' in sources, f"{table} is created by no migration"


# ---------------------------------------------------------------------------
# T054 — the full sweep, against a database created for it and dropped afterwards
# ---------------------------------------------------------------------------


def _maintenance_url() -> str:
    """A connection to `postgres`, so the sweep's own database can be created.

    As the **superuser**, not the owner: `eaios_owner` deliberately lacks `CREATEDB`, and
    granting it that privilege to run a test would widen the role the application uses
    every day. The superuser exists in the Compose stack for exactly this kind of
    administrative work.
    """
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_HOST_PORT", os.environ.get("POSTGRES_PORT", "5432"))
    user = os.environ.get("POSTGRES_SUPERUSER", "postgres")
    password = os.environ.get(
        "POSTGRES_SUPERUSER_PASSWORD",
        os.environ.get("POSTGRES_OWNER_PASSWORD", "eaios_owner_local_only"),
    )
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/postgres"


def _revisions_in_order() -> list[str]:
    """Every revision file under `alembic/versions/`, oldest first.

    Derived from the filenames, which are numerically prefixed by convention, rather
    than by parsing `down_revision` chains: a sweep that silently skipped a revision it
    failed to parse would report a clean round trip over a subset.
    """
    versions = ALEMBIC_DIR / "alembic" / "versions"
    return sorted(path.stem.split("_")[0] for path in versions.glob("[0-9]*.py"))


@pytest.fixture(scope="module")
def ephemeral_database() -> Iterator[str]:
    """A uniquely named database, created for this sweep and dropped in `finally`.

    **Why not the shared database.** The round trip below ends at `base`, which drops
    every table. `TestReversibility` above does that to the development database and
    reseeds afterwards — an expensive restore that also fails badly if the sweep dies
    partway. Sweeping every revision multiplies both the cost and the blast radius, so
    it gets its own database instead. Nothing here touches the configured one.

    The drop runs in `finally`, including when the sweep fails, because the failure is
    exactly the case that would otherwise leave a stray database behind for every run.
    """
    name = f"eaios_migration_sweep_{uuid.uuid4().hex[:16]}"
    configured = os.environ.get("POSTGRES_DB", "eaios")
    assert name != configured, "the sweep would run against the shared database"

    engine = create_engine(_maintenance_url(), isolation_level="AUTOCOMMIT")
    try:
        owner = os.environ.get("POSTGRES_OWNER_USER", "eaios_owner")
        with engine.connect() as conn:
            # Owned by the application's owner role, because alembic connects as that
            # role and would otherwise be unable to create anything in it.
            conn.execute(text(f'CREATE DATABASE "{name}" OWNER "{owner}"'))
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"cannot create an ephemeral database: {exc}")

    try:
        yield name
    finally:
        with engine.connect() as conn:
            # Terminate first: alembic's connection may linger, and `DROP DATABASE`
            # fails while any session is attached. Leaving the database behind on a
            # failed sweep is the litter this fixture exists to prevent.
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity"
                    " WHERE datname = :name AND pid <> pg_backend_pid()"
                ),
                {"name": name},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))


def _snapshot_of(database: str) -> dict[str, list[str]]:
    engine = create_engine(_owner_url().rsplit("/", 1)[0] + f"/{database}")
    inspector = inspect(engine)
    snapshot = {
        table: sorted(col["name"] for col in inspector.get_columns(table))
        for table in sorted(inspector.get_table_names())
        if table != "alembic_version"
    }
    engine.dispose()
    return snapshot


class TestEveryRevisionRoundTrips:
    """Up, down, up — over **every** revision, not only the newest.

    `TestReversibility` proves the head round trip. That leaves the older `downgrade()`
    bodies unexercised, and an untested downgrade is a rollback plan nobody has run. The
    sweep is serial by construction: each step depends on the state the last one left.
    """

    def test_the_sweep_has_revisions_to_walk(self, ephemeral_database: str) -> None:
        """Vacuity guard: a sweep over nothing round-trips perfectly."""
        assert len(_revisions_in_order()) >= 4, _revisions_in_order()

    def test_the_full_round_trip_is_lossless(self, ephemeral_database: str) -> None:
        assert _alembic("upgrade", "head", database=ephemeral_database).returncode == 0
        before = _snapshot_of(ephemeral_database)
        assert before, "upgrade produced no tables"

        assert _alembic("downgrade", "base", database=ephemeral_database).returncode == 0
        assert _snapshot_of(ephemeral_database) == {}, "downgrade left tables behind"

        assert _alembic("upgrade", "head", database=ephemeral_database).returncode == 0
        assert _snapshot_of(ephemeral_database) == before, (
            "the schema after down-then-up differs from the schema before it"
        )

    def test_each_revision_steps_down_and_back_up(self, ephemeral_database: str) -> None:
        """One revision at a time, so a failure names the migration that broke.

        A single head→base→head pass would fail as one line whichever `downgrade()` is
        wrong, and the whole point of sweeping is to say which.
        """
        revisions = _revisions_in_order()
        assert _alembic("upgrade", "head", database=ephemeral_database).returncode == 0

        for revision in reversed(revisions):
            at_revision = _snapshot_of(ephemeral_database)

            down = _alembic("downgrade", "-1", database=ephemeral_database)
            assert down.returncode == 0, (
                f"downgrading past revision {revision} failed:\n{down.stderr[-800:]}"
            )
            after_down = _snapshot_of(ephemeral_database)

            up = _alembic("upgrade", "+1", database=ephemeral_database)
            assert up.returncode == 0, (
                f"re-upgrading to revision {revision} failed:\n{up.stderr[-800:]}"
            )
            assert _snapshot_of(ephemeral_database) == at_revision, (
                f"revision {revision} is not reversible: the schema after down-then-up"
                " differs from the schema before it"
            )

            assert _alembic("downgrade", "-1", database=ephemeral_database).returncode == 0
            assert _snapshot_of(ephemeral_database) == after_down

        assert _snapshot_of(ephemeral_database) == {}, "the sweep did not reach base"
        assert _alembic("upgrade", "head", database=ephemeral_database).returncode == 0


class TestTheSweepLeavesNothingBehind:
    def test_the_ephemeral_name_is_not_the_configured_database(
        self, ephemeral_database: str
    ) -> None:
        assert ephemeral_database != os.environ.get("POSTGRES_DB", "eaios")
        assert ephemeral_database.startswith("eaios_migration_sweep_")

    def test_no_sweep_database_survives_from_an_earlier_run(
        self, ephemeral_database: str
    ) -> None:
        """A stray database per failed run is the litter the `finally` prevents; this
        notices if it ever stops working.

        This run's own database is excluded — it is alive by design while the
        module-scoped fixture is in scope, and its removal is asserted separately once
        the fixture has torn down.
        """
        engine = create_engine(_maintenance_url(), isolation_level="AUTOCOMMIT")
        with engine.connect() as conn:
            names = [
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT datname FROM pg_database"
                        " WHERE datname LIKE 'eaios_migration_sweep_%'"
                    )
                )
            ]
        engine.dispose()
        stale = [name for name in names if name != ephemeral_database]
        assert stale == [], f"ephemeral databases left behind: {stale}"

    def test_the_shared_database_still_has_its_tables(self, ephemeral_database: str) -> None:
        """The sweep ran; the configured database must be untouched by it."""
        assert _schema_snapshot(), "the shared database lost its schema to the sweep"
