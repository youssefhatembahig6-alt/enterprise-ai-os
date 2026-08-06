"""Layer ordering and short-circuiting (spec 003 FR-013).

FR-013 fixes the order — tenant, RBAC, ABAC, resource ACL, classification — and says
an earlier layer's refusal short-circuits the rest. Both halves need proving, and only
one of them is obvious.

That a *single* failing condition denies is barely a test: almost any implementation
does that. The claim FR-013 actually makes is about a request that fails **several**
layers at once — that the answer names the earliest one. An engine that evaluated in
the wrong order, or that gathered every failure and reported the last, would pass a
one-failure-at-a-time suite completely.

Order matters for a reason beyond tidiness. Layer 1 decides *not found* while layers 2
through 5 decide *forbidden* (FR-021, FR-030), so an engine that consulted RBAC first
would answer 403 for a resource in another tenant — confirming its existence. The
ordering is the anti-enumeration property.
"""

from __future__ import annotations

import pytest

from eaios_core.authz import (
    Action,
    Condition,
    KindPolicy,
    ReasonCode,
    ResourceKind,
    Rule,
    Scope,
    evaluate,
    evaluate_with,
)
from eaios_core.classification import Classification

from .authz_helpers import ALICE, BOB, CAROL, DELTA, SALES, context, descriptor

pytestmark = pytest.mark.unit


class TestTheAllowingCaseActuallyAllows:
    """The control. Without it every denial assertion below is satisfied by an engine
    that denies unconditionally — the most vacuous pass available to a policy engine."""

    def test_own_profile_is_allowed(self) -> None:
        decision = evaluate(context(), Action.READ, descriptor())
        assert decision.allowed, f"the baseline subject/resource pair must allow: {decision}"
        assert decision.reason is ReasonCode.ALLOWED_SELF
        assert decision.scope is Scope.SELF
        assert decision.tenant_absent is False

    def test_a_direct_reports_profile_is_allowed(self) -> None:
        decision = evaluate(
            context(), Action.READ, descriptor(owner_id=BOB, resource_id=str(BOB))
        )
        assert decision.allowed, f"a manager must reach a direct report: {decision}"
        assert decision.reason is ReasonCode.ALLOWED_TEAM
        assert decision.scope is Scope.TEAM


class TestEachLayerFiresOnItsOwn:
    """One layer failing at a time. Necessary, and on its own not sufficient — see the
    multi-failure class below."""

    def test_layer_one_wrong_tenant(self) -> None:
        decision = evaluate(context(), Action.READ, descriptor(company_id=DELTA))
        assert not decision.allowed
        assert decision.layer == 1
        assert decision.reason is ReasonCode.TENANT_MISMATCH
        assert decision.tenant_absent is True, (
            "a cross-tenant refusal must be reported as absence, not denial (FR-021, FR-030)"
        )

    def test_layer_two_missing_permission(self) -> None:
        subject = context(permission_codes=frozenset({"documents:read"}))
        decision = evaluate(subject, Action.READ, descriptor())
        assert not decision.allowed
        assert decision.layer == 2
        assert decision.reason is ReasonCode.PERMISSION_MISSING
        assert decision.tenant_absent is False

    def test_layer_three_outside_the_reporting_line(self) -> None:
        decision = evaluate(
            context(), Action.READ, descriptor(owner_id=CAROL, resource_id=str(CAROL))
        )
        assert not decision.allowed
        assert decision.layer == 3
        assert decision.reason is ReasonCode.NOT_IN_REPORTING_LINE

    def test_layer_four_no_resource_grant(self) -> None:
        decision = evaluate_with(
            context(),
            Action.READ,
            descriptor(owner_id=CAROL, department_id=SALES, acl_grants=frozenset()),
            _ACL_GATED,
        )
        assert not decision.allowed
        assert decision.layer == 4
        assert decision.reason is ReasonCode.ACL_DENIED

    def test_layer_five_classification_needs_an_explicit_grant(self) -> None:
        decision = evaluate_with(
            context(),
            Action.READ,
            descriptor(
                owner_id=CAROL,
                department_id=SALES,
                classification=Classification.RESTRICTED,
                acl_grants=None,
            ),
            _CLASSIFIED,
        )
        assert not decision.allowed
        assert decision.layer == 5
        assert decision.reason is ReasonCode.CLASSIFICATION_TOO_HIGH


