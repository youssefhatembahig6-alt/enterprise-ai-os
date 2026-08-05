"""Declarative base and the mixins that enforce the tenancy conventions.

``TenantMixin`` is the important one: it makes ``company_id`` non-nullable and
indexed on every table that uses it. A table that simply forgets to inherit it is
caught by ``tests/security/test_tenant_columns.py``, which walks the metadata and
compares it against the closed allowlist in :mod:`eaios_core.tenancy`.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Annotated

from sqlalchemy import ForeignKey, Index, MetaData, Numeric, String, text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

__all__ = [
    "Base",
    "Money",
    "TenantMixin",
    "TimestampMixin",
    "money_column",
    "uuid_pk",
]

# Predictable constraint names make migrations readable and downgrades reliable.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


#: Money is always exact. Floating point in a finance table is a correctness bug
#: waiting for a reconciliation test to find it (spec FR-038).
Money = Annotated[Decimal, mapped_column(Numeric(14, 2))]


def uuid_pk() -> Mapped[uuid.UUID]:
    """Primary key column.

    Deliberately no database default: identifiers are derived deterministically
    before insertion (research R1), so a server-side default would mask a bug where
    the generator forgot to supply one.
    """
    return mapped_column(PgUUID(as_uuid=True), primary_key=True)


def money_column(**kwargs: object) -> Mapped[Decimal]:
    return mapped_column(Numeric(14, 2), **kwargs)  # type: ignore[arg-type]


class TimestampMixin:
    """Audit timestamps set explicitly from the reference clock, never ``now()``.

    These are included in the fingerprint rather than excluded from it — see
    :data:`eaios_core.fingerprint.FINGERPRINT_EXCLUSIONS` for why.
    """

    created_at: Mapped[dt.datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class TenantMixin:
    """Every tenant-owned table carries this. No exceptions outside the allowlist."""

    @declared_attr
    def company_id(cls) -> Mapped[uuid.UUID]:  # noqa: N805
        return mapped_column(
            PgUUID(as_uuid=True),
            ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        )


class CurrencyMixin:
    currency: Mapped[str] = mapped_column(String(3), nullable=False)


def tenant_index(table: str, *columns: str) -> Index:
    """Composite index led by ``company_id`` — the shape every tenant query uses."""
    return Index(f"ix_{table}_company_{'_'.join(columns)}", "company_id", *columns)


SQL_UTC_NOW_FORBIDDEN = text("")  # placeholder kept out of use; timestamps are explicit
