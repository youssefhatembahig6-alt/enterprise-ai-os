"""Turning a decision into a response, and recording it (spec 003 FR-015, FR-017–FR-021).

One function, and its shape is the point: it **decides, audits, and raises** — it never
returns a boolean for a caller to interpret. A route that received `allowed: False` and
had to remember to raise the right exception is a route that will eventually forget, and
the forgetting looks like a successful read.

**The status is not chosen here either.** `tenant_absent` → 404, any other denial →
403, allow → return. That mapping is decided once, from a flag the engine sets only at
layer 1, so no route can accidentally answer 403 for a resource in another tenant and
thereby confirm it exists (FR-021, FR-030).

**Call this before reading the payload.** The descriptor is built from access
attributes — `company_id`, `owner_id`, `manager_id`, `classification` — and the
protected fields are read only after this returns. That ordering is FR-015, and
`tests/security/test_authorize_before_read.py` proves it by recording the statements a
request actually executed rather than by inspecting its response.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from eaios_core.authz import AccessContext, Action, Decision, ResourceDescriptor, evaluate

from ..auth.dependencies import get_engine
from ..errors import AccessDeniedError, ResourceAbsentError
from .audit import record_decision

__all__ = ["authorize"]


def authorize(
    subject: AccessContext,
    db: Session,
    action: Action,
    resource: ResourceDescriptor,
) -> Decision:
    """Decide, audit, and either return or refuse.

    Returns the decision so a caller can read its ``scope`` — a team-scoped allow and a
    company-scoped one reach the same record for different reasons, and a later feature
    may want to narrow what it returns accordingly. Nothing needs to check ``allowed``:
    if this returned, it was allowed.
    """
    decision = evaluate(subject, action, resource)

    # Audited before the refusal is raised. `record_decision` consults
    # `audit_required`, which the engine computed from the single sensitivity
    # definition — denials always, allows only when the resource is sensitive (FR-017,
    # FR-017a) — and routes a denial to its own connection, because this function is
    # about to raise and the request's transaction will roll back underneath it.
    record_decision(
        db,
        get_engine(),
        company_id=subject.company_id,
        actor_user_id=subject.user_id,
        resource_type=resource.kind.value,
        resource_id=resource.resource_id,
        outcome=decision,
    )

    if decision.allowed:
        return decision

    if decision.tenant_absent:
        # Layer 1 fired: the resource belongs to another tenant, so it is *absent*
        # rather than denied. Answering 403 here would confirm the record exists, which
        # is the enumeration this ordering exists to prevent.
        raise ResourceAbsentError(decision.reason.value)

    raise AccessDeniedError(decision.reason.value)
