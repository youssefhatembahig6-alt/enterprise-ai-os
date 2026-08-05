"""Contact submissions are actually deleted after 90 days (spec 002 FR-024b).

The requirement had a notice and no mechanism: `ContactForm.tsx` told every visitor
"we delete them after 90 days" while nothing in the API, the worker, or the seed
deleted anything. The convergence run found it by grepping for a purge and finding
only a test's cleanup fixture.

**The boundary is the whole behaviour.** A purge that deleted every row would
satisfy any check that merely counted rows afterwards, and a purge that deleted
nothing would satisfy any check that only asserted it ran without error. So each
case here places rows on both sides of the cutoff and asserts which survived —
never just how many.
"""

from __future__ import annotations

import datetime as dt
import os
import pathlib
import textwrap
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text

pytestmark = pytest.mark.integration

MARKER = "retention-probe@example.com"


@pytest.fixture(scope="module")
def engine() -> Engine:
    from eaios_core.db import create_owner_engine

    engine = create_owner_engine()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT count(*) FROM contact_submissions"))
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"database unavailable: {exc}")
    return engine


@pytest.fixture
def clean(engine: Engine) -> Iterator[None]:
    def purge() -> None:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM contact_submissions WHERE sender_email = :e"), {"e": MARKER}
            )

    purge()
    yield
    purge()


def _company_id() -> uuid.UUID:
    from eaios_core.constants import NILETECH
    from eaios_core.ids import derive

    return derive("company", NILETECH, NILETECH)


def _insert(engine: Engine, *, subject: str, age_days: float, now: dt.datetime) -> None:
    """Write one submission `age_days` old. Owner role — RLS does not apply."""
    submitted = now - dt.timedelta(days=age_days)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO contact_submissions (id, company_id, sender_name, sender_email,"
                " subject, message, content_hash, submitted_at, created_at, updated_at)"
                " VALUES (:id, :company, 'Retention Probe', :email, :subject, 'body',"
                " :digest, :at, :at, :at)"
            ),
            {
                "id": uuid.uuid4(),
                "company": _company_id(),
                "email": MARKER,
                "subject": subject,
                "digest": uuid.uuid4().hex[:16].ljust(64, "0"),
                "at": submitted,
            },
        )


def _surviving(engine: Engine) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT subject FROM contact_submissions WHERE sender_email = :e"), {"e": MARKER}
        ).scalars()
        return set(rows)


class TestTheWindowIsRespected:
    def test_an_aged_submission_is_deleted_and_a_recent_one_is_not(
        self, engine: Engine, clean: None
    ) -> None:
        from eaios_worker.tasks.retention import purge_contact_submissions

        now = dt.datetime.now(tz=dt.UTC)
        _insert(engine, subject="aged", age_days=120, now=now)
        _insert(engine, subject="recent", age_days=3, now=now)

        deleted = purge_contact_submissions(str(_company_id()), engine=engine, now=now)

        assert deleted == 1
        assert _surviving(engine) == {"recent"}

    def test_the_boundary_falls_on_the_correct_side(self, engine: Engine, clean: None) -> None:
        """89 days stays, 91 days goes. Asserting only "old rows are deleted" would
        pass with the comparison inverted by a day, a sign, or a unit."""
        from eaios_worker.tasks.retention import RETENTION_DAYS, purge_contact_submissions

        now = dt.datetime.now(tz=dt.UTC)
        _insert(engine, subject="just-inside", age_days=RETENTION_DAYS - 1, now=now)
        _insert(engine, subject="just-outside", age_days=RETENTION_DAYS + 1, now=now)

        purge_contact_submissions(str(_company_id()), engine=engine, now=now)

        assert _surviving(engine) == {"just-inside"}

    def test_it_deletes_nothing_when_nothing_has_aged(self, engine: Engine, clean: None) -> None:
        """Guards against a purge that empties the table. A retention job that
        deleted a visitor's message the day they sent it would pass a test that only
        checked aged rows were gone."""
        from eaios_worker.tasks.retention import purge_contact_submissions

        now = dt.datetime.now(tz=dt.UTC)
        for day in (0, 5, 30):
            _insert(engine, subject=f"day-{day}", age_days=day, now=now)

        deleted = purge_contact_submissions(str(_company_id()), engine=engine, now=now)

        assert deleted == 0
        assert _surviving(engine) == {"day-0", "day-5", "day-30"}


