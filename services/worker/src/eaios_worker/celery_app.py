"""Celery application.

The worker was introduced so the Compose stack is complete and so the
tenant-attribution contract for jobs is established before any real job is written
(spec FR-042). It now carries one scheduled job: the contact-submission retention
purge that spec 002 FR-024b requires and that the contact form already promises to
every visitor.
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from eaios_core.constants import COMPANY_SLUGS
from eaios_core.logging import configure_logging
from eaios_core.settings import get_settings

settings = get_settings()
configure_logging(level=settings.log_level, json_output=settings.log_json)

celery_app = Celery(
    "eaios",
    broker=settings.redis.url,
    backend=settings.redis.url,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    # Fail loudly rather than silently retrying forever; a stuck job that looks
    # like a slow job is harder to notice than one that errored.
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

#: FR-024b — retention runs on a schedule, because a purge that only runs when
#: someone remembers to run it is not a retention policy.
#:
#: Scheduled per tenant rather than once globally. `TenantTask` requires a
#: `company_slug` and the purge writes an explicit tenant predicate (it runs as the
#: owner role, which RLS does not constrain), so "every tenant" has to be spelled
#: out. Derived from `COMPANY_SLUGS` so a third tenant is covered by construction.
#:
#: 03:15 UTC is arbitrary but deliberate: off the hour, so it does not contend with
#: everything else in the world that runs at midnight.
celery_app.conf.beat_schedule = {
    f"purge-contact-submissions-{slug}": {
        "task": "eaios.retention.purge_expired_submissions",
        "schedule": crontab(hour="3", minute="15"),
        "kwargs": {"company_slug": slug},
    }
    for slug in COMPANY_SLUGS
}

# Registration is an explicit import, not autodiscovery.
#
# `autodiscover_tasks(["eaios_worker.tasks"])` was here and registered nothing: the
# argument names *packages*, and Celery appends the related name, so it looked for
# `eaios_worker.tasks.tasks`. The `beat_schedule` above then named a task that did
# not exist, and beat would have dispatched into nothing on a schedule. Autodiscovery
# is also lazy — it runs when a worker finalizes the app, so `celery_app.tasks` stays
# empty on import and the mistake is invisible to anything that merely imports this
# module.
#
# Placed at the bottom because task modules import `celery_app` from here; by this
# line it is bound, so the partially-initialized module already carries what they
# need.
from . import tasks as _tasks  # noqa: E402,F401  (imported for its registration side effect)

__all__ = ["celery_app"]
