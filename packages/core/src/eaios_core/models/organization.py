"""Organization entities (data-model.md §2)."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantMixin, TimestampMixin, uuid_pk

__all__ = [
    "Company",
    "Department",
    "Office",
    "Role",
    "RolePermission",
    "User",
    "UserRole",
]


class Company(Base, TimestampMixin):
    """The isolation boundary.

    ``company_id`` is self-referential here so the audit rule ("every tenant-owned
    table has a company_id") stays uniform with no special case for this table.
    """

    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    slug: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
    reporting_currency: Mapped[str] = mapped_column(String(3), nullable=False)


class Office(Base, TenantMixin, TimestampMixin):
    __tablename__ = "offices"
    __table_args__ = (UniqueConstraint("company_id", "code"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    city: Mapped[str] = mapped_column(String(64), nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    is_headquarters: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Department(Base, TenantMixin, TimestampMixin):
    __tablename__ = "departments"
    __table_args__ = (UniqueConstraint("company_id", "name"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    office_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("offices.id", ondelete="RESTRICT"), nullable=False
    )
    # Nullable only to break the circular dependency with users during insertion.
    # A post-load check asserts every department has a head who belongs to it
    # (spec FR-034); the column is never legitimately null in a completed dataset.
    head_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )


class Role(Base, TenantMixin, TimestampMixin):
    """Tenant-scoped. Seven per company; Platform Admin is not among them."""

    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("company_id", "name"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)


class RolePermission(Base, TenantMixin, TimestampMixin):
    """Join to the *global* permission catalog.

    Carries ``company_id`` even though it is derivable from the role, so RLS applies
    directly without a subquery.
    """

    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    role_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("permissions.id", ondelete="RESTRICT"), nullable=False
    )


class User(Base, TenantMixin, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("company_id", "email"),
        UniqueConstraint("company_id", "persona_key"),
        CheckConstraint("employment_type IN ('FULL_TIME','PART_TIME','CONTRACT')", name="employment_type"),
        CheckConstraint("id <> manager_id", name="not_own_manager"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    department_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False
    )
    office_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("offices.id", ondelete="RESTRICT"), nullable=False
    )
    # Null for exactly one user per company: the top-level executive (spec FR-034).
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )

    email: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    employment_type: Mapped[str] = mapped_column(String(16), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Column exists so the auth feature does not need a migration to start using it.
    # Nothing writes it in this feature (decision D1).
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Fixed personas referenced by name in acceptance tests and the demo script
    # (spec FR-025b, FR-025c).
    is_persona: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    persona_key: Mapped[str | None] = mapped_column(String(64), nullable=True)


class UserRole(Base, TenantMixin, TimestampMixin):
    """Exactly one primary role per user, plus Manager where they have reports."""

    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
