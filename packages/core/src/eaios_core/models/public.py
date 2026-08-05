"""Public-facing content (data-model.md §6).

Everything here is classification PUBLIC and is the only content an unauthenticated
visitor may ever see. ``tests/security/test_public_content.py`` scans every row for
salary figures, contract terms, internal financial values, and non-executive contact
details (spec SC-011).
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantMixin, TimestampMixin, uuid_pk

__all__ = ["LeadershipProfile", "NewsItem", "PublicProduct", "Service", "Vacancy"]


class Service(Base, TenantMixin, TimestampMixin):
    __tablename__ = "services"
    __table_args__ = (UniqueConstraint("company_id", "name"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    summary: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)


class PublicProduct(Base, TenantMixin, TimestampMixin):
    """Marketing content. Deliberately separate from the sellable ``products``
    catalog — the spec's glossary treats these as different entities."""

    __tablename__ = "public_products"
    __table_args__ = (UniqueConstraint("company_id", "name"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    tagline: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)


class LeadershipProfile(Base, TenantMixin, TimestampMixin):
    """Public profile of a real generated executive.

    Only public-appropriate fields: no salary, no personal contact details. The
    linked user must belong to Executive Management of the same company.
    """

    __tablename__ = "leadership_profiles"
    __table_args__ = (UniqueConstraint("user_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    public_title: Mapped[str] = mapped_column(String(128), nullable=False)
    bio: Mapped[str] = mapped_column(Text, nullable=False)
    photo_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)


class NewsItem(Base, TenantMixin, TimestampMixin):
    __tablename__ = "news_items"
    __table_args__ = (UniqueConstraint("company_id", "headline"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    headline: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    published_on: Mapped[dt.date] = mapped_column(Date, nullable=False)


class Vacancy(Base, TenantMixin, TimestampMixin):
    __tablename__ = "vacancies"
    __table_args__ = (UniqueConstraint("company_id", "title", "office_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    department_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False
    )
    office_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("offices.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    posted_on: Mapped[dt.date] = mapped_column(Date, nullable=False)
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
