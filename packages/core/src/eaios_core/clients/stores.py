"""Client factories and reachability probes for every backing service.

Each probe is deliberately cheap and independently timed, so ``/health/ready`` can
report per-dependency status rather than a single opaque boolean (spec FR-003).

Five services, not four. US1 acceptance scenario 3 names the background worker
alongside the relational store, vector store, cache, and object store, and the
worker was the one the endpoint could not see: Compose's own healthcheck knew when
it was wedged, but the response an operator actually reads showed four green rows
and said nothing about it.
"""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from typing import Literal

import redis as redis_lib
from minio import Minio
from qdrant_client import QdrantClient

from ..settings import Settings, get_settings

__all__ = [
    "DependencyName",
    "DependencyStatus",
    "check_minio",
    "check_postgres",
    "check_qdrant",
    "check_redis",
    "check_worker",
    "get_minio",
    "get_qdrant",
    "get_redis",
]

DependencyName = Literal["postgres", "redis", "qdrant", "minio", "worker"]


@dataclass(frozen=True, slots=True)
class DependencyStatus:
    name: DependencyName
    status: Literal["up", "down", "timeout"]
    latency_ms: int
    detail: str | None = None


def get_redis(settings: Settings | None = None) -> redis_lib.Redis:
    cfg = (settings or get_settings()).redis
    return redis_lib.Redis(host=cfg.host, port=cfg.port, db=cfg.db, decode_responses=True)


def get_qdrant(settings: Settings | None = None) -> QdrantClient:
    cfg = (settings or get_settings()).qdrant
    return QdrantClient(host=cfg.host, port=cfg.port)


def get_minio(settings: Settings | None = None) -> Minio:
    cfg = (settings or get_settings()).minio
    return Minio(
        cfg.endpoint,
        access_key=cfg.access_key,
        secret_key=cfg.secret_key.get_secret_value(),
        secure=cfg.secure,
    )


def check_postgres(settings: Settings | None = None) -> DependencyStatus:
    from sqlalchemy import text

    from ..db import create_app_engine

    cfg = settings or get_settings()
    started = _perf()
    try:
        engine = create_app_engine(cfg, connect_args={"connect_timeout": int(cfg.health_timeout_seconds)})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return DependencyStatus("postgres", "up", _elapsed_ms(started))
    except Exception as exc:
        return DependencyStatus("postgres", _classify(exc), _elapsed_ms(started), _safe_detail(exc))


def check_redis(settings: Settings | None = None) -> DependencyStatus:
    cfg = settings or get_settings()
    started = _perf()
    try:
        client = redis_lib.Redis(
            host=cfg.redis.host,
            port=cfg.redis.port,
            db=cfg.redis.db,
            socket_timeout=cfg.health_timeout_seconds,
            socket_connect_timeout=cfg.health_timeout_seconds,
        )
        client.ping()
        return DependencyStatus("redis", "up", _elapsed_ms(started))
    except Exception as exc:
        return DependencyStatus("redis", _classify(exc), _elapsed_ms(started), _safe_detail(exc))


def check_qdrant(settings: Settings | None = None) -> DependencyStatus:
    cfg = settings or get_settings()
    started = _perf()
    try:
        client = QdrantClient(
            host=cfg.qdrant.host, port=cfg.qdrant.port, timeout=int(cfg.health_timeout_seconds)
        )
        client.get_collections()
        return DependencyStatus("qdrant", "up", _elapsed_ms(started))
    except Exception as exc:
        return DependencyStatus("qdrant", _classify(exc), _elapsed_ms(started), _safe_detail(exc))


def check_minio(settings: Settings | None = None) -> DependencyStatus:
    cfg = settings or get_settings()
    started = _perf()
    try:
        get_minio(cfg).bucket_exists(cfg.minio.bucket)
        return DependencyStatus("minio", "up", _elapsed_ms(started))
    except Exception as exc:
        return DependencyStatus("minio", _classify(exc), _elapsed_ms(started), _safe_detail(exc))


def check_worker(settings: Settings | None = None) -> DependencyStatus:
    """Ask any running Celery worker to answer over the broker (US1/AC3, FR-042).

    `control.ping` is a broadcast with a bounded timeout, so a worker that has died
    or wedged reports `down` within that budget instead of hanging the readiness
    response. An empty reply list is the interesting case and the reason this is a
    real probe rather than a formality: the broker answers happily while no worker
    is consuming, which is exactly the partial-start FR-003 exists to expose.

    A broker that is itself unreachable also surfaces here, and that is correct —
    an unreachable worker is unusable whatever the cause. `check_redis` reports the
    broker separately, so the pair tells an operator which of the two failed.

    Celery is imported lazily. The seed and the migrations import this module
    transitively and must not pay for a broker library they never call.
    """
    from celery import Celery

    cfg = settings or get_settings()
    started = _perf()
    app: Celery | None = None
    try:
        app = Celery("eaios-health", broker=cfg.redis.url)
        app.conf.broker_connection_retry_on_startup = False
        app.conf.broker_connection_timeout = cfg.health_timeout_seconds
        # `limit=1` returns on the first reply. Without it the broadcast keeps
        # collecting for the whole timeout window even after a worker has answered,
        # so a perfectly healthy stack paid the full budget on every readiness call.
        replies = app.control.ping(timeout=cfg.health_timeout_seconds, limit=1) or []
        if not replies:
            return DependencyStatus(
                "worker", "down", _elapsed_ms(started), "no worker answered the ping"
            )
        return DependencyStatus("worker", "up", _elapsed_ms(started))
    except Exception as exc:
        return DependencyStatus("worker", _classify(exc), _elapsed_ms(started), _safe_detail(exc))
    finally:
        if app is not None:
            with suppress(Exception):
                app.close()


# --------------------------------------------------------------------------
# Timing helpers.
#
# perf_counter is a monotonic duration measurement, not a wall clock, and it never
# influences generated content — but the static guard in test_no_wallclock.py bans
# `time.*` outright in generation code, so it lives here in the clients module
# (which the guard does not cover) rather than being special-cased.
# --------------------------------------------------------------------------


def _perf() -> float:
    import time as _time

    return _time.perf_counter()


def _elapsed_ms(started: float) -> int:
    return max(0, int((_perf() - started) * 1000))


def _safe_detail(exc: Exception) -> str:
    """Summarise a failure without echoing credentials or connection strings.

    Health responses are unauthenticated; leaking a DSN here would be a real
    disclosure (see checklists/architecture.md CHK017).
    """
    return type(exc).__name__


def _classify(exc: Exception) -> Literal["down", "timeout"]:
    """Distinguish "did not answer in time" from "refused or failed".

    The contract documents both statuses, and they mean different things to an
    operator: a refused connection usually means the service is not up, while a
    timeout usually means it is up but saturated or wedged. Collapsing them into
    `down` made a documented value unreachable (converge finding F6).

    Detection is by exception-type name rather than by importing every driver's
    exception hierarchy — the four clients raise unrelated types for the same
    condition, and this keeps the classifier from depending on all of them.
    """
    names = {base.__name__ for base in type(exc).__mro__}
    if any("timeout" in name.lower() for name in names):
        return "timeout"
    if isinstance(exc, OSError) and "timed out" in str(exc).lower():
        return "timeout"
    return "down"
