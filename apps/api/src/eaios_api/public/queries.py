"""Reads for the public surface, with the tenant fixed in code (spec 002 FR-009a).

The tenant is a module constant, not a parameter. No function here accepts a
company, so there is no argument a request could reach — a caller cannot select a
tenant by hostname, path, parameter, header, or body, because nothing downstream
would know what to do with one. `tests/security/test_public_site_isolation.py`
asserts that eight different attempts change nothing at all.

Every query also runs inside `tenant_scope`, which sets the session tenant that
Row-Level Security predicates on. Application-level filtering is the control; RLS
is the backstop that fails closed if a filter is ever forgotten.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from eaios_core.constants import NILETECH
from eaios_core.db import session_scope, tenant_scope
from eaios_core.ids import derive
from eaios_core.logging import get_logger
from eaios_core.models import (
    AuditLog,
    Company,
    ContactSubmission,
    Department,
    LeadershipProfile,
    NewsItem,
    Office,
    PublicProduct,
    Service,
    User,
    Vacancy,
)

from .slugs import derive_slug

__all__ = [
    "PUBLIC_COMPANY_ID",
    "PUBLIC_TENANT",
    "ContactResult",
    "company",
    "leadership",
    "news_item",
    "news_list",
    "offices",
    "products",
    "record_contact",
    "services",
    "vacancies",
    "vacancy",
]

#: The one tenant this surface serves. A constant rather than configuration:
#: configuration can be changed by whoever controls the environment, and this
#: boundary should require a code change and a review.
PUBLIC_TENANT = NILETECH

#: Derived, not queried. Feature 001 builds every identifier deterministically from
#: a natural key, so the company's id is knowable without touching the database.
#:
#: That is not a micro-optimisation. Looking it up would need a query against
#: `companies`, which is itself under RLS — and RLS needs the tenant already set, so
#: the lookup cannot run before the scope it exists to establish. Deriving the value
#: removes the circularity and makes the tenant a compile-time constant rather than
#: something read from data a request might influence (FR-009a).
PUBLIC_COMPANY_ID = derive("company", PUBLIC_TENANT, PUBLIC_TENANT)

#: FR-022 — an identical submission inside this window is one intent, not two.
DEDUPE_WINDOW = dt.timedelta(minutes=10)


@dataclass(frozen=True, slots=True)
class ContactResult:
    """Whether a row was written. Both outcomes are reported to the visitor as
    success: their intent was satisfied either way (FR-022)."""

    stored: bool
    duplicate: bool


def _scoped(engine: Engine):  # type: ignore[no-untyped-def]
    """Session bound to the fixed tenant, for use as a context manager."""
    from contextlib import contextmanager

    @contextmanager
    def _inner():  # type: ignore[no-untyped-def]
        # Nesting order matters and is not interchangeable: `tenant_scope` clears
        # `app.company_id` when it exits, and `session_scope` commits when *it*
        # exits. Writes must therefore flush before leaving the inner scope — see
        # the note in `record_contact`.
        with (
            session_scope(engine) as session,
            tenant_scope(session, PUBLIC_COMPANY_ID) as scoped,
        ):
            yield scoped, PUBLIC_COMPANY_ID

    return _inner()


def company(engine: Engine) -> dict[str, Any]:
    with _scoped(engine) as (session, company_id):
        row = session.execute(
            select(Company.name, Company.domain).where(Company.id == company_id)
        ).one()
    return {"name": row.name, "domain": row.domain}


def offices(engine: Engine) -> list[dict[str, Any]]:
    with _scoped(engine) as (session, company_id):
        rows = session.execute(
            select(Office.city, Office.country, Office.address, Office.is_headquarters)
            .where(Office.company_id == company_id)
            .order_by(Office.is_headquarters.desc(), Office.city)
        ).all()
    return [
        {
            "city": r.city,
            "country": r.country,
            "address": r.address,
            "is_headquarters": r.is_headquarters,
        }
        for r in rows
    ]


def services(engine: Engine) -> list[dict[str, Any]]:
    with _scoped(engine) as (session, company_id):
        rows = session.execute(
            select(Service.name, Service.summary, Service.description, Service.display_order)
            .where(Service.company_id == company_id)
            .order_by(Service.display_order, Service.name)
        ).all()
    return [
        {
            "name": r.name,
            "summary": r.summary,
            "description": r.description,
            "display_order": r.display_order,
        }
        for r in rows
    ]


def products(engine: Engine) -> list[dict[str, Any]]:
    with _scoped(engine) as (session, company_id):
        rows = session.execute(
            select(
                PublicProduct.name,
                PublicProduct.tagline,
                PublicProduct.description,
                PublicProduct.display_order,
            )
            .where(PublicProduct.company_id == company_id)
            .order_by(PublicProduct.display_order, PublicProduct.name)
        ).all()
    return [
        {
            "name": r.name,
            "tagline": r.tagline,
            "description": r.description,
            "display_order": r.display_order,
        }
        for r in rows
    ]


def leadership(engine: Engine) -> list[dict[str, Any]]:
    """Joins to `users` for one column — the person's display name — and nothing
    else. See `LeadershipOut` for why `user_id` never leaves.

    **FR-013a — an unresolvable profile is omitted, and the omission is recorded.**
    The inner join below already drops a profile whose user row is missing, so the
    omission half held by construction rather than by decision; nothing noticed. A
    profile silently vanishing from a public page was indistinguishable from one the
    generator never produced, and feature 001's coherence checks would have been the
    only thing to catch it — long after the page had been served incomplete.

    Omission is the right behaviour, not merely the convenient one: rendering the
    profile with a placeholder where a real name belongs would present fabricated
    text as company record content, which FR-006 forbids.

    What is recorded is the *count* and the profile's display order. Never the
    person, and never `user_id` — FR-013 forbids exposing any other attribute of that
    individual, and an identifier written into a diagnostic record is still an
    exposure.
    """
    with _scoped(engine) as (session, company_id):
        rows = session.execute(
            select(
                User.full_name,
                LeadershipProfile.public_title,
                LeadershipProfile.bio,
                LeadershipProfile.display_order,
            )
            .join(User, User.id == LeadershipProfile.user_id)
            .where(LeadershipProfile.company_id == company_id)
            .order_by(LeadershipProfile.display_order, User.full_name)
        ).all()

        # Counted inside the same scope so both reads see one tenant and one
        # snapshot. A profile counted here but missing above is one the join dropped.
        declared = session.execute(
            select(func.count())
            .select_from(LeadershipProfile)
            .where(LeadershipProfile.company_id == company_id)
        ).scalar_one()

        unresolved = int(declared) - len(rows)
        if unresolved > 0:
            orders = session.execute(
                select(LeadershipProfile.display_order)
                .outerjoin(User, User.id == LeadershipProfile.user_id)
                .where(LeadershipProfile.company_id == company_id, User.id.is_(None))
                .order_by(LeadershipProfile.display_order)
            ).scalars().all()
            _record_unresolved_profiles(session, company_id, unresolved, list(orders))
    return [
        {
            "full_name": r.full_name,
            "public_title": r.public_title,
            "bio": r.bio,
            "display_order": r.display_order,
        }
        for r in rows
    ]


def _news_slug(headline: str, published_on: dt.date) -> str:
    # The natural key mirrors how feature 001 identifies the record, so the slug is
    # as stable as its UUID.
    return derive_slug("news", PUBLIC_TENANT, f"{published_on.isoformat()}:{headline}", headline)


def news_list(engine: Engine, *, limit: int = 20, offset: int = 0) -> dict[str, Any]:
    with _scoped(engine) as (session, company_id):
        total = session.execute(
            select(func.count())
            .select_from(NewsItem)
            .where(NewsItem.company_id == company_id)
        ).scalar_one()
        rows = session.execute(
            select(NewsItem.headline, NewsItem.published_on)
            .where(NewsItem.company_id == company_id)
            # Newest first (FR-008). Headline breaks ties so ordering is
            # deterministic rather than database-order dependent.
            .order_by(NewsItem.published_on.desc(), NewsItem.headline)
            .limit(limit)
            .offset(offset)
        ).all()
    return {
        "items": [
            {
                "slug": _news_slug(r.headline, r.published_on),
                "headline": r.headline,
                "published_on": r.published_on,
            }
            for r in rows
        ],
        "total": int(total),
    }


def news_item(engine: Engine, slug: str) -> dict[str, Any] | None:
    """Resolved by recomputing candidate slugs within the fixed tenant, never by
    parsing the suffix. A slug belonging to the other tenant therefore resolves to
    nothing — the same answer as one that never existed, so a visitor learns
    nothing about whether it exists elsewhere."""
    with _scoped(engine) as (session, company_id):
        rows = session.execute(
            select(NewsItem.headline, NewsItem.published_on, NewsItem.body).where(
                NewsItem.company_id == company_id
            )
        ).all()
    for r in rows:
        if _news_slug(r.headline, r.published_on) == slug:
            return {
                "slug": slug,
                "headline": r.headline,
                "published_on": r.published_on,
                "body": r.body,
            }
    return None


def _vacancy_slug(title: str, city: str, posted_on: dt.date) -> str:
    return derive_slug(
        "vacancy",
        PUBLIC_TENANT,
        f"{title}:{city}:{posted_on.isoformat()}",
        f"{title} {city}",
    )


def _vacancy_rows(session: Session, company_id: uuid.UUID) -> list[Any]:
    return list(
        session.execute(
            select(
                Vacancy.title,
                Vacancy.description,
                Vacancy.posted_on,
                Department.name.label("department"),
                Office.city.label("office_city"),
                Office.country.label("office_country"),
            )
            .join(Department, Department.id == Vacancy.department_id)
            .join(Office, Office.id == Vacancy.office_id)
            # Closed vacancies are absent from the response entirely rather than
            # flagged, so there is no state a client could misread (FR-014).
            .where(Vacancy.company_id == company_id, Vacancy.is_open.is_(True))
            .order_by(Vacancy.posted_on.desc(), Vacancy.title)
        ).all()
    )


def _now() -> dt.datetime:
    """Wall clock. This records a runtime observation, not generated content."""
    return dt.datetime.now(tz=dt.UTC)


def _record_unresolved_profiles(
    session: Session, company_id: uuid.UUID, count: int, display_orders: list[int]
) -> None:
    """Write the FR-013a record. Identifies profiles by display order, never by person.

    Logged *and* audited. The log makes it visible to whoever is watching the service
    now; the audit row makes it answerable later, which is what Constitution
    Principle X asks of a consequential operation — and content silently missing from
    a public page is consequential.
    """
    get_logger(__name__).warning(
        "public.leadership.unresolved_profile",
        count=count,
        display_orders=display_orders,
    )
    session.add(
        AuditLog(
            id=uuid.uuid4(),
            company_id=company_id,
            actor_user_id=None,
            actor_type="SYSTEM",
            action="public.content_omitted",
            resource_type="leadership_profiles",
            resource_id=f"display_order in {display_orders}"[:128],
            decision="DENY",
            reason=(
                f"{count} leadership profile(s) omitted from the public response:"
                " the linked employee record could not be resolved (FR-013a)"
            ),
            sources=[],
            created_at=_now(),
        )
    )
    session.flush()


def vacancies(
    engine: Engine, *, office: str | None = None, department: str | None = None
) -> list[dict[str, Any]]:
    with _scoped(engine) as (session, company_id):
        rows = _vacancy_rows(session, company_id)

    out = []
    for r in rows:
        if office and r.office_city.casefold() != office.casefold():
            continue
        if department and r.department.casefold() != department.casefold():
            continue
        out.append(
            {
                "slug": _vacancy_slug(r.title, r.office_city, r.posted_on),
                "title": r.title,
                "department": r.department,
                "office_city": r.office_city,
                "office_country": r.office_country,
                "posted_on": r.posted_on,
            }
        )
    return out


def vacancy(engine: Engine, slug: str) -> dict[str, Any] | None:
    with _scoped(engine) as (session, company_id):
        rows = _vacancy_rows(session, company_id)
    for r in rows:
        if _vacancy_slug(r.title, r.office_city, r.posted_on) == slug:
            return {
                "slug": slug,
                "title": r.title,
                "department": r.department,
                "office_city": r.office_city,
                "office_country": r.office_country,
                "posted_on": r.posted_on,
                "description": r.description,
            }
    return None


def content_hash(sender_name: str, sender_email: str, subject: str, message: str) -> str:
    """Normalised so trivial whitespace differences are still one intent."""
    material = "".join(
        part.strip().casefold() for part in (sender_name, sender_email, subject, message)
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def record_contact(
    engine: Engine,
    *,
    sender_name: str,
    sender_email: str,
    subject: str,
    message: str,
    now: dt.datetime,
) -> ContactResult:
    """Store the submission and write an audit entry. Delivers nothing (FR-023a).

    Duplicate suppression is a query-then-insert inside one transaction rather than
    a unique constraint. Permanent uniqueness would silently reject a genuine later
    enquiry that happened to repeat a short message — "Please call me" is a real
    message someone may send twice, months apart.
    """
    digest = content_hash(sender_name, sender_email, subject, message)

    with _scoped(engine) as (session, company_id):
        recent = session.execute(
            select(func.count())
            .select_from(ContactSubmission)
            .where(
                ContactSubmission.company_id == company_id,
                ContactSubmission.content_hash == digest,
                ContactSubmission.submitted_at >= now - DEDUPE_WINDOW,
            )
        ).scalar_one()

        if recent:
            return ContactResult(stored=False, duplicate=True)

        session.add(
            ContactSubmission(
                id=uuid.uuid4(),
                company_id=company_id,
                sender_name=sender_name,
                sender_email=sender_email,
                subject=subject,
                message=message,
                content_hash=digest,
                submitted_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        # Audit by default (Constitution Principle X). The entry records that a
        # submission arrived and nothing about its content — FR-024c forbids
        # writing the sender's name, address, or message anywhere but the row.
        #
        # Written through the ORM model rather than raw SQL. A hand-written INSERT
        # here omitted the non-nullable `sources` column and failed at runtime;
        # the model carries every required column and its defaults.
        session.add(
            AuditLog(
                id=uuid.uuid4(),
                company_id=company_id,
                actor_user_id=None,
                actor_type="SYSTEM",
                action="contact.submit",
                resource_type="contact_submission",
                resource_id=None,
                decision="ALLOW",
                reason="public contact form submission accepted",
                sources=[],
                created_at=now,
            )
        )

        # Flush *inside* the tenant scope. Without this the INSERTs are deferred to
        # commit, which happens after `tenant_scope` has cleared `app.company_id` —
        # so the RLS policy evaluates against an unset tenant and refuses the write
        # with "new row violates row-level security policy".
        #
        # Reads never hit this because a SELECT executes where it is written. It is
        # a write-only trap, and the failure names RLS rather than the ordering that
        # caused it.
        session.flush()

    return ContactResult(stored=True, duplicate=False)
