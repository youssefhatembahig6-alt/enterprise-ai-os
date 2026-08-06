"""Response models for the caller's own identity and context (spec 003 FR-011)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict

__all__ = ["AccessContextView", "CurrentUser"]

_STRICT = ConfigDict(extra="forbid", frozen=True)


class CurrentUser(BaseModel):
    """Who the portal greets, and what it may offer them."""

    model_config = _STRICT

    user_id: uuid.UUID
    full_name: str
    email: str
    #: The company **name**, not its identifier. The portal displays it; nothing keys
    #: on it, and exposing the id would put a tenant identifier in a page where a
    #: caller could read it and start supplying it (FR-010).
    company_name: str
    department: str
    office: str
    #: Display only. Role-aware navigation is built from `permissions`, never from
    #: these — FR-014 requires permission codes, and an interface that branched on a
    #: role name would break the moment roles are recomposed.
    roles: list[str]
    #: The codes navigation is built from (FR-028). Hiding an entry is presentation;
    #: the server refuses the address regardless of what was shown.
    permissions: list[str]


class AccessContextView(BaseModel):
    """The server's own view of the caller, rendered verbatim (FR-011).

    Exists so what the server believes is *observable* rather than inferred from
    behaviour. When this disagrees with a decision, one of the two is wrong and it is
    visible — instead of being reconstructed from which requests happened to succeed.

    Carries no credential, no token, and no session identifier.
    """

    model_config = _STRICT

    company_id: uuid.UUID
    user_id: uuid.UUID
    department_id: uuid.UUID
    office_id: uuid.UUID
    country: str
    employment_type: str
    manager_id: uuid.UUID | None
    direct_report_ids: list[uuid.UUID]
    roles: list[str]
    permissions: list[str]
    #: Digest over company plus sorted permission codes. Feature 004's cache keys are
    #: built from it (Constitution Principle III); exposed here because a value that
    #: decides what may be served from cache should be inspectable.
    permission_fingerprint: str
