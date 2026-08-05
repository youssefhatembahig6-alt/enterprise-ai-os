"""HR entities (data-model.md §3)."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantMixin, TimestampMixin, uuid_pk

__all__ = [
    "AttendanceRecord",
    "EmployeeProfile",
    "LeaveBalance",
    "LeaveRequest",
    "PerformanceReview",
    "TrainingRecord",
]


class EmployeeProfile(Base, TenantMixin, TimestampMixin):
    """Employment detail.

    ``salary_amount`` is the payload behind the blueprint's "another employee's
    salary → deny" scenario, which is why the corresponding document is classified
    RESTRICTED and why this table is one of the highest-risk RLS targets.
    """

    __tablename__ = "employee_profiles"
    __table_args__ = (UniqueConstraint("user_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    job_title: Mapped[str] = mapped_column(String(128), nullable=False)
    salary_band: Mapped[str] = mapped_column(String(8), nullable=False)
    salary_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    hire_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    employment_type: Mapped[str] = mapped_column(String(16), nullable=False)


class LeaveBalance(Base, TenantMixin, TimestampMixin):
    """Entitlement must match the leave policy's stated value (spec FR-035)."""

    __tablename__ = "leave_balances"
    __table_args__ = (
        UniqueConstraint("user_id", "leave_type", "year"),
        CheckConstraint("remaining_days = entitlement_days - used_days", name="balance_arithmetic"),
        CheckConstraint("used_days >= 0 AND entitlement_days >= 0", name="non_negative"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    leave_type: Mapped[str] = mapped_column(String(24), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    entitlement_days: Mapped[int] = mapped_column(Integer, nullable=False)
    used_days: Mapped[int] = mapped_column(Integer, nullable=False)
    remaining_days: Mapped[int] = mapped_column(Integer, nullable=False)


class LeaveRequest(Base, TenantMixin, TimestampMixin):
    __tablename__ = "leave_requests"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="date_order"),
        CheckConstraint(
            "status IN ('PENDING','APPROVED','REJECTED','CANCELLED')", name="status_values"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    approver_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    leave_type: Mapped[str] = mapped_column(String(24), nullable=False)
    start_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    end_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    days_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    submitted_at: Mapped[dt.datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class AttendanceRecord(Base, TenantMixin, TimestampMixin):
    """Capped at 6 months — these rows dominate total volume (spec FR-020a)."""

    __tablename__ = "attendance_records"
    __table_args__ = (
        UniqueConstraint("user_id", "work_date"),
        CheckConstraint(
            "status IN ('PRESENT','REMOTE','LEAVE','HOLIDAY')", name="status_values"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    work_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    hours_worked: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)


class TrainingRecord(Base, TenantMixin, TimestampMixin):
    __tablename__ = "training_records"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    course_name: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(128), nullable=False)
    completed_on: Mapped[dt.date] = mapped_column(Date, nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)


class PerformanceReview(Base, TenantMixin, TimestampMixin):
    __tablename__ = "performance_reviews"
    __table_args__ = (
        UniqueConstraint("user_id", "period_start"),
        CheckConstraint("rating BETWEEN 1 AND 5", name="rating_range"),
        CheckConstraint("period_end > period_start", name="period_order"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    period_start: Mapped[dt.date] = mapped_column(Date, nullable=False)
    period_end: Mapped[dt.date] = mapped_column(Date, nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
