"""Turning a credential into a verified identity (spec 003 FR-003, FR-004, FR-007).

This is authentication only: *who is asking, and may they ask anything at all*. What
they are allowed to reach is :mod:`eaios_api.authz`, built on top of what this
produces.

FR-003 lists what happens before anything else, and it happens in this order:

1. signature, issuer, audience, expiry, and token type (:mod:`.tokens`);
2. the tenant from the verified claim is **bound** as the RLS scope;
3. the session is live and inside both bounds (:mod:`.sessions`);
4. the user still exists, is still active, and still belongs to that tenant.

Steps 3 and 4 are read from **current records**, never from the credential (FR-004). A
user deactivated after sign-in loses access on their next request rather than at
expiry, and a signed-out credential stops working immediately rather than in eight
hours.

Binding the tenant *before* the session lookup is what makes a token from one tenant
useless against the other: the lookup runs inside that scope, so the other company's
session row is simply absent under RLS rather than being found and then rejected.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from typing import Final

from fastapi import Depends, Request
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from eaios_core.db import create_app_engine, session_scope, tenant_scope
from eaios_core.logging import get_logger
from eaios_core.models import User
from eaios_core.settings import get_settings

from ..errors import NotAuthenticatedError
from .sessions import InvalidSessionError, SessionRecord, end_session, validate_session
from .tokens import InvalidTokenError, TokenClaims, verify_access_token

__all__ = ["SESSION_COOKIE", "Identity", "authenticated", "get_engine", "read_credential"]

#: The cookie the site's own route handler sets. `httpOnly`, so browser JavaScript
#: never reads it; the API accepts it and the `Authorization` header identically,
#: because a server-side caller has no cookie jar (research R3).
SESSION_COOKIE: Final[str] = "eaios_session"


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """One pooled engine for the process.

    Cached because the alternative is what `refusal_audit.py` does — build an engine per
    call — which creates a fresh connection pool for every request and is fine for a
    path that runs rarely and wrong for one that runs on every protected read.
    """
    return create_app_engine(get_settings())


@dataclass(frozen=True, slots=True)
class Identity:
    """A verified caller. Identifiers only; attributes are the access context's job."""

    claims: TokenClaims
    session: SessionRecord
    user_id: uuid.UUID
    company_id: uuid.UUID


def read_credential(request: Request) -> str | None:
    """The bearer token, from either transport.

    The header wins when both are present. A request carrying two different credentials
    is confused rather than malicious, and picking one deterministically beats
    picking whichever the framework happened to parse first.
    """
    header = request.headers.get("authorization")
    if header:
        scheme, _, value = header.partition(" ")
        if scheme.lower() == "bearer" and value.strip():
            return value.strip()
        # A malformed header is not a reason to fall back to the cookie: it means the
        # caller believes they are sending a credential, and silently using a different
        # one would make the failure impossible to understand.
        return None
    return request.cookies.get(SESSION_COOKIE)


def authenticated(request: Request) -> Iterator[tuple[Identity, Session]]:
    """Verify the caller and hand back a tenant-scoped database session.

    Yields rather than returns so the session — and its RLS scope — lives exactly as
    long as the request. Every refusal is :class:`NotAuthenticatedError` with no detail: the
    caller cannot tell an expired session from a signed-out one from a deactivated
    user, and neither can an attacker.
    """
    token = read_credential(request)
    if not token:
        raise NotAuthenticatedError("no credential presented")

    try:
        claims = verify_access_token(token)
    except InvalidTokenError as exc:
        raise NotAuthenticatedError(str(exc)) from exc

    now = dt.datetime.now(tz=dt.UTC)
    engine = get_engine()

    with session_scope(engine) as db, tenant_scope(db, claims.company_id):
        try:
            record = validate_session(db, claims.session_id, now=now)
        except InvalidSessionError as exc:
            _expire(claims, exc, now)
            raise NotAuthenticatedError(exc.reason) from exc

        # Re-read per request (FR-004). The credential says who; the database says
        # whether they may still ask.
        user = db.execute(
            select(User.id, User.company_id, User.is_active).where(User.id == claims.user_id)
        ).first()

        if user is None:
            # Under RLS this also covers "the user belongs to another tenant" — the row
            # is not visible in this scope, so there is nothing to compare.
            raise NotAuthenticatedError("no such user in this tenant")
        if not user.is_active:
            raise NotAuthenticatedError("user is not active")
        if user.company_id != claims.company_id or record.user_id != claims.user_id:
            # Belt and braces over RLS. If either of these ever fires, something has
            # gone wrong that a tenant predicate alone did not catch.
            raise NotAuthenticatedError("identity is inconsistent with its records")

        yield (
            Identity(
                claims=claims,
                session=record,
                user_id=claims.user_id,
                company_id=claims.company_id,
            ),
            db,
        )


def _expire(claims: TokenClaims, exc: InvalidSessionError, now: dt.datetime) -> None:
    """Mark a session ended, and record why — both on a **separate** connection.

    This is the subtle half of enforcing expiry. The request's transaction is about to
    unwind: `authenticated` raises, `session_scope` rolls back, and anything written
    alongside the raise is discarded. A first version marked `ended_at` inside that
    transaction and the write vanished — so the refusal was correct, the row still said
    the session was live, and touching `last_seen_at` afterwards brought it back. The
    test that caught it is `test_an_ended_session_cannot_be_revived`.

    Nothing happens when there is no bound to record: a session that was already ended
    wrote its entry at sign-out, and one that never existed is a refusal rather than an
    expiry.
    """
    if exc.end_reason is None:
        return

    from ..authz.audit import record_out_of_band

    engine = get_engine()
    try:
        with session_scope(engine) as db, tenant_scope(db, claims.company_id):
            end_session(db, claims.session_id, exc.end_reason, now=now)
    except Exception:  # pragma: no cover - must not turn a refusal into a 500
        get_logger(__name__).warning(
            "session.expiry_write_failed", reason=exc.end_reason
        )

    record_out_of_band(
        engine,
        action="auth.session_expired",
        company_id=claims.company_id,
        actor_user_id=claims.user_id,
        resource_type="session",
        resource_id=str(claims.session_id),
        decision="DENY",
        reason=exc.reason,
    )


#: The dependency routes declare. Named so a signature reads as what it requires.
AuthenticatedCaller = Depends(authenticated)
