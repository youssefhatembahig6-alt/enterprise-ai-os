"""Sales and finance entities (data-model.md §4).

Every monetary total is derived, never independently generated: line totals come
from quantity × price, order subtotals from their lines, and invoices from their
order. The coherence check asserts each of those equalities rather than trusting the
generator (spec FR-038).
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantMixin, TimestampMixin, uuid_pk

__all__ = [
    "Budget",
    "Customer",
    "Expense",
    "Invoice",
    "MonthlyRevenue",
    "Order",
    "OrderLine",
    "Product",
    "SalesTarget",
]


class Customer(Base, TenantMixin, TimestampMixin):
    """A client organization of a Company. Never shared between tenants (FR-024a)."""

    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("company_id", "name"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    region: Mapped[str] = mapped_column(String(32), nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    account_owner_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    since_date: Mapped[dt.date] = mapped_column(Date, nullable=False)


class Product(Base, TenantMixin, TimestampMixin):
    """The internal sellable catalog — distinct from PublicProduct (marketing)."""

    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("company_id", "sku"),
        CheckConstraint("unit_price >= 0", name="non_negative_price"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    sku: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    tier: Mapped[str] = mapped_column(String(32), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Order(Base, TenantMixin, TimestampMixin):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("company_id", "order_number"),
        CheckConstraint("total = subtotal + tax", name="total_arithmetic"),
        CheckConstraint("subtotal >= 0 AND tax >= 0", name="non_negative_amounts"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    order_number: Mapped[str] = mapped_column(String(32), nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    sales_rep_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    order_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    region: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    tax: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)


class OrderLine(Base, TenantMixin, TimestampMixin):
    __tablename__ = "order_lines"
    __table_args__ = (
        CheckConstraint("line_total = quantity * unit_price", name="line_arithmetic"),
        CheckConstraint("quantity > 0", name="positive_quantity"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    order_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)


class Invoice(Base, TenantMixin, TimestampMixin):
    """``amount`` must equal ``orders.total`` — asserted, not assumed."""

    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("order_id"),
        UniqueConstraint("company_id", "invoice_number"),
        CheckConstraint("due_date >= issue_date", name="date_order"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    order_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    invoice_number: Mapped[str] = mapped_column(String(32), nullable=False)
    issue_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    due_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)


class SalesTarget(Base, TenantMixin, TimestampMixin):
    __tablename__ = "sales_targets"
    __table_args__ = (UniqueConstraint("sales_rep_id", "period_start"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    sales_rep_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    period_start: Mapped[dt.date] = mapped_column(Date, nullable=False)
    period_end: Mapped[dt.date] = mapped_column(Date, nullable=False)
    region: Mapped[str] = mapped_column(String(32), nullable=False)
    target_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)


class Expense(Base, TenantMixin, TimestampMixin):
    __tablename__ = "expenses"

    id: Mapped[uuid.UUID] = uuid_pk()
    department_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False
    )
    submitted_by_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    expense_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)


class Budget(Base, TenantMixin, TimestampMixin):
    __tablename__ = "budgets"
    __table_args__ = (UniqueConstraint("company_id", "department_id", "period_start"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    department_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False
    )
    period_start: Mapped[dt.date] = mapped_column(Date, nullable=False)
    period_end: Mapped[dt.date] = mapped_column(Date, nullable=False)
    allocated_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)


class MonthlyRevenue(Base, TenantMixin, TimestampMixin):
    """Pre-aggregated from orders at seed time.

    Exists so the later SQL agent has a fast path, and so the coherence check can
    prove that the aggregate equals the detail.
    """

    __tablename__ = "monthly_revenue"
    __table_args__ = (UniqueConstraint("company_id", "year_month", "region"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    year_month: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM
    region: Mapped[str] = mapped_column(String(32), nullable=False)
    revenue_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    order_count: Mapped[int] = mapped_column(Integer, nullable=False)
