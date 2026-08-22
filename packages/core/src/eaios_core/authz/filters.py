"""Retrieval filters derived from the access context (Constitution Principle III).

Principle III requires payload filters to be applied **at search time** rather than after
generation — "the system does not retrieve confidential material and then ask the model to
withhold it". So the filter is a function of the access context, and there is deliberately
no post-filter anywhere: a second pass that dropped rows after the search would satisfy
FR-013's letter and break its intent, because the passages would already have been read,
ranked, and counted.

**Verified by** `tests/unit/test_qdrant_filter.py` (every clause present, each removal
detected), `tests/unit/test_qdrant_filter_null_scope.py` (FR-014a null semantics),
`tests/security/test_filter_invariants.py` (tenant and classification never widened) and
`tests/unit/test_qdrant_filter_grants.py` (the five-layer order). The previous docstring
claimed this function was unit-tested when no such test existed — the claim is now true
and names where to check it.

**Why the shape is structured rather than a flat mapping.** A flat `{"country": "EG"}`
cannot express *null means company-wide*. Equality against `None` matches nothing, so a
document deliberately scoped to the whole company — the handbook, the travel policy —
would be invisible to everyone. The clause therefore has to say "equals mine **or** is
null", which needs a nested should-group (contracts §3).

**The five layers, and which are boundaries.** FR-014 orders them tenant, role, attribute,
resource grant, classification. Two of those are *boundaries* and are `must` clauses that
nothing widens:

* ``company_id`` — Principle I. A filter without it is not a narrower search, it is an
  unbounded one.
* ``classification`` — the ceiling. Above it, a payload filter is not sufficient on its
  own and a resource ACL decides.

The rest are *reaches*, and any one of them is enough: the caller's own attributes, a role
the document admits, ownership, or an explicit grant. They sit in a single should-group
with a minimum of one, because a caller who owns a document reaches it even when it
belongs to another department — that is what ownership means.

**The explicit grant arrives as ids, and that is a deliberate shape.** `document_acl` is
relational; a Qdrant payload is not. So layer 4 cannot be a clause the way ownership is.
The retrieval service (T094) resolves READ grants for the caller's user id, role ids and
department id — scoped to their company — **before** the search, and passes the resulting
document ids here. Three consequences, each load-bearing:

* Resolution happens *before* the query, so the grant **narrows the search** rather than
  filtering its results. Post-filtering would satisfy FR-013's letter and break its intent.
* This function **queries nothing**. It renders what it is handed, which is why the package
  depends on a database no more than it depends on a vector-store client.
* The ids are **never request-supplied**. They are derived server-side from a verified
  context; an endpoint that accepted them would be taking an authorization decision from
  the caller (FR-029). The parameter is keyword-only and defaults to empty for that reason:
  a caller who skips resolution gets no grant, never every grant.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Final

from ..classification import Classification
from .context import AccessContext

__all__ = [
    "FILTER_KEYS",
    "MAX_ANONYMOUS_CLASSIFICATION",
    "attribute_clause",
    "qdrant_filter",
]

#: The ceiling for a caller with no explicit grant. Above this, Principle III's payload
#: filter is not sufficient on its own and a resource ACL decides — which is layer 4 of
#: the policy engine, not a filter.
MAX_ANONYMOUS_CLASSIFICATION = Classification.INTERNAL

#: Every payload field this filter references, in FR-014b's order.
#:
#: **This is the canonical list.** `tests/integration/test_payload_indexes.py` derives the
#: set of required payload indexes from it rather than from a hand-maintained copy, so a
#: clause added here without an index fails that test instead of degrading a query plan
#: silently.
FILTER_KEYS: Final[tuple[str, ...]] = (
    "company_id",
    "classification",
    "department_id",
    "country",
    "allowed_roles",
    "owner_id",
    "document_id",
)


def _match(key: str, value: Any) -> dict[str, Any]:
    return {"key": key, "match": {"value": value}}


def _match_any(key: str, values: list[Any]) -> dict[str, Any]:
    return {"key": key, "match": {"any": values}}


def _is_null(key: str) -> dict[str, Any]:
    return {"is_null": {"key": key}}


def attribute_clause(key: str, value: Any) -> dict[str, Any]:
    """One attribute narrowing, with FR-014a's null semantics on both sides.

    Args:
        key: The payload field.
        value: The caller's value, or ``None`` when the caller has none.

    Returns:
        A should-group requiring at least one branch.

    The two cases differ and the difference is the requirement:

    * **Caller has a value** — reaches documents matching it *or* documents scoped
      company-wide (null). Two branches.
    * **Caller has none** — reaches *only* company-wide documents. One branch.

    Exposed rather than private because it is the unit that carries the semantics, and a
    caller with no department is not otherwise constructible in every consumer's tests.
    Note that the clause is never *omitted* for a null caller: dropping it would widen the
    search to every department, which is the opposite of what an absent attribute means.
    """
    branches: list[dict[str, Any]] = [_is_null(key)]
    if value is not None:
        branches.insert(0, _match(key, str(value)))
    return {"should": branches, "min_should": 1}


def qdrant_filter(
    subject: AccessContext,
    *,
    granted_document_ids: Iterable[Any] = (),
) -> dict[str, Any]:
    """The payload constraint for one caller's retrieval.

    Args:
        subject: The verified access context.
        granted_document_ids: Document ids the retrieval service resolved from
            `document_acl` for this caller, as READ grants, before the search. Empty when
            resolution found none — and empty by default, so a caller who omits the step
            gets no grant reach rather than an unbounded one. **Never request-supplied.**

    Returns:
        A plain mapping rather than a Qdrant filter object, deliberately: this package
        must not depend on a vector-store client, and a dict is what the search layer
        translates.

    The result is a pre-filter. Nothing downstream re-checks it, which is why every clause
    here is load-bearing and why `tests/unit/test_qdrant_filter.py` fails when any one of
    them goes missing.
    """
    reachable_levels = [
        level.value for level in Classification if level <= MAX_ANONYMOUS_CLASSIFICATION
    ]

    # Sorted and de-duplicated at the boundary: resolution joins three principal kinds, so
    # the same document arrives more than once, and two orderings of one grant set must
    # produce one filter or an identical query becomes a cache miss. Copied here rather
    # than held, so a list the caller mutates afterwards cannot change a built filter.
    granted = sorted({str(identifier) for identifier in granted_document_ids})

    return {
        "must": [
            # Layer 1 — tenant. Unconditional, never widened, not derived from anything
            # the request supplied.
            _match("company_id", str(subject.company_id)),
            # Layer 5 — classification ceiling. RESTRICTED is absent by construction:
            # `Classification.requires_explicit_grant` says role alone is insufficient
            # there, so it cannot be reached by a payload filter at all.
            _match_any("classification", reachable_levels),
            # Layers 2–4 — the reaches. Any one suffices.
            {
                "should": [
                    # Layer 3 — attributes. Both dimensions must admit the caller, so
                    # they are nested `must` rather than two loose branches: a document
                    # in the right country but the wrong department is not reachable
                    # this way.
                    {
                        "must": [
                            attribute_clause("department_id", subject.department_id),
                            attribute_clause("country", subject.country),
                        ]
                    },
                    # Layer 2 — role. Sent as ids: matching by name would follow a rename
                    # into granting access nobody decided to grant.
                    _match_any("allowed_roles", sorted(str(role) for role in subject.role_ids)),
                    # Layer 4 — ownership. A caller reaches their own documents whatever
                    # department or country those documents carry.
                    _match("owner_id", str(subject.user_id)),
                    # Layer 4 — the explicit grant, already resolved. Omitted entirely
                    # when nothing was granted: an empty match-any is a branch that
                    # matches nothing today and a branch someone widens tomorrow, and the
                    # absence of a grant should be the absence of the reach.
                    *([_match_any("document_id", granted)] if granted else []),
                ],
                "min_should": 1,
            },
        ]
    }
