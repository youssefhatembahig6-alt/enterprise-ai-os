"""Legal and document entities (data-model.md §5)."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ENUM, JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..classification import Classification
from .base import Base, TenantMixin, TimestampMixin, uuid_pk

__all__ = ["Contract", "Document", "DocumentAcl", "PolicyDocument", "classification_enum"]

#: Native PostgreSQL enum so an unrecognised level cannot be persisted (spec FR-010b).
classification_enum = ENUM(
    *[c.value for c in Classification],
    name="classification_level",
    create_type=False,
)


class Document(Base, TenantMixin, TimestampMixin):
    """Metadata for every stored file. Exactly one owner, same company (FR-031a)."""

    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("storage_key"),
        CheckConstraint("byte_size > 0", name="non_empty"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("departments.id", ondelete="RESTRICT"), nullable=True
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    document_type: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    classification: Mapped[str] = mapped_column(classification_enum, nullable=False)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)


class DocumentAcl(Base, TenantMixin, TimestampMixin):
    """Resource-level grants — the exception layer above role and attribute rules."""

    __tablename__ = "document_acl"
    __table_args__ = (
        UniqueConstraint("document_id", "principal_type", "principal_id", "permission"),
        CheckConstraint(
            "principal_type IN ('USER','ROLE','DEPARTMENT')", name="principal_type_values"
        ),
        CheckConstraint("permission IN ('READ','WRITE')", name="permission_values"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    principal_type: Mapped[str] = mapped_column(String(16), nullable=False)
    principal_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    permission: Mapped[str] = mapped_column(String(8), nullable=False)


class Contract(Base, TenantMixin, TimestampMixin):
    """Contracts and agreements.

    The generator produces a matched comparison pair whose notice periods and
    liability caps differ while payment terms agree, so the blueprint's
    contract-comparison scenario has a real, verifiable answer (spec FR-028a).
    """

    __tablename__ = "contracts"
    __table_args__ = (
        UniqueConstraint("document_id"),
        CheckConstraint("expiry_date > effective_date", name="date_order"),
        CheckConstraint(
            "contract_type IN ('CUSTOMER','SUPPLIER','NDA','EMPLOYMENT_TEMPLATE')",
            name="contract_type_values",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    counterparty_name: Mapped[str] = mapped_column(String(255), nullable=False)
    contract_type: Mapped[str] = mapped_column(String(32), nullable=False)
    effective_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    expiry_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    notice_period_days: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Null means uncapped — a material difference in the comparison pair.
    liability_cap_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    payment_terms: Mapped[str] = mapped_column(String(32), nullable=False)
    governing_law: Mapped[str] = mapped_column(String(64), nullable=False)


class PolicyDocument(Base, TenantMixin, TimestampMixin):
    """Internal governing documents.

    ``stated_values`` holds the machine-readable form of what the prose asserts,
    e.g. ``{"annual_leave_days": {"EG": 21, "AE": 22}}``. That is what makes the
    coherence check in FR-035 mechanical: the test compares this against
    ``leave_balances`` instead of parsing English.
    """

    __tablename__ = "policy_documents"
    __table_args__ = (
        UniqueConstraint("company_id", "policy_type"),
        CheckConstraint(
            "policy_type IN ('HANDBOOK','LEAVE','REMOTE_WORK','EXPENSE','SECURITY',"
            "'CODE_OF_CONDUCT','TRAVEL','BENEFITS')",
            name="policy_type_values",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    policy_type: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[str] = mapped_column(String(16), nullable=False)
    effective_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    stated_values: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
