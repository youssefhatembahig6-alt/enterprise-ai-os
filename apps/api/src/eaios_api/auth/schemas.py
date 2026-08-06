"""Typed request and response models for the authentication endpoints (spec 003).

The Constitution's *API contracts* section requires typed request and response models
at every boundary, with matching frontend types. These are the source those types are
generated from, so anything declared loosely here becomes an `any` in the portal.

`_STRICT` forbids unknown fields on input. On a sign-in body that is not tidiness: it
is where a `company_id` or a `roles` field supplied by a caller stops being ignored and
starts being *refused*, which is a clearer failure than silently dropping it (FR-010).
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

__all__ = ["LoginAccepted", "LoginRequest", "SessionState"]

_STRICT = ConfigDict(extra="forbid", frozen=True)


class LoginRequest(BaseModel):
    """Credentials, and nothing else.

    **No company field.** The tenant is resolved server-side by looking the address up
    under each known tenant in turn; a caller-supplied tenant would be exactly the
    trusted request value FR-010 forbids. `extra="forbid"` means supplying one is a
    422 rather than a value quietly ignored.
    """

    model_config = _STRICT

    email: EmailStr = Field(max_length=255)
    #: Bounded so an enormous body cannot be turned into an Argon2 denial of service.
    #: Never logged, never audited, never echoed (FR-018).
    password: str = Field(min_length=0, max_length=256)


class LoginAccepted(BaseModel):
    """A new session.

    The token is returned in the body for server-side callers. The site's own route
    handler moves it into an httpOnly cookie and does not pass it to browser
    JavaScript, which is what keeps it out of reach of an XSS (research R3).
    """

    model_config = _STRICT

    access_token: str
    token_type: str = "bearer"
    #: The **absolute** cap — eight hours from sign-in. Not the idle bound, which moves
    #: and which the interface must not try to track on its own: FR-005 requires the
    #: server to enforce expiry, and an interface that hid an expired session without
    #: the server refusing it would not satisfy that.
    expires_at: dt.datetime


class SessionState(BaseModel):
    """What the portal needs to tell "expired" apart from "never signed in".

    Both bounds are exposed because the interface has to *say which happened* — FR-005's
    edge case requires the expiry state to be distinct from the unauthenticated one, and
    a generic failure after a thirty-minute pause is the difference between a portal
    that explains itself and one that looks broken.
    """

    model_config = _STRICT

    session_id: uuid.UUID
    issued_at: dt.datetime
    absolute_expires_at: dt.datetime
    #: `last_seen_at + 30 minutes`, recomputed on each request. Advances with use; the
    #: absolute cap never does.
    idle_expires_at: dt.datetime
