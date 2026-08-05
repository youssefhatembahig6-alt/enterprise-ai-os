"""The pinned reference clock (spec FR-012, research R2).

Generation must never read the wall clock. If it does, the dataset becomes a
function of *when* it was seeded and two developers seeding on different days get
different data — which contradicts SC-002 outright.
"""

from __future__ import annotations

import datetime as dt
import os
import time

import pytest

from eaios_core import clock

pytestmark = pytest.mark.unit


class TestPinnedDate:
    def test_reference_date_is_pinned(self) -> None:
        assert clock.reference_date() == dt.date(2026, 6, 30)

    def test_reference_datetime_is_utc(self) -> None:
        moment = clock.reference_datetime()
        assert moment.tzinfo == dt.UTC
        assert moment.date() == dt.date(2026, 6, 30)

    def test_repeated_calls_are_identical(self) -> None:
        first = clock.reference_datetime()
        time.sleep(0.01)
        assert clock.reference_datetime() == first


class TestEnvironmentIndependence:
    @pytest.mark.parametrize("tz", ["UTC", "Africa/Cairo", "Asia/Dubai", "America/Los_Angeles"])
    def test_timezone_does_not_affect_the_reference_date(self, tz: str) -> None:
        previous = os.environ.get("TZ")
        os.environ["TZ"] = tz
        try:
            assert clock.reference_date() == dt.date(2026, 6, 30)
        finally:
            if previous is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = previous


class TestDerivedWindows:
    def test_history_window_spans_24_months_ending_at_the_reference_date(self) -> None:
        start, end = clock.history_window()
        assert end == dt.date(2026, 6, 30)
        assert start == dt.date(2024, 7, 1)

    def test_attendance_window_is_capped_at_6_months(self) -> None:
        """FR-020a — attendance rows dominate volume, so the window is shorter."""
        start, end = clock.attendance_window()
        assert end == dt.date(2026, 6, 30)
        assert start == dt.date(2026, 1, 1)

    def test_last_full_month_is_june_2026(self) -> None:
        """The blueprint's flagship demo asks for 'last month's sales report'."""
        start, end = clock.last_full_month()
        assert start == dt.date(2026, 6, 1)
        assert end == dt.date(2026, 6, 30)

    def test_days_before_is_relative_to_the_reference_date(self) -> None:
        assert clock.days_before(30) == dt.date(2026, 5, 31)

    def test_windows_are_inside_one_another(self) -> None:
        history_start, history_end = clock.history_window()
        attendance_start, attendance_end = clock.attendance_window()
        assert history_start < attendance_start
        assert attendance_end == history_end