class TestTheCheckCanFail:
    """Every assertion above rests on the fixture actually writing rows."""

    def test_the_fixture_inserts_what_the_purge_reads(self, engine: Engine, clean: None) -> None:
        now = dt.datetime.now(tz=dt.UTC)
        _insert(engine, subject="present", age_days=1, now=now)
        assert _surviving(engine) == {"present"}


class TestScopeAndScheduling:
    def test_another_tenant_is_untouched(self, engine: Engine, clean: None) -> None:
        """The purge runs as the owner role, which RLS does not constrain, so its
        tenant predicate is the only thing keeping it inside one company."""
        from eaios_core.constants import DELTA_RETAIL
        from eaios_core.ids import derive
        from eaios_worker.tasks.retention import purge_contact_submissions

        now = dt.datetime.now(tz=dt.UTC)
        _insert(engine, subject="niletech-aged", age_days=120, now=now)

        other = derive("company", DELTA_RETAIL, DELTA_RETAIL)
        deleted = purge_contact_submissions(str(other), engine=engine, now=now)

        assert deleted == 0
        assert _surviving(engine) == {"niletech-aged"}

    def test_the_purge_is_scheduled_for_every_tenant(self) -> None:
        """An unscheduled purge is one that runs when somebody remembers to run it."""
        from eaios_core.constants import COMPANY_SLUGS
        from eaios_worker.celery_app import celery_app

        schedule = celery_app.conf.beat_schedule
        scheduled = {
            entry["kwargs"]["company_slug"]
            for entry in schedule.values()
            if entry["task"] == "eaios.retention.purge_expired_submissions"
        }
        assert scheduled == set(COMPANY_SLUGS)

    def test_the_scheduled_task_name_is_actually_registered(self) -> None:
        """A beat entry naming a task the app never registered fails at runtime and
        nowhere else: the configuration reads correctly and the purge simply never
        happens.

        That is not hypothetical — it was the state of this code minutes ago.
        `autodiscover_tasks(["eaios_worker.tasks"])` made Celery look for
        `eaios_worker.tasks.tasks`, registered nothing, and the deployed worker
        reported `celery_app.tasks == []` while the schedule looked fine.

        **Run in a fresh interpreter, deliberately.** The first version of this
        assertion passed against the broken code, because a sibling test in this
        module had already imported the task module and registered it as a side
        effect. In-process, this check could not fail. A subprocess is also what the
        worker actually does: start, import, register.
        """
        import subprocess
        import sys

        probe = textwrap.dedent("""
            from eaios_worker.celery_app import celery_app

            schedule = celery_app.conf.beat_schedule.values()
            missing = [e["task"] for e in schedule if e["task"] not in celery_app.tasks]
            print("MISSING" if missing else "OK", missing)
        """)
        result = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True,
            text=True,
            check=False,
            # pytest builds the import path from `pyproject.toml`; a bare subprocess
            # inherits none of it and would fail to import for a reason that has
            # nothing to do with task registration.
            env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.startswith("OK"), (
            f"scheduled tasks are not registered in a fresh interpreter: {result.stdout.strip()}"
        )

    def test_the_fresh_interpreter_probe_can_fail(self) -> None:
        """Guards the subprocess check itself. If the probe silently failed to
        import, `returncode == 0` would be the only thing standing between a broken
        schedule and a green suite — so confirm a bad task name is caught."""
        import subprocess
        import sys

        probe = textwrap.dedent("""
            from eaios_worker.celery_app import celery_app

            print("MISSING" if "eaios.nonexistent" not in celery_app.tasks else "OK")
        """)
        result = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True,
            text=True,
            check=False,
            # pytest builds the import path from `pyproject.toml`; a bare subprocess
            # inherits none of it and would fail to import for a reason that has
            # nothing to do with task registration.
            env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.startswith("MISSING")

    def test_the_window_matches_what_the_visitor_is_told(self) -> None:
        """FR-024b requires the retention period to be *stated* in the notice. If
        these two ever disagree, the site is lying to the people it collects data
        from — and nothing else in the suite compares them."""
        import pathlib
        import re

        from eaios_worker.tasks.retention import RETENTION_DAYS

        notice = (
            pathlib.Path(__file__).resolve().parents[1]
            / ".."
            / "apps"
            / "web"
            / "components"
            / "ContactForm.tsx"
        ).resolve()
        text_content = notice.read_text(encoding="utf-8")

        stated = re.search(r"after (\d+) days", text_content)
        assert stated, "the contact form states no retention period"
        assert int(stated.group(1)) == RETENTION_DAYS


