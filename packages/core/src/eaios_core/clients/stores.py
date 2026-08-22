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
from typing import Any, Final, Literal, Protocol

import redis as redis_lib
from minio import Minio
from qdrant_client import QdrantClient

from ..authz.filters import FILTER_KEYS
from ..settings import Settings, get_settings

__all__ = [
    "REQUIRED_PAYLOAD_INDEXES",
    "DependencyName",
    "DependencyStatus",
    "PopulatedCollectionError",
    "check_minio",
    "check_postgres",
    "check_qdrant",
    "check_redis",
    "check_worker",
    "ensure_payload_indexes",
    "get_minio",
    "get_qdrant",
    "get_redis",
    "missing_payload_indexes",
]

DependencyName = Literal["postgres", "redis", "qdrant", "minio", "worker"]

#: Every payload field the retrieval filter constrains, and therefore every field that
#: needs an index.
#:
#: **Derived from `FILTER_KEYS`, never restated.** R3 found two lists of six that were not
#: the same six: `allowed_roles` was used by the filter and unindexed, `document_id`
#: indexed and idle. A hand-maintained copy is correct only until the next clause is added,
#: and the failure it produces is invisible — the query still returns the right rows and
#: merely costs more than the latency budget allows.
REQUIRED_PAYLOAD_INDEXES: Final[tuple[str, ...]] = FILTER_KEYS


class PopulatedCollectionError(RuntimeError):
    """Raised when provisioning would touch a collection that already holds points.

    Adding an index to a populated collection is a reindex, not a no-op: it has a cost the
    caller did not ask for and, on a large corpus, a duration nobody scheduled. So the
    default is to refuse, and a caller who genuinely means it passes `allow_populated`.
    """


class _SupportsPayloadIndexes(Protocol):
    """The slice of the Qdrant client this module needs.

    Narrow deliberately: it lets the unit tests exercise the populated and unknown-count
    branches without populating a real collection to do it.
    """

    def get_collection(self, collection_name: str) -> Any: ...

    def create_payload_index(
        self, *, collection_name: str, field_name: str, field_schema: Any
    ) -> Any: ...


def missing_payload_indexes(
    client: _SupportsPayloadIndexes, collection: str
) -> set[str]:
    """Required payload fields that `collection` does not index.

    Qdrant reports `None` rather than `{}` for a collection with no indexes at all, which
    is why the fallback matters: `set(None)` would raise and `or {}` keeps the answer
    "all of them missing", which is the truth.
    """
    indexed = set(client.get_collection(collection).payload_schema or {})
    return set(REQUIRED_PAYLOAD_INDEXES) - indexed


def ensure_payload_indexes(
    client: _SupportsPayloadIndexes,
    collection: str,
    *,
    allow_populated: bool = False,
) -> tuple[str, ...]:
    """Create every missing payload index on `collection`, idempotently.

    Args:
        client: A Qdrant client, or anything with its `get_collection` and
            `create_payload_index`.
        collection: The collection to provision. **Never created and never deleted here** —
            this function indexes what exists.
        allow_populated: Permit indexing a collection that already holds points, accepting
            the reindex cost. Off by default.

    Returns:
        The fields actually created, in sorted order. Empty on a second call — idempotence
        that still did the work is not idempotence, and re-creating six indexes on every
        start-up is a reindex nobody asked for.

    Raises:
        PopulatedCollectionError: The collection holds points, or its point count cannot be
            read, and `allow_populated` is not set. An unreadable count is refused rather
            than assumed to be zero: treating `None` as empty would wave through exactly
            the collection this check cannot vouch for.

    This function never calls `delete_collection` or `create_collection`. Recreating a
    populated collection is not a reindex, it is data loss, and the distinction is worth a
    sentence here because the two calls sit next to each other in the client's API.
    """
    info = client.get_collection(collection)
    points = getattr(info, "points_count", None)

    if not allow_populated:
        if points is None:
            raise PopulatedCollectionError(
                f"cannot read the point count for {collection!r}, so it is unknown whether"
                " provisioning would reindex live data; pass allow_populated=True to"
                " proceed anyway"
            )
        if points > 0:
            raise PopulatedCollectionError(
                f"{collection!r} holds {points} points; adding a payload index would"
                " reindex them. Pass allow_populated=True if that is intended"
            )

    indexed = set(info.payload_schema or {})
    created = sorted(set(REQUIRED_PAYLOAD_INDEXES) - indexed)
    for field in created:
        client.create_payload_index(
            collection_name=collection,
            field_name=field,
            field_schema=_keyword_schema(),
        )
    return tuple(created)


def _keyword_schema() -> Any:
    """Imported lazily so this module stays importable without the models package."""
    from qdrant_client import models as qmodels

    return qmodels.PayloadSchemaType.KEYWORD


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
