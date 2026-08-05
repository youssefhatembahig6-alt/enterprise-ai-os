"""Tenant-attributed task base (spec FR-042).

Every background job records the ``company_id`` of the work it performs. Enforcing
that here rather than at each call site means a future task cannot quietly run
without a tenant — the job record simply cannot be written without one.
"""

from __future__ import annotations

import uuid
from typing import Any

from celery import Task

from eaios_core.clock import reference_datetime
from eaios_core.db import create_app_engine, session_scope
from eaios_core.ids import derive
from eaios_core.logging import bind_company, clear_context, get_logger
from eaios_core.models import JobRecord
from eaios_core.tenancy import require_company

logger = get_logger(__name__)

__all__ = ["TenantTask", "record_job"]


class TenantTask(Task):  # type: ignore[misc]  # Celery ships no type stubs
    """Base for every task. Requires an explicit tenant.

    ``company_slug`` is a required keyword, so a task that forgets it fails at call
    time rather than running unattributed and being discovered later by audit.
    """

    abstract = True

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        company_slug = kwargs.get("company_slug")
        if company_slug is None:
            raise ValueError(
                f"{self.name} was invoked without company_slug; every job must be "
                "attributable to exactly one tenant (spec FR-042)"
            )
        require_company(company_slug)
        bind_company(company_slug)
        try:
            return super().__call__(*args, **kwargs)
        finally:
            clear_context()


def record_job(
    *,
    company_id: uuid.UUID,
    company_slug: str,
    job_name: str,
    status: str,
    error: str | None = None,
) -> None:
    """Persist a job record carrying its tenant."""
    engine = create_app_engine()
    now = reference_datetime()
    with session_scope(engine) as session:
        session.add(
            JobRecord(
                id=derive("job_record", company_slug, f"{job_name}:{now.isoformat()}"),
                company_id=company_id,
                job_name=job_name,
                status=status,
                started_at=now,
                finished_at=now if status in {"SUCCEEDED", "FAILED"} else None,
                error=error,
                created_at=now,
            )
        )
    logger.info("job.recorded", job_name=job_name, status=status, company=company_slug)
