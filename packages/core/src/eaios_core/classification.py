"""Data classification levels (spec FR-010a, FR-010b).

Exactly four, and the set is closed. Storage keys, vector payloads, and every future
authorization rule are written against these values, so a fifth level appearing by
accident would silently widen what "restricted" means.
"""

from __future__ import annotations

from enum import Enum
from typing import Final

__all__ = ["Classification"]

# Sensitivity order. Kept separate from the enum values so the stored strings stay
# stable even if the ordering is ever reconsidered.
_RANK: Final[dict[str, int]] = {
    "PUBLIC": 0,
    "INTERNAL": 1,
    "CONFIDENTIAL": 2,
    "RESTRICTED": 3,
}


class Classification(str, Enum):
    """How sensitive a resource is, and therefore who may reach it."""

    #: Visible without authentication. The only level the public site may render.
    PUBLIC = "PUBLIC"

    #: Any authenticated employee of the owning company.
    INTERNAL = "INTERNAL"

    #: Restricted to a department, role, or owner.
    CONFIDENTIAL = "CONFIDENTIAL"

    #: The most sensitive tier — role alone is insufficient, an explicit grant is
    #: required. Payroll, executive contracts, disciplinary records.
    RESTRICTED = "RESTRICTED"

    @property
    def rank(self) -> int:
        return _RANK[self.value]

    @property
    def is_public(self) -> bool:
        """True only for PUBLIC. Anonymous visitors may see nothing else."""
        return self is Classification.PUBLIC

    @property
    def requires_explicit_grant(self) -> bool:
        """True when holding the right role is not by itself sufficient."""
        return self is Classification.RESTRICTED

    def at_least(self, other: Classification) -> bool:
        """True when this level is at least as sensitive as ``other``."""
        return self.rank >= other.rank

    # The str mixin would otherwise give lexicographic comparison, which orders
    # CONFIDENTIAL < INTERNAL < PUBLIC < RESTRICTED — alphabetical and meaningless.
    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Classification):
            return NotImplemented
        return self.rank < other.rank

    def __le__(self, other: object) -> bool:
        if not isinstance(other, Classification):
            return NotImplemented
        return self.rank <= other.rank

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, Classification):
            return NotImplemented
        return self.rank > other.rank

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, Classification):
            return NotImplemented
        return self.rank >= other.rank

    def __str__(self) -> str:
        return self.value
