"""Policy documents and their machine-readable stated values (spec FR-029, FR-035).

`stated_values` is the point of this module. It holds the numbers the prose asserts
in a form a test can compare against, so the coherence check reads JSON instead of
parsing English. HR generation derives leave entitlements *from* these values rather
than inventing its own — which is what keeps "21 days" in the policy and "21 days"
in the records from ever drifting apart.
"""

from __future__ import annotations

from typing import Any

__all__ = ["POLICY_TYPES", "stated_values_for"]

POLICY_TYPES: tuple[str, ...] = (
    "HANDBOOK",
    "LEAVE",
    "REMOTE_WORK",
    "EXPENSE",
    "SECURITY",
    "CODE_OF_CONDUCT",
    "TRAVEL",
    "BENEFITS",
)

#: Per-country annual leave. Deliberately different between EG and AE so the
#: country-scoped ABAC rule in the next feature has something real to discriminate.
_ANNUAL_LEAVE = {"EG": 21, "AE": 22}
_SICK_LEAVE = {"EG": 10, "AE": 12}

#: Part-time entitlement is pro-rated; contractors accrue none.
_EMPLOYMENT_FACTOR = {"FULL_TIME": 1.0, "PART_TIME": 0.5, "CONTRACT": 0.0}


def stated_values_for(policy_type: str, company_slug: str) -> dict[str, Any]:
    if policy_type == "LEAVE":
        return {
            "annual_leave_days": dict(_ANNUAL_LEAVE),
            "sick_leave_days": dict(_SICK_LEAVE),
            "employment_factor": dict(_EMPLOYMENT_FACTOR),
            "probation_months": 3,
            "carry_over_days": 5,
        }
    if policy_type == "EXPENSE":
        return {"approval_threshold": 500, "currency": "USD", "receipt_required_above": 25}
    if policy_type == "REMOTE_WORK":
        return {"max_remote_days_per_week": 3, "core_hours": "10:00-16:00"}
    if policy_type == "TRAVEL":
        return {"advance_booking_days": 14, "economy_only_below_hours": 6}
    if policy_type == "BENEFITS":
        return {"health_cover_percent": 80, "training_budget": 1500, "currency": "USD"}
    if policy_type == "SECURITY":
        return {"password_min_length": 14, "mfa_required": True, "session_timeout_minutes": 30}
    return {}


def entitlement_days(country: str, employment_type: str) -> int:
    """The single source of truth for leave entitlement.

    Both the policy document and the leave balances call this, so they cannot
    disagree (FR-035).
    """
    base = _ANNUAL_LEAVE.get(country, _ANNUAL_LEAVE["EG"])
    factor = _EMPLOYMENT_FACTOR.get(employment_type, 1.0)
    return int(base * factor)
