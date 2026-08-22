"""Building the trusted access context (spec 003 FR-008, FR-009, FR-010).

Everything here comes from the database, inside the caller's tenant scope, on every
request. Nothing comes from the request — not a parameter, not a header, not a cookie,
not a body. FR-010 calls that absolute, and the reason is that a single trusted field
*is* the boundary: the moment one attribute can be supplied, the access context stops
describing who is asking and starts describing who they claimed to be.

**Read per request, not cached.** FR-004 requires current records, and this is where
that costs something — four queries per protected request. It buys the two properties
the specification is built on: a user deactivated after sign-in loses access on their
next request, and a role change takes effect without waiting for a stale token to
expire.

**Both manager directions** (FR-008). `manager_id` answers "whose team am I on";
`direct_report_ids` answers "whose records may I read". Only the second is consulted by
this feature's rules; the first is here because the requirement names it and feature
004's approval routing needs it.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from eaios_core.authz import AccessContext
from eaios_core.models import Permission, Role, RolePermission, User, UserRole

from ..errors import NotAuthenticatedError
from ..tenants import slug_of

__all__ = ["build_access_context"]


def build_access_context(
    db: Session, *, user_id: uuid.UUID, company_id: uuid.UUID, session_id: uuid.UUID
) -> AccessContext:
    """Assemble the caller's context from current rows.

    ``db`` must already be scoped to ``company_id``. Every query below therefore
    carries a tenant predicate whether or not it names one — which is the backstop, not
    the plan: the explicit scope is what makes the reads correct, and RLS is what makes
    a forgotten one return nothing rather than everything.
    """
    user = db.execute(
        select(
            User.id,
            User.company_id,
            User.department_id,
            User.office_id,
            User.country,
            User.employment_type,
            User.manager_id,
            User.is_active,
        ).where(User.id == user_id)
    ).first()

    if user is None or not user.is_active or user.company_id != company_id:
        # Reached only if something upstream let an inconsistent identity through. The
        # dependency already checks all three; repeating it here means the context can
        # never be built from a user this scope cannot see.
        raise NotAuthenticatedError("identity is inconsistent with its records")

    direct_reports = frozenset(
        row.id for row in db.execute(select(User.id).where(User.manager_id == user_id))
    )

    roles = db.execute(
        select(Role.id, Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
    ).all()

    permissions = frozenset(
        row.code
        for row in db.execute(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(UserRole, UserRole.role_id == RolePermission.role_id)
            .where(UserRole.user_id == user_id)
        )
    )

    return AccessContext(
        company_id=company_id,
        company_slug=slug_of(company_id),
        user_id=user.id,
        session_id=session_id,
        # Passed straight through, including absent. The `users` columns are NOT NULL
        # today, so in this dataset both are always present — but the context type now
        # admits absence (FR-014a), and the construction path must carry that through
        # rather than substitute a placeholder. A substituted department would put the
        # caller in a department nobody assigned them to.
        department_id=user.department_id,
        office_id=user.office_id,
        country=user.country,
        employment_type=user.employment_type,
        manager_id=user.manager_id,
        direct_report_ids=direct_reports,
        role_names=frozenset(row.name for row in roles),
        role_ids=frozenset(row.id for row in roles),
        permission_codes=permissions,
    )
