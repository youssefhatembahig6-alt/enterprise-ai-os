"""The deterministic authorization policy engine (Constitution Principle II).

Pure: no database, no cache, no HTTP, no clock, no randomness, no environment. It
receives an already-built :class:`AccessContext` and a :class:`ResourceDescriptor` and
returns a :class:`Decision`.

That purity is a design decision, not an accident of scope. Building the context and
fetching resource attributes are I/O and live in ``apps/api``; deciding is arithmetic
and lives here. The split is what makes layer ordering, short-circuiting, reason codes,
and default-deny testable with nothing running — the practical precondition for
Principle VIII's write-the-test-first cycle actually being followed rather than
intended.

It also satisfies the layering rule from spec 001 FR-001a: ``packages/*`` must not
import from ``apps/*``, ``services/*``, or ``scripts/*``, and this package imports
nothing outside ``eaios_core``.

See ``specs/003-auth-portal-shell/contracts/policy-engine.md`` for the contract and the
six guarantees the tests hold it to.
"""

from __future__ import annotations

from .context import AccessContext
from .decision import (
    AclGrant,
    Action,
    Condition,
    Decision,
    KindPolicy,
    ReasonCode,
    ResourceDescriptor,
    ResourceKind,
    Rule,
    Scope,
)
from .filters import qdrant_filter
from .policy import evaluate, evaluate_with
from .rules import POLICIES
from .sensitivity import is_sensitive

__all__ = [
    "POLICIES",
    "AccessContext",
    "AclGrant",
    "Action",
    "Condition",
    "Decision",
    "KindPolicy",
    "ReasonCode",
    "ResourceDescriptor",
    "ResourceKind",
    "Rule",
    "Scope",
    "evaluate",
    "evaluate_with",
    "is_sensitive",
    "qdrant_filter",
]
