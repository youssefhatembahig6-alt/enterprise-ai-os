"""Reading HR records in two halves (spec 003 FR-015, FR-025; research R7).

**The split this module exists for.** FR-015 forbids reading data before authorizing.
Taken literally that is unsatisfiable — deciding whether a manager may read an
employee's profile needs that employee's `company_id` and `manager_id`. So the read is
split, and the halves are named:

* :func:`load_descriptor` selects **access attributes only**: who owns the record,
  which company and department it belongs to. Reading these is part of the decision.
* :func:`load_profile_payload` and :func:`load_compensation_payload` select the
  **protected payload**: what the caller asked for. They run only after the decision
  allowed it.

That makes FR-015 precise and checkable: *no query selecting a protected payload column
may execute on a path that ends in a denial*. `tests/security/test_authorize_before_read.py`
asserts it by recording the statements a request actually executed — in both
directions, because "the forbidden query did not run" is trivially true when nothing
runs at all.

**Compensation is its own query, not a column on the profile.** That is what lets
FR-025's denial happen before the read rather than by omitting a field from a response.
A field left out of a response model has already been fetched.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from eaios_core.authz import ResourceDescriptor, ResourceKind
from eaios_core.models import Department, EmployeeProfile, LeaveBalance, Office, User

__all__ = [
    "CompensationRow",
    "ProfileRow",
    "load_compensation_payload",
    "load_descriptor",
    "load_direct_reports",
    "load_profile_payload",
]


@dataclass(frozen=True, slots=True)
class ProfileRow:
    user_id: uuid.UUID
    full_name: str
    email: str
    department: str
    office: str
    country: str
    employment_type: str
    job_title: str
    hire_date: dt.date
    manager_name: str | None
    leave_type: str | None
    leave_year: int | None
    entitlement_days: int | None
    used_days: int | None
    remaining_days: int | None


@dataclass(frozen=True, slots=True)
class CompensationRow:
    user_id: uuid.UUID
    salary_band: str
    salary_amount: Decimal
    currency: str


@dataclass(frozen=True, slots=True)
class DirectReportRow:
    user_id: uuid.UUID
    full_name: str
    job_title: str
    department: str


def load_descriptor(
    db: Session, subject_id: uuid.UUID, kind: ResourceKind
) -> ResourceDescriptor:
    """The access attributes of one person's HR record — and nothing else.

    Selects exactly four columns, none of them a payload field. Adding one here would
    quietly undo the whole split: the descriptor query runs *before* the decision, so
    anything it selects has been read regardless of the answer.

    A subject in another tenant is invisible under RLS, so the row is simply absent —
    which produces a descriptor with `company_id=None`, and the engine denies with
    `CONTEXT_INCOMPLETE`. That is a 403 rather than a 404, so the caller cannot tell
    "no such person anywhere" from "not in your company"; the tenant case is handled by
    the router, which supplies its own tenant so layer 1 can fire properly.
    """
    row = db.execute(
        select(User.id, User.company_id, User.department_id, User.manager_id).where(
            User.id == subject_id
        )
    ).first()

    if row is None:
        return ResourceDescriptor(kind=kind, resource_id=str(subject_id))

    return ResourceDescriptor(
        kind=kind,
        resource_id=str(subject_id),
        company_id=row.company_id,
        owner_id=row.id,
        department_id=row.department_id,
        # HR records carry no classification and no resource ACL — those are document
        # properties. Left as None, and the rules table marks these kinds neither
        # `classified` nor `acl_gated`, so layers 4 and 5 do not apply rather than
        # applying and passing on an absent value.
        classification=None,
        acl_grants=None,
    )


def subject_exists(db: Session, subject_id: uuid.UUID) -> bool:
    """Whether this tenant has such a person at all.

    Used by the router to tell "not yours" from "nobody's" *before* deciding — the two
    take different paths (404 versus a real authorization decision) and both must
    produce the same response for a caller in another tenant.
    """
    return (
        db.execute(select(User.id).where(User.id == subject_id)).first() is not None
    )


def load_profile_payload(db: Session, subject_id: uuid.UUID) -> ProfileRow | None:
    """The protected payload. Runs only after the decision allowed it.

    Carries **no** compensation field of any kind — not omitted from a response model,
    absent from the query. `salary_amount` lives in :func:`load_compensation_payload`
    behind its own decision.
    """
    manager = User.__table__.alias("manager")
    row = db.execute(
        select(
            User.id,
            User.full_name,
            User.email,
            User.country,
            User.employment_type,
            Department.name.label("department"),
            Office.city.label("office"),
            EmployeeProfile.job_title,
            EmployeeProfile.hire_date,
            manager.c.full_name.label("manager_name"),
            LeaveBalance.leave_type,
            LeaveBalance.year.label("leave_year"),
            LeaveBalance.entitlement_days,
            LeaveBalance.used_days,
            LeaveBalance.remaining_days,
        )
        .join(Department, Department.id == User.department_id)
        .join(Office, Office.id == User.office_id)
        .join(EmployeeProfile, EmployeeProfile.user_id == User.id)
        .outerjoin(manager, manager.c.id == User.manager_id)
        .outerjoin(
            LeaveBalance,
            (LeaveBalance.user_id == User.id) & (LeaveBalance.leave_type == "ANNUAL"),
        )
        .where(User.id == subject_id)
        .order_by(LeaveBalance.year.desc())
        .limit(1)
    ).first()

    if row is None:
        return None

    return ProfileRow(
        user_id=row.id,
        full_name=row.full_name,
        email=row.email,
        department=row.department,
        office=row.office,
        country=row.country,
        employment_type=row.employment_type,
        job_title=row.job_title,
        hire_date=row.hire_date,
        manager_name=row.manager_name,
        leave_type=row.leave_type,
        leave_year=row.leave_year,
        entitlement_days=row.entitlement_days,
        used_days=row.used_days,
        remaining_days=row.remaining_days,
    )


def load_compensation_payload(db: Session, subject_id: uuid.UUID) -> CompensationRow | None:
    """The blueprint's flagship protected read.

    A separate statement from the profile on purpose. Because it is separate, a denied
    request executes nothing that mentions `employee_profiles.salary_amount` — which is
    what SC-007 measures, and what a response-body assertion could never establish.
    """
    row = db.execute(
        select(
            EmployeeProfile.user_id,
            EmployeeProfile.salary_band,
            EmployeeProfile.salary_amount,
            EmployeeProfile.currency,
        ).where(EmployeeProfile.user_id == subject_id)
    ).first()

    if row is None:
        return None

    return CompensationRow(
        user_id=row.user_id,
        salary_band=row.salary_band,
        salary_amount=row.salary_amount,
        currency=row.currency,
    )


def load_direct_reports(db: Session, manager_id: uuid.UUID) -> list[DirectReportRow]:
    """One level, deliberately (FR-024, research open question 1).

    The dataset has a multi-level hierarchy, so a transitive reading would silently
    widen every manager's reach. Widening it is a change to the specification, not to
    this query.

    Deliberately thin: name, title, department. A team list is a navigation aid, and
    each profile it links to is fetched by its own authorized request — so this cannot
    become a way to read profile content in bulk without a per-record decision.
    """
    rows = db.execute(
        select(
            User.id,
            User.full_name,
            EmployeeProfile.job_title,
            Department.name.label("department"),
        )
        .join(EmployeeProfile, EmployeeProfile.user_id == User.id)
        .join(Department, Department.id == User.department_id)
        .where(User.manager_id == manager_id)
        .where(User.is_active)
        .order_by(User.full_name)
    ).all()

    return [
        DirectReportRow(
            user_id=row.id,
            full_name=row.full_name,
            job_title=row.job_title,
            department=row.department,
        )
        for row in rows
    ]
