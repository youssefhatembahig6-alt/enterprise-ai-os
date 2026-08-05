"""Schema-level tenancy audit (spec FR-009, FR-009a, FR-044, SC-003).

Walks the SQLAlchemy metadata rather than a live database, so it runs in the fast
unit lane and fails the moment a new model is declared without ``company_id``.

The check runs in *both* directions on purpose. A tenant table that lost its
``company_id`` is an obvious hole. A global table that gained one is subtler and
just as wrong: it means the shared permission vocabulary has begun to diverge
between tenants.
"""

from __future__ import annotations

import pytest

from eaios_core import tenancy
from eaios_core.models import Base, tenant_tables

pytestmark = [pytest.mark.security, pytest.mark.unit]

TENANT_COLUMN = "company_id"


def _tables() -> dict[str, bool]:
    """Table name → whether it declares a ``company_id`` column."""
    return {name: TENANT_COLUMN in table.c for name, table in Base.metadata.tables.items()}


class TestEveryTableIsAccountedFor:
    def test_metadata_is_populated(self) -> None:
        """A silent pass because no models were imported would defeat the test."""
        assert len(Base.metadata.tables) >= 25

    def test_no_scoping_violations_in_either_direction(self) -> None:
        violations = tenancy.audit_table_scoping(_tables())
        assert violations == [], "schema scoping violations:\n  " + "\n  ".join(violations)

    def test_global_tables_are_exactly_the_allowlist(self) -> None:
        unscoped = {name for name, has in _tables().items() if not has}
        # alembic_version is created by Alembic itself, not by our metadata.
        expected = tenancy.GLOBAL_ENTITIES - {"alembic_version"}
        assert unscoped == expected


class TestTenantColumnShape:
    @pytest.mark.parametrize("table_name", tenant_tables())
    def test_company_id_is_non_nullable(self, table_name: str) -> None:
        column = Base.metadata.tables[table_name].c[TENANT_COLUMN]
        assert not column.nullable, f"{table_name}.company_id must be NOT NULL (FR-009)"

    @pytest.mark.parametrize("table_name", tenant_tables())
    def test_company_id_references_companies(self, table_name: str) -> None:
        column = Base.metadata.tables[table_name].c[TENANT_COLUMN]
        targets = {fk.column.table.name for fk in column.foreign_keys}
        assert targets == {"companies"}, f"{table_name}.company_id must reference companies.id"

    @pytest.mark.parametrize("table_name", tenant_tables())
    def test_company_id_is_indexed(self, table_name: str) -> None:
        """Every tenant query filters on it; an unindexed scan would also make the
        SC-008 seed-time budget harder to hold."""
        table = Base.metadata.tables[table_name]
        indexed = any(
            TENANT_COLUMN in {c.name for c in index.columns} for index in table.indexes
        ) or table.c[TENANT_COLUMN].index
        assert indexed, f"{table_name}.company_id is not indexed"


class TestPlatformAdministratorIsSeparate:
    def test_users_cannot_be_tenant_less(self) -> None:
        """FR-009c — the platform account is its own table, not a nullable column.

        A nullable ``company_id`` on ``users`` would be exactly the hole every later
        query has to remember to close.
        """
        assert not Base.metadata.tables["users"].c[TENANT_COLUMN].nullable
        assert TENANT_COLUMN not in Base.metadata.tables["platform_administrators"].c
