"""Fixtures for the authentication and authorization suites (spec 003).

Not a test module. It exists so each security file states *what it is checking* rather
than restating how to reach the API and how to find a seeded person.

**Against the app in-process, not the deployed container.** The existing anonymous
suite drives a live API over HTTP, which is right for it — it is checking the deployed
boundary. These files check decisions, and running the same ASGI app in-process gives
the identical middleware stack, exception handlers, and routing without a rebuild
between every change. The deployed path is still covered: Playwright drives the real
container through a browser.

**Seeded people, never invented ones.** FR-033 requires the manager scenario to use
seeded users, and the reason generalises. A fixture user is a user whose relationships
the test author chose; a seeded one has the relationships the generator produced, which
is what makes "changing a reporting line in the data changes the reachable set" (FR-026)
a claim about the system rather than about the fixture.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from eaios_core.db import create_owner_engine

DEMO_PASSWORD = "eaios-demo-local-only"

#: Personas the generator guarantees (spec 001 FR-025b). Named rather than discovered
#: so a test failure says which person it was about.
MANAGER = "manager.engineering"
EMPLOYEE = "employee.engineering"
SALES_EMPLOYEE = "employee.sales"
HR = "hr.generalist"
DELTA_EMPLOYEE = "employee.delta"


@dataclass(frozen=True, slots=True)
class Person:
    """A seeded user, as the tests need to refer to them."""

    user_id: uuid.UUID
    company_id: uuid.UUID
    email: str
    full_name: str
    department_id: uuid.UUID
    manager_id: uuid.UUID | None


def load_person(persona_key: str) -> Person:
    """Look one persona up through the owner connection.

    The owner engine deliberately: this is establishing ground truth about who exists,
    which is the denominator every isolation claim is measured against. Using the app
    role here would prove only that a filtered view is filtered.
    """
    engine = create_owner_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, company_id, email, full_name, department_id, manager_id"
                " FROM users WHERE persona_key = :key"
            ),
            {"key": persona_key},
        ).first()
    if row is None:
        pytest.skip(f"persona {persona_key!r} not seeded; run `make seed`")
    return Person(
        user_id=row.id,
        company_id=row.company_id,
        email=row.email,
        full_name=row.full_name,
        department_id=row.department_id,
        manager_id=row.manager_id,
    )


def direct_report_ids(user_id: uuid.UUID) -> list[uuid.UUID]:
    engine = create_owner_engine()
    with engine.connect() as conn:
        return [
            row.id
            for row in conn.execute(
                text("SELECT id FROM users WHERE manager_id = :m ORDER BY id"),
                {"m": user_id},
            )
        ]


def unrelated_colleague(person: Person) -> Person:
    """Someone in the same company, a different department, who does not report to
    ``person``. The subject of every "and nobody else" assertion."""
    engine = create_owner_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, company_id, email, full_name, department_id, manager_id"
                " FROM users"
                " WHERE company_id = :c AND department_id <> :d"
                "   AND (manager_id IS NULL OR manager_id <> :u) AND id <> :u"
                " ORDER BY id LIMIT 1"
            ),
            {"c": person.company_id, "d": person.department_id, "u": person.user_id},
        ).first()
    if row is None:
        pytest.skip("no unrelated colleague in the dataset; the denial cannot be shown")
    return Person(
        user_id=row.id,
        company_id=row.company_id,
        email=row.email,
        full_name=row.full_name,
        department_id=row.department_id,
        manager_id=row.manager_id,
    )


def credentials_are_provisioned() -> bool:
    engine = create_owner_engine()
    with engine.connect() as conn:
        return bool(conn.execute(text("SELECT count(*) FROM user_credentials")).scalar_one())


def sign_in(client: TestClient, email: str, password: str = DEMO_PASSWORD):  # type: ignore[no-untyped-def]
    return client.post("/auth/login", json={"email": email, "password": password})


def token_for(client: TestClient, persona_key: str) -> str:
    """Sign in as a persona and return the bearer token.

    Asserts success rather than returning an optional: every caller needs a working
    session, and a test that silently proceeded without one would assert things about
    an anonymous caller while claiming to be about an authenticated one.
    """
    person = load_person(persona_key)
    response = sign_in(client, person.email)
    assert response.status_code == 200, (
        f"could not sign in as {persona_key} ({person.email}): "
        f"{response.status_code} {response.text[:200]}"
    )
    return str(response.json()["access_token"])


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
