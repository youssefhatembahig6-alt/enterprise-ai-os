"""Response models for the HR vertical slice (spec 003 FR-023–FR-025)."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_serializer

__all__ = ["Compensation", "DirectReport", "HrProfile", "LeaveBalanceView"]

_STRICT = ConfigDict(extra="forbid", frozen=True)


class LeaveBalanceView(BaseModel):
    model_config = _STRICT

    leave_type: str
    year: int
    entitlement_days: int
    used_days: int
    remaining_days: int


class HrProfile(BaseModel):
    """What FR-023 requires an employee can read about themselves, and what FR-024
    lets a manager read about a direct report.

    **No compensation field of any kind.** Not omitted, not optional, not null —
    absent. Salary lives behind `/hr/profiles/{user_id}/compensation`, which is what
    lets its denial happen before the query rather than by leaving a field out of a
    response that has already been fetched (FR-025, SC-007).
    """

    model_config = _STRICT

    user_id: uuid.UUID
    full_name: str
    email: str
    department: str
    office: str
    country: str
    employment_type: str
    job_title: str
    hire_date: dt.date
    #: Null for exactly one user per company: the top-level executive.
    manager_name: str | None
    #: Null when the dataset has no annual balance for this person — rendered by the
    #: portal as its empty state rather than as a zero, because "no record" and "zero
    #: days remaining" are different facts.
    leave_balance: LeaveBalanceView | None


class DirectReport(BaseModel):
    model_config = _STRICT

    user_id: uuid.UUID
    full_name: str
    job_title: str
    department: str


class Compensation(BaseModel):
    """Requires `hr:read_all`. A manager reading their own direct report is refused."""

    model_config = _STRICT

    user_id: uuid.UUID
    salary_band: str
    salary_amount: Decimal
    currency: str

    @field_serializer("salary_amount")
    def _exact(self, value: Decimal) -> str:
        """Serialised as a string, never a float.

        Money is exact everywhere else in this system — `Numeric(14, 2)` in the
        database, `Decimal` in Python — and JSON's number type is a double. Letting it
        through as a float would reintroduce, at the last boundary, precisely the
        rounding error the schema was built to avoid.
        """
        return f"{value:.2f}"
