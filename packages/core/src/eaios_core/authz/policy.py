"""The deterministic authorization decision (spec 003 FR-012-FR-015).

Constitution Principle II (NON-NEGOTIABLE) requires this to be code, and requires the
layers in a fixed order: tenant, RBAC, ABAC, resource ACL, classification. Both halves
are implemented here and both are tested — that a single failing condition denies is
barely a property; the claim FR-013 makes is that a request failing *several* layers
reports the **earliest** one.

That ordering is not tidiness. Layer 1 answers *not found* while layers 2 through 5
answer *forbidden* (FR-021, FR-030), so an engine that consulted RBAC first would
return 403 for a resource in another tenant and thereby confirm it exists. The order
is the anti-enumeration property.

**Pure.** No database, no cache, no clock, no randomness, no environment, and no
import from `apps/`, `services/`, or `scripts/` — enforced by
`tests/unit/test_dependency_direction.py`, which parses rather than greps. Purity is
the more consequential half of the design: layer ordering, short-circuiting, reason
codes, and default-deny are all unit tests with nothing running, which is what turns
"write the security test first" from a discipline into the path of least resistance.

**No model may call this, influence it, or be called by it.** This feature introduces
none; the boundary is stated so it exists before one arrives.
"""

from __future__ import annotations

from .context import AccessContext
from .decision import (
    AclGrant,
    Action,
    Condition,
    Decision,
    KindPolicy,
    ReasonCode,
    ResourceDescriptor,
    Scope,
)
from .rules import POLICIES
from .sensitivity import is_sensitive

__all__ = ["evaluate", "evaluate_with"]


def evaluate(
    subject: AccessContext, action: Action, resource: ResourceDescriptor
) -> Decision:
    """Decide one request. The entry point every route uses.

    Closed over the rules table: a ``(kind, action)`` pairing nobody wrote a rule for
    denies. Falling through to allow is how an endpoint ships unprotected, and it is
    the single most expensive default available here.
    """
    policy = POLICIES.get((resource.kind, action))
    if policy is None:  # pragma: no cover - the rules table covers every kind
        return _deny(ReasonCode.PERMISSION_MISSING, layer=2)
    return evaluate_with(subject, action, resource, policy)


def evaluate_with(
    subject: AccessContext,
    action: Action,
    resource: ResourceDescriptor,
    policy: KindPolicy,
) -> Decision:
    """Decide against a supplied policy rather than the table.

    Exists because layers 4 and 5 have nothing to decide for *this* feature's resource
    kinds — an HR profile carries neither a resource ACL nor a classification, because
    neither is a document. The layers are still implemented and still ordered, and they
    still have to be proven, so the engine tests drive them through here.

    Not a hole: constructing a ``KindPolicy`` is a deliberate act, and ``evaluate``
    stays closed over the real table. Feature 004's document kind adds a table entry
    and stops needing this.
    """
    del action  # part of the signature for symmetry with `evaluate`; the policy is
    # already resolved for this action by the time we get here.

    # --- Layer 1: the tenant boundary ---------------------------------------
    #
    # First, always, and never bypassed. A resource in another tenant is *absent*, not
    # denied — which is why `tenant_absent` is set here and nowhere else.
    if resource.company_id is None:
        # Not a cross-tenant refusal: a missing tenant is a defect in the caller that
        # built this descriptor. Reporting it as absence would turn a bug into a 404
        # and hide it.
        return _deny(ReasonCode.CONTEXT_INCOMPLETE, layer=1)
    if resource.company_id != subject.company_id:
        return _deny(ReasonCode.TENANT_MISMATCH, layer=1, tenant_absent=True)

    if not policy.rules:
        return _deny(ReasonCode.PERMISSION_MISSING, layer=2)

    # --- Layer 2: RBAC permission codes -------------------------------------
    #
    # Codes, never role names (FR-014). A check written against a role name is a defect
    # even when it produces the right answer, because it breaks the moment roles are
    # recomposed.
    held = tuple(
        rule
        for rule in policy.rules
        if rule.permission is None or subject.has(rule.permission)
    )
    if not held:
        return _deny(ReasonCode.PERMISSION_MISSING, layer=2)

    # --- Layer 3: attribute conditions --------------------------------------
    chosen = None
    saw_incomplete = False
    saw_relationship = False
    for rule in held:
        outcome = _condition_holds(rule.condition, subject, resource)
        if outcome is None:
            saw_incomplete = True
        elif outcome:
            chosen = rule
            break
        elif rule.condition is Condition.IS_DIRECT_REPORT:
            saw_relationship = True

    if chosen is None:
        if saw_incomplete:
            return _deny(ReasonCode.CONTEXT_INCOMPLETE, layer=3)
        # A reporting-line failure gets its own code: "not your report" and "some other
        # attribute did not match" are different findings for whoever reads the trail.
        if saw_relationship:
            return _deny(ReasonCode.NOT_IN_REPORTING_LINE, layer=3)
        return _deny(ReasonCode.ATTRIBUTE_MISMATCH, layer=3)

    # --- Layer 4: resource-level access control -----------------------------
    #
    # Only for kinds that have one. A global layer 4 would have to read an empty grant
    # set as "nothing granted" and would then deny every HR profile read — a layer that
    # does not apply is not a layer that failed.
    granted_by_acl = False
    if policy.acl_gated:
        if resource.acl_grants is None:
            return _deny(ReasonCode.CONTEXT_INCOMPLETE, layer=4)
        granted_by_acl = _acl_matches(subject, resource.acl_grants)
        if not granted_by_acl:
            return _deny(ReasonCode.ACL_DENIED, layer=4)

    # --- Layer 5: classification and ownership ------------------------------
    if policy.classified:
        if resource.classification is None:
            return _deny(ReasonCode.CONTEXT_INCOMPLETE, layer=5)
        if resource.classification.requires_explicit_grant:
            # Feature 001 already wrote this rule down on the enum itself: at
            # RESTRICTED, "holding the right role is not by itself sufficient". Owning
            # the record counts as sufficient — the alternative locks a person out of
            # their own payroll record, which is not what the level means.
            owns_it = resource.owner_id is not None and resource.owner_id == subject.user_id
            explicitly_granted = granted_by_acl or (
                resource.acl_grants is not None
                and _acl_matches(subject, resource.acl_grants)
            )
            if not (owns_it or explicitly_granted):
                return _deny(ReasonCode.CLASSIFICATION_TOO_HIGH, layer=5)

    return Decision(
        allowed=True,
        reason=chosen.allow_reason,
        layer=None,
        scope=chosen.scope,
        audit_required=is_sensitive(resource, subject),
        tenant_absent=False,
    )


