"""The dependency every protected route declares (spec 003 FR-008–FR-010).

Returns an immutable access context and a database session already bound to that
context's tenant. Binding here rather than in each route is what makes "no query runs
without a tenant constraint derived from the server-built access context"
(Constitution Principle I) a property of the plumbing instead of a rule every route
has to remember.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from eaios_core.authz import AccessContext

from ..auth.dependencies import Identity, authenticated
from .context_builder import build_access_context
from .tenant_guard import note_supplied_authority

__all__ = ["Caller", "CallerContext", "require_context"]


def require_context(
    request: Request,
    caller: tuple[Identity, Session] = Depends(authenticated),
) -> Iterator[tuple[AccessContext, Session]]:
    """Verified identity in, immutable access context out.

    The session handed back is the *same* one the identity was verified on, still
    inside its tenant scope. Opening a second session here would leave a window where
    the tenant is unbound, and an unbound session sees zero rows — a bug that reads as
    "the record disappeared" rather than as a scoping mistake.

    The context is built **before** the request is inspected for supplied authority,
    and that order is the point: the inspection cannot influence what was built, it can
    only notice what was tried (FR-010).
    """
    identity, db = caller
    context = build_access_context(
        db,
        user_id=identity.user_id,
        company_id=identity.company_id,
        session_id=identity.session.id,
    )
    note_supplied_authority(request, context, db)
    yield context, db


#: What a protected route declares. Reads as a requirement in the signature.
CallerContext = Annotated[tuple[AccessContext, Session], Depends(require_context)]

#: Alias kept short for route signatures that already carry a path parameter.
Caller = CallerContext
