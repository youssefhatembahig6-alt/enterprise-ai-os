"""Fixtures for the tenant-isolation suite.

Two engines, deliberately:

* ``owner_engine`` is the schema owner. PostgreSQL exempts table owners from RLS,
  so this connection sees across tenants — it establishes *ground truth* about what
  exists, which is what makes "the app role saw none of it" a meaningful claim.
* ``app_engine`` is the non-owner application role. Every policy applies to it.

Asserting isolation using only the app role would be circular: you would be proving
that a filtered view is filtered. The owner connection is what supplies the
denominator.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from eaios_core.db import create_app_engine, create_owner_engine, tenant_scope


def _skip_unless_seeded(engine: Engine) -> None:
    try:
        with engine.connect() as conn:
            seeded = conn.execute(text("SELECT count(*) FROM companies")).scalar_one()
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"database unavailable: {exc}")
    if not seeded:
        pytest.skip("environment not seeded; run `make up && make seed`")


@pytest.fixture(scope="session")
def owner_engine() -> Engine:
    engine = create_owner_engine()
    _skip_unless_seeded(engine)
    return engine


@pytest.fixture(scope="session")
def app_engine() -> Engine:
    return create_app_engine()


@pytest.fixture(scope="session")
def company_ids(owner_engine: Engine) -> dict[str, uuid.UUID]:
    with owner_engine.connect() as conn:
        rows = conn.execute(text("SELECT slug, id FROM companies")).all()
    ids = dict(rows)
    assert set(ids) == {"niletech", "delta-retail"}, f"unexpected tenants: {sorted(ids)}"
    return ids


@pytest.fixture
def app_session(app_engine: Engine) -> Iterator[Session]:
    factory = sessionmaker(bind=app_engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def scoped_to(app_session: Session):  # type: ignore[no-untyped-def]
    """Return a helper that runs a query as the app role scoped to one tenant."""

    def _run(company_id: uuid.UUID, sql: str, **params: object) -> list[tuple]:
        with tenant_scope(app_session, company_id) as session:
            return list(session.execute(text(sql), params).all())

    return _run
