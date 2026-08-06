"""Bounding repeated sign-in attempts (spec 003 FR-007a, SC-013).

**Two dimensions, because either alone is defeated.** An address-only bound is beaten
by spreading attempts across addresses, which is the ordinary shape of credential
stuffing. An account-only bound lets an attacker lock a real user out on purpose by
failing deliberately against their address. The specification's clarification chose both
knowing the second is a bounded denial of service against one account; fifteen minutes
keeps it bounded, and the audit entry makes it visible rather than mysterious.

**The refusal is indistinguishable from a wrong password.** Same status, same body, no
`Retry-After`, no remaining-attempt count. Each of those would tell an attacker the
address is real and that they found it — an enumeration signal FR-022 forbids, arriving
through a channel that is easy to leave open after closing the body.

Counters reuse feature 002's machinery and its key prefix, so `reset_all` clears them
with the sweep it already runs. The identities are digests, never the address or the
email: the reasoning is the one already written in `public/rate_limit.py`, and it
applies with more force here because an email is a person's name.

**Fails CLOSED when Redis is unavailable**, and the reasoning changed.

The first version failed open, on the argument that refusing every sign-in because a
cache is down turns a cache outage into a total outage. That is a real cost and it is
not the point. FR-007a says failed sign-in attempts **MUST** be bounded. An
implementation that silently removes the bound whenever a dependency is unreachable
does not satisfy a MUST — it satisfies it on the days nothing is wrong, which is
exactly when it is not needed. Calling the gap a "residual risk" was a way of writing
down that the requirement was unmet without treating it as unmet.

So an unavailable limiter now refuses sign-in with a generic 503. The trade is
deliberate: a cache outage becomes a sign-in outage, loudly, rather than a silent
window of unbounded credential guessing that nothing would ever report. A limiter whose
failure mode is "no limit" is not a limit.

It leaks nothing. The refusal happens **before** any account lookup, so it is identical
for every caller — an unknown address, a real one, and a locked one all get the same
503, and no comparison between them says whether an account exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from fastapi import Request

from eaios_core.clients.stores import get_redis
from eaios_core.keys import (
    LOGIN_ACCOUNT_BUCKET,
    LOGIN_ADDRESS_BUCKET,
    login_identity,
    rate_limit_key,
)
from eaios_core.logging import get_logger
from eaios_core.settings import Settings, get_settings

from ..public.rate_limit import client_identity

__all__ = [
    "BoundState",
    "LimiterUnavailableError",
    "clear_account",
    "current_state",
    "record_failure",
]

logger = get_logger(__name__)


class LimiterUnavailableError(Exception):
    """The attempt counters cannot be reached, so the bound cannot be enforced.

    Raised rather than swallowed. FR-007a's "MUST be bounded" has no exception for a
    dependency being down, and a function that returned "zero failures so far" when it
    could not tell would be reporting a fact it does not have.
    """


@dataclass(frozen=True, slots=True)
class BoundState:
    """Which bounds, if any, are currently reached."""

    account_reached: bool
    address_reached: bool
    account_failures: int
    address_failures: int

    @property
    def blocked(self) -> bool:
        return self.account_reached or self.address_reached

    @property
    def which(self) -> str:
        """For the audit entry only. Never for a response — naming the bound tells the
        caller which one they hit, and the account bound firing means the address is
        real."""
        if self.account_reached and self.address_reached:
            return "account and address"
        if self.account_reached:
            return "account"
        return "address"


def _keys(email: str, request: Request) -> tuple[str, str]:
    return (
        rate_limit_key(LOGIN_ACCOUNT_BUCKET, login_identity(email)),
        rate_limit_key(LOGIN_ADDRESS_BUCKET, client_identity(request)),
    )


def _state(account: int, address: int, cfg: Settings) -> BoundState:
    return BoundState(
        account_reached=account >= cfg.auth.login_account_max_failures,
        address_reached=address >= cfg.auth.login_address_max_failures,
        account_failures=account,
        address_failures=address,
    )


def current_state(
    email: str, request: Request, settings: Settings | None = None
) -> BoundState:
    """Read both counters without changing them.

    Read rather than incremented, so a caller who is already blocked does not push
    their own counter further out on every attempt — which would turn a fifteen-minute
    lockout into a permanent one for anyone who keeps a tab open retrying.
    """
    cfg = settings or get_settings()
    account_key, address_key = _keys(email, request)
    try:
        client = get_redis()
        # redis-py types the sync and async clients through one signature, so `mget`
        # is declared as returning an awaitable. This client is the synchronous one.
        counters = cast("list[Any]", client.mget([account_key, address_key]))
        account, address = counters[0], counters[1]
    except Exception as exc:  # pragma: no cover - exercised by taking Redis down
        logger.warning("login_bounds.unavailable", operation="read")
        raise LimiterUnavailableError("attempt counters unreachable") from exc
    return _state(int(account or 0), int(address or 0), cfg)


def record_failure(
    email: str, request: Request, settings: Settings | None = None
) -> tuple[BoundState, bool]:
    """Count one failure against both bounds.

    Returns the new state and whether this failure is the one that **reached** a bound.
    Auditing the transition rather than every subsequent attempt is what keeps a lockout
    from writing an entry per retry — the mistake feature 002 had to correct after the
    fact for anonymous refusals.
    """
    cfg = settings or get_settings()
    account_key, address_key = _keys(email, request)
    window = cfg.auth.login_bound_window_seconds

    try:
        client = get_redis()
        pipeline = client.pipeline()
        pipeline.incr(account_key)
        # Expiry set every time. `INCR` on a missing key creates it without a TTL, and
        # a counter that lost its expiry would bound that account forever.
        pipeline.expire(account_key, window)
        pipeline.incr(address_key)
        pipeline.expire(address_key, window)
        # redis-py ships no stubs for the pipeline's execute(); the same cast is made
        # in `public/rate_limit.py` for the same reason.
        results = cast("list[Any]", pipeline.execute())  # type: ignore[no-untyped-call]
        account, address = int(results[0]), int(results[2])
    except Exception as exc:  # pragma: no cover - exercised by taking Redis down
        # A failure that cannot be counted is a failure that does not count towards the
        # bound. Raising means the caller refuses rather than quietly letting this
        # attempt — and every attempt while the outage lasts — be free.
        logger.warning("login_bounds.unavailable", operation="record")
        raise LimiterUnavailableError("attempt counters unreachable") from exc

    state = _state(account, address, cfg)
    just_reached = (
        account == cfg.auth.login_account_max_failures
        or address == cfg.auth.login_address_max_failures
    )
    return state, just_reached


def clear_account(email: str) -> None:
    """Reset the account counter after a successful sign-in (FR-007a).

    Required explicitly by the specification, and it matters in practice: without it a
    user who mistypes four times and then succeeds is one mistake away from a lockout
    for the rest of the window.

    The **address** counter is deliberately not cleared. One success from an address
    that has just failed nineteen times against nineteen different accounts is what
    credential stuffing looks like when it works, and clearing on success would hand
    the attacker a fresh budget for finding the next one.
    """
    try:
        get_redis().delete(rate_limit_key(LOGIN_ACCOUNT_BUCKET, login_identity(email)))
    except Exception:  # pragma: no cover - exercised by taking Redis down
        logger.warning("login_bounds.unavailable", operation="clear")
