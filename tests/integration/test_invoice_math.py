"""Monetary totals are exact and derived (spec FR-038, SC-007).

Every figure has exactly one source: line totals from quantity and price, order
subtotals from their lines, invoices from their order, monthly revenue from the
orders. These tests prove no second source crept in — a generator that computed a
total independently would drift, and the drift would surface later as an AI that
"hallucinated" a number it actually read correctly.

All comparisons are exact at two decimal places. Money is `NUMERIC`, never float.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import Engine, text

pytestmark = pytest.mark.integration


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


class TestLineArithmetic:
    def test_line_total_equals_quantity_times_price(self, engine: Engine) -> None:
        with engine.connect() as conn:
            broken = conn.execute(
                text(
                    "SELECT count(*) FROM order_lines"
                    " WHERE line_total <> round(quantity * unit_price, 2)"
                )
            ).scalar_one()
        assert broken == 0

    def test_quantities_are_positive(self, engine: Engine) -> None:
        with engine.connect() as conn:
            bad = conn.execute(
                text("SELECT count(*) FROM order_lines WHERE quantity <= 0")
            ).scalar_one()
        assert bad == 0

    def test_every_order_has_at_least_one_line(self, engine: Engine) -> None:
        with engine.connect() as conn:
            empty = conn.execute(
                text(
                    "SELECT count(*) FROM orders o"
                    " WHERE NOT EXISTS (SELECT 1 FROM order_lines l WHERE l.order_id = o.id)"
                )
            ).scalar_one()
        assert empty == 0


class TestOrderArithmetic:
    def test_subtotal_equals_sum_of_lines(self, engine: Engine) -> None:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT o.id, o.subtotal, sum(l.line_total) AS lines_total"
                    " FROM orders o JOIN order_lines l ON l.order_id = o.id"
                    " GROUP BY o.id, o.subtotal"
                    " HAVING o.subtotal <> sum(l.line_total)"
                )
            ).all()
        assert rows == [], f"{len(rows)} order(s) whose subtotal disagrees with their lines"

    def test_total_equals_subtotal_plus_tax(self, engine: Engine) -> None:
        with engine.connect() as conn:
            broken = conn.execute(
                text("SELECT count(*) FROM orders WHERE total <> subtotal + tax")
            ).scalar_one()
        assert broken == 0

    def test_no_negative_amounts(self, engine: Engine) -> None:
        with engine.connect() as conn:
            negative = conn.execute(
                text("SELECT count(*) FROM orders WHERE subtotal < 0 OR tax < 0 OR total < 0")
            ).scalar_one()
        assert negative == 0

    def test_order_lines_reference_products_of_the_same_company(self, engine: Engine) -> None:
        with engine.connect() as conn:
            crossing = conn.execute(
                text(
                    "SELECT count(*) FROM order_lines l JOIN products p ON p.id = l.product_id"
                    " WHERE p.company_id <> l.company_id"
                )
            ).scalar_one()
        assert crossing == 0


class TestInvoiceArithmetic:
    def test_invoice_amount_equals_order_total(self, engine: Engine) -> None:
        with engine.connect() as conn:
            broken = conn.execute(
                text(
                    "SELECT count(*) FROM invoices i JOIN orders o ON o.id = i.order_id"
                    " WHERE i.amount <> o.total"
                )
            ).scalar_one()
        assert broken == 0

    def test_exactly_one_invoice_per_order(self, engine: Engine) -> None:
        with engine.connect() as conn:
            orders = conn.execute(text("SELECT count(*) FROM orders")).scalar_one()
            invoices = conn.execute(text("SELECT count(*) FROM invoices")).scalar_one()
        assert orders == invoices

    def test_due_date_follows_issue_date(self, engine: Engine) -> None:
        with engine.connect() as conn:
            broken = conn.execute(
                text("SELECT count(*) FROM invoices WHERE due_date < issue_date")
            ).scalar_one()
        assert broken == 0

    def test_invoice_currency_matches_its_order(self, engine: Engine) -> None:
        with engine.connect() as conn:
            broken = conn.execute(
                text(
                    "SELECT count(*) FROM invoices i JOIN orders o ON o.id = i.order_id"
                    " WHERE i.currency <> o.currency"
                )
            ).scalar_one()
        assert broken == 0


class TestMonthlyRevenueAggregate:
    def test_aggregate_equals_the_detail(self, engine: Engine) -> None:
        """The pre-aggregated table exists for query speed; it must not be a second
        source of truth that can disagree with the orders it summarises."""
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT m.company_id, m.year_month, m.region, m.revenue_amount,"
                    "       m.order_count,"
                    "       coalesce(sum(o.total), 0) AS actual_amount,"
                    "       count(o.id) AS actual_count"
                    " FROM monthly_revenue m"
                    " LEFT JOIN orders o"
                    "   ON o.company_id = m.company_id"
                    "  AND o.region = m.region"
                    "  AND to_char(o.order_date, 'YYYY-MM') = m.year_month"
                    " GROUP BY m.company_id, m.year_month, m.region, m.revenue_amount, m.order_count"
                )
            ).all()

        assert rows, "no monthly revenue rows to check"
        mismatches = [
            f"{row.year_month}/{row.region}: recorded {row.revenue_amount} "
            f"({row.order_count} orders), actual {row.actual_amount} ({row.actual_count})"
            for row in rows
            if row.revenue_amount != row.actual_amount or row.order_count != row.actual_count
        ]
        assert mismatches == [], "\n".join(mismatches[:10])

    def test_revenue_is_scoped_per_tenant(self, engine: Engine) -> None:
        """Aggregating across tenants would be a silent cross-tenant disclosure."""
        with engine.connect() as conn:
            total_by_company = conn.execute(
                text(
                    "SELECT company_id, sum(revenue_amount) FROM monthly_revenue GROUP BY 1"
                )
            ).all()
            orders_by_company = conn.execute(
                text("SELECT company_id, sum(total) FROM orders GROUP BY 1")
            ).all()
        assert dict(total_by_company) == dict(orders_by_company)


class TestCurrencyConsistency:
    def test_one_currency_per_company(self, engine: Engine) -> None:
        with engine.connect() as conn:
            for table in ("orders", "invoices", "products", "expenses", "budgets"):
                rows = conn.execute(
                    text(f"SELECT company_id, count(DISTINCT currency) AS n FROM {table} GROUP BY 1")
                ).all()
                for row in rows:
                    assert row.n == 1, f"{table} has {row.n} currencies for one company"

    def test_currency_matches_the_company_setting(self, engine: Engine) -> None:
        with engine.connect() as conn:
            mismatched = conn.execute(
                text(
                    "SELECT count(*) FROM orders o JOIN companies c ON c.id = o.company_id"
                    " WHERE o.currency <> c.reporting_currency"
                )
            ).scalar_one()
        assert mismatched == 0

    def test_amounts_are_exact_decimals_not_floats(self, engine: Engine) -> None:
        with engine.connect() as conn:
            value = conn.execute(text("SELECT total FROM orders LIMIT 1")).scalar_one()
        assert isinstance(value, Decimal)
        assert value == value.quantize(Decimal("0.01"))
