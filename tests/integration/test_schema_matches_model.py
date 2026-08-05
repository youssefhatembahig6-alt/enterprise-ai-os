"""The live schema matches what data-model.md documents (converge finding F10).

Migration 0001 builds the schema from the declarative metadata rather than explicit
DDL. That removes drift between models and migration, but it also means nothing
independently checks that the *documented* constraints actually exist. A check
constraint that was written into the model but silently not emitted would leave the
database accepting data the data model says is impossible.

These assertions read the live catalogue, not the metadata, so they would catch a
constraint that exists in Python but never reached PostgreSQL.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def engine() -> Engine:
    from eaios_core.db import create_owner_engine

    engine = create_owner_engine()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"database unavailable: {exc}")
    return engine


@pytest.fixture(scope="module")
def check_constraints(engine: Engine) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT conname FROM pg_constraint c"
                " JOIN pg_class t ON t.oid = c.conrelid"
                " JOIN pg_namespace n ON n.oid = t.relnamespace"
                " WHERE c.contype = 'c' AND n.nspname = 'public'"
            )
        ).all()
    return {row[0] for row in rows}


class TestDocumentedCheckConstraints:
    """Each of these is stated in data-model.md as an invariant."""

    @pytest.mark.parametrize(
        "constraint",
        [
            "ck_leave_balances_balance_arithmetic",
            "ck_leave_balances_non_negative",
            "ck_leave_requests_date_order",
            "ck_orders_total_arithmetic",
            "ck_orders_non_negative_amounts",
            "ck_order_lines_line_arithmetic",
            "ck_order_lines_positive_quantity",
            "ck_invoices_date_order",
            "ck_contracts_date_order",
            "ck_performance_reviews_rating_range",
            "ck_performance_reviews_period_order",
            "ck_users_not_own_manager",
            "ck_documents_non_empty",
        ],
    )
    def test_constraint_exists(self, check_constraints: set[str], constraint: str) -> None:
        assert constraint in check_constraints, (
            f"{constraint} is documented in data-model.md but not present in the database"
        )

    def test_the_catalogue_was_actually_read(self, check_constraints: set[str]) -> None:
        assert len(check_constraints) >= 20


class TestConstraintsAreEnforced:
    """Existing is not the same as enforced. These prove the database refuses."""

    def test_balance_arithmetic_is_rejected(self, engine: Engine) -> None:
        with pytest.raises(Exception, match="balance_arithmetic"), engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE leave_balances SET remaining_days = entitlement_days + 999"
                    " WHERE id = (SELECT id FROM leave_balances LIMIT 1)"
                )
            )

    def test_negative_quantity_is_rejected(self, engine: Engine) -> None:
        """Isolated deliberately.

        Setting quantity alone also breaks `line_arithmetic`, which fires first and
        would let this pass without ever exercising `positive_quantity`. Updating
        line_total to stay consistent leaves the quantity guard as the only thing
        that can reject the row.
        """
        with pytest.raises(Exception, match="positive_quantity"), engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE order_lines SET quantity = -1, line_total = -unit_price"
                    " WHERE id = (SELECT id FROM order_lines LIMIT 1)"
                )
            )

    def test_an_unknown_classification_is_rejected(self, engine: Engine) -> None:
        """FR-010b — the enum is closed, so an unrecognised level cannot persist."""
        with pytest.raises(DBAPIError), engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE documents SET classification = 'TOP_SECRET'"
                    " WHERE id = (SELECT id FROM documents LIMIT 1)"
                )
            )

    def test_a_null_company_id_is_rejected(self, engine: Engine) -> None:
        """FR-009 — the tenant column is non-nullable everywhere."""
        with pytest.raises(DBAPIError), engine.begin() as conn:
            conn.execute(
                text("UPDATE users SET company_id = NULL WHERE id = (SELECT id FROM users LIMIT 1)")
            )


class TestDocumentedUniqueConstraints:
    @pytest.mark.parametrize(
        ("table", "columns"),
        [
            ("companies", ["slug"]),
            ("users", ["company_id", "email"]),
            ("users", ["company_id", "persona_key"]),
            ("documents", ["storage_key"]),
            ("invoices", ["order_id"]),
            ("products", ["company_id", "sku"]),
            ("policy_documents", ["company_id", "policy_type"]),
            ("attendance_records", ["user_id", "work_date"]),
            ("offices", ["company_id", "code"]),
            ("departments", ["company_id", "name"]),
            ("roles", ["company_id", "name"]),
        ],
    )
    def test_unique_constraint_exists(
        self, engine: Engine, table: str, columns: list[str]
    ) -> None:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT array_agg(a.attname ORDER BY a.attname) AS cols"
                    " FROM pg_constraint c"
                    " JOIN pg_class t ON t.oid = c.conrelid"
                    " JOIN unnest(c.conkey) AS k(attnum) ON true"
                    " JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum"
                    " WHERE c.contype = 'u' AND t.relname = :table"
                    " GROUP BY c.oid"
                ),
                {"table": table},
            ).all()
        found = [sorted(row.cols) for row in rows]
        assert sorted(columns) in found, (
            f"{table} has no unique constraint on {columns}; found {found}"
        )


class TestEnumMatchesTheModel:
    def test_classification_levels_are_exactly_the_four(self, engine: Engine) -> None:
        from eaios_core.classification import Classification

        with engine.connect() as conn:
            labels = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid"
                        " WHERE t.typname = 'classification_level'"
                    )
                )
            }
        assert labels == {level.value for level in Classification}


class TestAuditTriggerExists:
    def test_the_append_only_trigger_is_installed(self, engine: Engine) -> None:
        with engine.connect() as conn:
            count = conn.execute(
                text("SELECT count(*) FROM pg_trigger WHERE tgname = 'audit_logs_append_only'")
            ).scalar_one()
        assert count == 1
