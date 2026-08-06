"""Refusal responses for the authenticated surface (spec 003 FR-019–FR-022).

Three statuses, and the difference between them is the feature:

* **401** — missing, malformed, expired, or otherwise invalid identity (FR-019).
* **403** — a verified identity, refused by authorization layers 2 through 5 (FR-020).
* **404** — the resource belongs to another tenant (FR-021). Layer 1 is the tenant
  boundary, applied *before* authorization, so the resource is absent rather than
  denied. The body is byte-identical to the one for an identifier belonging to nobody,
  which is the entire point: a 403 here would confirm the record exists.

Every body is the `Problem` envelope feature 002 introduced, so the authenticated
surface and the public one refuse in the same shape rather than growing a second
vocabulary.

**Nothing internal reaches a body** (FR-022): no stack trace, no query text, no internal
identifier, no reason code, no indication of what would have been permitted. The
sentences below are the complete vocabulary of refusal, written for a person. The
reason lives in the audit entry, where an auditor can read it and a caller cannot.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from .public.schemas import Problem

__all__ = [
    "AccessDeniedError",
    "NotAuthenticatedError",
    "ResourceAbsentError",
    "SecurityControlUnavailableError",
    "access_denied_handler",
    "not_authenticated_handler",
    "resource_absent_handler",
    "security_control_unavailable_handler",
]


class NotAuthenticatedError(Exception):
    """No usable identity. Answered 401.

    Carries no detail by design. Callers raise it for a missing header, a forged
    signature, an expired token, a signed-out session, and a deactivated user alike —
    and if the exception could distinguish them, a response eventually would.
    """


class AccessDeniedError(Exception):
    """A verified identity, refused by authorization. Answered 403."""


class ResourceAbsentError(Exception):
    """Not found *for this caller*. Answered 404.

    Raised for a resource in another tenant and for an identifier that exists nowhere.
    That the two are indistinguishable is the requirement, not a simplification.
    """


class SecurityControlUnavailableError(Exception):
    """A control that MUST hold cannot be evaluated. Answered 503.

    Distinct from a 500: nothing is broken, a dependency is unreachable, and the
    correct response is to refuse rather than to proceed without the control. FR-007a
    says sign-in attempts must be bounded, and an implementation that dropped the bound
    whenever Redis blinked would satisfy that requirement only while it was not needed.

    Raised before any account is looked up, so the response is identical for every
    caller and reveals nothing about which accounts exist.
    """


def _problem(status: int, title: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content=Problem(title=title, status=status, detail=detail).model_dump(),
    )


async def not_authenticated_handler(request: Request, exc: Exception) -> JSONResponse:
    del request, exc
    return _problem(
        401,
        "Not signed in",
        "This request needs a valid session. Please sign in and try again.",
    )


async def access_denied_handler(request: Request, exc: Exception) -> JSONResponse:
    del request, exc
    return _problem(
        403,
        "Not permitted",
        "You do not have access to this record.",
    )


async def resource_absent_handler(request: Request, exc: Exception) -> JSONResponse:
    del request, exc
    return _problem(
        404,
        "Not found",
        "No such record.",
    )


async def security_control_unavailable_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    del request, exc
    # Says a service is unavailable and nothing about which one or why. "Try shortly"
    # is true and actionable; naming the limiter would tell a caller precisely which
    # protection is currently absent.
    return _problem(
        503,
        "Temporarily unavailable",
        "Sign-in is unavailable at the moment. Please try again shortly.",
    )
