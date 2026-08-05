"""The public surface behind the NileTech website (spec 002).

Read-only except for one write path. Every response is a hand-written model from
`schemas.py` — the declared field allowlist — and no endpoint accepts a tenant.

`response_model` is set on every route rather than relying on the return
annotation, so FastAPI filters the payload through the declared model. A dict with
an extra key cannot leak: it is dropped at serialisation and caught by
`tests/security/test_public_field_allowlist.py` before that.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Query, Request, Response, status

from eaios_core.db import create_app_engine
from eaios_core.settings import Settings, get_settings

from . import queries
from .errors import PublicNotFoundError, PublicRateLimitedError
from .rate_limit import (
    CONTACT_LIMIT,
    CONTACT_WINDOW_SECONDS,
    client_identity,
    consume,
)
from .schemas import (
    CompanyOut,
    ContactAccepted,
    ContactIn,
    LeadershipOut,
    NewsDetailOut,
    NewsPage,
    OfficeOut,
    Problem,
    ProductOut,
    ServiceOut,
    VacancyDetailOut,
    VacancyOut,
    ValidationProblem,
)

router = APIRouter(prefix="/public", tags=["public"])

_NOT_FOUND = "No such item."


@router.get("/company", response_model=CompanyOut, summary="Company identity")
def get_company(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    return queries.company(create_app_engine(settings))


@router.get("/offices", response_model=list[OfficeOut], summary="Office locations")
def list_offices(settings: Settings = Depends(get_settings)) -> list[dict[str, object]]:
    return queries.offices(create_app_engine(settings))


@router.get("/services", response_model=list[ServiceOut], summary="Service offerings")
def list_services(settings: Settings = Depends(get_settings)) -> list[dict[str, object]]:
    return queries.services(create_app_engine(settings))


@router.get("/products", response_model=list[ProductOut], summary="Public product offerings")
def list_products(settings: Settings = Depends(get_settings)) -> list[dict[str, object]]:
    return queries.products(create_app_engine(settings))


@router.get("/leadership", response_model=list[LeadershipOut], summary="Leadership profiles")
def list_leadership(settings: Settings = Depends(get_settings)) -> list[dict[str, object]]:
    return queries.leadership(create_app_engine(settings))


@router.get("/news", response_model=NewsPage, summary="News items, newest first")
def list_news(
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    return queries.news_list(create_app_engine(settings), limit=limit, offset=offset)


@router.get(
    "/news/{slug}",
    response_model=NewsDetailOut,
    summary="One news item in full",
    responses={404: {"model": Problem, "description": "No such item for this tenant"}},
)
def get_news_item(
    slug: str, settings: Settings = Depends(get_settings)
) -> dict[str, object]:
    item = queries.news_item(create_app_engine(settings), slug)
    if item is None:
        # A slug belonging to the other tenant lands here too, which is correct: a
        # visitor learns nothing about whether it exists elsewhere.
        raise PublicNotFoundError(_NOT_FOUND)
    return item


@router.get("/vacancies", response_model=list[VacancyOut], summary="Open vacancies")
def list_vacancies(
    office: str | None = Query(default=None, max_length=60),
    department: str | None = Query(default=None, max_length=60),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, object]]:
    return queries.vacancies(
        create_app_engine(settings), office=office, department=department
    )


@router.get(
    "/vacancies/{slug}",
    response_model=VacancyDetailOut,
    summary="One vacancy in full",
    responses={404: {"model": Problem, "description": "No such open vacancy for this tenant"}},
)
def get_vacancy(slug: str, settings: Settings = Depends(get_settings)) -> dict[str, object]:
    item = queries.vacancy(create_app_engine(settings), slug)
    if item is None:
        raise PublicNotFoundError(_NOT_FOUND)
    return item


@router.post(
    "/contact",
    response_model=ContactAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a contact enquiry",
    # Declared so the published schema matches what `public_validation_handler`
    # actually returns. FastAPI's default `HTTPValidationError` was being advertised
    # here, and `packages/contracts` is generated from that — which is why the web
    # client had to hand-write the real shape.
    responses={
        422: {"model": ValidationProblem, "description": "Field-addressed validation errors"},
        429: {"model": Problem, "description": "Submission bound for this address reached"},
    },
)
def submit_contact(
    payload: ContactIn,
    request: Request,
    response: Response,
    settings: Settings = Depends(get_settings),
) -> ContactAccepted:
    """Stores and audits. Delivers nothing — no email, no queue, no notification.

    That is why this does not engage the constitution's human-approval gate:
    storing a message is not an irreversible outward action. If delivery is ever
    added it becomes a send action and the gate applies.

    A duplicate inside the suppression window is reported as success without
    creating a second row. The visitor's intent was satisfied by the first, and
    telling them otherwise would invite them to submit again.

    The bound (FR-024d) is consumed *before* the write and refuses with 429 rather
    than reporting success: a caller past the limit must not be told their message
    was received when no record exists. It is checked before duplicate suppression
    on purpose — a script sending distinct messages is exactly what the bound is
    for, and suppression would not see those as duplicates.
    """
    decision = consume(
        "contact",
        client_identity(request),
        limit=CONTACT_LIMIT,
        window_seconds=CONTACT_WINDOW_SECONDS,
    )
    if not decision.allowed:
        raise PublicRateLimitedError(
            "We have received several messages from you recently. "
            "Please try again later, or write to us directly."
        )

    queries.record_contact(
        create_app_engine(settings),
        sender_name=payload.sender_name.strip(),
        sender_email=str(payload.sender_email).strip(),
        subject=payload.subject.strip(),
        message=payload.message.strip(),
        now=dt.datetime.now(tz=dt.UTC),
    )
    response.status_code = status.HTTP_202_ACCEPTED
    return ContactAccepted()
