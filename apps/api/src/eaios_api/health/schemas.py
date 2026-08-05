"""Typed response models for the health and manifest endpoints.

Mirrors `specs/001-foundation-tenant-seed/contracts/health-api.yaml`; the contract
test in `tests/integration/test_health_contract.py` compares the two so they cannot
drift apart silently.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "DatasetManifestResponse",
    "DependencyStatusModel",
    "LivenessResponse",
    "Problem",
    "ReadinessResponse",
]


class LivenessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["alive"] = "alive"
    service: str
    version: str


class DependencyStatusModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Literal["postgres", "redis", "qdrant", "minio", "worker"]
    status: Literal["up", "down", "timeout"]
    latency_ms: int = Field(ge=0)
    #: Present only on failure, and never contains credentials or connection
    #: strings — health is unauthenticated, so a DSN here would be a disclosure.
    detail: str | None = None


class ReadinessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ready", "degraded"]
    #: Five, not four — the background worker is a backing service US1/AC3 names
    #: explicitly. The bound is exact so a probe that silently stops being called
    #: fails the contract test rather than quietly shrinking the report.
    dependencies: list[DependencyStatusModel] = Field(min_length=5, max_length=5)


class DatasetManifestResponse(BaseModel):
    """Provenance only — never tenant-owned business data.

    There is no authentication yet (decision D1), so this endpoint deliberately
    exposes counts and digests and nothing else.
    """

    model_config = ConfigDict(extra="forbid")

    root_seed: str
    reference_date: dt.date
    generator_version: str
    profile: str
    entity_counts: dict[str, int]
    family_digests: dict[str, str]
    root_fingerprint: str
    started_at: dt.datetime
    completed_at: dt.datetime | None
    is_complete: bool


class Problem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    status: int
    detail: str | None = None
