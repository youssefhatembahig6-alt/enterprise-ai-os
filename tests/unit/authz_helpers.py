"""Builders for the policy-engine tests (spec 003 FR-012–FR-014).

Not a test module — no ``test_`` prefix, so pytest imports it and collects nothing
from it. It exists so the four engine test files describe *what they are checking*
rather than each restating how to construct a subject and a resource.

Every identifier is derived with ``uuid5`` from a readable name. Fixed values keep a
failure message legible ("expected NILETECH, got DELTA") and mean a test never
depends on the order fixtures happened to run in.
"""

from __future__ import annotations

import uuid
from typing import Any

from eaios_core.authz import AccessContext, ResourceDescriptor, ResourceKind

_NS = uuid.UUID("00000000-0000-0000-0000-0000000003a1")


def ident(name: str) -> uuid.UUID:
    """A stable identifier for a readable name."""
    return uuid.uuid5(_NS, name)


NILETECH = ident("company:niletech")
DELTA = ident("company:delta-retail")

ALICE = ident("user:alice")  # a manager
BOB = ident("user:bob")  # reports to Alice
CAROL = ident("user:carol")  # reports to nobody in this fixture
ENGINEERING = ident("dept:engineering")
SALES = ident("dept:sales")


def context(**overrides: Any) -> AccessContext:
    """An access context for Alice — a NileTech engineering manager with one report.

    Defaults describe the most common subject in these tests. Every field is
    overridable, because a test that has to reconstruct the whole context to change
    one attribute stops saying which attribute mattered.
    """
    fields: dict[str, Any] = {
        "company_id": NILETECH,
        "company_slug": "niletech",
        "user_id": ALICE,
        "session_id": ident("session:alice"),
        "department_id": ENGINEERING,
        "office_id": ident("office:cai"),
        "country": "EG",
        "employment_type": "FULL_TIME",
        "manager_id": ident("user:ceo"),
        "direct_report_ids": frozenset({BOB}),
        "role_names": frozenset({"Manager"}),
        "role_ids": frozenset({ident("role:manager")}),
        "permission_codes": frozenset({"documents:read", "hr:read_self", "hr:read_team"}),
    }
    fields.update(overrides)
    return AccessContext(**fields)


def descriptor(**overrides: Any) -> ResourceDescriptor:
    """Alice's own HR profile, in her own tenant — the allowing case by default.

    Tests deny by taking one thing away, which is what makes the failure message
    point at the cause.
    """
    fields: dict[str, Any] = {
        "kind": ResourceKind.HR_PROFILE,
        "resource_id": str(ALICE),
        "company_id": NILETECH,
        "owner_id": ALICE,
        "department_id": ENGINEERING,
        "classification": None,
        "acl_grants": None,
    }
    fields.update(overrides)
    return ResourceDescriptor(**fields)
