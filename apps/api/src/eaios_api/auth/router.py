"""Sign in, sign out, and read the current session (spec 003 FR-001, FR-006, FR-007).

**Resolving the tenant without a tenant.** Sign-in supplies an address and no company,
but `users` is unique on `(company_id, email)` and an `eaios_app` session with no
tenant bound sees zero rows. The circularity is the one feature 002 already solved and
wrote down at `public/queries.py:74`: company identifiers are *derived* from the slug
rather than queried, so each known tenant can be bound in turn and the address looked up
inside that scope. Every read stays under RLS and no request path touches the
RLS-exempt owner connection.

**Every refusal is identical.** Unknown address, wrong password, inactive user, no
credential row, and a reached attempt bound all produce the same status, the same body,
and the same headers — and all of them pay for a password verification, so the answer
is not available with a stopwatch either (FR-022, research R12).
"""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from eaios_core.db import session_scope, tenant_scope
from eaios_core.models import User, UserCredential
from eaios_core.passwords import verify_dummy, verify_password
from eaios_core.settings import get_settings

from ..authz.audit import record, record_out_of_band
from ..errors import NotAuthenticatedError, SecurityControlUnavailableError
from ..tenants import TENANT_IDS
from .dependencies import Identity, authenticated, get_engine
from .login_bounds import (
    LimiterUnavailableError,
    clear_account,
    current_state,
    record_failure,
)
from .schemas import LoginAccepted, LoginRequest, SessionState
from .sessions import create_session, end_session
from .tokens import mint_access_token

__all__ = ["router"]

router = APIRouter(tags=["auth"])

class _Resolved:
    """A matched address, or the absence of one. Deliberately not a dataclass with an
    optional field: the two cases take different paths and conflating them is how the
    unknown-address path ends up skipping work the known one does."""

    __slots__ = ("company_id", "password_hash", "user_id")

    def __init__(
        self, company_id: uuid.UUID, user_id: uuid.UUID, password_hash: str
    ) -> None:
        self.company_id = company_id
        self.user_id = user_id
        self.password_hash = password_hash


def _resolve(db: Session, email: str) -> _Resolved | None:
    """Find the one active user with this address, across every known tenant.

    Every tenant is searched even after a match, so the work does not depend on which
    company the address belongs to. Two matches would be ambiguous — the `credentials`
    command refuses to provision when any address exists in more than one tenant, so
    this cannot happen with a provisioned dataset; if it somehow does, both are
    discarded and the attempt is refused like any other.
    """
    found: list[_Resolved] = []
    needle = email.strip().lower()

    for company_id in TENANT_IDS.values():
        with tenant_scope(db, company_id):
            row = db.execute(
                select(User.id, User.company_id, UserCredential.password_hash)
                .join(UserCredential, UserCredential.user_id == User.id)
                .where(func.lower(User.email) == needle)
                .where(User.is_active)
            ).first()
        if row is not None:
            found.append(_Resolved(row.company_id, row.id, row.password_hash))

    return found[0] if len(found) == 1 else None


@router.post(
    "/auth/login",
    response_model=LoginAccepted,
    responses={401: {"description": "Refused. Identical for every cause."}},
    summary="Exchange credentials for a session",
)
def login(request: Request, body: LoginRequest) -> LoginAccepted:
    settings = get_settings()
    engine = get_engine()
    email = str(body.email)

    # Read, never increment. A caller who is already blocked must not push their own
    # counter further out on every retry, which would turn a fifteen-minute lockout
    # into a permanent one for anyone with a tab open.
    #
    # Raised before any account is looked up, so an unreachable limiter refuses every
    # caller identically and says nothing about which accounts exist (FR-007a, FR-022).
    try:
        state = current_state(email, request, settings)
    except LimiterUnavailableError as exc:
        raise SecurityControlUnavailableError("attempt bound cannot be enforced") from exc

    if state.blocked:
        # Same work as every other path, so the refusal is not faster.
        verify_dummy(body.password)
        raise NotAuthenticatedError("attempt bound reached")

    with session_scope(engine) as db:
        resolved = _resolve(db, email)

    if resolved is None or not verify_password(body.password, resolved.password_hash):
        if resolved is None:
            # The whole point of `verify_dummy`: an unknown address costs what a known
            # one costs, so "does this account exist?" is not answerable by timing.
            verify_dummy(body.password)
        _record_failure(request, email, resolved)
        raise NotAuthenticatedError("credentials not accepted")

    now = dt.datetime.now(tz=dt.UTC)
    with session_scope(engine) as db, tenant_scope(db, resolved.company_id):
        session = create_session(
            db, user_id=resolved.user_id, company_id=resolved.company_id, now=now
        )
        record(
            db,
            action="auth.sign_in",
            company_id=resolved.company_id,
            actor_user_id=resolved.user_id,
            resource_type="session",
            resource_id=str(session.id),
            decision="ALLOW",
            reason="credentials verified",
        )

    clear_account(email)

    return LoginAccepted(
        access_token=mint_access_token(
            user_id=resolved.user_id,
            company_id=resolved.company_id,
            session_id=session.id,
            issued_at=session.issued_at,
            expires_at=session.absolute_expires_at,
            settings=settings,
        ),
        expires_at=session.absolute_expires_at,
    )