class TestTheEarliestLayerWins:
    """The claim FR-013 actually makes.

    Each case fails at least two layers. An engine that evaluated in a different order,
    or that collected every failure and reported the last, passes every test above and
    fails every test here.
    """

    def test_wrong_tenant_beats_missing_permission(self) -> None:
        subject = context(permission_codes=frozenset())
        decision = evaluate(subject, Action.READ, descriptor(company_id=DELTA))
        assert decision.layer == 1, (
            "tenant is layer 1 and must decide before RBAC — otherwise a resource in"
            " another tenant answers 403 and confirms it exists"
        )
        assert decision.reason is ReasonCode.TENANT_MISMATCH
        assert decision.tenant_absent is True

    def test_wrong_tenant_beats_a_failed_relationship(self) -> None:
        decision = evaluate(
            context(), Action.READ, descriptor(company_id=DELTA, owner_id=CAROL)
        )
        assert decision.layer == 1
        assert decision.tenant_absent is True

    def test_missing_permission_beats_a_failed_relationship(self) -> None:
        subject = context(permission_codes=frozenset({"documents:read"}))
        decision = evaluate(subject, Action.READ, descriptor(owner_id=CAROL))
        assert decision.layer == 2, "RBAC is layer 2 and must decide before ABAC"
        assert decision.reason is ReasonCode.PERMISSION_MISSING

    def test_a_failed_relationship_beats_a_missing_grant(self) -> None:
        decision = evaluate_with(
            context(),
            Action.READ,
            descriptor(owner_id=CAROL, acl_grants=frozenset()),
            _ACL_GATED_WITH_RELATIONSHIP,
        )
        assert decision.layer == 3, "ABAC is layer 3 and must decide before the ACL"
        assert decision.reason is ReasonCode.NOT_IN_REPORTING_LINE

    def test_a_missing_grant_beats_a_classification_refusal(self) -> None:
        decision = evaluate_with(
            context(),
            Action.READ,
            descriptor(
                owner_id=CAROL,
                acl_grants=frozenset(),
                classification=Classification.RESTRICTED,
            ),
            _ACL_GATED_AND_CLASSIFIED,
        )
        assert decision.layer == 4, "the resource ACL is layer 4 and precedes classification"
        assert decision.reason is ReasonCode.ACL_DENIED

    def test_every_layer_failing_at_once_reports_the_first(self) -> None:
        """All five wrong. Exactly one answer is correct."""
        decision = evaluate_with(
            context(permission_codes=frozenset()),
            Action.READ,
            descriptor(
                company_id=DELTA,
                owner_id=CAROL,
                department_id=SALES,
                acl_grants=frozenset(),
                classification=Classification.RESTRICTED,
            ),
            _ACL_GATED_AND_CLASSIFIED,
        )
        assert decision.layer == 1
        assert decision.reason is ReasonCode.TENANT_MISMATCH


class TestShortCircuiting:
    def test_a_denied_decision_names_exactly_one_layer(self) -> None:
        """`layer` is a single number, not a list. Stated as a test because a future
        change to "report every failure" would break the not-found/forbidden split
        without breaking anything that reads `reason`."""
        decision = evaluate(context(permission_codes=frozenset()), Action.READ, descriptor())
        assert isinstance(decision.layer, int)

    def test_an_allowed_decision_reports_no_failing_layer(self) -> None:
        decision = evaluate(context(), Action.READ, descriptor())
        assert decision.allowed
        assert decision.layer is None


class TestUnknownPairingsDeny:
    def test_an_action_with_no_rule_is_refused(self) -> None:
        """Default deny for a pairing nobody wrote a rule for. The alternative — an
        unknown pairing falling through to allow — is how a new endpoint ships
        unprotected."""
        decision = evaluate(
            context(), Action.READ, descriptor(kind=ResourceKind.AUDIT_LOG)
        )
        assert not decision.allowed, "no seeded permission here grants audit:read"
        assert decision.reason is ReasonCode.PERMISSION_MISSING


# ---------------------------------------------------------------------------
# Policies for the two layers no *current* resource kind exercises.
#
# Feature 003 has HR profiles, compensation, and the caller's own session — none of
# which carries a resource ACL or a classification, because none of them is a
# document. Layers 4 and 5 are still implemented, still ordered, and still have to be
# proven, so these policies drive them directly through `evaluate_with`.
#
# Constructing a policy is a deliberate act, which is why the seam is acceptable:
# `evaluate` remains closed over the real kind table, and a production caller cannot
# reach these by accident. Feature 004's document kind will add a table entry and stop
# needing them.
# ---------------------------------------------------------------------------

_READ_TEAM = Rule(
    permission="hr:read_team",
    condition=Condition.NONE,
    scope=Scope.TEAM,
    allow_reason=ReasonCode.ALLOWED_TEAM,
)
_READ_TEAM_OF_REPORT = Rule(
    permission="hr:read_team",
    condition=Condition.IS_DIRECT_REPORT,
    scope=Scope.TEAM,
    allow_reason=ReasonCode.ALLOWED_TEAM,
)

_ACL_GATED = KindPolicy(rules=(_READ_TEAM,), acl_gated=True)
_ACL_GATED_WITH_RELATIONSHIP = KindPolicy(rules=(_READ_TEAM_OF_REPORT,), acl_gated=True)
_CLASSIFIED = KindPolicy(rules=(_READ_TEAM,), classified=True)
_ACL_GATED_AND_CLASSIFIED = KindPolicy(rules=(_READ_TEAM,), acl_gated=True, classified=True)


class TestTheLayerFourAndFiveHarnessIsReal:
    """These two layers are only reachable here, so the harness itself needs a control.
    Without one, `_ACL_GATED` could be denying for some unrelated reason and every
    layer-4 assertion above would still pass."""

    def test_a_matching_grant_allows(self) -> None:
        from eaios_core.authz import AclGrant

        grant = AclGrant(principal_type="USER", principal_id=ALICE, permission="READ")
        decision = evaluate_with(
            context(),
            Action.READ,
            descriptor(owner_id=CAROL, acl_grants=frozenset({grant})),
            _ACL_GATED,
        )
        assert decision.allowed, f"an explicit USER grant must satisfy layer 4: {decision}"

    def test_an_ordinary_classification_allows(self) -> None:
        decision = evaluate_with(
            context(),
            Action.READ,
            descriptor(owner_id=CAROL, classification=Classification.INTERNAL),
            _CLASSIFIED,
        )
        assert decision.allowed, (
            f"INTERNAL needs no explicit grant — only RESTRICTED does: {decision}"
        )

    def test_the_owner_reaches_their_own_restricted_resource(self) -> None:
        decision = evaluate_with(
            context(),
            Action.READ,
            descriptor(owner_id=ALICE, classification=Classification.RESTRICTED),
            _CLASSIFIED,
        )
        assert decision.allowed, (
            "RESTRICTED requires an explicit grant *or* ownership; the owner is not"
            f" locked out of their own record: {decision}"
        )
