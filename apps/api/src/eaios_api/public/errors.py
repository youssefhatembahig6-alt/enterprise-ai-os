"""Validation failures the public site can actually render (spec 002 FR-021).

FastAPI's default 422 body is `detail: [{loc, msg, type, ctx, input}]`, and its
messages are written for developers — "String should have at least 1 character".
Two problems with shipping that from a public form:

* It does not match `contracts/public-api.yaml`, which declares
  `{title, status, errors: [{field, message}]}`. A contract the implementation
  does not honour is worse than no contract.
* FR-021 requires the error to state *what is expected*. A visitor cannot act on
  "String should have at least 1 character", and `input` echoes back what they
  typed — which for this form is personal data (FR-024c).

So the handler below rewrites both the shape and the wording, and drops `input`
entirely.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .schemas import FieldError, Problem, ValidationProblem

__all__ = ["public_validation_handler"]

#: What each field expects, in the words a visitor would use. Keyed by field, then
#: by Pydantic's error type so the message matches the actual failure.
_MESSAGES: dict[str, dict[str, str]] = {
    "sender_name": {
        "missing": "Please tell us your name.",
        "string_too_short": "Please tell us your name.",
        "string_too_long": "Your name is too long — please use 120 characters or fewer.",
    },
    "sender_email": {
        "missing": "Please give us an email address so we can reply.",
        "value_error": "That does not look like an email address. Please check it.",
        "string_too_long": "That email address is too long.",
    },
    "subject": {
        "missing": "Please add a subject.",
        "string_too_short": "Please add a subject.",
        "string_too_long": "Your subject is too long — please use 150 characters or fewer.",
    },
    "message": {
        "missing": "Please write your message.",
        "string_too_short": "Please write your message.",
        "string_too_long": "Your message is too long — please use 4000 characters or fewer.",
    },
}

_FALLBACK = "This value is not valid."


def _field(error: dict[str, Any]) -> str:
    # Annotated rather than inferred: without it the empty-tuple default narrows to
    # `tuple[()]` and the index below is a static error even though it is guarded.
    location: Sequence[Any] = error.get("loc") or ()
    # ("body", "sender_email") -> "sender_email"; anything odd -> "form".
    return str(location[-1]) if len(location) > 1 else "form"


def _message(field: str, error: dict[str, Any]) -> str:
    by_type = _MESSAGES.get(field, {})
    return by_type.get(str(error.get("type", "")), _FALLBACK)


async def public_validation_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Rewrite validation failures on `/public/*` into the contracted shape.

    Requests to any other path keep FastAPI's default body — this is a public-form
    concern, not a global one, and changing the shape everywhere would break the
    health and manifest contracts feature 001 established.
    """
    if not request.url.path.startswith("/public/"):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": exc.errors()},
        )

    errors = []
    seen: set[str] = set()
    for raw in exc.errors():
        field = _field(dict(raw))
        # One message per field. Pydantic can report several failures for the same
        # value, and stacking them under one control reads as shouting.
        if field in seen:
            continue
        seen.add(field)
        errors.append({"field": field, "message": _message(field, dict(raw))})

    # Built through the model rather than as a dict literal, so the body and the
    # published schema cannot drift apart again.
    body = ValidationProblem(
        title="Some details need your attention",
        status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        errors=[FieldError(**error) for error in errors],
    )
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=body.model_dump())


class PublicNotFoundError(Exception):
    """Raised where a public record does not exist for this tenant.

    A dedicated exception rather than `HTTPException` so the handler below can
    render the contracted `Problem` envelope for public routes only, leaving
    feature 001's health and manifest error bodies untouched.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class PublicRateLimitedError(Exception):
    """Raised when a caller has passed FR-024d's submission bound.

    Carries the visitor-facing sentence and nothing else. FR-024d requires the
    refusal to be informative without disclosing the limit's internals — telling a
    script the exact threshold and window is telling it precisely how to stay under
    them.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


async def public_rate_limited_handler(request: Request, exc: Exception) -> JSONResponse:
    detail = getattr(exc, "detail", "Too many requests.")
    body = Problem(
        title="Too many messages",
        status=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=str(detail),
    )
    return JSONResponse(status_code=status.HTTP_429_TOO_MANY_REQUESTS, content=body.model_dump())


async def public_not_found_handler(request: Request, exc: Exception) -> JSONResponse:
    detail = getattr(exc, "detail", "Not found.")
    body = Problem(
        title="Not found",
        status=status.HTTP_404_NOT_FOUND,
        detail=str(detail),
    )
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content=body.model_dump())
