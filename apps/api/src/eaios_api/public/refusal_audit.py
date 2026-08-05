"""Record anonymous requests that were refused (spec 002 FR-047, Constitution X).

Principle X requires an audit record for authorization allows **and denies**, and
FR-047 says the same in words: "each refusal MUST write an audit entry recording
what was attempted". Neither happened. The refusal itself worked — a request to
`/internal/documents` returned 404 — but it came from FastAPI's default router
with nothing in the path to record it, so `audit_logs` was unchanged before and
after. `tests/security/test_anonymous_refusal.py` asserted status codes only, and
passed throughout.

**What is and is not audited.** FR-047a classifies the endpoint surface into three
sets, and only one of them produces a refusal worth recording:

* **public** (`/public/*`) — served. A 404 here means *no such record*, which is
  ordinary browsing: a mistyped slug, a stale bookmark, a crawler following an old
  link. Auditing those would bury the real signal in noise.
* **operational** (health, dataset manifest) — anonymous by design, never refused.
* **non-public** — everything else. Refused, and recorded here.

**What the entry contains.** The attempted method and path, and nothing else. Not
the request body, not headers, not query values — FR-024c forbids propagating
submitted personal data, and a probe's body is exactly the kind of thing that
should not be copied into a table someone later reads.

**The bound this created, and how it is closed.** This is an unauthenticated write
path: anonymous traffic causes rows, so a loop against `/admin` grew `audit_logs`
without limit — the audit requirement produced its own denial-of-service surface, and
burying the real signal in that volume defeats what the trail is for. FR-047b now
bounds it at 60 individually-audited refusals per address per hour. Past that, every
request is **still refused** — the bound governs recording, never enforcement — and
one coalesced entry per window records that the threshold was reached.

The count in that coalesced entry is the count at the moment of coalescing, not a
running total, because `audit_logs` is append-only by database trigger and a total
cannot be revised in place. The precise ongoing count lives in the rate-limit
counter; the row records that the bound was crossed and at what point.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from eaios_core.db import create_app_engine, session_scope, tenant_scope
from eaios_core.logging import get_logger
from eaios_core.models import AuditLog
from eaios_core.settings import get_settings

from .queries import PUBLIC_COMPANY_ID
from .rate_limit import (
    REFUSAL_AUDIT_LIMIT,
    REFUSAL_AUDIT_WINDOW_SECONDS,
    client_identity,
    consume,
    mark_coalesced,
)

__all__ = ["REFUSAL_STATUSES", "audit_refusals", "is_auditable_refusal"]

#: Statuses that mean "you may not have this", as opposed to a server fault.
REFUSAL_STATUSES = frozenset({401, 403, 404, 405})

#: Prefixes that are served rather than refused (FR-047a).
_SERVED_PREFIXES = ("/public/", "/health/", "/dataset/", "/docs", "/redoc", "/openapi.json")


def is_auditable_refusal(path: str, status: int) -> bool:
    """True when this response refused access to something non-public."""
    if status not in REFUSAL_STATUSES:
        return False
    return not any(path.startswith(prefix) for prefix in _SERVED_PREFIXES)


async def audit_refusals(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Middleware: record refusals of non-public endpoints.

    Failing to write the audit entry must not change what the caller receives. The
    refusal already happened, and turning an audit outage into a 500 would convert
    a logging problem into a service problem — so the write is best-effort and its
    failure is logged rather than raised.
    """
    response = await call_next(request)

    if not is_auditable_refusal(request.url.path, response.status_code):
        return response

    # FR-047b. The refusal above has already happened and is returned either way —
    # what this decides is whether the entry is written individually.
    identity = client_identity(request)
    decision = consume(
        "refusal-audit",
        identity,
        limit=REFUSAL_AUDIT_LIMIT,
        window_seconds=REFUSAL_AUDIT_WINDOW_SECONDS,
    )
    coalesced = False
    if not decision.allowed:
        if not mark_coalesced(
            "refusal-audit", identity, window_seconds=REFUSAL_AUDIT_WINDOW_SECONDS
        ):
            # This window's single entry is already written. The refusal stands.
            return response
        coalesced = True

    try:
        engine = create_app_engine(get_settings())
        with (
            session_scope(engine) as session,
            tenant_scope(session, PUBLIC_COMPANY_ID),
        ):
            session.add(
                AuditLog(
                    id=uuid.uuid4(),
                    company_id=PUBLIC_COMPANY_ID,
                    actor_user_id=None,
                    actor_type="SYSTEM",
                    action="public.refused",
                    resource_type="endpoint",
                    # Method and path only. Bounded so a long probe path cannot
                    # overflow the column.
                    resource_id=(
                        "COALESCED (multiple paths)"
                        if coalesced
                        else f"{request.method} {request.url.path}"[:128]
                    ),
                    decision="DENY",
                    reason=(
                        f"refusal audit bound reached at {decision.count} refusals in the"
                        f" window; further refusals from this caller are refused but not"
                        f" individually recorded (FR-047b)"
                        if coalesced
                        else f"anonymous request refused with {response.status_code}"
                    ),
                    sources=[],
                    created_at=_now(),
                )
            )
            # Flushed inside the tenant scope: `tenant_scope` clears
            # `app.company_id` on exit and `session_scope` commits after that, so a
            # deferred INSERT would be evaluated against an unset tenant and
            # refused by RLS.
            session.flush()
    except Exception:  # pragma: no cover - audit must not break the response
        get_logger(__name__).warning(
            "audit.refusal_write_failed", path=request.url.path, status=response.status_code
        )

    return response


def _now() -> dt.datetime:
    """Wall clock. A refusal is a runtime event, not part of the pinned dataset."""
    return dt.datetime.now(tz=dt.UTC)
