"""Tenant scoping and the closed global-entity allowlist (spec FR-009a–FR-009c).

Every table is tenant-owned unless it appears on the allowlist below. The list is
enforced here in code rather than only in prose, because the structural audit has to
distinguish "correctly global" from "wrongly unscoped" — and prose cannot do that.

The audit checks both directions on purpose. A tenant table that lost its
``company_id`` is an obvious hole; a global table that *gained* one is subtler but
just as wrong, because it means the permission catalog has started to diverge
between tenants.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from .constants import COMPANY_SLUGS

__all__ = [
    "COMPANY_SLUGS",
    "GLOBAL_ENTITIES",
    "audit_table_scoping",
    "is_known_company",
    "is_tenant_scoped",
    "require_company",
    "requires_company_id",
]

#: The complete set of entities that legitimately have no ``company_id``.
#: Adding to this set widens the tenant boundary and must be a deliberate,
#: reviewed decision — `tests/unit/test_tenancy.py` asserts the exact membership.
GLOBAL_ENTITIES: Final[frozenset[str]] = frozenset(
    {
        # Shared vocabulary — one catalog so permission codes cannot drift apart
        # between tenants (FR-009b).
        "permissions",
        # Platform-level account bound to no company (FR-009c).
        "platform_administrators",
        # Migration bookkeeping, not dataset content.
        "alembic_version",
        # Provenance record for the dataset as a whole.
        "dataset_manifest",
    }
)


def is_tenant_scoped(table: str) -> bool:
    """True when the table must carry a ``company_id``."""
    return table not in GLOBAL_ENTITIES


def requires_company_id(table: str) -> bool:
    """Alias of :func:`is_tenant_scoped`, named for schema-audit call sites."""
    return is_tenant_scoped(table)


def audit_table_scoping(has_company_id: Mapping[str, bool]) -> list[str]:
    """Report scoping violations in both directions (spec FR-044).

    Args:
        has_company_id: Table name → whether it currently has a ``company_id`` column.

    Returns:
        Sorted violation descriptions; empty when the schema is correct.
    """
    violations: list[str] = []
    for table in sorted(has_company_id):
        present = has_company_id[table]
        if is_tenant_scoped(table) and not present:
            violations.append(f"{table}: tenant-owned table has no company_id")
        elif not is_tenant_scoped(table) and present:
            violations.append(f"{table}: global table must not have a company_id")
    return violations


def is_known_company(slug: str) -> bool:
    return slug in COMPANY_SLUGS


def require_company(slug: str) -> str:
    """Return ``slug`` if it names a known tenant, else raise.

    Used by the key builders so an unattributable key cannot be constructed in the
    first place, rather than being detected later by audit.
    """
    if not is_known_company(slug):
        raise ValueError(f"unknown company: {slug!r} (expected one of {list(COMPANY_SLUGS)})")
    return slug
