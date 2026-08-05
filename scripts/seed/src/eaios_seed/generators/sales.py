"""Sales and finance generator (spec FR-027, FR-038, FR-020c).

Every total is *derived*, never independently generated: line totals from quantity
and price, order subtotals from their lines, invoices from their order, and monthly
revenue from the orders themselves. That is what makes the FR-038 coherence checks
pass by construction — there is no second source for any figure to disagree with.

Volumes follow a deterministic seasonal curve so that "June vs May" and
year-over-year questions have a real trend to find rather than noise (FR-020c).
"""

from __future__ import annotations

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from eaios_core.clock import history_window, reference_datetime
from eaios_core.constants import COMPANY_CURRENCIES, DELTA_RETAIL, NILETECH
from eaios_core.ids import derive

from ..config import SeedConfig
from ..dataset import Dataset
from ..rng import Rng
from .organization import OrgContext

__all__ = ["generate_sales"]

CENTS = Decimal("0.01")
_TAX_RATE = Decimal("0.14")  # single flat rate; realism is not the point here

REGIONS = ("EMEA", "GULF", "NORTH_AFRICA", "EUROPE")

_CATALOG: dict[str, list[tuple[str, str, int, int]]] = {
    # (name, tier, price_low, price_high)
    NILETECH: [
        ("Workflow Automation Platform", "Enterprise", 24000, 48000),
        ("Workflow Automation Platform", "Business", 9000, 18000),
        ("Document Intelligence Suite", "Enterprise", 20000, 40000),
        ("Document Intelligence Suite", "Business", 7500, 15000),
        ("Integration Gateway", "Standard", 4000, 9000),
        ("Analytics Workspace", "Business", 6000, 14000),
        ("Managed Support Retainer", "Standard", 2500, 6000),
        ("Implementation Services", "Professional", 12000, 30000),
    ],
    DELTA_RETAIL: [
        ("Bulk Grocery Pallet", "Wholesale", 800, 2400),
        ("Household Essentials Case", "Wholesale", 300, 950),
        ("Seasonal Apparel Lot", "Retail", 1200, 3800),
        ("Consumer Electronics Bundle", "Retail", 2200, 7500),
        ("Fresh Produce Crate", "Perishable", 150, 640),
        ("Beverage Multipack", "Retail", 220, 880),
    ],
}

_EXPENSE_CATEGORIES = (
    "TRAVEL", "SOFTWARE", "HARDWARE", "TRAINING", "MARKETING", "FACILITIES", "PROFESSIONAL_FEES",
)


def _money(value: Decimal | float | int) -> Decimal:
    return Decimal(str(value)).quantize(CENTS, rounding=ROUND_HALF_UP)


def _seasonal_factor(month: int) -> float:
    """Deterministic seasonality — a real curve, not random noise."""
    curve = {
        1: 0.86, 2: 0.88, 3: 1.02, 4: 0.98, 5: 1.05, 6: 1.18,
        7: 0.92, 8: 0.84, 9: 1.08, 10: 1.12, 11: 1.22, 12: 1.10,
    }
    return curve[month]


def _growth_factor(order_date: dt.date, start: dt.date) -> float:
    """Gentle year-over-year growth so trend questions have an answer."""
    months = (order_date.year - start.year) * 12 + (order_date.month - start.month)
    return 1.0 + (months * 0.011)


def generate_sales(dataset: Dataset, config: SeedConfig, ctx: OrgContext) -> None:
    for slug in ctx.users:
        _generate_for_company(dataset, config, ctx, slug)


