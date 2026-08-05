"""Platform entities — audit and jobs (data-model.md §7)."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantMixin, uuid_pk

__all__ = ["AuditLog", "JobRecord"]


class AuditLog(Base, TenantMixin):
    """Append-only record of consequential operations (Constitution Principle X).

    Immutability is enforced by a database trigger created in the initial migration,
    not by convention — an audit log that the application can quietly rewrite is not
    evidence of anything.

    The seed itself writes entries here for the dataset it creates and the reset it
    performs (spec FR-043).
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        CheckConstraint("actor_type IN ('USER','SYSTEM','SEED')", name="actor_type_values"),
        CheckConstraint("decision IN ('ALLOW','DENY','NA')", name="decision_values"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    decision: Mapped[str] = mapped_column(String(8), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    sources: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[dt.datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class JobRecord(Base, TenantMixin):
    """Background job carrying the tenant of the work it performs (spec FR-042)."""

    __tablename__ = "job_records"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING','RUNNING','SUCCEEDED','FAILED')", name="status_values"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    job_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    scheduled_for: Mapped[dt.datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    started_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    finished_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
