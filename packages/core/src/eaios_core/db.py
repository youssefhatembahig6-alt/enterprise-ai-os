"""Database engine, sessions, and the RLS tenant context (research R6).

Row-Level Security is bound to a session-scoped setting, ``app.company_id``, rather
than to an authenticated principal — because there is no authentication yet
(decision D1). The next feature sets the same variable from a verified token claim
instead of from a fixture, and no policy changes.

The important property is the default. With no tenant set, an ``eaios_app`` session
sees **zero rows**: the system fails closed. A future code path that forgets to set
the tenant returns nothing rather than everything, which is the only acceptable
direction for a security default (spec FR-009d).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from .settings import Settings, get_settings

__all__ = [
    "TENANT_SETTING",
    "create_app_engine",
    "create_owner_engine",
    "session_scope",
    "tenant_scope",
]

#: PostgreSQL session variable the RLS policies read.
TENANT_SETTING = "app.company_id"


def create_app_engine(settings: Settings | None = None, **kwargs: object) -> Engine:
    """Engine for the API and worker. RLS is enforced against this role."""
    cfg = settings or get_settings()
    return create_engine(cfg.postgres.url(as_owner=False), pool_pre_ping=True, **kwargs)


def create_owner_engine(settings: Settings | None = None, **kwargs: object) -> Engine:
    """Engine for migrations and seeding. Owns the tables, so RLS does not apply.

    Never use this to serve a request — it is the one connection that can see across
    tenants, and it exists only so the schema and the dataset can be created.
    """
    cfg = settings or get_settings()
    return create_engine(cfg.postgres.url(as_owner=True), pool_pre_ping=True, **kwargs)


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    """A transactional session that commits on success and rolls back on error."""
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def tenant_scope(session: Session, company_id: UUID | str) -> Iterator[Session]:
    """Run queries scoped to one tenant.

    Sets ``app.company_id`` for the duration and clears it on exit, so a leaked
    session cannot carry another request's tenant. ``set_config(..., true)`` makes
    the setting local to the current transaction.
    """
    session.execute(
        text(f"SELECT set_config('{TENANT_SETTING}', :company_id, true)"),
        {"company_id": str(company_id)},
    )
    try:
        yield session
    finally:
        session.execute(text(f"SELECT set_config('{TENANT_SETTING}', '', true)"))
