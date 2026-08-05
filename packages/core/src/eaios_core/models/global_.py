"""Global entities — the closed allowlist (spec FR-009a, data-model.md §1).

These four are the *only* tables without a ``company_id``. Each one is here for a
stated reason, and the structural audit fails if the set changes in either
direction.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import Boolean, Date, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, uuid_pk

__all__ = ["DatasetManifest", "Permission", "PlatformAdministrator"]


class Permission(Base, TimestampMixin):
    """Shared permission vocabulary (spec FR-009b).

    Global on purpose: one catalog means permission codes cannot drift apart between
    tenants, and every authorization check later compares codes rather than role
    names.
    """

    __tablename__ = "permissions"

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)


class PlatformAdministrator(Base, TimestampMixin):
    """The cross-tenant platform account (spec FR-009c).

    A separate table rather than a nullable ``company_id`` on ``users``. A nullable
    tenant column on the main user table is exactly the hole every later query would
    have to remember to close; keeping it separate makes "no user is tenant-less"
    enforceable by ``NOT NULL``.
    """

    __tablename__ = "platform_administrators"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class DatasetManifest(Base):
    """Provenance for the seeded dataset (spec FR-016, FR-014b).

    ``completed_at`` is written last, in the same transaction as the fingerprint. A
    manifest without it describes an environment that is unambiguously incomplete —
    which is what lets an interrupted seed be reported as *incomplete* rather than as
    a confusing fingerprint mismatch.
    """

    __tablename__ = "dataset_manifest"

    id: Mapped[uuid.UUID] = uuid_pk()
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    root_seed: Mapped[str] = mapped_column(String(64), nullable=False)
    reference_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    generator_version: Mapped[str] = mapped_column(String(32), nullable=False)
    profile: Mapped[str] = mapped_column(String(16), nullable=False)

    entity_counts: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    family_digests: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    root_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    fingerprint_exclusions: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    started_at: Mapped[dt.datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    completed_at: Mapped[dt.datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    duration_seconds: Mapped[float | None] = mapped_column(nullable=True)
    host_platform: Mapped[str | None] = mapped_column(String(32), nullable=True)

    @property
    def is_complete(self) -> bool:
        return self.completed_at is not None
