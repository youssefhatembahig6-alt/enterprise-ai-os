# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TZ=UTC \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY packages/core/pyproject.toml packages/core/pyproject.toml
COPY services/worker/pyproject.toml services/worker/pyproject.toml
COPY packages/core/src packages/core/src
COPY services/worker/src services/worker/src

RUN pip install --no-cache-dir ./packages/core ./services/worker

# `-B` embeds the beat scheduler in this worker process.
#
# Without it, `celery_app.conf.beat_schedule` is configuration that no process ever
# reads: the FR-024b retention purge was registered, scheduled, and unable to fire,
# because the command started a worker and nothing started a scheduler.
#
# Embedded rather than a second service, for this stack specifically. Celery advises
# against `-B` in production because every worker node runs its own scheduler, so N
# nodes produce N copies of each run. This stack runs exactly **one** worker, whose
# healthcheck targets its own node — and an embedded beat failure takes that process
# down, which the healthcheck then reports. A separate beat container would need a
# liveness check of its own, and a beat that had quietly died in a container marked
# healthy is the failure this flag exists to avoid repeating.
#
# If a worker replica is ever added, this must become a dedicated beat service.
# `tests/integration/test_retention.py::TestTheSchedulerActuallyRuns` asserts against
# this line, so the requirement cannot be met by configuration alone again.
#
# The schedule database goes to /tmp: the working directory is not writable, and beat
# exits on startup if it cannot create the file.
CMD ["celery", "-A", "eaios_worker.celery_app", "worker", "--beat",      "--schedule=/tmp/celerybeat-schedule", "--loglevel=info"]
