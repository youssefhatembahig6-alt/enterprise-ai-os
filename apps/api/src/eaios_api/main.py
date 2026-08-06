"""FastAPI application factory."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError

from eaios_core.logging import bind_request, clear_context, configure_logging, get_logger
from eaios_core.settings import get_settings

from .auth.router import router as auth_router
from .errors import (
    AccessDeniedError,
    NotAuthenticatedError,
    ResourceAbsentError,
    access_denied_handler,
    not_authenticated_handler,
    resource_absent_handler,
)
from .health.manifest_router import router as manifest_router
from .health.router import router as health_router
from .hr.router import router as hr_router
from .me.router import router as me_router
from .public.errors import (
    PublicNotFoundError,
    PublicRateLimitedError,
    public_not_found_handler,
    public_rate_limited_handler,
    public_validation_handler,
)
from .public.refusal_audit import audit_refusals
from .public.router import router as public_router

__all__ = ["app", "create_app"]


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(level=settings.log_level, json_output=settings.log_json)
    get_logger(__name__).info(
        "api.startup", service=settings.service_name, environment=settings.environment
    )
    yield
    get_logger(__name__).info("api.shutdown")


def create_app() -> FastAPI:
    settings = get_settings()

    application = FastAPI(
        title="Enterprise AI OS — Foundation API",
        version=settings.version,
        description=(
            "Health, readiness, and dataset provenance. No authentication and no "
            "tenant-owned business data are exposed in this feature (decision D1)."
        ),
        lifespan=lifespan,
    )

    @application.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        bind_request(request_id)
        try:
            response = await call_next(request)
        finally:
            # Cleared per request so a pooled context cannot carry one request's
            # identifiers — later, one tenant's identifiers — into the next.
            clear_context()
        response.headers["x-request-id"] = request_id
        return response

    # Registered before the routers so it wraps every response, including the
    # 404s FastAPI's default router produces for paths no route matches — which is
    # exactly where an anonymous probe lands (FR-047, Constitution X).
    application.middleware("http")(audit_refusals)

    application.include_router(health_router)
    application.include_router(manifest_router)
    application.include_router(public_router)
    application.include_router(auth_router)
    application.include_router(me_router)
    application.include_router(hr_router)

    # Public-form validation failures are rewritten into the shape
    # contracts/public-api.yaml declares, with messages a visitor can act on
    # (FR-021). Other paths keep FastAPI's default body.
    application.add_exception_handler(RequestValidationError, public_validation_handler)  # type: ignore[arg-type]
    # Public 404s carry the contracted `Problem` envelope. Registered for a dedicated
    # exception rather than for `HTTPException`, so feature 001's health and manifest
    # error bodies keep the shape their own contracts declare.
    application.add_exception_handler(PublicNotFoundError, public_not_found_handler)
    # FR-024d — the contact form's per-address bound.
    application.add_exception_handler(PublicRateLimitedError, public_rate_limited_handler)

    # Feature 003. Three statuses, and the difference between them is the feature:
    # 401 for no usable identity, 403 for a verified identity refused by authorization,
    # 404 for a resource in another tenant — which is *absent* rather than denied,
    # because the tenant boundary is layer 1 and is applied before authorization
    # (FR-019, FR-020, FR-021, FR-030).
    application.add_exception_handler(NotAuthenticatedError, not_authenticated_handler)
    application.add_exception_handler(AccessDeniedError, access_denied_handler)
    application.add_exception_handler(ResourceAbsentError, resource_absent_handler)
    return application


app = create_app()
