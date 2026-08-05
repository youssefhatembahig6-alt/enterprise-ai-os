"""Health and readiness endpoints (spec FR-003).

Liveness and readiness are separate on purpose. Liveness touches no dependency, so
a slow store cannot cause Compose to restart-loop the API while it is still warming
up. Readiness checks the four stores *and the background worker* concurrently and
reports each one individually — a single boolean cannot tell an operator *which*
service failed, which is exactly what FR-003 asks for.

The worker is included because US1 acceptance scenario 3 names it. Leaving it out
made a stack with a dead worker report `ready`, which is the precise condition
FR-003 exists to make visible.
"""

from __future__ import annotations

import asyncio
from typing import Final

from fastapi import APIRouter, Depends, Response, status

from eaios_core.clients.stores import (
    DependencyStatus,
    check_minio,
    check_postgres,
    check_qdrant,
    check_redis,
    check_worker,
)
from eaios_core.settings import Settings, get_settings

from .schemas import DependencyStatusModel, LivenessResponse, ReadinessResponse

router = APIRouter(prefix="/health", tags=["health"])

_CHECKS: Final = (check_postgres, check_redis, check_qdrant, check_minio, check_worker)


@router.get("/live", response_model=LivenessResponse, summary="Liveness probe")
async def liveness(settings: Settings = Depends(get_settings)) -> LivenessResponse:
    return LivenessResponse(service=settings.service_name, version=settings.version)


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe with per-dependency detail",
    responses={503: {"model": ReadinessResponse}},
)
async def readiness(
    response: Response, settings: Settings = Depends(get_settings)
) -> ReadinessResponse:
    # Concurrent, so total latency is the slowest dependency rather than their sum.
    # Each probe carries its own timeout and reports failure as a status rather
    # than raising, so one unreachable store cannot mask the other three.
    results: list[DependencyStatus] = await asyncio.gather(
        *(asyncio.to_thread(check, settings) for check in _CHECKS)
    )

    dependencies = [
        DependencyStatusModel(
            name=item.name, status=item.status, latency_ms=item.latency_ms, detail=item.detail
        )
        for item in results
    ]
    healthy = all(item.status == "up" for item in results)

    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(status="ready" if healthy else "degraded", dependencies=dependencies)
