"""Response models for the public surface — this file *is* the field allowlist.

Every model is written by hand and forbids extra fields. Nothing here is derived
from an ORM row, and none of these models is shared with a future authenticated
endpoint (spec 002 FR-044, FR-045).

That is deliberate and it is the whole design. The common shape — serialize the
model, exclude what looks sensitive — fails **open**: a column added later appears
in the response until somebody notices. An allowlist fails closed. This matters
more than usual because the same database holds RESTRICTED payroll records,
executive contracts, and a second tenant's data.

`contracts/public-fields.md` is the human-readable statement of the same list, and
`tests/security/test_public_field_allowlist.py` asserts responses match it exactly —
failing on an *extra* key, not only a missing one.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, EmailStr, Field

__all__ = [
    "CompanyOut",
    "ContactAccepted",
    "ContactIn",
    "LeadershipOut",
    "NewsDetailOut",
    "NewsOut",
    "NewsPage",
    "OfficeOut",
    "ProductOut",
    "ServiceOut",
    "VacancyDetailOut",
    "VacancyOut",
]

#: `extra="forbid"` on every model. A field that reaches a response without being
#: declared here is a construction error, not a runtime surprise.
_STRICT = ConfigDict(extra="forbid")


class CompanyOut(BaseModel):
    model_config = _STRICT

    name: str
    domain: str


class OfficeOut(BaseModel):
    model_config = _STRICT

    city: str
    country: str
    address: str
    is_headquarters: bool


class ServiceOut(BaseModel):
    model_config = _STRICT

    name: str
    summary: str
    description: str
    display_order: int


class ProductOut(BaseModel):
    """The *public* catalog. The internal sellable `products` table is a different
    table, and no public route reads it."""

    model_config = _STRICT

    name: str
    tagline: str
    description: str
    display_order: int


class LeadershipOut(BaseModel):
    """The one model that draws from `users`, and it takes a single column.

    `user_id` is deliberately absent. It identifies a real employee row carrying
    salary band, hire date, country, and manager — handing it to an anonymous
    visitor would be a key into the private data model even though the key alone
    returns nothing today.
    """

    model_config = _STRICT

    full_name: str
    public_title: str
    bio: str
    display_order: int


class NewsOut(BaseModel):
    """List shape — no body. A list shipping full article bodies would be both a
    performance problem and a larger disclosure surface than the contract states."""

    model_config = _STRICT

    slug: str
    headline: str
    published_on: dt.date


class NewsDetailOut(NewsOut):
    model_config = _STRICT

    body: str


class NewsPage(BaseModel):
    model_config = _STRICT

    items: list[NewsOut]
    #: Total available, so the interface can offer the remainder (FR-016).
    total: int = Field(ge=0)


class VacancyOut(BaseModel):
    """`is_open` is absent by design: closed vacancies are filtered out server-side
    (FR-014), so there is no state for a client to misread."""

    model_config = _STRICT

    slug: str
    title: str
    department: str
    office_city: str
    office_country: str
    posted_on: dt.date


class VacancyDetailOut(VacancyOut):
    model_config = _STRICT

    description: str


class ContactIn(BaseModel):
    """Bounds mirror FR-019 exactly.

    Validated here *and* by database check constraints. FR-020 makes the server the
    control rather than the browser, and the database constraint is the last one
    standing if a future caller ever bypasses this layer.
    """

    model_config = _STRICT

    sender_name: str = Field(min_length=1, max_length=120)
    sender_email: EmailStr = Field(max_length=254)
    subject: str = Field(min_length=1, max_length=150)
    message: str = Field(min_length=1, max_length=4000)


class ContactAccepted(BaseModel):
    """No identifier of the stored row and no echo of the content — an anonymous
    writer gets confirmation, not a handle (FR-023b)."""

    model_config = _STRICT

    status: str = "accepted"


class FieldError(BaseModel):
    """One field-addressed message, so the form can attach it to its control."""

    model_config = _STRICT

    field: str
    message: str


class ValidationProblem(BaseModel):
    """The 422 body, declared rather than assembled from a dict literal.

    The API already returned exactly this shape — `public_validation_handler` builds
    it — but the shape existed only as a dict literal in that handler and as a
    schema in `contracts/public-api.yaml`. FastAPI therefore published
    `HTTPValidationError` (its default `{detail: [...]}`) as the declared 422 for
    every public route: a schema describing a response this API never sends.

    That mattered because `packages/contracts` is generated from that published
    schema, so `apps/web/lib/api.ts` had to hand-write the real shape from a comment
    rather than import a generated type. The constitution's Mandatory Contracts
    section requires typed request *and response* models with matching types on the
    frontend; this is the response half.
    """

    model_config = _STRICT

    title: str
    status: int
    errors: list[FieldError]


class Problem(BaseModel):
    """The 404 body.

    Unlike the 422, this one is a genuine behaviour change rather than a
    declaration catching up: the routes raised `HTTPException`, so the body was
    FastAPI's `{"detail": "No such item."}` — which does not match the `Problem`
    schema `contracts/public-api.yaml` has always declared. The contract is the
    better shape (it carries the status a client can branch on without re-reading
    the response object), nothing consumed the old body, and having two different
    error envelopes on one public surface was the accident.
    """

    model_config = _STRICT

    title: str
    status: int
    detail: str | None = None
