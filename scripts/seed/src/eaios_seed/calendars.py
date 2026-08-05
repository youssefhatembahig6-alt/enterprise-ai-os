"""Working calendars per country (spec FR-012, Edge Cases).

Committed data rather than an external calendar service, because generation must
be reproducible offline and forever. Egypt and the UAE both use a Friday–Saturday
weekend, which is why a naive Mon–Fri assumption would produce impossible working
days for every employee in the dataset.

Holiday dates are approximations for a fictional company. They exist so attendance
has realistic gaps, not to be authoritative.
"""

from __future__ import annotations

import datetime as dt
from typing import Final

__all__ = ["HOLIDAYS", "WEEKEND", "is_working_day", "working_days_between"]

#: Weekday indices (Mon=0 … Sun=6). Friday and Saturday in both countries.
WEEKEND: Final[dict[str, frozenset[int]]] = {
    "EG": frozenset({4, 5}),
    "AE": frozenset({4, 5}),
}

HOLIDAYS: Final[dict[str, frozenset[dt.date]]] = {
    "EG": frozenset(
        {
            dt.date(2026, 1, 7),  # Coptic Christmas
            dt.date(2026, 1, 25),  # Revolution Day
            dt.date(2026, 3, 20),  # Eid al-Fitr (approx.)
            dt.date(2026, 3, 21),
            dt.date(2026, 4, 25),  # Sinai Liberation Day
            dt.date(2026, 5, 1),  # Labour Day
            dt.date(2026, 5, 27),  # Eid al-Adha (approx.)
            dt.date(2026, 6, 30),  # June 30 Revolution
            dt.date(2025, 1, 7),
            dt.date(2025, 1, 25),
            dt.date(2025, 4, 25),
            dt.date(2025, 5, 1),
            dt.date(2024, 10, 6),
            dt.date(2024, 7, 23),
        }
    ),
    "AE": frozenset(
        {
            dt.date(2026, 1, 1),  # New Year
            dt.date(2026, 3, 20),  # Eid al-Fitr (approx.)
            dt.date(2026, 3, 21),
            dt.date(2026, 5, 27),  # Eid al-Adha (approx.)
            dt.date(2026, 6, 16),  # Islamic New Year (approx.)
            dt.date(2025, 1, 1),
            dt.date(2025, 12, 2),  # National Day
            dt.date(2024, 12, 2),
            dt.date(2024, 7, 7),
        }
    ),
}


def is_working_day(day: dt.date, country: str) -> bool:
    weekend = WEEKEND.get(country, frozenset({5, 6}))
    if day.weekday() in weekend:
        return False
    return day not in HOLIDAYS.get(country, frozenset())


def working_days_between(start: dt.date, end: dt.date, country: str) -> list[dt.date]:
    """Every working day in [start, end], inclusive, oldest first."""
    days: list[dt.date] = []
    current = start
    while current <= end:
        if is_working_day(current, country):
            days.append(current)
        current += dt.timedelta(days=1)
    return days
