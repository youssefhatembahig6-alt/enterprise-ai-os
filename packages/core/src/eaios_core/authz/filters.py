"""Retrieval filters derived from the access context (Constitution Principle III).

Declared now, used by feature 004. Principle III requires payload filters to be applied
**at search time** rather than after generation — "the system does not retrieve
confidential material and then ask the model to withhold it" — so the filter has to be
a function of the access context, and the access context is what this feature builds.

**Nothing here searches anything.** No Qdrant client is imported, no connection is
opened, and the vector collections hold nothing to search (feature 001 decision D2).
Defining it here means feature 004 consumes a filter derived from the same context the
policy engine reads, rather than inventing a second, subtly different notion of what a
caller may see.

It is unit-tested against a real context, which is the only honest thing to do with
code that cannot yet be exercised end to end.
"""

from __future__ import annotations

from typing import Any

from ..classification import Classification
from .context import AccessContext

__all__ = ["MAX_ANONYMOUS_CLASSIFICATION", "qdrant_filter"]

#: The ceiling for a caller with no explicit grant. Above this, Principle III's payload
#: filter is not sufficient on its own and a resource ACL decides — which is layer 4 of
#: the policy engine, not a filter.
MAX_ANONYMOUS_CLASSIFICATION = Classification.INTERNAL


def qdrant_filter(subject: AccessContext) -> dict[str, Any]:
    """The payload constraint for one caller's retrieval.

    Returns a plain mapping rather than a Qdrant filter object, deliberately: this
    package must not depend on a vector-store client, and a dict is what the search
    layer translates. The keys are the payload fields Principle III enumerates.

    ``company_id`` is first and unconditional. Every other key narrows further; that
    one is the boundary, and a filter built without it is not a narrower search but an
    unbounded one.
    """
    return {
        # Principle I. Not negotiable, not optional, and not derived from anything the
        # request supplied.
        "company_id": str(subject.company_id),
        "department_id": str(subject.department_id),
        "country": subject.country,
        # Levels reachable without an explicit resource grant. RESTRICTED is absent by
        # construction: `Classification.requires_explicit_grant` says role alone is
        # insufficient there, so it cannot be reached by a payload filter at all.
        "classification": [
            level.value
            for level in Classification
            if level <= MAX_ANONYMOUS_CLASSIFICATION
        ],
        # Sent as ids. A chunk's `allowed_roles` payload is matched against the
        # caller's roles, and matching by name would follow a rename into granting
        # access nobody decided to grant.
        "allowed_roles": sorted(str(role_id) for role_id in subject.role_ids),
        "owner_id": str(subject.user_id),
    }