def _condition_holds(
    condition: Condition, subject: AccessContext, resource: ResourceDescriptor
) -> bool | None:
    """Evaluate one attribute condition.

    Three outcomes, not two. ``None`` means *the attribute needed to decide was
    absent* — which must deny, and must deny with its own reason. An implementation
    that returned ``False`` here would report "you are not in the reporting line" for
    what is actually a query that forgot a column, and the bug would look like policy.
    """
    if condition is Condition.NONE:
        return True
    if resource.owner_id is None:
        return None
    if condition is Condition.IS_SELF:
        return resource.owner_id == subject.user_id
    if condition is Condition.IS_DIRECT_REPORT:
        return subject.manages(resource.owner_id)
    # Deliberately no trailing `return`. A member added to `Condition` without a branch
    # above falls out of this function as `None`, which the caller reads as "could not
    # decide" and denies. Raising instead would turn a forgotten branch into a 500 for
    # every request touching that rule; an authorization engine should fail closed and
    # quiet rather than open or loud. An explicit `return None` here would be dead code
    # today — mypy's `warn_unreachable` says so — so the gap is caught at test time
    # instead: `tests/unit/test_authz_policy.py` asserts every member has a branch.


def _acl_matches(subject: AccessContext, grants: frozenset[AclGrant]) -> bool:
    """True when any grant names this caller, one of their roles, or their department.

    Role and department are matched by **id**, never by name: a name is a label someone
    can edit, and an ACL that followed a rename would silently change who has access.
    """
    for grant in grants:
        if grant.permission != "READ":
            continue
        if grant.principal_type == "USER" and grant.principal_id == subject.user_id:
            return True
        if grant.principal_type == "ROLE" and grant.principal_id in subject.role_ids:
            return True
        if (
            grant.principal_type == "DEPARTMENT"
            and grant.principal_id == subject.department_id
        ):
            return True
    return False


def _deny(reason: ReasonCode, *, layer: int, tenant_absent: bool = False) -> Decision:
    """A refusal.

    ``audit_required`` is unconditionally true: FR-017 gives denials no exemption and
    no coalescing, because they are the security signal. Sensitivity narrows which
    *allows* are recorded and never which denials are.
    """
    return Decision(
        allowed=False,
        reason=reason,
        layer=layer,
        scope=Scope.NONE,
        audit_required=True,
        tenant_absent=tenant_absent,
    )
