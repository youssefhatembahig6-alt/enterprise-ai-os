"""Row-Level Security enforcement (spec FR-009d, Constitution Principle I).

The property that matters most is the **default**. With no tenant set on the
session, the application role must see zero rows — a future code path that forgets
to scope returns nothing rather than everything. Failing closed is the only
acceptable direction for a security default, and it is the first thing asserted
here.

Ground truth comes from the owner connection, which bypasses RLS. Without it these
tests would only be proving that a filtered view is filtered.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import Engine, text

from eaios_core.db import tenant_scope
from eaios_core.models import tenant_tables

pytestmark = pytest.mark.security

#: Tables carrying the most sensitive tenant data. Checked individually because a
#: policy missing from any one of them is a real breach, not a rounding error.
HIGH_RISK_TABLES = (
    "users",
    "employee_profiles",
    "leave_balances",
    "documents",
    "contracts",
    "orders",
    "invoices",
    "audit_logs",
)


class TestFailsClosed:
    """With no tenant set, the app role sees nothing."""

    @pytest.mark.parametrize("table", HIGH_RISK_TABLES)
    def test_unset_tenant_returns_zero_rows(self, app_engine: Engine, table: str) -> None:
        with app_engine.connect() as conn:
            count = conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
        assert count == 0, (
            f"{table} returned {count} rows with no app.company_id set — "
            "the system is failing OPEN"
        )

    def test_the_data_actually_exists(self, owner_engine: Engine) -> None:
        """Guards against a vacuous pass: zero rows everywhere would satisfy the
        test above even if the database were empty."""
        with owner_engine.connect() as conn:
            for table in HIGH_RISK_TABLES:
                count = conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
                assert count > 0, f"{table} is empty; the isolation test would be vacuous"

    def test_empty_string_tenant_is_not_a_wildcard(self, app_engine: Engine) -> None:
        """`current_setting(..., true)` returns '' when unset; NULLIF makes that
        match nothing rather than erroring or matching everything."""
        with app_engine.connect() as conn:
            conn.execute(text("SELECT set_config('app.company_id', '', true)"))
            count = conn.execute(text("SELECT count(*) FROM users")).scalar_one()
        assert count == 0


class TestTenantScoping:
    @pytest.mark.parametrize("slug", ["niletech", "delta-retail"])
    def test_scoped_session_sees_only_its_own_rows(
        self, app_session, company_ids: dict[str, uuid.UUID], slug: str
    ) -> None:  # type: ignore[no-untyped-def]
        own = company_ids[slug]
        other = company_ids["delta-retail" if slug == "niletech" else "niletech"]

        with tenant_scope(app_session, own) as session:
            for table in HIGH_RISK_TABLES:
                foreign = session.execute(
                    text(f"SELECT count(*) FROM {table} WHERE company_id = :other"),
                    {"other": other},
                ).scalar_one()
                assert foreign == 0, f"{table} leaked {foreign} rows from the other tenant"

    @pytest.mark.parametrize("slug", ["niletech", "delta-retail"])
    def test_scoped_session_sees_all_of_its_own_rows(
        self, app_session, owner_engine: Engine, company_ids: dict[str, uuid.UUID], slug: str
    ) -> None:  # type: ignore[no-untyped-def]
        """Isolation must not over-filter: a tenant must still see its own data."""
        company_id = company_ids[slug]
        with owner_engine.connect() as conn:
            expected = conn.execute(
                text("SELECT count(*) FROM users WHERE company_id = :cid"),
                {"cid": company_id},
            ).scalar_one()

        with tenant_scope(app_session, company_id) as session:
            actual = session.execute(text("SELECT count(*) FROM users")).scalar_one()
        assert actual == expected

    def test_switching_tenant_switches_the_view(
        self, app_session, company_ids: dict[str, uuid.UUID]
    ) -> None:  # type: ignore[no-untyped-def]
        with tenant_scope(app_session, company_ids["niletech"]) as session:
            first = session.execute(text("SELECT slug FROM companies")).scalar_one()
        with tenant_scope(app_session, company_ids["delta-retail"]) as session:
            second = session.execute(text("SELECT slug FROM companies")).scalar_one()
        assert (first, second) == ("niletech", "delta-retail")

    def test_leaving_the_scope_restores_the_closed_default(
        self, app_session, company_ids: dict[str, uuid.UUID]
    ) -> None:  # type: ignore[no-untyped-def]
        """A session returned to the pool must not carry the previous tenant."""
        with tenant_scope(app_session, company_ids["niletech"]):
            pass
        count = app_session.execute(text("SELECT count(*) FROM users")).scalar_one()
        assert count == 0

    def test_an_unknown_tenant_sees_nothing(self, app_session) -> None:  # type: ignore[no-untyped-def]
        with tenant_scope(app_session, uuid.uuid4()) as session:
            assert session.execute(text("SELECT count(*) FROM users")).scalar_one() == 0


class TestPolicyCoverage:
    def test_every_tenant_table_has_a_policy(self, owner_engine: Engine) -> None:
        """Migration 0002 derives its list from the model metadata, so a newly added
        table gets a policy automatically. This asserts that actually happened."""
        with owner_engine.connect() as conn:
            covered = {
                row[0]
                for row in conn.execute(
                    text("SELECT tablename FROM pg_policies WHERE policyname = 'tenant_isolation'")
                )
            }
        missing = sorted(set(tenant_tables()) - covered)
        assert missing == [], f"tenant tables without an RLS policy: {missing}"

    def test_rls_is_enabled_not_merely_defined(self, owner_engine: Engine) -> None:
        """A policy on a table without RLS enabled does nothing at all."""
        with owner_engine.connect() as conn:
            disabled = [
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT c.relname FROM pg_class c"
                        " JOIN pg_namespace n ON n.oid = c.relnamespace"
                        " WHERE n.nspname = 'public' AND c.relkind = 'r'"
                        " AND NOT c.relrowsecurity AND c.relname = ANY(:tables)"
                    ),
                    {"tables": tenant_tables()},
                )
            ]
        assert disabled == [], f"RLS not enabled on: {sorted(disabled)}"

    def test_the_app_role_cannot_bypass_rls(self, owner_engine: Engine) -> None:
        """BYPASSRLS or superuser on the app role would silently disable every
        policy while leaving them all present and looking correct."""
        with owner_engine.connect() as conn:
            row = conn.execute(
                text("SELECT rolbypassrls, rolsuper FROM pg_roles WHERE rolname = 'eaios_app'")
            ).first()
        assert row is not None, "eaios_app role is missing"
        assert row.rolbypassrls is False
        assert row.rolsuper is False


class TestAuditImmutability:
    def test_audit_log_rejects_update(self, owner_engine: Engine) -> None:
        with pytest.raises(Exception, match="append-only"), owner_engine.begin() as conn:
            conn.execute(text("UPDATE audit_logs SET reason = 'tampered'"))

    def test_audit_log_rejects_delete(self, owner_engine: Engine) -> None:
        with pytest.raises(Exception, match="append-only"), owner_engine.begin() as conn:
            conn.execute(text("DELETE FROM audit_logs"))

    def test_audit_rows_survived_the_attempts(self, owner_engine: Engine) -> None:
        with owner_engine.connect() as conn:
            count = conn.execute(
                text("SELECT count(*) FROM audit_logs WHERE actor_type = 'SEED'")
            ).scalar_one()
        assert count == 2, "expected one seed audit entry per tenant"


class TestTheOwnerExemptionIsDeliberate:
    """`FORCE ROW LEVEL SECURITY` is withheld on purpose, and that has to stay true.

    PostgreSQL exempts a table's owner from its own RLS policies. Migration 0002
    relies on that exemption and says so: it is what lets `eaios_owner` run
    migrations and seed both tenants. Two later pieces depend on it as well — the
    FR-024b retention purge deletes aged contact submissions as the owner precisely
    because `eaios_app` holds only `SELECT, INSERT` on that table, and the seed's
    reset truncates as the owner.

    Nothing pinned this. `specs/002-public-website/data-model.md` stated that
    migration 0003 "enables and **forces** RLS", which is the opposite of what the
    code does and of what it must do; a reader who trusted the document and
    "corrected" the migration would have broken migrations, seeding, and retention in
    one change, and no test would have objected. The document is now correct, and
    this is the guard that keeps the code correct.

    Note what is *not* being asserted: that RLS is weak. `TestFailsClosed` and
    `TestTenantScoping` above prove the policy holds for `eaios_app`, which is the
    role every request runs as. The owner is not a request path.
    """

    def test_rls_is_enabled_on_every_tenant_table(self, owner_engine: Engine) -> None:
        from eaios_core.models import tenant_tables

        with owner_engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class"
                    " WHERE relname = ANY(:names)"
                ),
                {"names": list(tenant_tables())},
            ).all()

        assert rows, "no tenant tables found; the comparison would be empty"
        not_enabled = sorted(row.relname for row in rows if not row.relrowsecurity)
        assert not_enabled == [], f"RLS is not enabled on: {not_enabled}"

    def test_rls_is_not_forced_on_any_tenant_table(self, owner_engine: Engine) -> None:
        from eaios_core.models import tenant_tables

        with owner_engine.connect() as conn:
            forced = sorted(
                row.relname
                for row in conn.execute(
                    text(
                        "SELECT relname, relforcerowsecurity FROM pg_class"
                        " WHERE relname = ANY(:names)"
                    ),
                    {"names": list(tenant_tables())},
                ).all()
                if row.relforcerowsecurity
            )

        assert forced == [], (
            f"FORCE ROW LEVEL SECURITY is set on {forced}. The owner role would then be"
            " subject to its own policies, which breaks `alembic upgrade`, the seed, and"
            " the FR-024b retention purge. See migration 0002's docstring."
        )

    def test_the_owner_can_still_read_across_tenants(self, owner_engine: Engine) -> None:
        """The exemption, demonstrated rather than inferred from a catalogue flag.

        If FORCE were ever set, this query would return one tenant's rows or none —
        the assertion above would catch the flag, and this catches the consequence.
        """
        with owner_engine.connect() as conn:
            companies = conn.execute(text("SELECT count(DISTINCT company_id) FROM services")).scalar_one()

        assert companies >= 2, (
            f"the owner sees {companies} tenant(s) in `services`; the seed writes two,"
            " so the owner's RLS exemption is not in force"
        )
