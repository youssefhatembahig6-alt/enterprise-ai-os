"""Noticing when a request tries to supply its own authority (spec 003 FR-010).

FR-010 has two halves. The first — such a value MUST be ignored — is satisfied by the
access context being built entirely from the database; nothing in this module is
required for that, and nothing in it can weaken it. The second half is the SHOULD: the
attempt ought to be recorded.

That is what this is for, and it is worth being clear about what it is *not*. This is
not a filter and it must never become one. A value that reached a route and had to be
stripped would mean something was reading it, and the answer to that is to stop reading
it — not to sanitise the input. The guard observes; the context is the control.

**Names, not values.** The entry records that a field with a tenant-ish name appeared,
never what it contained. A probe's payload is exactly the kind of thing that should not
be copied into a table other people read, and feature 002 already made that call for
anonymous refusals.
"""

from __future__ import annotations

from typing import Final

from fastapi import Request
from sqlalchemy.orm import Session

from eaios_core.authz import AccessContext

from .audit import record

__all__ = ["SUSPECT_NAMES", "note_supplied_authority", "supplied_authority_names"]

#: Field names that would be an attempt to supply identity, tenant, or authority.
#:
#: A closed list, and deliberately a small one. It is a *detector*, so a name missing
#: from it costs an audit entry and nothing else — the value was already ignored. A name
#: wrongly on it would cost a false entry every time an unrelated parameter happened to
#: match, which is the more expensive mistake.
SUSPECT_NAMES: Final[frozenset[str]] = frozenset(
    {
        "company",
        "company_id",
        "companyid",
        "tenant",
        "tenant_id",
        "tenantid",
        "user_id",
        "userid",
        "sub",
        "role",
        "roles",
        "permission",
        "permissions",
        "scope",
    }
)


def _normalise(name: str) -> str:
    return name.strip().lower().removeprefix("x-").replace("-", "_")


def supplied_authority_names(request: Request) -> list[str]:
    """Which suspect names appear, and where. Sorted, so the entry is stable.

    Query, headers, and cookies — the three places a caller chooses freely.

    **Path parameters are deliberately not inspected.** `/hr/profiles/{user_id}` names
    the *resource*, not the caller, and it is the route that decides what the segment
    means. Scanning them would fire on every profile read and fill the trail with
    entries for the feature's most ordinary request, which is how a signal becomes
    noise and then gets switched off.

    **The body is not read.** Doing so would consume the stream a route is about to
    parse, and a body value is already *refused* rather than ignored — every request
    model sets `extra="forbid"`, so a `company_id` in a sign-in body is a 422 and never
    reaches this point.
    """
    found: set[str] = set()

    for name in request.query_params:
        if _normalise(name) in SUSPECT_NAMES:
            found.add(f"query:{_normalise(name)}")

    for name in request.headers:
        normalised = _normalise(name)
        if normalised in SUSPECT_NAMES:
            found.add(f"header:{normalised}")

    for name in request.cookies:
        if _normalise(name) in SUSPECT_NAMES:
            found.add(f"cookie:{_normalise(name)}")

    return sorted(found)


def note_supplied_authority(
    request: Request, subject: AccessContext, db: Session
) -> list[str]:
    """Record an attempt, if there was one. Returns what was seen, for tests.

    Written under the **caller's** company, because that is whose action it was — the
    tenant they named is not theirs to have an audit trail in.
    """
    names = supplied_authority_names(request)
    if not names:
        return []

    record(
        db,
        action="authz.tenant_value_supplied",
        company_id=subject.company_id,
        actor_user_id=subject.user_id,
        resource_type="request",
        resource_id=f"{request.method} {request.url.path}"[:128],
        decision="DENY",
        # Names only. Never the values.
        reason=f"ignored request-supplied authority fields: {', '.join(names)}",
    )
    return names
