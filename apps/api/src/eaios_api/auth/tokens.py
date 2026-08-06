"""Minting and verifying session credentials (spec 003 FR-003, FR-019).

A JWT identifies; the database decides. That division matters and is easy to lose: the
token carries a user, a tenant, and a session id, and **nothing** downstream trusts its
contents for authorization. FR-004 requires active status and tenant membership to be
re-read from current records on every request, and FR-007 requires sign-out to end
access — neither is possible if the credential is treated as the authority.

So the checks here are narrow and complete: is this token one we issued, is it still
inside its window, and is it the kind of token this endpoint accepts. Everything else
is a query.

**The algorithm list is pinned at every call.** An unpinned verifier accepts `alg:
none` — a token anyone can write — and accepts an RS256 public key presented as an HMAC
secret. Both are ordinary attacks, neither is visible in a round-trip test, and both
are in `tests/unit/test_tokens.py`.

**No leeway.** A credential marginally outside its window is refused. That is the
direction that costs a user one sign-in rather than granting a minute of access nobody
authorised (spec edge case: "clock skew must fail closed, not open").
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any, Final

import jwt

from eaios_core.settings import Settings, get_settings

__all__ = ["ACCESS_TOKEN_TYPE", "InvalidTokenError", "TokenClaims", "mint_access_token", "verify_access_token"]

#: The one token type this feature issues. Checked on every verification so a second
#: type — a refresh token, a one-time link — cannot be replayed against a protected
#: endpoint the day it arrives.
ACCESS_TOKEN_TYPE: Final[str] = "access"


class InvalidTokenError(Exception):
    """The credential is not one we will accept.

    One exception for every cause: forged signature, wrong issuer, wrong audience,
    expired, wrong type, missing claim, unparseable. Callers refuse identically, and a
    caller that could distinguish them would eventually surface the distinction in a
    response (FR-022).

    Its message is for logs and never for a response body.
    """


@dataclass(frozen=True, slots=True)
class TokenClaims:
    """What a verified token asserts. Identifiers only — never an attribute."""

    user_id: uuid.UUID
    company_id: uuid.UUID
    session_id: uuid.UUID
    issued_at: dt.datetime
    expires_at: dt.datetime


def mint_access_token(
    *,
    user_id: uuid.UUID,
    company_id: uuid.UUID,
    session_id: uuid.UUID,
    issued_at: dt.datetime,
    expires_at: dt.datetime,
    settings: Settings | None = None,
) -> str:
    """Issue a credential for one session.

    ``expires_at`` is the session's **absolute** cap, not its idle bound. The token
    expiry is a fast path — it lets an obviously-dead credential be refused before a
    database round trip — and never the mechanism. Encoding the idle bound here instead
    would mean re-issuing a token on every request, and would put the shorter of the
    two bounds in the one place the server cannot withdraw.
    """
    cfg = settings or get_settings()
    payload: dict[str, Any] = {
        "iss": cfg.auth.jwt_issuer,
        "aud": cfg.auth.jwt_audience,
        "sub": str(user_id),
        "cid": str(company_id),
        "sid": str(session_id),
        "typ": ACCESS_TOKEN_TYPE,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
        # A unique id per token. Nothing reads it in this feature; it is here so two
        # tokens minted in the same second for the same session are distinguishable in
        # a log, which is the difference between "replayed" and "reissued".
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(
        payload, cfg.auth.jwt_signing_key.get_secret_value(), algorithm=cfg.auth.jwt_algorithm
    )


def verify_access_token(token: str, settings: Settings | None = None) -> TokenClaims:
    """Check a credential and return what it asserts, or raise :class:`InvalidTokenError`.

    Verifies, in one call: signature, issuer, audience, and expiry. Then the type and
    the three identifiers, because PyJWT has no opinion about claims it did not define.
    """
    cfg = settings or get_settings()
    try:
        payload = jwt.decode(
            token,
            cfg.auth.jwt_signing_key.get_secret_value(),
            # Pinned. Not read from the token's own header, which is what makes
            # `alg: none` and RS256-as-HMAC confusion impossible rather than unlikely.
            algorithms=[cfg.auth.jwt_algorithm],
            issuer=cfg.auth.jwt_issuer,
            audience=cfg.auth.jwt_audience,
            leeway=0,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(f"token rejected: {exc}") from exc

    if payload.get("typ") != ACCESS_TOKEN_TYPE:
        raise InvalidTokenError(f"wrong token type: {payload.get('typ')!r}")

    try:
        return TokenClaims(
            user_id=uuid.UUID(str(payload["sub"])),
            company_id=uuid.UUID(str(payload["cid"])),
            session_id=uuid.UUID(str(payload["sid"])),
            issued_at=dt.datetime.fromtimestamp(int(payload["iat"]), tz=dt.UTC),
            expires_at=dt.datetime.fromtimestamp(int(payload["exp"]), tz=dt.UTC),
        )
    except (KeyError, ValueError, TypeError) as exc:
        # A claim that is present but not an identifier. Refused at the boundary rather
        # than left to become a database error deep in the context builder, where it
        # would read as a permissions problem.
        raise InvalidTokenError(f"malformed claim: {exc}") from exc
