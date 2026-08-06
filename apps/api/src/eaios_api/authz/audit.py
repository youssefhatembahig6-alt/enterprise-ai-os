"""Writing the audit trail (spec 003 FR-017, FR-018; Constitution Principle X).

One writer, one field allowlist. The alternative — each router assembling its own entry
— is how a field that must never be recorded eventually gets recorded by the one call
site nobody reviewed.

**What is recorded.** Every denial, always, with no exemption and no coalescing: they
are the security signal. Allows only when the resource is sensitive, decided once by
`eaios_core.authz.sensitivity` and carried on the decision itself, so no call site
restates the rule (FR-017b).

**What is never recorded.** No password, no token, no fragment of either, and no
attempted email address (FR-018). The email is worth being explicit about: an audit
table listing every address someone tried is an enumeration surface with a longer memory
than the sign-in form, readable by anyone holding `audit:read`. The operational question
— "is one account under attack?" — is answerable from the bound counters, which key on
a digest.

**Attribution on a cross-tenant attempt.** The entry is written under the **actor's**
company, never the target's. Writing a NileTech action into Delta Retail's trail would
itself be a cross-tenant leak, and FR-030 makes it coherent: at layer 1 the other
tenant's resource is absent, so there is nothing of theirs to attribute.

**Failing to audit must not change what the caller receives.** The refusal or the read
already happened; turning a logging outage into a 500 would convert an observability
problem into a service one. Writes are best-effort and their failure is logged.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Final, Literal

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from eaios_core.authz import Decision
from eaios_core.db import session_scope, tenant_scope
from eaios_core.logging import get_logger
from eaios_core.models import AuditLog

__all__ = ["AuditAction", "record", "record_decision", "record_out_of_band"]

logger = get_logger(__name__)

#: Every action this feature writes. A closed set so a typo becomes an import error
#: rather than an entry nobody can find again by searching for the name they expected.
AuditAction = Literal[
    "auth.sign_in",
    "auth.sign_in_failed",
    "auth.locked_out",
    "auth.sign_out",
    "auth.session_expired",
    "authz.denied",
    "authz.allowed",
    "authz.tenant_value_supplied",
]

#: Bounds the column and, more usefully, bounds what a caller can push into the trail by
#: putting a very long value in a path segment.
_MAX_RESOURCE_ID: Final[int] = 128
_MAX_REASON: Final[int] = 500


def _now() -> dt.datetime:
    """Wall clock. An authorization decision is a runtime event, not dataset content."""
    return dt.datetime.now(tz=dt.UTC)


def record(
    db: Session,
    *,
    action: AuditAction,
    company_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    resource_type: str,
    resource_id: str | None,
    decision: Literal["ALLOW", "DENY"],
    reason: str,
) -> None:
    """Write one entry through an already tenant-scoped session.

    Flushed here rather than left to the caller's commit: `tenant_scope` clears
    `app.company_id` on exit and the commit happens after that, so a deferred INSERT
    would be evaluated against an unset tenant and refused by RLS. Feature 002
    documented this trap in `refusal_audit.py`; it is the same one.
    """
    db.add(
        AuditLog(
            id=uuid.uuid4(),
            company_id=company_id,
            actor_user_id=actor_user_id,
            actor_type="USER" if actor_user_id else "SYSTEM",
            action=action,
            resource_type=resource_type[:64],
            resource_id=resource_id[:_MAX_RESOURCE_ID] if resource_id else None,
            decision=decision,
            reason=reason[:_MAX_REASON],
            sources=[],
            created_at=_now(),
        )
    )
    db.flush()


def _decision_reason(outcome: Decision) -> str:
    """The reason code, plus the layer that decided.

    Both are internal vocabulary and neither ever reaches a response body (FR-022). The
    layer matters to whoever reads the trail: "no such permission" and "not your
    report" are different findings, and so are the layers they fire at.
    """
    layer = f" at layer {outcome.layer}" if outcome.layer is not None else ""
    return f"{outcome.reason.value}{layer} (scope {outcome.scope.value})"


def record_decision(
    db: Session,
    engine: Engine,
    *,
    company_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    resource_type: str,
    resource_id: str | None,
    outcome: Decision,
) -> None:
    """Write an authorization decision, if it needs writing.

    ``Decision.audit_required`` is computed by the engine from the single sensitivity
    definition. Consulting it here rather than re-deriving the rule is what FR-017b
    asks for: adding a resource type is a change to that definition and to nothing else.

    **Allows and denials take different connections, and they have to.** An allow is
    written into the request's transaction and commits with it, which is right: if the
    request then fails, the read never happened and the entry describing it should not
    survive.

    A denial cannot do that. `authorize` raises immediately afterwards, `session_scope`
    rolls back on exception, and the entry is discarded — so *every denial went
    unrecorded* while FR-017 said each one must be. That is the requirement's whole
    point, and it failed silently: the refusal was correct, the response was correct,
    and the trail was empty. `tests/security/test_authz_audit.py` is what found it.
    """
    if not outcome.audit_required:
        return

    kwargs = {
        "action": "authz.allowed" if outcome.allowed else "authz.denied",
        "company_id": company_id,
        "actor_user_id": actor_user_id,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "decision": "ALLOW" if outcome.allowed else "DENY",
        "reason": _decision_reason(outcome),
    }

    if outcome.allowed:
        record(db, **kwargs)  # type: ignore[arg-type]
    else:
        record_out_of_band(engine, **kwargs)  # type: ignore[arg-type]


def record_out_of_band(
    engine: Engine,
    *,
    action: AuditAction,
    company_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    resource_type: str,
    resource_id: str | None,
    decision: Literal["ALLOW", "DENY"],
    reason: str,
) -> None:
    """Write an entry on its own connection, for paths with no request session.

    Sign-in failures are the case that needs this: there is no authenticated session to
    piggyback on, and the tenant is whichever one the address resolved to — or, when it
    resolved to none, the one the attempt was aimed at.

    Best-effort. An audit outage must not turn a refusal into a 500.
    """
    try:
        with session_scope(engine) as db, tenant_scope(db, company_id):
            record(
                db,
                action=action,
                company_id=company_id,
                actor_user_id=actor_user_id,
                resource_type=resource_type,
                resource_id=resource_id,
                decision=decision,
                reason=reason,
            )
    except Exception:  # pragma: no cover - audit must not break the response
        logger.warning("audit.write_failed", action=action)
