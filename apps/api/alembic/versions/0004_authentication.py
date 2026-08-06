"""Credentials and sessions.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-06

The first tables the system writes on behalf of an identified person (spec 003).
Both are tenant-owned and both are runtime state, which is the combination that
determines everything below:

* **Tenant-owned** — non-nullable ``company_id``, the same ``tenant_isolation``
  policy every other tenant table carries. A password hash is unambiguously a
  company-owned artifact, so it lives behind RLS rather than in a global table made
  convenient by the sign-in lookup (Constitution Principle I, research R4).
  Migration 0002 derived its list from ``tenant_tables()`` and has already run, so
  the policies are applied here explicitly — exactly as 0003 did.
* **Runtime, not generated** — excluded from the dataset fingerprint by never
  entering ``dataset.rows``, and added to ``RUNTIME_TABLES`` in ``scripts/seed`` so
  reset truncates them and the emptiness pre-flight counts them.

``DELETE`` is withheld from the application role, matching the existing posture.
Ending a session is an ``UPDATE``; nothing in this feature removes a row.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PgUUID

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREDENTIALS = "user_credentials"
_SESSIONS = "sessions"
_POLICY = "tenant_isolation"
_APP_ROLE = "eaios_app"

#: Both tables, in creation order. `sessions` has no dependency on `user_credentials`,
#: but keeping one list means the policy, grant, and teardown loops cannot disagree
#: about which tables this migration owns.
_TABLES = (_CREDENTIALS, _SESSIONS)


def upgrade() -> None:
    op.create_table(
        _CREDENTIALS,
        sa.Column("id", PgUUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            PgUUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            PgUUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Argon2id encoded string: algorithm, parameters, and a per-hash random salt
        # all travel with the value, so a later parameter change is a per-hash
        # migration rather than a flag day.
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", TIMESTAMP(timezone=True), nullable=False),
        # Bare constraint names throughout this migration. `Base.metadata`'s naming
        # convention (`ck_%(table_name)s_%(constraint_name)s`) is applied by the
        # migration context too, so a name that already carries the prefix comes out
        # doubled — `ck_sessions_ck_sessions_expiry_after_issue`. Migration 0003 does
        # exactly that, and two of its names then exceeded PostgreSQL's 63-character
        # identifier limit and were truncated with a hash suffix. Nothing noticed,
        # because `test_migrations.py` snapshots columns and not constraint names.
        # No name at all here, unlike the check constraints below. The unique
        # convention is `uq_%(table_name)s_%(column_0_N_name)s` — it builds the name
        # from the *column*, so any explicit name wins over it and produces something
        # the metadata does not describe. Omitting it is what matches the model.
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_user_credentials_company_id", _CREDENTIALS, ["company_id"])

    op.create_table(
        _SESSIONS,
        sa.Column("id", PgUUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            PgUUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            PgUUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("issued_at", TIMESTAMP(timezone=True), nullable=False),
        # Set at sign-in and never moved. `last_seen_at` advances with use; a single
        # combined "expires at" would silently discard the absolute cap, which is the
        # only bound limiting how long a stolen credential stays useful (FR-005).
        sa.Column("absolute_expires_at", TIMESTAMP(timezone=True), nullable=False),
        sa.Column("last_seen_at", TIMESTAMP(timezone=True), nullable=False),
        sa.Column("ended_at", TIMESTAMP(timezone=True), nullable=True),
        sa.Column("ended_reason", sa.String(16), nullable=True),
        sa.Column("created_at", TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", TIMESTAMP(timezone=True), nullable=False),
        # Bare names — see the note on `user_credentials` above. These must match
        # `models/auth.py` exactly, so a schema built from migrations and one built
        # from the metadata describe the same database.
        sa.CheckConstraint("absolute_expires_at > issued_at", name="expiry_after_issue"),
        sa.CheckConstraint(
            "ended_reason IN ('SIGN_OUT','IDLE','ABSOLUTE')",
            name="ended_reason_values",
        ),
        # Both columns say the session ended, or neither does. Refused here rather
        # than interpreted by every query that reads the row.
        sa.CheckConstraint(
            "(ended_at IS NULL) = (ended_reason IS NULL)", name="ended_consistently"
        ),
    )
    op.create_index("ix_sessions_company_id", _SESSIONS, ["company_id"])
    # The shape every session lookup uses: this tenant's live sessions for one user.
    op.create_index(
        "ix_sessions_company_user_id_ended_at",
        _SESSIONS,
        ["company_id", "user_id", "ended_at"],
    )

    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {_POLICY} ON {table}
            USING (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)
            """
        )
        # UPDATE is needed on `sessions` to advance `last_seen_at` and to end a
        # session; `user_credentials` gets it so re-provisioning can rewrite a hash
        # in place rather than deleting and reinserting, which it has no DELETE for.
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO {_APP_ROLE}")


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.execute(f"REVOKE SELECT, INSERT, UPDATE ON {table} FROM {_APP_ROLE}")
        op.execute(f"DROP POLICY IF EXISTS {_POLICY} ON {table}")

    op.drop_index("ix_sessions_company_user_id_ended_at", table_name=_SESSIONS)
    op.drop_index("ix_sessions_company_id", table_name=_SESSIONS)
    op.drop_table(_SESSIONS)

    op.drop_index("ix_user_credentials_company_id", table_name=_CREDENTIALS)
    op.drop_table(_CREDENTIALS)
