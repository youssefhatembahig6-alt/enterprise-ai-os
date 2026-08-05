"""Every date sits inside its window and after its parent (spec FR-037, FR-020a).

Two failure modes this catches. A date outside the pinned window means something
read the wall clock despite the static guard. A child record predating its parent —
an order before its customer existed, leave before a hire date — is the kind of
incoherence that makes a dataset unusable for demonstration the moment anyone looks
closely.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import Engine, text

from eaios_core.clock import attendance_window, history_window, reference_date

pytestmark = pytest.mark.integration

HISTORY_START, HISTORY_END = history_window()
ATTENDANCE_START, ATTENDANCE_END = attendance_window()


@pytest.fixture(scope="module")
def engine() -> Engine:
    from eaios_core.db import create_owner_engine

    engine = create_owner_engine()
    try:
        with engine.connect() as conn:
            seeded = conn.execute(text("SELECT count(*) FROM orders")).scalar_one()
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"database unavailable: {exc}")
    if not seeded:
        pytest.skip("environment not seeded; run `make up && make seed`")
    return engine


def _out_of_window(engine: Engine, table: str, column: str, start: dt.date, end: dt.date) -> int:
    with engine.connect() as conn:
        return int(
            conn.execute(
                text(f"SELECT count(*) FROM {table} WHERE {column} < :start OR {column} > :end"),
                {"start": start, "end": end},
            ).scalar_one()
        )


class TestHistoryWindow:
    @pytest.mark.parametrize(
        ("table", "column"),
        [
            ("orders", "order_date"),
            ("invoices", "issue_date"),
            ("expenses", "expense_date"),
            ("leave_requests", "start_date"),
            ("training_records", "completed_on"),
            ("news_items", "published_on"),
        ],
    )
    def test_dates_fall_inside_the_24_month_window(
        self, engine: Engine, table: str, column: str
    ) -> None:
        out = _out_of_window(engine, table, column, HISTORY_START, HISTORY_END)
        assert out == 0, f"{table}.{column}: {out} row(s) outside {HISTORY_START}..{HISTORY_END}"

    def test_the_window_is_the_pinned_one(self) -> None:
        assert HISTORY_END == reference_date() == dt.date(2026, 6, 30)
        assert dt.date(2024, 7, 1) == HISTORY_START


class TestAttendanceWindow:
    def test_attendance_is_capped_at_six_months(self, engine: Engine) -> None:
        """FR-020a — attendance rows dominate volume, so the window is shorter."""
        out = _out_of_window(
            engine, "attendance_records", "work_date", ATTENDANCE_START, ATTENDANCE_END
        )
        assert out == 0

    def test_the_attendance_window_is_narrower_than_history(self) -> None:
        assert ATTENDANCE_START > HISTORY_START
        assert ATTENDANCE_END == HISTORY_END

    def test_no_attendance_on_a_weekend(self, engine: Engine) -> None:
        """Egypt and the UAE both use a Friday-Saturday weekend; a Mon-Fri
        assumption would produce impossible working days for everyone."""
        with engine.connect() as conn:
            weekend_rows = conn.execute(
                text(
                    "SELECT count(*) FROM attendance_records a JOIN users u ON u.id = a.user_id"
                    " WHERE u.country IN ('EG', 'AE')"
                    "   AND EXTRACT(ISODOW FROM a.work_date) IN (5, 6)"
                )
            ).scalar_one()
        assert weekend_rows == 0


class TestNoChildPredatesItsParent:
    def test_orders_do_not_precede_their_customer(self, engine: Engine) -> None:
        with engine.connect() as conn:
            bad = conn.execute(
                text(
                    "SELECT count(*) FROM orders o JOIN customers c ON c.id = o.customer_id"
                    " WHERE o.order_date < c.since_date"
                )
            ).scalar_one()
        assert bad == 0

    def test_leave_requests_do_not_precede_the_hire_date(self, engine: Engine) -> None:
        with engine.connect() as conn:
            bad = conn.execute(
                text(
                    "SELECT count(*) FROM leave_requests lr"
                    " JOIN employee_profiles ep ON ep.user_id = lr.user_id"
                    " WHERE lr.start_date < ep.hire_date"
                )
            ).scalar_one()
        assert bad == 0

    def test_attendance_does_not_precede_the_hire_date(self, engine: Engine) -> None:
        with engine.connect() as conn:
            bad = conn.execute(
                text(
                    "SELECT count(*) FROM attendance_records a"
                    " JOIN employee_profiles ep ON ep.user_id = a.user_id"
                    " WHERE a.work_date < ep.hire_date"
                )
            ).scalar_one()
        assert bad == 0

    def test_invoices_do_not_precede_their_order(self, engine: Engine) -> None:
        with engine.connect() as conn:
            bad = conn.execute(
                text(
                    "SELECT count(*) FROM invoices i JOIN orders o ON o.id = i.order_id"
                    " WHERE i.issue_date < o.order_date"
                )
            ).scalar_one()
        assert bad == 0

    def test_leave_ends_on_or_after_it_starts(self, engine: Engine) -> None:
        with engine.connect() as conn:
            bad = conn.execute(
                text("SELECT count(*) FROM leave_requests WHERE end_date < start_date")
            ).scalar_one()
        assert bad == 0

    def test_contracts_expire_after_they_take_effect(self, engine: Engine) -> None:
        with engine.connect() as conn:
            bad = conn.execute(
                text("SELECT count(*) FROM contracts WHERE expiry_date <= effective_date")
            ).scalar_one()
        assert bad == 0


class TestNothingFromTheFuture:
    def test_no_business_date_exceeds_the_reference_date(self, engine: Engine) -> None:
        """A date after the pinned reference would mean the wall clock leaked in."""
        with engine.connect() as conn:
            for table, column in (
                ("orders", "order_date"),
                ("attendance_records", "work_date"),
                ("leave_requests", "start_date"),
                ("expenses", "expense_date"),
            ):
                future = conn.execute(
                    text(f"SELECT count(*) FROM {table} WHERE {column} > :ref"),
                    {"ref": reference_date()},
                ).scalar_one()
                assert future == 0, f"{table}.{column} has {future} future-dated row(s)"

    def test_hire_dates_precede_the_reference_date(self, engine: Engine) -> None:
        with engine.connect() as conn:
            future = conn.execute(
                text("SELECT count(*) FROM employee_profiles WHERE hire_date > :ref"),
                {"ref": reference_date()},
            ).scalar_one()
        assert future == 0
