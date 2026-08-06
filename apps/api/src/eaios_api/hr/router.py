"""One address, different answers depending on who asks (spec 003 FR-023–FR-025).

The blueprint's flagship demonstration lives here: `GET /hr/profiles/{user_id}` returns
a record to the person it belongs to, to their manager, and to HR — and refuses
everyone else. Same request, same route, different outcome, decided by data rather than
by code.

Every handler follows the same three steps, and the order is the requirement:

1. build a descriptor from **access attributes only**;
2. `authorize`, which decides, audits, and raises;
3. read the payload.

Step 3 is unreachable on a denied request, which is what makes "authorization precedes
retrieval" checkable by recording executed statements rather than by inspecting
responses (FR-015, FR-036, SC-007).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from eaios_core.authz import Action, ResourceKind

from ..authz.dependencies import CallerContext
from ..authz.enforce import authorize
from ..errors import ResourceAbsentError
from .queries import (
    load_compensation_payload,
    load_descriptor,
    load_profile_payload,
    subject_exists,
)
from .schemas import Compensation, HrProfile, LeaveBalanceView

__all__ = ["profile_response", "router"]

router = APIRouter(tags=["hr"])


@router.get(
    "/hr/profiles/{user_id}",
    response_model=HrProfile,
    responses={
        401: {"description": "No usable identity."},
        403: {"description": "Verified identity, refused by authorization."},
        404: {"description": "No such record for this caller."},
    },
    summary="One employee's HR profile",
)
def employee_profile(user_id: uuid.UUID, caller: CallerContext) -> HrProfile:
    context, db = caller

    # Absence is checked first and answered identically for "nobody has this id" and
    # "somebody in another company does". The lookup runs inside the caller's tenant
    # scope, so the other company's row is invisible under RLS and the two cases are
    # the same case (FR-021, FR-030, SC-004).
    if not subject_exists(db, user_id):
        raise ResourceAbsentError("no such person in this tenant")

    descriptor = load_descriptor(db, user_id, ResourceKind.HR_PROFILE)
    authorize(context, db, Action.READ, descriptor)

    payload = load_profile_payload(db, user_id)
    if payload is None:  # pragma: no cover - the existence check above already ran
        raise ResourceAbsentError("no such person in this tenant")
    return profile_response(payload)


@router.get(
    "/hr/profiles/{user_id}/compensation",
    response_model=Compensation,
    responses={
        401: {"description": "No usable identity."},
        403: {"description": "Verified identity, refused by authorization."},
        404: {"description": "No such record for this caller."},
    },
    summary="One employee's compensation",
)
def employee_compensation(user_id: uuid.UUID, caller: CallerContext) -> Compensation:
    """FR-025 — the flagship denial. Requires `hr:read_all`.

    A manager reading their own direct report is refused, and the refusal happens
    before any statement mentioning `salary_amount` is executed. Every outcome is
    audited, including an allow for the caller's own record: compensation is sensitive
    "of any kind, including the requester's own" (FR-017a).
    """
    context, db = caller

    if not subject_exists(db, user_id):
        raise ResourceAbsentError("no such person in this tenant")

    descriptor = load_descriptor(db, user_id, ResourceKind.HR_COMPENSATION)
    authorize(context, db, Action.READ, descriptor)

    payload = load_compensation_payload(db, user_id)
    if payload is None:  # pragma: no cover - every seeded user has a profile
        raise ResourceAbsentError("no compensation record")

    return Compensation(
        user_id=payload.user_id,
        salary_band=payload.salary_band,
        salary_amount=payload.salary_amount,
        currency=payload.currency,
    )


def profile_response(payload: object) -> HrProfile:
    """Shape a profile row into its response model.

    Shared with `/me/hr-profile`, which is the same read with the subject fixed to the
    caller — one shaping function so the two cannot drift into describing the same
    person differently.
    """
    from .queries import ProfileRow

    assert isinstance(payload, ProfileRow)

    balance = None
    if payload.leave_type is not None:
        balance = LeaveBalanceView(
            leave_type=payload.leave_type,
            year=payload.leave_year or 0,
            entitlement_days=payload.entitlement_days or 0,
            used_days=payload.used_days or 0,
            remaining_days=payload.remaining_days or 0,
        )

    return HrProfile(
        user_id=payload.user_id,
        full_name=payload.full_name,
        email=payload.email,
        department=payload.department,
        office=payload.office,
        country=payload.country,
        employment_type=payload.employment_type,
        job_title=payload.job_title,
        hire_date=payload.hire_date,
        manager_name=payload.manager_name,
        leave_balance=balance,
    )
