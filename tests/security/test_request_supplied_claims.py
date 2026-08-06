"""Nothing in a request can change who the caller is (spec 003 FR-010, FR-035, SC-005).

FR-010 is the most absolute sentence in the specification: the system MUST NOT accept a
tenant, identity, role, or permission value from any request parameter, header, cookie,
or body. The reason it is absolute is that a single trusted field *is* the boundary —
the moment one attribute can be supplied, the access context stops describing who is
asking and starts describing who they claimed to be.

**The assertion shape matters more than the coverage.** SC-005 says supplying such a
value changes the response in *zero* cases, and the tempting test — "the manipulated
request returns nothing" — is nearly worthless: a manipulated request that fails for an
unrelated reason also returns nothing. Every test here asserts the manipulated response
is **equal** to the clean one.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from eaios_core.db import create_owner_engine

from .auth_helpers import DELTA_EMPLOYEE, EMPLOYEE, auth, load_person, token_for

pytestmark = pytest.mark.security

PROTECTED = "/me/access-context"


@pytest.fixture(scope="module")
def clean(client: TestClient) -> tuple[str, dict[str, object]]:
    """One unmanipulated response, as the baseline every comparison uses."""
    token = token_for(client, EMPLOYEE)
    response = client.get(PROTECTED, headers=auth(token))
    assert response.status_code == 200, response.text
    return token, dict(response.json())


class TestTheBaselineIsReal:
    """Every comparison below is `manipulated == clean`. If the baseline were empty or
    an error body, the manipulated responses would match it trivially."""

    def test_the_clean_response_describes_the_signed_in_person(
        self, clean: tuple[str, dict[str, object]]
    ) -> None:
        person = load_person(EMPLOYEE)
        _, body = clean
        assert body["user_id"] == str(person.user_id)
        assert body["company_id"] == str(person.company_id)
        assert body["permissions"], "the baseline caller holds no permissions at all"


class TestSuppliedTenantIsIgnored:
    @pytest.mark.parametrize(
        "supply",
        ["query", "header", "cookie", "body"],
    )
    def test_a_company_id_changes_nothing(
        self, client: TestClient, clean: tuple[str, dict[str, object]], supply: str
    ) -> None:
        token, baseline = clean
        other = _other_tenant_id()
        headers = auth(token)
        kwargs: dict[str, object] = {"headers": headers}

        url = f"{PROTECTED}?company_id={other}" if supply == "query" else PROTECTED
        if supply == "header":
            headers["X-Company-Id"] = str(other)
            headers["X-Tenant"] = str(other)
        if supply == "cookie":
            headers["cookie"] = f"company_id={other}; tenant_id={other}"
        if supply == "body":
            # A GET with a body is unusual and entirely legal, which is exactly why it
            # is worth checking: a handler that read the body "just in case" would be
            # invisible to a test that only varied the query string.
            kwargs["content"] = f'{{"company_id": "{other}"}}'.encode()
            headers["content-type"] = "application/json"

        # `request` rather than `get`: httpx's `get` signature accepts neither a body
        # nor per-request cookies, and both are cases this test exists to cover.
        response = client.request("GET", url, **kwargs)  # type: ignore[arg-type]
        assert response.status_code == 200, response.text
        assert response.json() == baseline, (
            f"supplying a company_id via {supply} changed the response — the tenant"
            " must come from the verified identity and nowhere else (FR-010)"
        )


class TestSuppliedRolesAndPermissionsAreIgnored:
    @pytest.mark.parametrize(
        ("name", "value"),
        [
            ("roles", "Company Admin"),
            ("permissions", "hr:read_all"),
            ("permission", "audit:read"),
            ("user_id", "00000000-0000-0000-0000-000000000001"),
            ("sub", "00000000-0000-0000-0000-000000000001"),
        ],
    )
    def test_supplying_it_changes_nothing(
        self,
        client: TestClient,
        clean: tuple[str, dict[str, object]],
        name: str,
        value: str,
    ) -> None:
        token, baseline = clean
        headers = auth(token)
        headers[f"X-{name.replace('_', '-').title()}"] = value

        response = client.get(f"{PROTECTED}?{name}={value}", headers=headers)
        assert response.status_code == 200, response.text
        assert response.json() == baseline, (
            f"supplying {name}={value!r} changed the access context"
        )

    def test_a_widened_permission_does_not_reach_a_protected_read(
        self, client: TestClient
    ) -> None:
        """The consequence, not just the context. An employee claiming `hr:read_all`
        must still be refused compensation — a context that ignored the claim but a
        route that read it would be a hole this file's other tests cannot see."""
        person = load_person(EMPLOYEE)
        token = token_for(client, EMPLOYEE)
        response = client.get(
            f"/hr/profiles/{person.user_id}/compensation?permissions=hr:read_all",
            headers={**auth(token), "X-Permissions": "hr:read_all"},
        )
        assert response.status_code == 403, response.text


class TestACredentialCannotBeMovedBetweenTenants:
    def test_a_delta_token_does_not_reach_niletech_records(
        self, client: TestClient
    ) -> None:
        """A validly-signed credential for one tenant, presented against the other's
        record. The signature covers `cid`, so editing the claim breaks the token; what
        this checks is the replay of an intact one."""
        delta_token = token_for(client, DELTA_EMPLOYEE)
        niletech = load_person(EMPLOYEE)

        response = client.get(
            f"/hr/profiles/{niletech.user_id}", headers=auth(delta_token)
        )
        assert response.status_code == 404, (
            "a cross-tenant record must be *absent*, not forbidden — 403 confirms it"
            f" exists (FR-021, FR-030); got {response.status_code}"
        )

    def test_the_delta_caller_still_reaches_their_own_records(
        self, client: TestClient
    ) -> None:
        """Without this, the 404 above is satisfied by a Delta caller who can reach
        nothing at all."""
        delta_token = token_for(client, DELTA_EMPLOYEE)
        person = load_person(DELTA_EMPLOYEE)
        response = client.get(f"/hr/profiles/{person.user_id}", headers=auth(delta_token))
        assert response.status_code == 200, response.text


class TestTheAttemptIsRecorded:
    def test_supplying_a_tenant_writes_an_audit_entry(self, client: TestClient) -> None:
        """FR-010 says the attempt SHOULD be recorded. A value that is ignored silently
        is a probe nobody sees; the whole point of noticing is being able to say
        afterwards that somebody tried."""
        token = token_for(client, EMPLOYEE)
        before = _audit_count("authz.tenant_value_supplied")
        client.get(
            f"{PROTECTED}?company_id={_other_tenant_id()}",
            headers={**auth(token), "X-Company-Id": str(_other_tenant_id())},
        )
        assert _audit_count("authz.tenant_value_supplied") > before


def _other_tenant_id() -> uuid.UUID:
    person = load_person(EMPLOYEE)
    with create_owner_engine().connect() as conn:
        row = conn.execute(
            text("SELECT id FROM companies WHERE id <> :c LIMIT 1"),
            {"c": person.company_id},
        ).first()
    assert row is not None, "only one tenant exists; cross-tenant cases cannot be shown"
    return uuid.UUID(str(row.id))


def _audit_count(action: str) -> int:
    with create_owner_engine().connect() as conn:
        return int(
            conn.execute(
                text("SELECT count(*) FROM audit_logs WHERE action = :a"), {"a": action}
            ).scalar_one()
        )
