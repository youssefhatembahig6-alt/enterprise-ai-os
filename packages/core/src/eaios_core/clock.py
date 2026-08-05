"""The pinned reference clock.

This module is the *only* sanctioned source of time in generation code. Everything
else is forbidden from reading the wall clock, and `tests/unit/test_no_wallclock.py`
enforces that statically (spec FR-012, research R2).

Why it matters: if generation reads `datetime.now()`, the dataset becomes a function
of when it was seeded. Two developers seeding on different days would get different
data, which contradicts SC-002. The symptom — a fingerprint that differs by machine
and by day — is unpleasant to diagnose after the fact.
"""

from __future__ import annotations

import datetime as dt

from .constants import ATTENDANCE_MONTHS, HISTORY_MONTHS, REFERENCE_DATE

__all__ = [
    "attendance_window",
    "days_before",
    "history_window",
    "last_full_month",
    "month_starts",
    "reference_date",
    "reference_datetime",
]


def reference_date() -> dt.date:
    """The pinned generation date. Never the wall clock."""
    return REFERENCE_DATE


def reference_datetime(hour: int = 0, minute: int = 0, second: int = 0) -> dt.datetime:
    """A timezone-aware UTC instant on the reference date."""
    return dt.datetime(
        REFERENCE_DATE.year,
        REFERENCE_DATE.month,
        REFERENCE_DATE.day,
        hour,
        minute,
        second,
        tzinfo=dt.UTC,
    )


def _shift_months(anchor: dt.date, months: int) -> dt.date:
    """Move to the first day of the month `months` before `anchor`."""
    total = anchor.year * 12 + (anchor.month - 1) - months
    return dt.date(total // 12, total % 12 + 1, 1)


def history_window() -> tuple[dt.date, dt.date]:
    """The full transactional history: 24 months ending at the reference date."""
    return _shift_months(REFERENCE_DATE, HISTORY_MONTHS - 1), REFERENCE_DATE


def attendance_window() -> tuple[dt.date, dt.date]:
    """Attendance only: 6 months ending at the reference date (spec FR-020a)."""
    return _shift_months(REFERENCE_DATE, ATTENDANCE_MONTHS - 1), REFERENCE_DATE


def last_full_month() -> tuple[dt.date, dt.date]:
    """The most recent complete calendar month.

    The reference date is deliberately a month end, so this is that same month —
    which is what makes the blueprint's "generate last month's sales report" demo
    resolve to a month with complete data.
    """
    start = dt.date(REFERENCE_DATE.year, REFERENCE_DATE.month, 1)
    return start, REFERENCE_DATE


def days_before(days: int) -> dt.date:
    """A date `days` before the reference date."""
    return REFERENCE_DATE - dt.timedelta(days=days)


def month_starts() -> list[dt.date]:
    """First day of every month in the history window, oldest first."""
    start, _ = history_window()
    return [_shift_months(REFERENCE_DATE, offset) for offset in range(HISTORY_MONTHS - 1, -1, -1)][
        : HISTORY_MONTHS
    ] or [start]