def _generate_for_company(
    dataset: Dataset, config: SeedConfig, ctx: OrgContext, slug: str
) -> None:
    rng = Rng(config.seed, "sales", slug)
    now = reference_datetime()
    company_id = ctx.company_ids[slug]
    currency = COMPANY_CURRENCIES[slug]
    volumes = config.for_tenant(slug)
    history_start, history_end = history_window()

    def row(**kwargs: Any) -> dict[str, Any]:
        return {"company_id": company_id, "created_at": now, "updated_at": now, **kwargs}

    reps = [u for u in ctx.users[slug] if u.department == "Sales"]
    if not reps:
        reps = ctx.users[slug][:1]

    # -- products ---------------------------------------------------------
    catalog = _CATALOG[slug]
    products: list[dict[str, Any]] = []
    for index in range(volumes.products):
        name, tier, low, high = catalog[index % len(catalog)]
        sku = f"{slug[:3].upper()}-{index + 1:04d}"
        product = row(
            id=derive("product", slug, sku, seed=config.seed),
            sku=sku,
            name=f"{name} {index // len(catalog) + 1}" if index >= len(catalog) else name,
            tier=tier,
            unit_price=_money(rng.randint(low, high)),
            currency=currency,
            is_active=True,
        )
        products.append(product)
        dataset.add("products", product)

    # -- customers --------------------------------------------------------
    customers: list[dict[str, Any]] = []
    for index in range(volumes.customers):
        natural_key = f"customer-{index + 1:04d}"
        owner = reps[index % len(reps)]
        since_offset = rng.randint(60, 2200)
        customer = row(
            id=derive("customer", slug, natural_key, seed=config.seed),
            # Disjoint name pools per tenant: a customer must never be reusable
            # across companies (FR-024a).
            name=f"{rng.company_name()} ({'NT' if slug == NILETECH else 'DR'}-{index + 1:03d})",
            region=rng.choice(list(REGIONS)),
            country=owner.country,
            account_owner_id=owner.id,
            since_date=config.reference_date - dt.timedelta(days=since_offset),
        )
        customers.append(customer)
        dataset.add("customers", customer)

    # -- orders, lines, invoices ------------------------------------------
    total_days = (history_end - history_start).days
    revenue: dict[tuple[str, str], list[Decimal]] = {}

    # Orders are allocated across months in proportion to the seasonal and growth
    # curves, rather than sampled uniformly and nudged. Rejection sampling produced
    # a trend too weak to see — and the blueprint's flagship demo ("last month's
    # sales report", June up on May) needs the curve to actually be legible.
    order_dates = _allocate_order_dates(volumes.orders, history_start, history_end, rng)

    for index in range(volumes.orders):
        customer = customers[index % len(customers)]
        rep = reps[index % len(reps)]

        order_date = max(order_dates[index], customer["since_date"])  # never predates customer
        if order_date > history_end:
            order_date = history_end

        order_number = f"SO-{index + 1:06d}"
        order_id = derive("order", slug, order_number, seed=config.seed)

        subtotal = Decimal("0.00")
        line_count = rng.randint(1, 4)
        for line_index in range(line_count):
            product = products[(index + line_index) % len(products)]
            quantity = rng.randint(1, 12)
            unit_price = product["unit_price"]
            line_total = _money(unit_price * quantity)
            subtotal += line_total
            dataset.add(
                "order_lines",
                row(
                    id=derive("order_line", slug, f"{order_number}:{line_index}", seed=config.seed),
                    order_id=order_id, product_id=product["id"], quantity=quantity,
                    unit_price=unit_price, line_total=line_total,
                ),
            )

        subtotal = _money(subtotal)
        tax = _money(subtotal * _TAX_RATE)
        total = _money(subtotal + tax)
        region = customer["region"]

        dataset.add(
            "orders",
            row(
                id=order_id, order_number=order_number, customer_id=customer["id"],
                sales_rep_id=rep.id, order_date=order_date, region=region,
                status=rng.weighted({"FULFILLED": 0.78, "PENDING": 0.12, "CANCELLED": 0.10}),
                subtotal=subtotal, tax=tax, total=total, currency=currency,
            ),
        )

        # Clamped to the window: an order on the final day would otherwise produce
        # an invoice dated after it, violating FR-037.
        issue = min(order_date + dt.timedelta(days=rng.randint(0, 5)), history_end)
        dataset.add(
            "invoices",
            row(
                id=derive("invoice", slug, order_number, seed=config.seed),
                order_id=order_id, invoice_number=f"INV-{index + 1:06d}",
                issue_date=issue, due_date=issue + dt.timedelta(days=30),
                amount=total,  # must equal orders.total (FR-038)
                currency=currency,
                status=rng.weighted({"PAID": 0.74, "OPEN": 0.18, "OVERDUE": 0.08}),
            ),
        )

        key = (f"{order_date.year:04d}-{order_date.month:02d}", region)
        revenue.setdefault(key, []).append(total)

    # -- monthly revenue, aggregated from the orders above -----------------
    for (year_month, region), amounts in sorted(revenue.items()):
        dataset.add(
            "monthly_revenue",
            row(
                id=derive("monthly_revenue", slug, f"{year_month}:{region}", seed=config.seed),
                year_month=year_month, region=region,
                revenue_amount=_money(sum(amounts, Decimal("0.00"))),
                currency=currency, order_count=len(amounts),
            ),
        )

    # -- sales targets: per rep, per quarter -------------------------------
    for rep in reps:
        for quarter_start in _quarters(history_start, history_end):
            quarter_end = _quarter_end(quarter_start)
            dataset.add(
                "sales_targets",
                row(
                    id=derive("sales_target", slug, f"{rep.natural_key}:{quarter_start.isoformat()}",
                              seed=config.seed),
                    sales_rep_id=rep.id, period_start=quarter_start, period_end=quarter_end,
                    region=rng.choice(list(REGIONS)),
                    target_amount=_money(rng.randint(40000, 260000)), currency=currency,
                ),
            )

    # -- expenses and budgets ---------------------------------------------
    departments = ctx.departments[slug]
    dept_names = sorted(departments)
    for index in range(volumes.expenses):
        dept = dept_names[index % len(dept_names)]
        submitter = ctx.head_of(slug, dept)
        dataset.add(
            "expenses",
            row(
                id=derive("expense", slug, f"expense-{index + 1:05d}", seed=config.seed),
                department_id=departments[dept], submitted_by_id=submitter.id,
                category=rng.choice(list(_EXPENSE_CATEGORIES)),
                expense_date=history_start + dt.timedelta(days=rng.randint(0, total_days)),
                amount=_money(rng.randint(45, 8400)), currency=currency,
                status=rng.weighted({"APPROVED": 0.80, "SUBMITTED": 0.12, "REJECTED": 0.08}),
            ),
        )

    for dept in dept_names:
        for quarter_start in _quarters(history_start, history_end):
            dataset.add(
                "budgets",
                row(
                    id=derive("budget", slug, f"{dept}:{quarter_start.isoformat()}", seed=config.seed),
                    department_id=departments[dept], period_start=quarter_start,
                    period_end=_quarter_end(quarter_start),
                    allocated_amount=_money(rng.randint(25000, 320000)), currency=currency,
                ),
            )


