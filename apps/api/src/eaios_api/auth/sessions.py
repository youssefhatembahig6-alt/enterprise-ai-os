"""Server-side session records (spec 003 FR-005, FR-007).

**Why the session is state and not just a token.** FR-007 requires signing out to end
access. A self-contained credential cannot be withdrawn: without a row to mark ended,
"sign out" deletes the client's copy and leaves the credential valid until it expires.
The cost of the row is small because the lookup was happening anyway — FR-004 already
requires active status and tenant membership to be re-read from current records on
every request, so session validity joins a query that runs regardless.

**Two bounds, and only one of them moves.** ``last_seen_at`` advances with use;
``absolute_expires_at`` is written at sign-in and never touched again. A single
combined expiry pushed forward on activity silently discards the cap, and the cap is
the only bound that limits how long a stolen credential stays useful — a session kept
alive by constant use would never end.

Every function here takes a session that is **already tenant-scoped**. Binding the
tenant is the caller's job (see :mod:`eaios_api.authz.dependencies`); doing it here
would need a tenant this module has no trustworthy source for.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from eaios_core.models import UserSession
from eaios_core.settings import Settings, get_settings

__all__ = [
    "EndReason",
    "InvalidSessionError",
    "SessionRecord",
    "create_session",
    "end_session",
    "validate_session",
]

EndReason = Literal["SIGN_OUT", "IDLE", "ABSOLUTE"]


class InvalidSessionError(Exception):
    """The session named by a credential is not usable.

    Carries the reason for the audit trail and for nothing else. The caller answers 401
    identically whatever it says — a response that distinguished "expired" from "signed
    out" from "never existed" would be telling an attacker which of those they are
    looking at.

    ``end_reason`` is set when this session has *just* reached a bound and needs to be
    marked ended. The marking cannot happen here: raising unwinds the request's
    transaction, and `session_scope` rolls back on exception — so a write made
    alongside the raise is discarded, and the session comes back to life the moment its
    timestamps are touched again. The caller performs it on its own connection.
    """

    def __init__(self, reason: str, end_reason: EndReason | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.end_reason: EndReason | None = end_reason


@dataclass(frozen=True, slots=True)
class SessionRecord:
    id: uuid.UUID
    company_id: uuid.UUID
    user_id: uuid.UUID
    issued_at: dt.datetime
    absolute_expires_at: dt.datetime
    last_seen_at: dt.datetime


def create_session(
    db: Session,
    *,
    user_id: uuid.UUID,
    company_id: uuid.UUID,
    now: dt.datetime,
    settings: Settings | None = None,
) -> SessionRecord:
    """Open a session. The absolute cap is fixed here and never revised."""
    cfg = settings or get_settings()
    row = UserSession(
        id=uuid.uuid4(),
        company_id=company_id,
        user_id=user_id,
        issued_at=now,
        absolute_expires_at=now + dt.timedelta(seconds=cfg.auth.absolute_lifetime_seconds),
        last_seen_at=now,
        ended_at=None,
        ended_reason=None,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    # Flushed inside the caller's tenant scope. A deferred INSERT would be evaluated
    # after `tenant_scope` cleared `app.company_id` and refused by RLS — the same trap
    # feature 002 documented in `refusal_audit.py`.
    db.flush()
    return _record(row)


def validate_session(
    db: Session,
    session_id: uuid.UUID,
    *,
    now: dt.datetime,
    settings: Settings | None = None,
) -> SessionRecord:
    """Check a session is live, advance its activity, and return it.

    Checks run in the order FR-005 implies, and the order matters for the audit trail
    rather than for correctness: a session that is both past its cap and idle is
    reported as having hit the cap, which is the more informative fact.

    Raises :class:`InvalidSessionError` for every failure, including "no such session" —
    which is what a credential for another tenant produces, because the lookup runs
    inside the caller's tenant scope and RLS makes another company's row simply absent.
    """
    cfg = settings or get_settings()
    row = db.execute(
        select(UserSession).where(UserSession.id == session_id)
    ).scalar_one_or_none()

    if row is None:
        raise InvalidSessionError("no such session for this tenant")

    if row.ended_at is not None:
        # Already ended, and it stays ended. Re-deriving liveness from the timestamps
        # here would let a session come back the moment the row was touched.
        raise InvalidSessionError(f"session already ended ({row.ended_reason})")

    # Checked before the idle bound so a session that is both past its cap and idle is
    # reported as having hit the cap — the more informative of the two facts, and the
    # one that says the credential's useful life is over rather than paused.
    if now >= row.absolute_expires_at:
        raise InvalidSessionError("session reached its absolute lifetime", end_reason="ABSOLUTE")

    idle_for = now - row.last_seen_at
    if idle_for >= dt.timedelta(seconds=cfg.auth.idle_timeout_seconds):
        raise InvalidSessionError("session was idle past its timeout", end_reason="IDLE")

    row.last_seen_at = now
    row.updated_at = now
    db.flush()
    return _record(row)


def end_session(
    db: Session, session_id: uuid.UUID, reason: EndReason, *, now: dt.datetime
) -> bool:
    """End a session. Returns False when it was already ended.

    Idempotent on purpose: a second sign-out succeeds. An interrupted request that
    could not complete an action it had already completed would leave the interface
    stuck on something that already happened.
    """
    row = db.execute(
        select(UserSession).where(UserSession.id == session_id)
    ).scalar_one_or_none()
    if row is None or row.ended_at is not None:
        return False
    _end(row, reason, now)
    db.flush()
    return True


def _end(row: UserSession, reason: EndReason, now: dt.datetime) -> None:
    row.ended_at = now
    row.ended_reason = reason
    row.updated_at = now


def _record(row: UserSession) -> SessionRecord:
    return SessionRecord(
        id=row.id,
        company_id=row.company_id,
        user_id=row.user_id,
        issued_at=row.issued_at,
        absolute_expires_at=row.absolute_expires_at,
        last_seen_at=row.last_seen_at,
    )