class TestThePurgeIsAudited:
    """Constitution Principle X — erasing a visitor's record is a consequential
    operation and must leave evidence.

    The first version of this task wrote a structlog line and no `audit_logs` row.
    Personal data disappeared on a schedule with nothing an auditor could read, and
    every test in this file passed: they all asked whether the right rows were
    deleted, never whether the deletion was recorded.
    """

    @staticmethod
    def _entries(engine: Engine) -> list[tuple[str, str, str, str]]:
        from eaios_worker.tasks.retention import RETENTION_ACTION

        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT actor_type, resource_type, resource_id, reason, decision"
                    " FROM audit_logs WHERE action = :a ORDER BY created_at DESC"
                ),
                {"a": RETENTION_ACTION},
            ).all()
        return [tuple(row) for row in rows]  # type: ignore[misc]

    def test_a_purge_writes_an_entry(self, engine: Engine, clean: None) -> None:
        from eaios_worker.tasks.retention import purge_contact_submissions

        now = dt.datetime.now(tz=dt.UTC)
        _insert(engine, subject="aged", age_days=120, now=now)
        before = len(self._entries(engine))

        purge_contact_submissions(str(_company_id()), engine=engine, now=now)

        assert len(self._entries(engine)) == before + 1

    def test_a_run_that_deletes_nothing_still_writes_one(
        self, engine: Engine, clean: None
    ) -> None:
        """The distinction the record exists to make. Without an entry, "the job ran
        and found nothing" is indistinguishable from "the job never ran" — which is
        the exact failure this feature has already hit twice, at the task-registration
        layer and at the scheduler layer."""
        from eaios_worker.tasks.retention import purge_contact_submissions

        now = dt.datetime.now(tz=dt.UTC)
        before = len(self._entries(engine))

        deleted = purge_contact_submissions(str(_company_id()), engine=engine, now=now)

        assert deleted == 0
        assert len(self._entries(engine)) == before + 1

    def test_the_entry_carries_what_principle_x_requires(
        self, engine: Engine, clean: None
    ) -> None:
        from eaios_worker.tasks.retention import purge_contact_submissions

        now = dt.datetime.now(tz=dt.UTC)
        _insert(engine, subject="aged", age_days=120, now=now)
        purge_contact_submissions(str(_company_id()), engine=engine, now=now)

        actor_type, resource_type, resource_id, reason, decision = self._entries(engine)[0]
        assert actor_type == "SYSTEM"
        assert resource_type == "contact_submissions"
        assert decision == "ALLOW"
        assert "1 deleted" in reason
        assert resource_id and "submitted_at<" in resource_id

    def test_the_entry_carries_no_personal_data(self, engine: Engine, clean: None) -> None:
        """FR-024c. The purge knows every sender it is about to erase, which makes
        this the easiest place in the system to leak one."""
        from eaios_worker.tasks.retention import purge_contact_submissions

        now = dt.datetime.now(tz=dt.UTC)
        _insert(engine, subject="Highly-Distinctive-Subject", age_days=120, now=now)
        purge_contact_submissions(str(_company_id()), engine=engine, now=now)

        blob = " ".join(str(value) for value in self._entries(engine)[0])
        assert MARKER not in blob
        assert "Highly-Distinctive-Subject" not in blob
        assert "Retention Probe" not in blob

    def test_the_entry_is_scoped_to_the_tenant_it_purged(
        self, engine: Engine, clean: None
    ) -> None:
        from eaios_worker.tasks.retention import RETENTION_ACTION, purge_contact_submissions

        now = dt.datetime.now(tz=dt.UTC)
        purge_contact_submissions(str(_company_id()), engine=engine, now=now)

        with engine.connect() as conn:
            company = conn.execute(
                text(
                    "SELECT company_id FROM audit_logs WHERE action = :a"
                    " ORDER BY created_at DESC LIMIT 1"
                ),
                {"a": RETENTION_ACTION},
            ).scalar_one()
        assert company == _company_id()

    def test_the_delete_and_the_entry_share_a_transaction(
        self, engine: Engine, clean: None
    ) -> None:
        """Rows must never disappear without the record of it. Asserted by counting
        both sides of one run rather than by inspecting the code."""
        from eaios_worker.tasks.retention import purge_contact_submissions

        now = dt.datetime.now(tz=dt.UTC)
        for index in range(3):
            _insert(engine, subject=f"aged-{index}", age_days=120, now=now)
        entries_before = len(self._entries(engine))

        deleted = purge_contact_submissions(str(_company_id()), engine=engine, now=now)

        assert deleted == 3
        assert _surviving(engine) == set()
        assert len(self._entries(engine)) == entries_before + 1