def _month_starts(start: dt.date, end: dt.date) -> list[dt.date]:
    months: list[dt.date] = []
    year, month = start.year, start.month
    while dt.date(year, month, 1) <= end:
        months.append(dt.date(year, month, 1))
        month += 1
        if month > 12:
            month, year = 1, year + 1
    return months


def _allocate_order_dates(
    total: int, start: dt.date, end: dt.date, rng: Rng
) -> list[dt.date]:
    """Distribute order dates across the window following the seasonal curve.

    Deterministic: month counts come from the weights, and the day within a month
    comes from the generator's own seeded RNG.
    """
    months = _month_starts(start, end)
    weights = [_seasonal_factor(m.month) * _growth_factor(m, start) for m in months]
    weight_sum = sum(weights)

    counts = [int(total * w / weight_sum) for w in weights]
    index = 0
    while sum(counts) < total:  # hand out the remainder, heaviest months first
        order = sorted(range(len(weights)), key=lambda i: (-weights[i], i))
        counts[order[index % len(order)]] += 1
        index += 1

    dates: list[dt.date] = []
    for month_start, count in zip(months, counts, strict=True):
        next_month = _month_starts(month_start, month_start)[0]
        last_day = (
            dt.date(next_month.year + (next_month.month // 12), next_month.month % 12 + 1, 1)
            - dt.timedelta(days=1)
        )
        span = min(last_day, end)
        for _ in range(count):
            dates.append(month_start + dt.timedelta(days=rng.randint(0, (span - month_start).days)))
    return dates


def _quarters(start: dt.date, end: dt.date) -> list[dt.date]:
    quarters: list[dt.date] = []
    year, month = start.year, ((start.month - 1) // 3) * 3 + 1
    while dt.date(year, month, 1) <= end:
        quarters.append(dt.date(year, month, 1))
        month += 3
        if month > 12:
            month, year = 1, year + 1
    return quarters


def _quarter_end(quarter_start: dt.date) -> dt.date:
    month = quarter_start.month + 3
    year = quarter_start.year
    if month > 12:
        month, year = month - 12, year + 1
    return dt.date(year, month, 1) - dt.timedelta(days=1)
