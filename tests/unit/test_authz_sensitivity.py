"""What gets audited, and what deliberately does not (spec 003 FR-017, FR-017a/b).

Two rules, and the second is the one that needs care:

* **Every denial** writes an entry. No exemption, no coalescing — denials are the
  security signal.
* **Allows** are audited only for the four enumerated sensitive cases. A user reading
  their own non-compensation profile writes nothing.

The second rule exists because feature 002 learned the cost of the alternative the
expensive way: auditing every read makes one page view write dozens of rows and buries
the entries an auditor actually needs. Principle X asks "who saw this?" — a question
about sensitive material, not about someone loading their own name.

That makes an *absence* load-bearing, which is a dangerous thing to assert. A broken
audit writer and a correctly-quiet one look identical from the outside. So every test
here that asserts nothing is audited sits beside one that asserts something is.
"""

from __future__ import annotations

import pytest

from eaios_core.authz import Action, ReasonCode, ResourceKind, evaluate, is_sensitive
from eaios_core.classification import Classification

from .authz_helpers import ALICE, BOB, CAROL, context, descriptor

pytestmark = pytest.mark.unit


class TestTheEnumeratedSensitiveSet:
    """FR-017a lists four cases. Each gets a test that names it."""

    def test_someone_elses_hr_record_is_sensitive(self) -> None:
        assert is_sensitive(descriptor(owner_id=BOB), context()) is True

    def test_your_own_hr_record_is_not(self) -> None:
        assert is_sensitive(descriptor(owner_id=ALICE), context()) is False

    def test_compensation_is_sensitive_even_when_it_is_your_own(self) -> None:
        """Clause 2 says "of any kind, including the requester's own". Stated
        separately because it is the one clause that does not follow from ownership,
        and the natural implementation — "sensitive when it belongs to someone else" —
        gets it wrong."""
        own = descriptor(kind=ResourceKind.HR_COMPENSATION, owner_id=ALICE)
        assert is_sensitive(own, context()) is True

    def test_compensation_belonging_to_another_is_sensitive(self) -> None:
        other = descriptor(kind=ResourceKind.HR_COMPENSATION, owner_id=BOB)
        assert is_sensitive(other, context()) is True

    def test_a_classification_above_the_ordinary_level_is_sensitive(self) -> None:
        above = descriptor(owner_id=ALICE, classification=Classification.CONFIDENTIAL)
        assert is_sensitive(above, context()) is True

    def test_an_ordinary_classification_is_not(self) -> None:
        ordinary = descriptor(owner_id=ALICE, classification=Classification.INTERNAL)
        assert is_sensitive(ordinary, context()) is False

    def test_reading_the_audit_log_is_sensitive(self) -> None:
        assert is_sensitive(descriptor(kind=ResourceKind.AUDIT_LOG), context()) is True

    def test_the_callers_own_access_context_is_not(self) -> None:
        own = descriptor(kind=ResourceKind.ACCESS_CONTEXT, owner_id=ALICE)
        assert is_sensitive(own, context()) is False


class TestTheSetIsDefinedInExactlyOnePlace:
    def test_the_definition_is_importable_and_covers_every_kind(self) -> None:
        """FR-017b: adding a resource type must be a change to the definition, not to
        a call site. A kind the function cannot classify would force the decision
        somewhere else."""
        subject = context()
        for kind in ResourceKind:
            verdict = is_sensitive(descriptor(kind=kind, owner_id=ALICE), subject)
            assert isinstance(verdict, bool), f"{kind} has no sensitivity verdict"

    def test_at_least_one_kind_is_sensitive_and_one_is_not(self) -> None:
        """A definition that answered True for everything, or False for everything,
        would satisfy every per-case test above that happened to agree with it."""
        subject = context()
        verdicts = {
            kind: is_sensitive(descriptor(kind=kind, owner_id=ALICE), subject)
            for kind in ResourceKind
        }
        assert any(verdicts.values()), f"nothing is sensitive: {verdicts}"
        assert not all(verdicts.values()), f"everything is sensitive: {verdicts}"


class TestDecisionsCarryTheAuditFlag:
    """The engine computes `audit_required` so no router has to. These assert the two
    rules through the decision itself, which is what the enforcement layer reads."""

    def test_an_allow_for_your_own_profile_is_not_audited(self) -> None:
        decision = evaluate(context(), Action.READ, descriptor())
        assert decision.allowed
        assert decision.audit_required is False, (
            "loading your own name must not write a row (FR-017a)"
        )

    def test_an_allow_for_a_direct_report_is_audited(self) -> None:
        """Sits immediately beside the test above on purpose: together they show the
        flag distinguishes cases rather than being stuck at one value."""
        decision = evaluate(
            context(), Action.READ, descriptor(owner_id=BOB, resource_id=str(BOB))
        )
        assert decision.allowed
        assert decision.audit_required is True

    def test_every_denial_is_audited(self) -> None:
        for descriptor_kwargs in (
            {"owner_id": CAROL},  # layer 3
            {"company_id": None},  # CONTEXT_INCOMPLETE
        ):
            decision = evaluate(context(), Action.READ, descriptor(**descriptor_kwargs))
            assert not decision.allowed
            assert decision.audit_required is True, (
                f"denials have no exemption (FR-017): {decision}"
            )

    def test_a_cross_tenant_refusal_is_audited(self) -> None:
        """Reported to the caller as not-found, recorded internally as what it was.
        FR-030: the audit entry records the true reason either way."""
        from .authz_helpers import DELTA

        decision = evaluate(context(), Action.READ, descriptor(company_id=DELTA))
        assert not decision.allowed
        assert decision.tenant_absent is True
        assert decision.audit_required is True
        assert decision.reason is ReasonCode.TENANT_MISMATCH

    def test_denials_are_audited_for_every_kind(self) -> None:
        """No kind may become quietly exempt. Parametrised over the enum so a kind
        added later is covered without anyone remembering to add a case."""
        subject = context(permission_codes=frozenset())
        for kind in ResourceKind:
            decision = evaluate(subject, Action.READ, descriptor(kind=kind, owner_id=CAROL))
            if not decision.allowed:
                assert decision.audit_required is True, f"{kind} denial not audited"
