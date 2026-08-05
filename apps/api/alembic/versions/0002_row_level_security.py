"""Row-Level Security on every tenant-owned table.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-01

Constitution Principle I (NON-NEGOTIABLE) requires RLS as the final safety net, and
spec FR-009d makes it an explicit requirement. Application-level filtering stays
mandatory regardless — this is a backstop, not a substitute.

Two design points worth stating:

* ``FORCE ROW LEVEL SECURITY`` is deliberately **not** set. PostgreSQL exempts table
  owners from RLS, and that exemption is what lets ``eaios_owner`` run migrations and
  seed both tenants. The application role ``eaios_app`` is a non-owner, so policies
  apply to it in full.
* The policy compares against ``current_setting('app.company_id', true)``, which
  returns NULL when unset. ``company_id = NULL`` is never true, so a session that
  forgets to set a tenant sees **zero rows** — the system fails closed.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from eaios_core.models import tenant_tables

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POLICY = "tenant_isolation"
_APP_ROLE = "eaios_app"


def upgrade() -> None:
    # `baseline_only` because this revision runs before any later migration's tables
    # exist. Each of those applies its own policy where it is created, and
    # `tests/security/test_rls.py` walks the *full* list, so an omission fails there.
    for table in tenant_tables(baseline_only=True):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {_POLICY} ON {table}
            USING (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)
            """
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO {_APP_ROLE}")

    # The application never deletes tenant data in this feature; withholding DELETE
    # keeps the blast radius of a future bug smaller.
    op.execute(f"GRANT SELECT ON audit_logs TO {_APP_ROLE}")

    # Global tables are readable by the app role but carry no tenant predicate.
    for table in ("permissions", "platform_administrators", "dataset_manifest"):
        op.execute(f"GRANT SELECT ON {table} TO {_APP_ROLE}")


def downgrade() -> None:
    for table in tenant_tables(baseline_only=True):
        op.execute(f"DROP POLICY IF EXISTS {_POLICY} ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE SELECT, INSERT, UPDATE ON {table} FROM {_APP_ROLE}")

    for table in ("permissions", "platform_administrators", "dataset_manifest"):
        op.execute(f"REVOKE SELECT ON {table} FROM {_APP_ROLE}")
