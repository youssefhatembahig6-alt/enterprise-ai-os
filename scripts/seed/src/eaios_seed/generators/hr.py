"""HR generator: profiles, leave, attendance, training, reviews (spec FR-026).

Leave entitlement is read from the leave policy rather than generated, which is
what makes the FR-035 coherence check pass by construction instead of by luck.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from eaios_core.clock import attendance_window, history_window, reference_datetime
from eaios_core.constants import COMPANY_CURRENCIES
from eaios_core.ids import derive

from ..calendars import working_days_between
from ..config import SeedConfig
from ..dataset import Dataset
from ..rng import Rng
from .organization import SALARY_BANDS, OrgContext, UserRef
from .policies import entitlement_days

__all__ = ["generate_hr"]

_LEAVE_TYPES = ("ANNUAL", "SICK")
_COURSES = [
    "Secure Coding Fundamentals", "Data Privacy Essentials", "Effective Communication",
    "Advanced SQL", "Incident Response Basics", "Leadership Foundations",
    "Customer Empathy Workshop", "Financial Controls Overview",
]
_PROVIDERS = ["Internal Academy", "Coursera", "Pluralsight", "Local Training Partner"]


def generate_hr(dataset: Dataset, config: SeedConfig, ctx: OrgContext) -> None:
    for slug, users in ctx.users.items():
        _generate_for_company(dataset, config, slug, users)


def _generate_for_company(
    dataset: Dataset, config: SeedConfig, slug: str, users: list[UserRef]
) -> None:
    rng = Rng(config.seed, "hr", slug)
    now = reference_datetime()
    company_id = users[0].company_id
    currency = COMPANY_CURRENCIES[slug]
    volumes = config.for_tenant(slug)
    history_start, history_end = history_window()
    att_start, att_end = attendance_window()
    year = config.reference_date.year

    def row(**kwargs: Any) -> dict[str, Any]:
        return {"company_id": company_id, "created_at": now, "updated_at": now, **kwargs}

    for user in users:
        low, high = SALARY_BANDS[user.salary_band]
        salary = Decimal(rng.randint(low, high)).quantize(Decimal("0.01"))
        dataset.add(
            "employee_profiles",
            row(
                id=derive("employee_profile", slug, user.natural_key, seed=config.seed),
                user_id=user.id, job_title=user.job_title, salary_band=user.salary_band,
                salary_amount=salary, currency=currency, hire_date=user.hire_date,
                employment_type=user.employment_type,
            ),
        )

        # -- leave balances, derived from the policy (FR-035) -------------
        for leave_type in _LEAVE_TYPES:
            entitlement = (
                entitlement_days(user.country, user.employment_type)
                if leave_type == "ANNUAL"
                else max(0, int(10 if user.country == "EG" else 12))
            )
            used = rng.randint(0, entitlement) if entitlement else 0
            dataset.add(
                "leave_balances",
                row(
                    id=derive("leave_balance", slug, f"{user.natural_key}:{leave_type}:{year}",
                              seed=config.seed),
                    user_id=user.id, leave_type=leave_type, year=year,
                    entitlement_days=entitlement, used_days=used,
                    remaining_days=entitlement - used,
                ),
            )

    # -- leave requests ---------------------------------------------------
    requestable = [u for u in users if u.manager_id is not None]
    for index in range(volumes.leave_requests):
        user = requestable[index % len(requestable)]
        earliest = max(history_start, user.hire_date)  # never predates hire (FR-037)
        span_days = (history_end - earliest).days
        if span_days <= 5:
            continue
        start = earliest + dt.timedelta(days=rng.randint(0, span_days - 5))
        length = rng.randint(1, 5)
        dataset.add(
            "leave_requests",
            row(
                id=derive("leave_request", slug, f"{user.natural_key}:{index:05d}", seed=config.seed),
                user_id=user.id, approver_id=user.manager_id,
                leave_type=rng.choice(list(_LEAVE_TYPES)),
                start_date=start, end_date=start + dt.timedelta(days=length - 1),
                days_count=length,
                status=rng.weighted({"APPROVED": 0.72, "PENDING": 0.12,
                                     "REJECTED": 0.08, "CANCELLED": 0.08}),
                submitted_at=now,
            ),
        )

    # -- attendance, capped at 6 months (FR-020a) --------------------------
    for user in users:
        if user.employment_type == "CONTRACT":
            continue
        start = max(att_start, user.hire_date)
        for day in working_days_between(start, att_end, user.country):
            status = rng.weighted({"PRESENT": 0.70, "REMOTE": 0.24, "LEAVE": 0.06})
            hours = Decimal("0.00") if status == "LEAVE" else Decimal(
                str(round(rng.uniform(6.5, 9.0), 2))
            )
            dataset.add(
                "attendance_records",
                row(
                    id=derive("attendance", slug, f"{user.natural_key}:{day.isoformat()}",
                              seed=config.seed),
                    user_id=user.id, work_date=day, status=status, hours_worked=hours,
                ),
            )

    # -- training ---------------------------------------------------------
    for index in range(volumes.training_records):
        user = users[index % len(users)]
        # Clamped at BOTH ends. A long-tenured employee's hire date plus 30 days can
        # land before the history window opens, which the upper clamp alone missed
        # (FR-037).
        completed = user.hire_date + dt.timedelta(days=rng.randint(30, 900))
        completed = min(max(completed, history_start), history_end)
        dataset.add(
            "training_records",
            row(
                id=derive("training", slug, f"{user.natural_key}:{index:05d}", seed=config.seed),
                user_id=user.id, course_name=rng.choice(_COURSES),
                provider=rng.choice(_PROVIDERS), completed_on=completed,
                outcome=rng.weighted({"PASSED": 0.88, "ATTENDED": 0.12}),
                score=rng.randint(62, 100),
            ),
        )

    # -- performance reviews: 4 semi-annual cycles -------------------------
    cycles = [
        (dt.date(2024, 7, 1), dt.date(2024, 12, 31)),
        (dt.date(2025, 1, 1), dt.date(2025, 6, 30)),
        (dt.date(2025, 7, 1), dt.date(2025, 12, 31)),
        (dt.date(2026, 1, 1), dt.date(2026, 6, 30)),
    ]
    for user in users:
        if user.manager_id is None:
            continue  # the CEO reviews nobody upward
        for period_start, period_end in cycles:
            if user.hire_date > period_start:
                continue
            dataset.add(
                "performance_reviews",
                row(
                    id=derive("performance_review", slug,
                              f"{user.natural_key}:{period_start.isoformat()}", seed=config.seed),
                    user_id=user.id, reviewer_id=user.manager_id,
                    period_start=period_start, period_end=period_end,
                    rating=int(rng.weighted({"3": 0.34, "4": 0.40, "5": 0.14, "2": 0.10})),
                    summary=rng.sentence(14),
                ),
            )
