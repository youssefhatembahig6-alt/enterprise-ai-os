"""Initial schema — all tables, the classification enum, and the audit trigger.

Revision ID: 0001
Revises:
Create Date: 2026-08-01

This first migration builds the schema from the declarative metadata rather than
from 27 hand-written ``create_table`` blocks. For a greenfield initial revision that
is both accurate and reversible, and it removes an entire class of drift between the
models and the migration. Every *subsequent* migration is explicit — this shortcut
applies only to the baseline.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from eaios_core.classification import Classification
from eaios_core.models import Base, baseline_tables

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ENUM_NAME = "classification_level"

# Any consequential operation is evidence, so the log must not be quietly
# rewritable by the application that produces it (Constitution Principle X).
_AUDIT_IMMUTABILITY = """
CREATE OR REPLACE FUNCTION eaios_audit_is_append_only()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'audit_logs is append-only: % is not permitted', TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_logs_append_only
BEFORE UPDATE OR DELETE ON audit_logs
FOR EACH ROW EXECUTE FUNCTION eaios_audit_is_append_only();
"""

_AUDIT_IMMUTABILITY_DOWN = """
DROP TRIGGER IF EXISTS audit_logs_append_only ON audit_logs;
DROP FUNCTION IF EXISTS eaios_audit_is_append_only();
"""


def _baseline() -> list:
    """The Table objects this revision owns, in metadata order."""
    names = set(baseline_tables())
    return [table for table in Base.metadata.sorted_tables if table.name in names]


def upgrade() -> None:
    bind = op.get_bind()

    # The enum is declared with create_type=False on the model so its lifecycle is
    # owned here, where the downgrade can drop it in the right order.
    sa.Enum(*[c.value for c in Classification], name=_ENUM_NAME).create(bind, checkfirst=True)

    # Restricted to this revision's own tables. `create_all` reads the metadata at
    # migration time, so without this filter a model added by a later migration is
    # created here *and* by the migration that introduces it — which is exactly what
    # broke a fresh `upgrade head` once `contact_submissions` was added.
    Base.metadata.create_all(bind=bind, tables=_baseline())

    op.execute(_AUDIT_IMMUTABILITY)


def downgrade() -> None:
    bind = op.get_bind()

    op.execute(_AUDIT_IMMUTABILITY_DOWN)

    Base.metadata.drop_all(bind=bind, tables=_baseline())

    sa.Enum(name=_ENUM_NAME).drop(bind, checkfirst=True)
