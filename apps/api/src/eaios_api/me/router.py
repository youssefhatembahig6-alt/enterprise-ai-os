"""The caller's own identity and access context (spec 003 FR-011).

Both endpoints are about the caller themselves, so authorization is ownership and
nothing else — there is no permission code that would decide anything here, because
every signed-in user necessarily holds it. The rules table says so explicitly
(`ACCESS_CONTEXT` and `SESSION` carry `permission=None` with an `IS_SELF` condition)
rather than leaving these routes to skip the engine, which is how a route ends up
being the one nobody checked.
"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import Session

from eaios_core.authz import AccessContext, Action, ResourceDescriptor, ResourceKind
from eaios_core.models import Company, Department, Office, User

from ..authz.dependencies import CallerContext
from ..authz.enforce import authorize
from ..errors import ResourceAbsentError
from ..hr.queries import load_descriptor, load_direct_reports, load_profile_payload
from ..hr.router import profile_response
from ..hr.schemas import DirectReport, HrProfile
from .schemas import AccessContextView, CurrentUser

__all__ = ["router"]

router = APIRouter(tags=["me"])


@router.get("/me", response_model=CurrentUser, summary="The authenticated user's identity")
def current_user(caller: CallerContext) -> CurrentUser:
    context, db = caller
    return _current_user(context, db)


@router.get(
    "/me/access-context",
    response_model=AccessContextView,
    summary="What the server believes about the caller",
)
def access_context(caller: CallerContext) -> AccessContextView:
    context, db = caller

    # Runs through the engine even though the answer is never in doubt. A route that
    # skips the decision because "it is obviously allowed" is a route with no audit
    # entry when it is later made less obvious.
    authorize(
        context,
        db,
        Action.READ,
        ResourceDescriptor(
            kind=ResourceKind.ACCESS_CONTEXT,
            resource_id=str(context.user_id),
            company_id=context.company_id,
            owner_id=context.user_id,
        ),
    )

    return AccessContextView(
        company_id=context.company_id,
        user_id=context.user_id,
        department_id=context.department_id,
        office_id=context.office_id,
        country=context.country,
        employment_type=context.employment_type,
        manager_id=context.manager_id,
        # Sorted so the response is stable between requests. An unordered list would
        # make a contract diff noisy and a test comparison order-dependent.
        direct_report_ids=sorted(context.direct_report_ids),
        roles=sorted(context.role_names),
        permissions=sorted(context.permission_codes),
        permission_fingerprint=context.permission_fingerprint,
    )


@router.get(
    "/me/hr-profile",
    response_model=HrProfile,
    summary="The caller's own HR profile",
)
def own_hr_profile(caller: CallerContext) -> HrProfile:
    """FR-023. Requires `hr:read_self`.

    Writes **no** audit entry: reading one's own non-compensation profile is not in the
    sensitive set (FR-017a), and its absence from the trail is by design rather than an
    omission. `tests/security/test_authz_audit.py` asserts the zero alongside a
    sensitive read that writes exactly one, so a silently broken audit writer cannot
    hide behind it.
    """
    context, db = caller

    descriptor = load_descriptor(db, context.user_id, ResourceKind.HR_PROFILE)
    authorize(context, db, Action.READ, descriptor)

    payload = load_profile_payload(db, context.user_id)
    if payload is None:  # pragma: no cover - every seeded user has a profile
        raise ResourceAbsentError("no profile for this user")
    return profile_response(payload)


@router.get(
    "/me/direct-reports",
    response_model=list[DirectReport],
    summary="The people who report to the caller",
)
def own_direct_reports(caller: CallerContext) -> list[DirectReport]:
    """Requires `hr:read_team`.

    An empty list — not a refusal — for a permitted caller with no reports. The portal
    then renders its empty state rather than its access-denied state, which are
    different sentences: "you have no direct reports" is not "you may not see this".
    """
    context, db = caller

    authorize(
        context,
        db,
        Action.READ,
        ResourceDescriptor(
            kind=ResourceKind.DIRECT_REPORTS,
            resource_id=str(context.user_id),
            company_id=context.company_id,
            owner_id=context.user_id,
        ),
    )

    return [
        DirectReport(
            user_id=row.user_id,
            full_name=row.full_name,
            job_title=row.job_title,
            department=row.department,
        )
        for row in load_direct_reports(db, context.user_id)
    ]


def _current_user(context: AccessContext, db: Session) -> CurrentUser:
    row = db.execute(
        select(
            User.full_name,
            User.email,
            Company.name.label("company_name"),
            Department.name.label("department"),
            Office.city.label("office"),
        )
        .join(Company, Company.id == User.company_id)
        .join(Department, Department.id == User.department_id)
        .join(Office, Office.id == User.office_id)
        .where(User.id == context.user_id)
    ).first()

    if row is None:  # pragma: no cover - the dependency already proved the user exists
        raise ResourceAbsentError("no such user")

    return CurrentUser(
        user_id=context.user_id,
        full_name=row.full_name,
        email=row.email,
        company_name=row.company_name,
        department=row.department,
        office=row.office,
        roles=sorted(context.role_names),
        permissions=sorted(context.permission_codes),
    )
