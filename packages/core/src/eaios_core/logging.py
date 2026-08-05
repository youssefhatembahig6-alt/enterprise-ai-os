"""Structured logging (Constitution Principle X, plan research R9).

JSON, one line per event, so ``docker compose logs`` stays greppable.

``company_id`` is bound into the log context deliberately from the start. There is
no authenticated principal yet (decision D1), so nothing sets it — but wiring the
binding point now means the audit and observability story does not need retrofitting
once the tenant becomes known per request.

Care is required in the other direction too: log output is an isolation surface. A
message carrying one tenant's content into a shared log is a leak even if no query
ever crossed the boundary. ``tests/security/test_log_safety.py`` covers that.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

__all__ = ["bind_company", "bind_request", "clear_context", "configure_logging", "get_logger"]


def configure_logging(*, level: str = "info", json_output: bool = True) -> None:
    """Configure structlog and the stdlib root logger to agree."""
    # NOTE: `structlog.stdlib.add_logger_name` is deliberately absent. It reads
    # `logger.name`, which only exists on a stdlib logger — pairing it with
    # PrintLoggerFactory below raises AttributeError on the first log call and
    # takes the whole service down at startup. The logger name is bound in
    # get_logger() instead, which works with any factory.
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    processors.append(
        structlog.processors.JSONRenderer() if json_output else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(
        format="%(message)s", stream=sys.stderr, level=getattr(logging, level.upper(), logging.INFO)
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound logger, with the module name carried as an event field.

    Binding the name rather than deriving it from the underlying logger keeps this
    working regardless of which logger factory is configured.
    """
    logger = structlog.get_logger()
    if name:
        logger = logger.bind(logger=name)
    return logger  # type: ignore[no-any-return]


def bind_request(request_id: str) -> None:
    structlog.contextvars.bind_contextvars(request_id=request_id)


def bind_company(company_id: str) -> None:
    """Bind the active tenant to the log context.

    Unused until authentication exists (decision D1). The binding point is defined
    now so every later log line is tenant-attributed by construction rather than by
    each call site remembering.
    """
    structlog.contextvars.bind_contextvars(company_id=company_id)


def clear_context() -> None:
    structlog.contextvars.clear_contextvars()
