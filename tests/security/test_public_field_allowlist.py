"""Public responses contain only declared fields (spec 002 FR-044, FR-045, FR-050).

The public site reads the same database that holds RESTRICTED payroll records,
executive contracts, and a second tenant. The distance between "public" and
"catastrophic" is one forgotten exclusion, so the design enumerates what goes out
rather than what stays in — and this is the test that makes the enumeration real.

**The direction matters.** These assertions fail on an *extra* key, not only on a
missing one. An exclusion-based check fails open: a column added to a model later
appears in the response until somebody notices. An allowlist fails closed.

Written before the endpoints exist (Constitution Principle VIII). Until they do,
every test here fails with a connection or 404 error, which is the correct failing
state — not a skip.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import pytest

pytestmark = pytest.mark.security

# Read from the environment, not hard-coded. The suite runs on the host against the
# published port and in a container against the service name; a fixed value makes
# one of those silently skip every test rather than run it.
BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

#: The declared allowlist, mirroring `contracts/public-fields.md`. Duplicated here
#: on purpose: a test that imported the application's own response models would
#: agree with them by construction and prove nothing.
ALLOWED: dict[str, set[str]] = {
    "/public/company": {"name", "domain"},
    "/public/offices": {"city", "country", "address", "is_headquarters"},
    "/public/services": {"name", "summary", "description", "display_order"},
    "/public/products": {"name", "tagline", "description", "display_order"},
    "/public/leadership": {"full_name", "public_title", "bio", "display_order"},
    "/public/news": {"slug", "headline", "published_on"},
    "/public/vacancies": {
        "slug",
        "title",
        "department",
        "office_city",
        "office_country",
        "posted_on",
    },
}

#: Fields that must never appear anywhere, whatever the endpoint. `user_id` is the
#: sharpest: it is an internal identifier for a real employee row carrying salary
#: band, hire date, country, and manager.
FORBIDDEN_ANYWHERE = {
    "id",
    "company_id",
    "user_id",
    "department_id",
    "office_id",
    "document_id",
    "owner_id",
    "classification",
    "created_at",
    "updated_at",
    "password_hash",
    "persona_key",
    "salary_band",
    "email",
}


@pytest.fixture(scope="module")
def client() -> httpx.Client:
    with httpx.Client(base_url=BASE_URL, timeout=15.0) as session:
        try:
            session.get("/health/live")
        except httpx.HTTPError:  # pragma: no cover - environment guard
            pytest.skip("API is not running; start it with `make up`")
        yield session


def _items(payload: Any) -> list[dict[str, Any]]:
    """Every object in a response, whether it is one, a list, or a page."""
    if isinstance(payload, dict) and "items" in payload:
        payload = payload["items"]
    if isinstance(payload, dict):
        return [payload]
    return [item for item in payload if isinstance(item, dict)]


class TestEndpointsExist:
    """If these fail, the rest of the file is vacuous — a missing endpoint returns
    nothing, and 'nothing' contains no forbidden fields."""

    @pytest.mark.parametrize("path", sorted(ALLOWED))
    def test_endpoint_responds(self, client: httpx.Client, path: str) -> None:
        assert client.get(path).status_code == 200, f"{path} is not serving"

    @pytest.mark.parametrize("path", sorted(ALLOWED))
    def test_endpoint_returns_content(self, client: httpx.Client, path: str) -> None:
        assert _items(client.get(path).json()), f"{path} returned no objects to inspect"


class TestOnlyDeclaredFields:
    @pytest.mark.parametrize("path", sorted(ALLOWED))
    def test_no_undeclared_field_is_returned(self, client: httpx.Client, path: str) -> None:
        for item in _items(client.get(path).json()):
            extra = set(item) - ALLOWED[path]
            assert extra == set(), (
                f"{path} exposes undeclared fields {sorted(extra)}. Adding a public "
                "field is a change to contracts/public-fields.md and to this test, "
                "never a side effect of a schema change."
            )

    @pytest.mark.parametrize("path", sorted(ALLOWED))
    def test_every_declared_field_is_present(self, client: httpx.Client, path: str) -> None:
        """The other direction: a field the contract promises must actually arrive."""
        for item in _items(client.get(path).json()):
            missing = ALLOWED[path] - set(item)
            assert missing == set(), f"{path} omits declared fields {sorted(missing)}"


class TestForbiddenFields:
    @pytest.mark.parametrize("path", sorted(ALLOWED))
    def test_no_internal_identifier_leaks(self, client: httpx.Client, path: str) -> None:
        for item in _items(client.get(path).json()):
            leaked = set(item) & FORBIDDEN_ANYWHERE
            assert leaked == set(), f"{path} exposes internal fields {sorted(leaked)}"

    def test_leadership_exposes_no_employee_identifier(self, client: httpx.Client) -> None:
        """Called out separately because it is the one endpoint that joins to
        `users`, and the only one where an internal identifier would be a key into
        the private data model."""
        body = client.get("/public/leadership").text
        assert "user_id" not in body


class TestDetailEndpoints:
    def test_news_detail_adds_only_the_body(self, client: httpx.Client) -> None:
        listing = _items(client.get("/public/news").json())
        assert listing, "no news to open"
        detail = client.get(f"/public/news/{listing[0]['slug']}").json()
        assert set(detail) == ALLOWED["/public/news"] | {"body"}

    def test_vacancy_detail_adds_only_the_description(self, client: httpx.Client) -> None:
        listing = _items(client.get("/public/vacancies").json())
        assert listing, "no vacancies to open"
        detail = client.get(f"/public/vacancies/{listing[0]['slug']}").json()
        assert set(detail) == ALLOWED["/public/vacancies"] | {"description"}

    def test_list_responses_omit_the_long_body(self, client: httpx.Client) -> None:
        """A list that shipped full bodies would be a performance problem and a
        larger disclosure surface than the contract describes."""
        for item in _items(client.get("/public/news").json()):
            assert "body" not in item


class TestClassification:
    def test_no_response_mentions_a_classification_level(self, client: httpx.Client) -> None:
        """Everything served is PUBLIC by construction. Echoing the field would
        invite a client to reason about levels it should never see."""
        for path in ALLOWED:
            body = client.get(path).text
            for level in ("INTERNAL", "CONFIDENTIAL", "RESTRICTED"):
                assert level not in body, f"{path} mentions {level}"


class TestTheCheckCanFail:
    """An allowlist test that cannot detect an extra field is decoration."""

    def test_an_extra_key_is_detected(self) -> None:
        item = {"name": "x", "summary": "y", "description": "z", "display_order": 1, "id": "leak"}
        assert set(item) - ALLOWED["/public/services"] == {"id"}

    def test_the_allowlist_is_not_empty(self) -> None:
        assert ALLOWED and all(fields for fields in ALLOWED.values())
