"""Per-address bounds on the anonymous write paths (spec 002 FR-024d, FR-047b).

The public surface has two paths that an unauthenticated caller can make write to
the database, and until now neither was bounded:

* the contact form, which stores a row per accepted submission (FR-023); and
* the **refusal audit**, which stores a row per refused request to a non-public
  address (FR-047, Constitution Principle X).

The second is the sharper of the two, and it is worth being clear about why: the
audit requirement *created* it. Recording every denial is right, and it means a loop
against `/admin` grows `audit_logs` without limit — burying the real signal in the
volume it produced. FR-047b bounds the recording without relaxing the refusal.

**Fixed windows, not a sliding log.** A counter with an expiry costs one round trip
and no storage per event. A sliding window would be more precise at the boundary and
would need the per-event record this module exists to avoid keeping.

**The identity is hashed.** A client address is personal data, and FR-024c's
prohibition on writing submitted personal data to logs applies with at least equal
force to an address the visitor never chose to give. Keys carry a digest, never the
address. Be honest about the strength of that: the IPv4 space is small enough to
enumerate, so this is defence against casual disclosure — a key nobody can read at a
glance — not anonymisation.

**`X-Forwarded-For` is deliberately ignored.** Trusting a caller-supplied header lets
anyone bypass the bound by varying it, which is worse than no bound at all because it
looks like protection. This stack terminates connections directly; a deployment that
adds a proxy must configure the proxy's real-address handling and revisit this.

**What happens when Redis is unavailable** differs by path, and the difference is
deliberate:

* the **contact form fails open** — a visitor's genuine enquiry must not be refused
  because a cache is down. Duplicate suppression (FR-022) and the database's own
  constraints still apply, so the failure mode is "the bound is not enforced for the
  duration of the outage", not "anything goes";
* the **refusal audit also fails open**, meaning it writes the individual entry. When
  the counter is unavailable the conservative choice for an audit trail is to record
  more, not less.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from fastapi import Request

from eaios_core.clients.stores import get_redis
from eaios_core.keys import RATE_LIMIT_PREFIX, rate_limit_key
from eaios_core.logging import get_logger

__all__ = [
    "CONTACT_LIMIT",
    "CONTACT_WINDOW_SECONDS",
    "REFUSAL_AUDIT_LIMIT",
    "REFUSAL_AUDIT_WINDOW_SECONDS",
    "Decision",
    "client_identity",
    "consume",
    "mark_coalesced",
]

logger = get_logger(__name__)

#: FR-024d — accepted contact submissions per address per hour.
CONTACT_LIMIT = 5
CONTACT_WINDOW_SECONDS = 3600

#: FR-047b — individually audited refusals per address per hour.
REFUSAL_AUDIT_LIMIT = 60
REFUSAL_AUDIT_WINDOW_SECONDS = 3600

#: Imported rather than restated. `reset_all` clears these keys by pattern, and a
#: second copy of the prefix here is how the writer and the cleaner drift apart.
_PREFIX = RATE_LIMIT_PREFIX


@dataclass(frozen=True)
class Decision:
    """The outcome of one consumption.

    ``count`` is the number of events seen in the current window *including* this
    one, so a caller can report "the bound was reached at N" without a second read.

    There is deliberately no `degraded` flag. One existed briefly, set on the
    fail-open path and read by nobody, with a comment saying callers should log which
    case they were in — a responsibility no caller took, and one already discharged
    here: `consume` logs `ratelimit.unavailable` with the bucket that identifies the
    path. A field kept "for when someone needs it" is indistinguishable from a
    half-finished feature, and this project has twice been misled by exactly that
    (`ErrorState.retry`, passed by no caller; a comment naming three page regions
    where the requirement named four).
    """

    allowed: bool
    count: int
    limit: int


def client_identity(request: Request) -> str:
    """A stable, non-obvious key for the caller's address.

    Falls back to a fixed literal when the address is unavailable — a test client or
    a unix socket — so every caller still shares one bucket rather than bypassing the
    bound by being unidentifiable.
    """
    address = request.client.host if request.client else "unknown"
    return hashlib.sha256(address.encode("utf-8")).hexdigest()[:32]


def consume(bucket: str, identity: str, *, limit: int, window_seconds: int) -> Decision:
    """Count one event against ``bucket`` and say whether it is within the bound."""
    key = rate_limit_key(bucket, identity)
    try:
        client = get_redis()
        pipeline = client.pipeline()
        pipeline.incr(key)
        # Set the expiry every time rather than only on creation. `INCR` on a missing
        # key creates it without a TTL, and a key that lost its expiry would bound
        # that caller forever.
        pipeline.expire(key, window_seconds)
        # redis-py ships no stubs for the pipeline's execute().
        count = int(pipeline.execute()[0])  # type: ignore[no-untyped-call]
    except Exception:  # pragma: no cover - exercised by taking Redis down
        # Never the address, and never at error level: an unreachable cache is an
        # operational event, and the request itself succeeded.
        logger.warning("ratelimit.unavailable", bucket=bucket, limit=limit)
        # Fail open: see the module docstring for why, per path.
        return Decision(allowed=True, count=0, limit=limit)

    return Decision(allowed=count <= limit, count=count, limit=limit)


def mark_coalesced(bucket: str, identity: str, *, window_seconds: int) -> bool:
    """Claim the right to write this window's single coalesced audit entry.

    Returns True exactly once per address per window; every later call in the same
    window returns False. That is what turns "one entry per refusal" into "one entry
    per window" without an update — `audit_logs` is append-only by database trigger
    (feature 001), so a running total cannot be revised in place. The precise number
    of suppressed refusals therefore lives in the counter above rather than in the
    row; the row records that the bound was reached and at what count.
    """
    key = rate_limit_key(bucket, f"coalesced:{identity}")
    try:
        client = get_redis()
        claimed = bool(client.set(key, "1", nx=True, ex=window_seconds))
    except Exception:  # pragma: no cover - exercised by taking Redis down
        logger.warning("ratelimit.coalesce_unavailable", bucket=bucket)
        return True
    return claimed
