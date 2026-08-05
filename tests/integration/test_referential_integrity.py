"""Zero orphaned references anywhere (spec FR-033, SC-006).

`tests/security/test_cross_tenant_refs.py` checks that no reference *crosses a
tenant*. This checks the simpler and more fundamental property: that every
reference resolves at all.

Declared foreign keys make most of this structurally impossible, which is the
point — the value here is proving the constraints are actually declared and
enforced, not merely intended. A relationship enforced only by convention would
pass a hand-written check and fail in production.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, text

from eaios_core.models import Base, tenant_tables

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def engine() -> Engine:
    from eaios_core.db import create_owner_engine

    engine = create_owner_engine()
    try:
        with engine.connect() as conn:
            seeded = conn.execute(text("SELECT count(*) FROM companies")).scalar_one()
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"database unavailable: {exc}")
    if not seeded:
        pytest.skip("environment not seeded; run `make up && make seed`")
    return engine


@pytest.fixture(scope="module")
def foreign_keys(engine: Engine) -> list[tuple[str, str, str, str]]:
    """(source_table, source_column, target_table, target_column) from the catalogue."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT tc.table_name, kcu.column_name,
                       ccu.table_name AS target_table, ccu.column_name AS target_column
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON kcu.constraint_name = tc.constraint_name
                JOIN information_schema.constraint_column_usage ccu
                  ON ccu.constraint_name = tc.constraint_name
                WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'
                ORDER BY 1, 2
                """
            )
        ).all()
    return [tuple(row) for row in rows]  # type: ignore[misc]


class TestForeignKeysAreDeclared:
    def test_the_schema_declares_a_meaningful_number(
        self, foreign_keys: list[tuple[str, str, str, str]]
    ) -> None:
        assert len(foreign_keys) >= 40, f"only {len(foreign_keys)} foreign keys declared"

    def test_every_tenant_table_declares_its_company_fk(
        self, foreign_keys: list[tuple[str, str, str, str]]
    ) -> None:
        declared = {source for source, column, _t, _c in foreign_keys if column == "company_id"}
        missing = sorted(set(tenant_tables()) - declared)
        assert missing == [], f"tables whose company_id is not a declared FK: {missing}"


class TestNoOrphans:
    def test_no_reference_dangles(
        self, engine: Engine, foreign_keys: list[tuple[str, str, str, str]]
    ) -> None:
        orphans: list[str] = []
        with engine.connect() as conn:
            for source, column, target, target_column in foreign_keys:
                count = conn.execute(
                    text(
                        f"SELECT count(*) FROM {source} s"
                        f" LEFT JOIN {target} t ON t.{target_column} = s.{column}"
                        f" WHERE s.{column} IS NOT NULL AND t.{target_column} IS NULL"
                    )
                ).scalar_one()
                if count:
                    orphans.append(f"{source}.{column} -> {target}: {count}")
        assert orphans == [], "\n".join(orphans)


class TestRequiredRelationshipsArePopulated:
    """A nullable column that is always null would pass the orphan check trivially."""

    @pytest.mark.parametrize(
        ("table", "column"),
        [
            ("users", "department_id"),
            ("users", "office_id"),
            ("departments", "head_user_id"),
            ("documents", "owner_id"),
            ("orders", "customer_id"),
            ("orders", "sales_rep_id"),
            ("order_lines", "order_id"),
            ("invoices", "order_id"),
            ("employee_profiles", "user_id"),
            ("leave_balances", "user_id"),
            ("contracts", "document_id"),
            ("policy_documents", "document_id"),
            ("leadership_profiles", "user_id"),
        ],
    )
    def test_column_is_fully_populated(self, engine: Engine, table: str, column: str) -> None:
        with engine.connect() as conn:
            total = conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
            nulls = conn.execute(
                text(f"SELECT count(*) FROM {table} WHERE {column} IS NULL")
            ).scalar_one()
        assert total > 0, f"{table} is empty; the check would be vacuous"
        assert nulls == 0, f"{table}.{column} has {nulls} null(s) of {total}"


class TestUniquenessHolds:
    @pytest.mark.parametrize(
        ("table", "columns"),
        [
            ("companies", "slug"),
            ("users", "company_id, email"),
            ("documents", "storage_key"),
            ("orders", "company_id, order_number"),
            ("invoices", "order_id"),
            ("products", "company_id, sku"),
            ("employee_profiles", "user_id"),
            ("policy_documents", "company_id, policy_type"),
        ],
    )
    def test_no_duplicates(self, engine: Engine, table: str, columns: str) -> None:
        with engine.connect() as conn:
            duplicates = conn.execute(
                text(
                    f"SELECT count(*) FROM (SELECT {columns} FROM {table}"
                    f" GROUP BY {columns} HAVING count(*) > 1) s"
                )
            ).scalar_one()
        assert duplicates == 0


class TestModelMetadataMatchesTheDatabase:
    def test_every_model_table_exists(self, engine: Engine) -> None:
        with engine.connect() as conn:
            live = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables"
                        " WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
                    )
                )
            }
        missing = sorted(set(Base.metadata.tables) - live)
        assert missing == [], f"models without a table: {missing}"
