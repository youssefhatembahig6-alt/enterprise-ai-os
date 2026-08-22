"""The server-built description of who is asking (spec 003 FR-008, FR-009).

Built once per request from verified identity and current database rows — never from
anything the request supplied (FR-010). Immutable thereafter, structurally rather than
by convention: ``frozen=True`` refuses attribute assignment and every collection is a
``frozenset``, so nothing downstream can add a permission, change the tenant, or widen
the scope of a request already in progress.

Request-scoped and never persisted. It describes what was true when the request
started, which is the point — FR-004 requires these attributes to be re-read per
request rather than carried in the credential, so a user deactivated after sign-in
loses access on their next request rather than at expiry.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Final

__all__ = ["NULL_SENTINEL", "AccessContext"]

#: How a missing attribute is written into a fingerprint. Chosen so no real value can
#: produce it: a UUID never contains `<`, and an ISO country code is two letters.
NULL_SENTINEL: Final[str] = "<null>"


def _render(value: object | None) -> str:
    """Render one nullable attribute for the fingerprint, explicitly."""
    return NULL_SENTINEL if value is None else str(value)


@dataclass(frozen=True, slots=True)
class AccessContext:
    """Who the server believes is asking, and what they hold."""

    company_id: uuid.UUID
    #: The slug, carried alongside the id because the cache and object-storage key
    #: builders take a slug and deriving one from an id would need a query.
    company_slug: str

    user_id: uuid.UUID
    session_id: uuid.UUID

    #: Nullable, because FR-014a distinguishes a caller *with* an attribute from a caller
    #: *without* one: the first reaches matching-or-company-wide documents, the second
    #: reaches only company-wide ones. A non-optional field cannot express the second
    #: caller at all, so `qdrant_filter` could never have been tested against them.
    #:
    #: Company identity and the classification ceiling stay mandatory. Those are the
    #: boundary; these two are narrowings, and a narrowing that is absent narrows to the
    #: company-wide set rather than to everything.
    department_id: uuid.UUID | None
    office_id: uuid.UUID
    country: str | None
    employment_type: str

    #: Both directions, as FR-008 requires, because they answer different questions.
    #: ``manager_id`` is "whose team am I on" — unused by this feature's rules and
    #: present because the requirement names it and feature 004's approval routing
    #: needs it. ``direct_report_ids`` is "whose records may I read", which is the one
    #: layer 3 consults. Null manager for exactly one user per company: the top-level
    #: executive.
    manager_id: uuid.UUID | None
    direct_report_ids: frozenset[uuid.UUID]

    #: **Display only.** FR-014 requires code to check permission codes and never role
    #: names, and `tests/unit/test_authz_policy.py` asserts by AST scan that the engine
    #: modules never read this field. It is here so the portal can say "Manager" in the
    #: interface, which is a presentation concern and not an access-control one.
    role_names: frozenset[str]

    #: Role identifiers, for matching ROLE-typed resource ACL grants at layer 4. Ids
    #: rather than names for the same reason as everywhere else: a name is a label that
    #: can be edited, and an ACL that followed a rename would silently change who has
    #: access.
    role_ids: frozenset[uuid.UUID]

    #: The only thing authorization decisions are made from.
    permission_codes: frozenset[str]

    def has(self, code: str) -> bool:
        """The single sanctioned permission test (FR-014)."""
        return code in self.permission_codes

    def manages(self, user_id: uuid.UUID) -> bool:
        """True when ``user_id`` reports **directly** to this caller.

        One level, deliberately. FR-024 says "direct reports"; the dataset has a
        multi-level hierarchy, so a transitive reading would silently widen every
        manager's reach. Widening it is a change to the specification, not to this
        method.
        """
        return user_id in self.direct_report_ids

    @property
    def permission_fingerprint(self) -> str:
        """A stable digest over tenant plus permission set (FR-016, Principle III).

        The component ``eaios_core.keys.cache_key`` has required since feature 001 and
        nothing has ever produced — the parameter existed, unfilled, waiting for the
        feature where a permission set first exists.

        Sorted before hashing, and that is the load-bearing detail. A ``frozenset``
        has no order, but its *iteration* order varies with insertion and with the
        process hash seed, so hashing the iteration order directly would produce a
        value that changed between processes: a cache that missed on every restart and
        a fingerprint that meant nothing.

        The tenant is included even though ``cache_key`` already takes one separately.
        It costs one field and removes any dependence on every future caller
        assembling the key correctly.

        **Department and country are included, and a missing one is explicit.** Two
        callers in one company can hold identical permission codes and still reach
        different documents, because the attribute layer narrows by department and
        country (FR-014a). A fingerprint blind to them would give both the same cache
        key for the same question and serve one the other's answer — the precise leak
        FR-018 exists to prevent.

        ``None`` is rendered as ``<null>``, which no real value can produce: a UUID
        never contains ``<`` and an ISO country code is two letters. Rendering it as
        the empty string would let a caller with no department collide with one whose
        department is somehow blank, and rendering it as ``"None"`` would collide with
        the literal country code ``"None"`` if one ever existed. The sentinel is chosen
        so that collision is impossible rather than unlikely.
        """
        material = "|".join(
            [
                str(self.company_id),
                f"department={_render(self.department_id)}",
                f"country={_render(self.country)}",
                *sorted(self.permission_codes),
            ]
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]
