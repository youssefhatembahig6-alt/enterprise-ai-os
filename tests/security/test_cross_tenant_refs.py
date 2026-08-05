"""No relationship crosses a company boundary (spec FR-024, FR-024a, FR-044).

RLS stops a *query* from reading another tenant's rows. This is the complementary
guarantee: that no row legitimately visible to one tenant points at a row owned by
another. A cross-tenant foreign key would let a perfectly scoped query follow a
reference straight across the boundary.

The check is generated from the live foreign-key catalogue, so a relationship added
later is covered without anyone remembering to update a list.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import Engine, text

from eaios_core.tenancy import GLOBAL_ENTITIES
from eaios_seed.audit_checks.structural import run_structural_audit

pytestmark = pytest.mark.security


@pytest.fixture(scope="module")
def report(owner_engine: Engine):  # type: ignore[no-untyped-def]
    return run_structural_audit(owner_engine)


class TestStructuralAudit:
    def test_no_scoping_violations(self, report) -> None:  # type: ignore[no-untyped-def]
        assert report.scoping == [], "\n".join(report.scoping)

    def test_no_cross_tenant_references(self, report) -> None:  # type: ignore[no-untyped-def]
        assert report.cross_tenant == [], "\n".join(report.cross_tenant)

    def test_no_orphaned_references(self, report) -> None:  # type: ignore[no-untyped-def]
        """FR-033 / SC-006 — zero orphans across every relationship."""
        assert report.orphans == [], "\n".join(report.orphans)

    def test_audit_reports_ok(self, report) -> None:  # type: ignore[no-untyped-def]
        assert report.ok, report.describe()

    def test_the_audit_actually_inspected_something(self, owner_engine: Engine) -> None:
        """A pass over zero foreign keys would be meaningless."""
        from eaios_seed.audit_checks.structural import _tenant_foreign_keys

        assert len(_tenant_foreign_keys(owner_engine)) >= 25


class TestSharedNothing:
    """FR-024a — the tenants share nothing but the global allowlist."""

    def test_no_customer_is_shared(self, owner_engine: Engine) -> None:
        with owner_engine.connect() as conn:
            shared = conn.execute(
                text(
                    "SELECT count(*) FROM (SELECT name FROM customers"
                    " GROUP BY name HAVING count(DISTINCT company_id) > 1) s"
                )
            ).scalar_one()
        assert shared == 0

    def test_no_user_email_is_shared(self, owner_engine: Engine) -> None:
        with owner_engine.connect() as conn:
            shared = conn.execute(
                text(
                    "SELECT count(*) FROM (SELECT email FROM users"
                    " GROUP BY email HAVING count(DISTINCT company_id) > 1) s"
                )
            ).scalar_one()
        assert shared == 0

    def test_no_storage_key_is_shared(self, owner_engine: Engine) -> None:
        with owner_engine.connect() as conn:
            shared = conn.execute(
                text(
                    "SELECT count(*) FROM (SELECT storage_key FROM documents"
                    " GROUP BY storage_key HAVING count(DISTINCT company_id) > 1) s"
                )
            ).scalar_one()
        assert shared == 0

    def test_identifiers_are_disjoint_between_tenants(
        self, owner_engine: Engine, company_ids: dict[str, uuid.UUID]
    ) -> None:
        """Derived identifiers include the tenant, so a collision would mean the
        derivation lost its company component."""
        with owner_engine.connect() as conn:
            collisions = conn.execute(
                text(
                    "SELECT count(*) FROM (SELECT id FROM users"
                    " GROUP BY id HAVING count(DISTINCT company_id) > 1) s"
                )
            ).scalar_one()
        assert collisions == 0


class TestGlobalAllowlistIsRespected:
    def test_global_tables_carry_no_company_id(self, owner_engine: Engine) -> None:
        with owner_engine.connect() as conn:
            offenders = [
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.columns"
                        " WHERE table_schema = 'public' AND column_name = 'company_id'"
                        " AND table_name = ANY(:tables)"
                    ),
                    {"tables": sorted(GLOBAL_ENTITIES)},
                )
            ]
        assert offenders == [], f"global tables must not have company_id: {offenders}"

    def test_permission_catalog_is_shared_not_duplicated(self, owner_engine: Engine) -> None:
        """FR-009b — one catalog, so codes cannot drift apart between tenants."""
        with owner_engine.connect() as conn:
            total = conn.execute(text("SELECT count(*) FROM permissions")).scalar_one()
            distinct = conn.execute(
                text("SELECT count(DISTINCT code) FROM permissions")
            ).scalar_one()
        assert total == distinct == 17

    def test_both_tenants_reference_the_same_permission_rows(
        self, owner_engine: Engine, company_ids: dict[str, uuid.UUID]
    ) -> None:
        with owner_engine.connect() as conn:
            per_tenant = {
                slug: {
                    row[0]
                    for row in conn.execute(
                        text(
                            "SELECT DISTINCT permission_id FROM role_permissions"
                            " WHERE company_id = :cid"
                        ),
                        {"cid": cid},
                    )
                }
                for slug, cid in company_ids.items()
            }
        overlap = per_tenant["niletech"] & per_tenant["delta-retail"]
        assert overlap, "tenants share no permission rows — the catalog was duplicated"
