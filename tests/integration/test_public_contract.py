"""The public API against its published contract (spec 002, plan: contracts/).

Feature 001 established this pattern in `test_health_contract.py`, and feature 002
wrote `contracts/public-api.yaml` without the matching check. The cost was concrete:
the document declared `Problem` and `ValidationProblem` for the error responses,
FastAPI published its default `HTTPValidationError` instead, and the API returned a
third thing again for 404 — three descriptions of one surface, none of which agreed,
through fourteen phases of this feature. `packages/contracts` is generated from the
published schema, so the web client had to hand-write the real error shape.

Two comparisons, because they catch different failures:

* **The document against the served schema.** Checked in *both* directions. A path
  the contract describes but the API does not serve is as much a defect as an
  endpoint the contract has never heard of — the first is a promise to a consumer
  that nothing keeps, the second is an undocumented public surface.
* **Real response bodies against their declared schemas**, including an error body,
  which is the case that actually drifted. A schema comparison alone would have
  missed the 404: the contract and the code can agree on a name while the handler
  sends something else entirely.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, ClassVar

import httpx
import pytest

pytestmark = pytest.mark.integration

CONTRACT = (
    Path(__file__).resolve().parents[2]
    / "specs"
    / "002-public-website"
    / "contracts"
    / "public-api.yaml"
)
# Read from the environment, as every other feature-002 test does. Feature 001's
# contract test hard-codes this, which is why it skips wherever the suite runs
# somewhere other than the host — and a file that skips is a file that checks
# nothing.
BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")


@pytest.fixture(scope="module")
def client() -> httpx.Client:
    with httpx.Client(base_url=BASE_URL, timeout=15.0) as session:
        try:
            session.get("/health/live")
        except httpx.HTTPError:  # pragma: no cover - environment guard
            pytest.skip("API is not running; start it with `make up`")
        yield session


@pytest.fixture(scope="module")
def served(client: httpx.Client) -> dict[str, Any]:
    return dict(client.get("/openapi.json").json())


@pytest.fixture(scope="module")
def contract_paths() -> set[str]:
    """Paths declared in the contract document.

    Read with a line scan rather than a YAML parser: the repository's Python
    environment carries no YAML dependency, and the structure being read here is two
    levels deep. An earlier ad-hoc parser in this area reported a field as missing
    that the document plainly declares, so this one is deliberately narrow — it
    reads path keys only, and everything else comes from the served schema.
    """
    text = CONTRACT.read_text(encoding="utf-8")
    body = text.split("\npaths:", 1)[1].split("\ncomponents:", 1)[0]
    return {m.group(1) for m in re.finditer(r"^  (/[^\s:]*):\s*$", body, re.M)}


class TestTheComparisonHasSubjects:
    """Guards every assertion below. Two empty sets are equal, and this feature has
    rediscovered that failure often enough to check for it first."""

    def test_the_contract_declares_paths(self, contract_paths: set[str]) -> None:
        assert len(contract_paths) >= 8, f"only parsed {contract_paths} from the contract"

    def test_the_api_serves_public_paths(self, served: dict[str, Any]) -> None:
        assert len([p for p in served["paths"] if p.startswith("/public")]) >= 8

    def test_the_contract_file_is_the_one_the_feature_ships(self) -> None:
        assert CONTRACT.exists(), f"{CONTRACT} does not exist"
        assert "ValidationProblem" in CONTRACT.read_text(encoding="utf-8")


class TestPathsAgree:
    def test_every_documented_path_is_served(
        self, contract_paths: set[str], served: dict[str, Any]
    ) -> None:
        missing = sorted(contract_paths - set(served["paths"]))
        assert missing == [], f"the contract promises paths the API does not serve: {missing}"

    def test_every_public_path_is_documented(
        self, contract_paths: set[str], served: dict[str, Any]
    ) -> None:
        undocumented = sorted(
            path for path in served["paths"] if path.startswith("/public") and path not in contract_paths
        )
        assert undocumented == [], f"undocumented public endpoints: {undocumented}"


class TestErrorResponsesAreDeclared:
    """The half that drifted, and the reason this file exists."""

    def test_the_contact_422_declares_the_shape_it_returns(self, served: dict[str, Any]) -> None:
        schema = served["paths"]["/public/contact"]["post"]["responses"]["422"]["content"][
            "application/json"
        ]["schema"]
        assert schema["$ref"].endswith("/ValidationProblem"), (
            f"the published 422 schema is {schema} — FastAPI's default was advertised here "
            "while the API returned a field-addressed body"
        )

    @pytest.mark.parametrize("path", ["/public/news/{slug}", "/public/vacancies/{slug}"])
    def test_detail_routes_declare_a_404_body(self, served: dict[str, Any], path: str) -> None:
        response = served["paths"][path]["get"]["responses"]["404"]
        assert "content" in response, f"{path} declares a 404 with no schema at all"
        assert response["content"]["application/json"]["schema"]["$ref"].endswith("/Problem")

    def test_a_real_404_body_matches_its_schema(
        self, client: httpx.Client, served: dict[str, Any]
    ) -> None:
        """Schemas agreeing with each other is not the same as the server agreeing
        with both. The 404 handler previously sent `{"detail": ...}` while every
        document said otherwise."""
        schemas = served["components"]["schemas"]
        assert "Problem" in schemas, "the API publishes no Problem schema for its 404s"

        body = client.get("/public/news/no-such-article-000000").json()
        properties = schemas["Problem"]["properties"]

        assert set(body) <= set(properties), f"404 body carries undeclared fields: {body}"
        for required in ("title", "status"):
            assert required in body, f"404 body omits {required}"
        assert body["status"] == 404

    def test_a_real_422_body_matches_its_schema(
        self, client: httpx.Client, served: dict[str, Any]
    ) -> None:
        # Presence checked before use: with nothing declaring the model, the lookup
        # below raised a bare `KeyError` during the falsification run — a correct
        # failure with a message that explained nothing.
        schemas = served["components"]["schemas"]
        assert "ValidationProblem" in schemas, (
            "the API publishes no ValidationProblem schema, so the 422 it returns is undeclared"
        )

        body = client.post("/public/contact", json={"sender_name": "", "sender_email": "bad"}).json()
        properties = schemas["ValidationProblem"]["properties"]

        assert set(body) <= set(properties), f"422 body carries undeclared fields: {body}"
        assert body["status"] == 422
        assert body["errors"], "a rejected submission named no field"
        for error in body["errors"]:
            assert set(error) == {"field", "message"}


class TestSuccessResponsesMatchTheirSchemas:
    """One real body per collection endpoint. The field allowlist is enforced by
    `tests/security/test_public_field_allowlist.py`; what is checked here is the
    narrower contract question — does the served body match the schema the document
    publishes for it."""

    ENDPOINTS: ClassVar[dict[str, str]] = {
        "/public/services": "ServiceOut",
        "/public/products": "ProductOut",
        "/public/leadership": "LeadershipOut",
        "/public/offices": "OfficeOut",
        "/public/vacancies": "VacancyOut",
    }

    @pytest.mark.parametrize("path,schema_name", sorted(ENDPOINTS.items()))
    def test_each_item_matches_the_declared_schema(
        self, client: httpx.Client, served: dict[str, Any], path: str, schema_name: str
    ) -> None:
        items = client.get(path).json()
        assert items, f"{path} returned nothing to compare"

        schema = served["components"]["schemas"][schema_name]
        declared = set(schema["properties"])
        required = set(schema.get("required", []))

        for item in items:
            assert set(item) == declared, (
                f"{path} item fields {sorted(set(item))} != declared {sorted(declared)}"
            )
            assert required <= set(item)

    def test_the_company_endpoint_matches_its_schema(
        self, client: httpx.Client, served: dict[str, Any]
    ) -> None:
        body = client.get("/public/company").json()
        assert set(body) == set(served["components"]["schemas"]["CompanyOut"]["properties"])

    def test_the_news_page_matches_its_schema(
        self, client: httpx.Client, served: dict[str, Any]
    ) -> None:
        body = client.get("/public/news").json()
        assert set(body) == set(served["components"]["schemas"]["NewsPage"]["properties"])
        assert body["items"], "the news page returned no items to compare"
        assert set(body["items"][0]) == set(served["components"]["schemas"]["NewsOut"]["properties"])
