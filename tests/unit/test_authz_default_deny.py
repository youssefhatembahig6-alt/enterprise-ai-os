"""Default deny when required context is absent (spec 003 FR-013).

"Fails closed" is the easiest security property to claim and the easiest to leave
untested, because the happy path never exercises it. The shape of the failure it
guards against is specific: a descriptor built by a query that returned fewer columns
than expected, or a join that missed, leaving an attribute ``None`` — and an engine
that reads ``None`` as "no constraint" rather than "unknown" then allows.

Every case here removes exactly one attribute from a descriptor that otherwise
allows, so a failure names the attribute that was not required.

The anti-vacuity guard is the first test: it asserts the required set is **non-empty**
before anything is parametrised over it. A version of this file that discovered zero
required attributes would report a full pass while checking nothing at all.
"""

from __future__ import annotations

import dataclasses

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

from .authz_helpers import BOB, context, descriptor

pytestmark = pytest.mark.unit

#: Attributes an HR_PROFILE decision genuinely needs. Written out rather than derived
#: from the dataclass: deriving it from the fields would make the test agree with the
#: implementation by construction, which is the failure mode this whole file exists to
#: avoid. `classification` and `acl_grants` are absent because HR profiles are not
#: classified and carry no ACL — a fact the second class below pins down.
REQUIRED_FOR_HR_PROFILE = ("company_id", "owner_id")


class TestTheParametrisationHasSubjects:
    def test_the_required_set_is_not_empty(self) -> None:
        assert REQUIRED_FOR_HR_PROFILE, (
            "a default-deny suite parametrised over an empty set passes while"
            " checking nothing"
        )

    def test_the_baseline_descriptor_allows(self) -> None:
        """Without this, every "removing X denies" assertion below is satisfied by an
        engine that denies unconditionally."""
        decision = evaluate(context(), Action.READ, descriptor())
        assert decision.allowed, f"the baseline must allow or nothing below means anything: {decision}"

    def test_every_named_attribute_exists_on_the_descriptor(self) -> None:
        """A typo in `REQUIRED_FOR_HR_PROFILE` would otherwise silently skip a field."""
        fields = {f.name for f in dataclasses.fields(descriptor())}
        missing = [name for name in REQUIRED_FOR_HR_PROFILE if name not in fields]
        assert missing == [], f"not descriptor fields: {missing}"


class TestMissingAttributesDeny:
    @pytest.mark.parametrize("attribute", REQUIRED_FOR_HR_PROFILE)
    def test_removing_one_required_attribute_denies(self, attribute: str) -> None:
        decision = evaluate(context(), Action.READ, descriptor(**{attribute: None}))
        assert not decision.allowed, (
            f"{attribute} was absent and the decision still allowed — an unknown"
            " attribute must never read as an absent constraint"
        )
        assert decision.reason is ReasonCode.CONTEXT_INCOMPLETE, (
            f"{attribute} absent should report CONTEXT_INCOMPLETE, got {decision.reason}"
        )

    def test_an_absent_tenant_is_not_reported_as_absence(self) -> None:
        """A missing `company_id` is a defect in the caller, not a resource in another
        tenant. Reporting `tenant_absent` would turn a bug into a 404 and hide it."""
        decision = evaluate(context(), Action.READ, descriptor(company_id=None))
        assert not decision.allowed
        assert decision.tenant_absent is False
        assert decision.reason is ReasonCode.CONTEXT_INCOMPLETE


class TestGatedLayersRequireTheirAttributes:
    """Layers 4 and 5 have their own required attributes, and "not loaded" must not
    read as "nothing to check"."""

    _ACL_GATED = KindPolicy(
        rules=(
            Rule(
                permission="hr:read_team",
                condition=Condition.NONE,
                scope=Scope.TEAM,
                allow_reason=ReasonCode.ALLOWED_TEAM,
            ),
        ),
        acl_gated=True,
    )
    _CLASSIFIED = KindPolicy(rules=_ACL_GATED.rules, classified=True)

    def test_an_acl_gated_kind_denies_when_grants_were_never_loaded(self) -> None:
        decision = evaluate_with(
            context(), Action.READ, descriptor(acl_grants=None), self._ACL_GATED
        )
        assert not decision.allowed
        assert decision.reason is ReasonCode.CONTEXT_INCOMPLETE
        assert decision.layer == 4

    def test_an_empty_grant_set_is_a_denial_not_an_omission(self) -> None:
        """`None` means "not loaded" and `frozenset()` means "loaded, nothing granted".
        Both deny, and they deny for different stated reasons — collapsing them would
        make a forgotten query indistinguishable from a correct refusal."""
        decision = evaluate_with(
            context(), Action.READ, descriptor(acl_grants=frozenset()), self._ACL_GATED
        )
        assert not decision.allowed
        assert decision.reason is ReasonCode.ACL_DENIED

    def test_a_classified_kind_denies_when_the_level_was_never_loaded(self) -> None:
        decision = evaluate_with(
            context(), Action.READ, descriptor(classification=None), self._CLASSIFIED
        )
        assert not decision.allowed
        assert decision.reason is ReasonCode.CONTEXT_INCOMPLETE
        assert decision.layer == 5


class TestUnknownPairingsDeny:
    def test_a_kind_with_no_rules_denies(self) -> None:
        """The pairing a future endpoint forgets to add. Falling through to allow is
        how an unprotected route ships."""
        decision = evaluate_with(context(), Action.READ, descriptor(), KindPolicy(rules=()))
        assert not decision.allowed
        assert decision.reason is ReasonCode.PERMISSION_MISSING

    def test_every_declared_kind_has_a_rule(self) -> None:
        """Not a default-deny case — the opposite. Every kind the enum declares must be
        reachable, or an endpoint is silently unserviceable and the denial looks like
        an authorization decision rather than a missing table entry."""
        from eaios_core.authz.rules import POLICIES

        missing = [kind for kind in ResourceKind if (kind, Action.READ) not in POLICIES]
        assert missing == [], f"declared kinds with no READ rule: {missing}"


class TestASubjectMissingPermissionsDenies:
    def test_no_permissions_at_all(self) -> None:
        """The spec's edge case: a user with no roles must still sign in and reach
        their own record. `hr:read_self` comes from the Employee role, so a user
        holding literally nothing is refused here — and that refusal is a 403 with a
        designed page, not a crash."""
        decision = evaluate(
            context(permission_codes=frozenset()), Action.READ, descriptor()
        )
        assert not decision.allowed
        assert decision.reason is ReasonCode.PERMISSION_MISSING
        assert decision.layer == 2

    def test_a_report_is_unreachable_without_the_team_permission(self) -> None:
        """An employee holding only `hr:read_self` cannot read a colleague.

        Refused at **layer 3**, not layer 2, and the distinction is the point. The
        caller does hold a permission that appears in this resource kind's rules —
        `hr:read_self` — so RBAC has nothing to refuse. What fails is the condition
        attached to that code: the record is not theirs.

        Reporting `PERMISSION_MISSING` here would tell an auditor the caller holds no
        HR permission at all, which is false and points the investigation at the wrong
        thing. `ATTRIBUTE_MISMATCH` says what happened: self-scope access, someone
        else's record.
        """
        subject = context(permission_codes=frozenset({"hr:read_self"}))
        decision = evaluate(
            subject, Action.READ, descriptor(owner_id=BOB, resource_id=str(BOB))
        )
        assert not decision.allowed
        assert decision.layer == 3
        assert decision.reason is ReasonCode.ATTRIBUTE_MISMATCH
