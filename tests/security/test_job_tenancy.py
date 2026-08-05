"""Background jobs carry their tenant (spec FR-042, Constitution Principle I).

The worker runs no business tasks in this feature, so `job_records` is empty and
the tenant-attribution contract had never been exercised. An unexercised contract
is an assumption, not a guarantee — the first real task would be the thing that
discovers whether it works.

Tasks are registered against the real Celery app and run eagerly. Calling
``Task.__call__`` on an unbound instance works for the rejection paths — the guard
raises before delegating — but the accept path needs Celery's request stack, and a
test that only ever exercises the failure branch would not prove the guard lets
legitimate work through.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import Engine, text

from eaios_core.tenancy import COMPANY_SLUGS
from eaios_worker.celery_app import celery_app
from eaios_worker.tasks.base import TenantTask

pytestmark = pytest.mark.security

# Run tasks in-process and let exceptions surface, so the guard can be observed
# directly rather than through a broker.
celery_app.conf.task_always_eager = True
celery_app.conf.task_eager_propagates = True

#: Records every invocation that reached the task body.
CALLS: list[dict[str, Any]] = []


@celery_app.task(base=TenantTask, name="test.recording", bind=False)
def recording(**kwargs: Any) -> str:
    CALLS.append(kwargs)
    return "ran"


@celery_app.task(base=TenantTask, name="test.failing", bind=False)
def failing(**kwargs: Any) -> None:
    raise RuntimeError("boom")


@pytest.fixture(autouse=True)
def _reset_calls() -> None:
    CALLS.clear()


class TestTenantIsRequired:
    def test_an_invocation_without_a_tenant_is_refused(self) -> None:
        with pytest.raises(ValueError, match="company_slug"):
            recording.apply(kwargs={"payload": "anything"}).get()
        assert CALLS == [], "the task body ran despite having no tenant"

    def test_the_error_names_the_requirement(self) -> None:
        with pytest.raises(ValueError, match="attributable"):
            recording.apply(kwargs={}).get()

    def test_an_unknown_tenant_is_refused(self) -> None:
        with pytest.raises(ValueError, match="unknown company"):
            recording.apply(kwargs={"company_slug": "acme"}).get()
        assert CALLS == []

    @pytest.mark.parametrize("slug", COMPANY_SLUGS)
    def test_a_known_tenant_is_accepted(self, slug: str) -> None:
        assert recording.apply(kwargs={"company_slug": slug}).get() == "ran"
        assert [{"company_slug": slug}] == CALLS


class TestContextIsCleanedUp:
    def test_the_tenant_binding_does_not_outlive_the_task(self) -> None:
        """A worker process handles many tenants in sequence. A binding that
        survives would attribute the next job to the previous tenant."""
        import structlog

        recording.apply(kwargs={"company_slug": "niletech"}).get()
        assert structlog.contextvars.get_contextvars() == {}

    def test_the_binding_is_cleared_even_when_the_task_raises(self) -> None:
        import structlog

        with pytest.raises(RuntimeError, match="boom"):
            failing.apply(kwargs={"company_slug": "niletech"}).get()
        assert structlog.contextvars.get_contextvars() == {}


class TestJobRecordsAreTenantScoped:
    def test_the_table_requires_a_company(self, owner_engine: Engine) -> None:
        with owner_engine.connect() as conn:
            nullable = conn.execute(
                text(
                    "SELECT is_nullable FROM information_schema.columns"
                    " WHERE table_name = 'job_records' AND column_name = 'company_id'"
                )
            ).scalar_one()
        assert nullable == "NO"

    def test_a_job_record_can_be_written_and_is_scoped(
        self, owner_engine: Engine, company_ids: dict[str, uuid.UUID]
    ) -> None:
        """Exercises the write path end to end, then cleans up after itself."""
        from eaios_core.clock import reference_datetime
        from eaios_core.ids import derive

        job_id = derive("job_record", "niletech", "test:tenancy")
        now = reference_datetime()
        try:
            with owner_engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO job_records"
                        " (id, company_id, job_name, status, created_at)"
                        " VALUES (:id, :cid, 'test.tenancy', 'SUCCEEDED', :now)"
                    ),
                    {"id": job_id, "cid": company_ids["niletech"], "now": now},
                )

            with owner_engine.connect() as conn:
                stored = conn.execute(
                    text("SELECT company_id FROM job_records WHERE id = :id"), {"id": job_id}
                ).scalar_one()
            assert stored == company_ids["niletech"]
        finally:
            with owner_engine.begin() as conn:
                conn.execute(text("DELETE FROM job_records WHERE id = :id"), {"id": job_id})

    def test_job_records_carry_an_rls_policy(self, owner_engine: Engine) -> None:
        with owner_engine.connect() as conn:
            policies = conn.execute(
                text(
                    "SELECT count(*) FROM pg_policies"
                    " WHERE tablename = 'job_records' AND policyname = 'tenant_isolation'"
                )
            ).scalar_one()
        assert policies == 1