def _record_failure(request: Request, email: str, resolved: _Resolved | None) -> None:
    """Count the failure and audit it, without recording the address.

    The tenant an entry is written under is the resolved one when there is one, and the
    first known tenant otherwise. That fallback is a compromise worth naming: an attempt
    against an address belonging to nobody has no natural tenant, and the alternative —
    not recording it at all — would leave the most interesting failures invisible.

    Raises :class:`SecurityControlUnavailableError` if the counter cannot be written.
    A failure that goes uncounted is a free guess, and enough of them are what the
    bound exists to stop.
    """
    try:
        state, just_reached = record_failure(email, request)
    except LimiterUnavailableError as exc:
        raise SecurityControlUnavailableError("attempt bound cannot be enforced") from exc
    company_id = resolved.company_id if resolved else next(iter(TENANT_IDS.values()))

    record_out_of_band(
        get_engine(),
        action="auth.sign_in_failed",
        company_id=company_id,
        actor_user_id=resolved.user_id if resolved else None,
        resource_type="credential",
        # No address, ever (FR-018). An audit table listing every attempted address is
        # an enumeration surface with a longer memory than the sign-in form.
        resource_id=None,
        decision="DENY",
        reason="sign-in refused",
    )

    if just_reached:
        record_out_of_band(
            get_engine(),
            action="auth.locked_out",
            company_id=company_id,
            actor_user_id=resolved.user_id if resolved else None,
            resource_type="credential",
            resource_id=None,
            decision="DENY",
            reason=f"{state.which} attempt bound reached",
        )


@router.post(
    "/auth/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={401: {"description": "No usable identity."}},
    summary="End the current session",
)
def logout(
    caller: tuple[Identity, Session] = Depends(authenticated),
) -> Response:
    """Mark the session ended. Idempotent — a second sign-out succeeds.

    The previously issued token stops being accepted immediately, because every
    protected request consults this row. That is what makes signing out real rather
    than cosmetic, and it is what SC-002a measures by replaying the exact credential.
    """
    identity, db = caller
    now = dt.datetime.now(tz=dt.UTC)

    if end_session(db, identity.session.id, "SIGN_OUT", now=now):
        record(
            db,
            action="auth.sign_out",
            company_id=identity.company_id,
            actor_user_id=identity.user_id,
            resource_type="session",
            resource_id=str(identity.session.id),
            decision="ALLOW",
            reason="signed out",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/auth/session",
    response_model=SessionState,
    responses={401: {"description": "No usable identity."}},
    summary="Current session state",
)
def session_state(
    caller: tuple[Identity, Session] = Depends(authenticated),
) -> SessionState:
    """Lets the portal tell "expired" from "never signed in" (FR-027, FR-029).

    Both bounds are exposed because the interface has to say *which* happened. It must
    not use them to decide access — FR-005 requires the server to enforce expiry, and
    it does, on every request including this one.
    """
    identity, _ = caller
    settings = get_settings()
    return SessionState(
        session_id=identity.session.id,
        issued_at=identity.session.issued_at,
        absolute_expires_at=identity.session.absolute_expires_at,
        idle_expires_at=identity.session.last_seen_at
        + dt.timedelta(seconds=settings.auth.idle_timeout_seconds),
    )
