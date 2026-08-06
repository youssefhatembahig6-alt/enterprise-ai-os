"""The types an authorization decision is made from and reported in (spec 003 §3).

Everything here is frozen and comparable. A decision that could be mutated after the
fact is a decision no audit entry can be trusted to describe.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum

from ..classification import Classification

__all__ = [
    "AclGrant",
    "Action",
    "Condition",
    "Decision",
    "KindPolicy",
    "ReasonCode",
    "ResourceDescriptor",
    "ResourceKind",
    "Rule",
    "Scope",
]


class Action(StrEnum):
    """What the caller wants to do.

    One member. Feature 003 reads and never writes, which is what keeps Principle
    VII's approval gate out of scope — and the enum exists rather than a bare string
    so the first write action is a change here, visible in review, rather than a new
    literal appearing at a call site.
    """

    READ = "READ"


class ResourceKind(StrEnum):
    """What is being reached for.

    Closed. An unknown kind cannot be constructed, so an endpoint cannot ask for a
    decision about something the rules table has never heard of.
    """

    HR_PROFILE = "HR_PROFILE"
    HR_COMPENSATION = "HR_COMPENSATION"
    DIRECT_REPORTS = "DIRECT_REPORTS"
    ACCESS_CONTEXT = "ACCESS_CONTEXT"
    SESSION = "SESSION"
    AUDIT_LOG = "AUDIT_LOG"


class Scope(StrEnum):
    """How wide the granted reach is. Reported for the audit trail, which needs to say
    not just that access was allowed but on what basis."""

    SELF = "SELF"
    TEAM = "TEAM"
    DEPARTMENT = "DEPARTMENT"
    COMPANY = "COMPANY"
    NONE = "NONE"


class ReasonCode(StrEnum):
    """Why the decision went the way it did.

    Stable strings: they are written into audit entries and asserted by tests, so
    renaming one is a data migration and not a refactor. Deliberately never shown to a
    caller — FR-022 forbids a refusal disclosing internal detail, and a reason code is
    exactly that.
    """

    # Denials, by layer.
    TENANT_MISMATCH = "TENANT_MISMATCH"  # 1
    PERMISSION_MISSING = "PERMISSION_MISSING"  # 2
    NOT_IN_REPORTING_LINE = "NOT_IN_REPORTING_LINE"  # 3
    ATTRIBUTE_MISMATCH = "ATTRIBUTE_MISMATCH"  # 3
    ACL_DENIED = "ACL_DENIED"  # 4
    CLASSIFICATION_TOO_HIGH = "CLASSIFICATION_TOO_HIGH"  # 5

    #: A required attribute was absent. Its own code rather than reusing the layer's
    #: ordinary denial, because "you may not" and "I could not tell" are different
    #: facts and only one of them is a bug worth chasing.
    CONTEXT_INCOMPLETE = "CONTEXT_INCOMPLETE"

    # Allows, distinguished so the trail says which rule applied.
    ALLOWED_SELF = "ALLOWED_SELF"
    ALLOWED_TEAM = "ALLOWED_TEAM"
    ALLOWED_ALL = "ALLOWED_ALL"


class Condition(StrEnum):
    """The attribute conditions layer 3 can evaluate.

    An enum rather than a callable so the rules table stays data — inspectable,
    printable, and comparable — instead of a collection of closures nobody can read
    without running them.
    """

    NONE = "NONE"
    IS_SELF = "IS_SELF"
    IS_DIRECT_REPORT = "IS_DIRECT_REPORT"


@dataclass(frozen=True, slots=True)
class AclGrant:
    """One resource-level grant. Layer 4's unit of evidence."""

    principal_type: str  # USER | ROLE | DEPARTMENT
    principal_id: uuid.UUID
    permission: str  # READ | WRITE


@dataclass(frozen=True, slots=True)
class ResourceDescriptor:
    """The **access attributes** of the thing being reached for — never its content.

    This split is what makes FR-015 checkable rather than aspirational. Deciding
    whether a manager may read an employee's profile needs that employee's
    ``company_id`` and ``manager_id``; it does not need their salary. So a descriptor
    is populated by a query that selects access columns only, the decision is made, and
    the payload is read afterwards — and a denied request therefore performs no read of
    the data it was denied.

    A descriptor carrying a payload field would quietly undo that, which is why
    ``tests/security/test_authorize_before_read.py`` asserts this class declares none.

    ``acl_grants`` distinguishes three states on purpose. ``None`` means *not loaded*,
    an empty set means *loaded and nothing was granted*, and a populated set means
    *these were granted*. Collapsing the first two would make a forgotten query
    indistinguishable from a correct refusal.
    """

    kind: ResourceKind
    resource_id: str | None = None
    company_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    classification: Classification | None = None
    acl_grants: frozenset[AclGrant] | None = None


@dataclass(frozen=True, slots=True)
class Rule:
    """One way to be allowed: a permission code, and a condition on top of it.

    ``permission=None`` means no code is required — used only where the resource *is*
    the caller (their own session, their own access context), so the ownership
    condition is the whole rule.
    """

    permission: str | None
    condition: Condition
    scope: Scope
    allow_reason: ReasonCode


@dataclass(frozen=True, slots=True)
class KindPolicy:
    """Everything the engine needs to decide one ``(kind, action)`` pairing.

    ``rules`` are alternatives, evaluated in order: the first whose code the caller
    holds *and* whose condition passes decides.

    ``acl_gated`` and ``classified`` say whether layers 4 and 5 apply at all. They are
    per-kind rather than global because an HR profile has no resource ACL and no
    classification — those are document properties. A global layer 4 would have to read
    an empty grant set as "nothing granted" and deny every profile read; a per-kind
    flag says "this layer does not apply here" without pretending it passed.
    """

    rules: tuple[Rule, ...]
    acl_gated: bool = False
    classified: bool = False


@dataclass(frozen=True, slots=True)
class Decision:
    """The answer, and everything the caller needs to act on it without re-deciding."""

    allowed: bool
    reason: ReasonCode
    #: Which of the five layers decided a denial. ``None`` on an allow — nothing
    #: refused, so there is no layer to name.
    layer: int | None
    scope: Scope
    #: FR-017/017a. Computed once, here, from the single sensitivity definition, so no
    #: router restates the rule and adding a resource kind is one edit.
    audit_required: bool
    #: True only when layer 1 refused. The API maps this to *not found* and every other
    #: denial to *forbidden* (FR-021, FR-030) — one boolean, decided once, so a router
    #: cannot accidentally answer 403 for a resource in another tenant and confirm it
    #: exists.
    tenant_absent: bool = field(default=False)