class TestTheSchedulerActuallyRuns:
    """FR-024b — something has to read the schedule.

    `test_the_purge_is_scheduled_for_every_tenant` asserts that `beat_schedule`
    contains the right entries. That was true from the moment the constant was
    written, and it stayed true while the deployed command was
    `celery -A eaios_worker.celery_app worker --loglevel=info` — a worker with no
    scheduler. The task was registered, the schedule was correct, and the purge could
    never fire. Two layers of this feature had already failed the same way: a beat
    entry naming an unregistered task, then a schedule no process read.

    So these assertions read the **deployment artifacts** rather than the config
    object. They are static, and that is the point: the config object cannot tell you
    what command the container runs.
    """

    @staticmethod
    def _repo() -> pathlib.Path:
        import pathlib as _p

        return _p.Path(__file__).resolve().parents[2]

    def test_the_worker_command_starts_a_scheduler(self) -> None:
        dockerfile = (self._repo() / "services/worker/Dockerfile").read_text(encoding="utf-8")
        command = [line for line in dockerfile.splitlines() if line.startswith("CMD")]

        assert command, "the worker Dockerfile declares no CMD"
        assert any("--beat" in line or '"beat"' in line for line in command), (
            f"the worker runs no scheduler, so beat_schedule is never read: {command}"
        )

    def test_compose_does_not_override_the_command(self) -> None:
        """A `command:` in Compose silently replaces the Dockerfile's CMD, which would
        undo the assertion above without touching the file it reads."""
        compose = (self._repo() / "infrastructure/docker-compose.yml").read_text(encoding="utf-8")

        worker = compose.split("\n  worker:", 1)
        assert len(worker) == 2, "no worker service found in the compose file"
        block = worker[1].split("\n  web:", 1)[0]

        assert "command:" not in block or "beat" in block, (
            "compose overrides the worker command without starting a scheduler"
        )

    def test_the_artifact_check_reads_the_real_files(self) -> None:
        """Guards both assertions above: a wrong path would make them vacuous."""
        assert (self._repo() / "services/worker/Dockerfile").exists()
        assert (self._repo() / "infrastructure/docker-compose.yml").exists()
        assert "celery" in (self._repo() / "services/worker/Dockerfile").read_text(encoding="utf-8")

    def test_the_scheduler_writes_where_it_can(self) -> None:
        """Beat exits at startup if it cannot create its schedule database, and the
        image's working directory is not writable — so a missing `--schedule` path
        turns "scheduler runs" back into "scheduler does not run"."""
        dockerfile = (self._repo() / "services/worker/Dockerfile").read_text(encoding="utf-8")
        assert "--schedule=" in dockerfile
