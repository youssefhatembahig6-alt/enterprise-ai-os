"""The global-entity allowlist (spec FR-009a, FR-009b, FR-009c).

Every table is tenant-owned unless it appears on a closed allowlist of four. The
allowlist has to be enforced in code rather than merely documented, because the
structural audit needs to tell "correctly global" apart from "wrongly unscoped" —
and a documented-only list cannot do that.
"""

from __future__ import annotations

import pytest

from eaios_core import tenancy

pytestmark = pytest.mark.unit


class TestAllowlistIsClosed:
    def test_exactly_four_global_entities(self) -> None:
        assert len(tenancy.GLOBAL_ENTITIES) == 4

    def test_the_four_are_the_specified_ones(self) -> None:
        assert frozenset(
            {
                "permissions",
                "platform_administrators",
                "alembic_version",
                "dataset_manifest",
            }
        ) == tenancy.GLOBAL_ENTITIES

    def test_allowlist_is_immutable(self) -> None:
        with pytest.raises(AttributeError):
            tenancy.GLOBAL_ENTITIES.add("users")  # type: ignore[attr-defined]


class TestScopingDecisions:
    @pytest.mark.parametrize(
        "table", ["users", "documents", "orders", "audit_logs", "leadership_profiles"]
    )
    def test_ordinary_tables_are_tenant_scoped(self, table: str) -> None:
        assert tenancy.is_tenant_scoped(table) is True
        assert tenancy.requires_company_id(table) is True

    @pytest.mark.parametrize(
        "table",
        ["permissions", "platform_administrators", "alembic_version", "dataset_manifest"],
    )
    def test_allowlisted_tables_are_global(self, table: str) -> None:
        assert tenancy.is_tenant_scoped(table) is False
        assert tenancy.requires_company_id(table) is False


class TestAuditDirections:
    """FR-044 requires the audit to catch violations in *both* directions."""

    def test_unscoped_non_allowlisted_table_is_a_violation(self) -> None:
        violations = tenancy.audit_table_scoping({"users": False, "orders": True})
        assert violations == ["users: tenant-owned table has no company_id"]

    def test_allowlisted_table_that_gained_a_tenant_column_is_a_violation(self) -> None:
        violations = tenancy.audit_table_scoping({"permissions": True})
        assert violations == ["permissions: global table must not have a company_id"]

    def test_a_correct_schema_produces_no_violations(self) -> None:
        violations = tenancy.audit_table_scoping(
            {
                "users": True,
                "documents": True,
                "permissions": False,
                "platform_administrators": False,
                "dataset_manifest": False,
                "alembic_version": False,
            }
        )
        assert violations == []


class TestCompanySlugs:
    def test_exactly_two_tenants(self) -> None:
        assert tenancy.COMPANY_SLUGS == ("niletech", "delta-retail")

    def test_slug_validation_rejects_unknown_tenants(self) -> None:
        assert tenancy.is_known_company("niletech")
        assert not tenancy.is_known_company("acme")

    def test_require_company_raises_on_unknown(self) -> None:
        with pytest.raises(ValueError, match="unknown company"):
            tenancy.require_company("acme")
