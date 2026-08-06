"""The permission-code table (spec 003 FR-014, contracts/policy-engine.md §3).

Data, not code. One table, reviewable as a unit, so "who may read an HR profile" is a
question with a written answer rather than a search through routers.

Every code here comes from the seeded catalog
(`scripts/seed/src/eaios_seed/generators/organization.py:39`). The engine invents
none — a code that exists only in this file would be a permission nobody can ever be
granted, and the denial would look like policy rather than a typo.
"""

from __future__ import annotations

from .decision import Action, Condition, KindPolicy, ReasonCode, ResourceKind, Rule, Scope

__all__ = ["POLICIES"]

#: `(kind, action)` → how to decide it.
#:
#: The three `HR_PROFILE` rules are **alternatives evaluated in order**: the first
#: whose code the caller holds and whose condition passes decides. Holding none of the
#: codes denies with `PERMISSION_MISSING`; holding one but failing its condition denies
#: with `NOT_IN_REPORTING_LINE`. Two separate reason codes because they answer
#: different questions for whoever reads the audit trail — "this person should not have
#: this role" versus "this person asked about someone outside their team".
POLICIES: dict[tuple[ResourceKind, Action], KindPolicy] = {
    (ResourceKind.HR_PROFILE, Action.READ): KindPolicy(
        rules=(
            Rule("hr:read_self", Condition.IS_SELF, Scope.SELF, ReasonCode.ALLOWED_SELF),
            Rule(
                "hr:read_team",
                Condition.IS_DIRECT_REPORT,
                Scope.TEAM,
                ReasonCode.ALLOWED_TEAM,
            ),
            Rule("hr:read_all", Condition.NONE, Scope.COMPANY, ReasonCode.ALLOWED_ALL),
        )
    ),
    # FR-025, the blueprint's flagship denial: `hr:read_all`, **not** `hr:read_team`.
    # A manager reading their own direct report is refused. That is a rule stated here,
    # not a field omitted from a response model — which is what lets the refusal happen
    # before the query rather than after it.
    (ResourceKind.HR_COMPENSATION, Action.READ): KindPolicy(
        rules=(Rule("hr:read_all", Condition.NONE, Scope.COMPANY, ReasonCode.ALLOWED_ALL),)
    ),
    # The caller's own team roster. `IS_SELF` because the resource *is* the caller —
    # you list your reports, never someone else's.
    (ResourceKind.DIRECT_REPORTS, Action.READ): KindPolicy(
        rules=(Rule("hr:read_team", Condition.IS_SELF, Scope.TEAM, ReasonCode.ALLOWED_TEAM),)
    ),
    # No permission code: the resource is the caller themselves, so ownership is the
    # entire rule. A code would be one every user necessarily holds, which is a code
    # that decides nothing.
    (ResourceKind.ACCESS_CONTEXT, Action.READ): KindPolicy(
        rules=(Rule(None, Condition.IS_SELF, Scope.SELF, ReasonCode.ALLOWED_SELF),)
    ),
    (ResourceKind.SESSION, Action.READ): KindPolicy(
        rules=(Rule(None, Condition.IS_SELF, Scope.SELF, ReasonCode.ALLOWED_SELF),)
    ),
    (ResourceKind.AUDIT_LOG, Action.READ): KindPolicy(
        rules=(Rule("audit:read", Condition.NONE, Scope.COMPANY, ReasonCode.ALLOWED_ALL),)
    ),
}
