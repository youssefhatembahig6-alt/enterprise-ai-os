"""The public site serves one tenant, and the caller cannot change which one
(spec 002 FR-009a, FR-052; Constitution Principle I).

Feature 001 generated `PUBLIC` content for **both** companies on purpose — its
FR-030 says public content is itself an isolation surface. This feature renders
NileTech only, which makes Delta Retail's public content exactly the right bait:
it exists, it is classified `PUBLIC`, and it must never appear here.

Two distinct claims are tested, because passing one does not imply the other:

1. **Nothing leaks** — Delta's marker phrases appear in no public response.
2. **Nothing can be made to leak** — no hostname, path, parameter, header, or body
   an anonymous caller can construct selects the other tenant. A site that happens
   to serve NileTech because that is the first row is not the same as one where the
   tenant is fixed.

Written before the endpoints exist (Constitution Principle VIII).
"""

from __future__ import annotations

import os

import httpx
import pytest

from eaios_seed.generators.markers import markers_for

pytestmark = pytest.mark.security

# Read from the environment, not hard-coded. The suite runs on the host against the
# published port and in a container against the service name; a fixed value makes
# one of those silently skip every test rather than run it.
BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

PUBLIC_PATHS = (
    "/public/company",
    "/public/offices",
    "/public/services",
    "/public/products",
    "/public/leadership",
    "/public/news",
    "/public/vacancies",
)

DELTA_MARKERS = tuple(markers_for("delta-retail"))
NILETECH_MARKERS = tuple(markers_for("niletech"))

#: Every way a caller might try to name a tenant. Each must be ignored.
TENANT_SELECTION_ATTEMPTS = (
    {"params": {"company": "delta-retail"}},
    {"params": {"company_id": "delta-retail"}},
    {"params": {"tenant": "delta-retail"}},
    {"params": {"slug": "delta-retail"}},
    {"headers": {"X-Company": "delta-retail"}},
    {"headers": {"X-Company-Id": "delta-retail"}},
    {"headers": {"X-Tenant": "delta-retail"}},
    {"headers": {"Host": "delta-retail.localhost"}},
)


@pytest.fixture(scope="module")
def client() -> httpx.Client:
    with httpx.Client(base_url=BASE_URL, timeout=15.0) as session:
        try:
            session.get("/health/live")
        except httpx.HTTPError:  # pragma: no cover - environment guard
            pytest.skip("API is not running; start it with `make up`")
        yield session


class TestTheBaitIsReal:
    """A leak test means nothing if the thing being hunted does not exist."""

    def test_delta_has_marker_phrases(self) -> None:
        assert DELTA_MARKERS and all(DELTA_MARKERS)

    def test_the_markers_are_distinctive(self) -> None:
        """Ordinary generated prose will never contain these by chance, which is
        what makes a hit unambiguous rather than a judgement call.

        Only the first marker is an uppercase token; the others are deliberately
        odd prose phrases ("vermilion armadillo restocking clause"). Length plus
        multi-word improbability is the property they share, not casing."""
        for marker in DELTA_MARKERS:
            assert len(marker) >= 20, f"{marker!r} is short enough to occur by chance"

    def test_the_two_tenants_have_different_markers(self) -> None:
        assert not (set(DELTA_MARKERS) & set(NILETECH_MARKERS))

    def test_public_endpoints_return_content(self, client: httpx.Client) -> None:
        """Without content, 'no Delta content' is true and worthless."""
        empty = [p for p in PUBLIC_PATHS if not client.get(p).text.strip("[]{} \n")]
        assert empty == [], f"endpoints returned nothing to inspect: {empty}"


class TestNoDeltaContentIsServed:
    @pytest.mark.parametrize("path", PUBLIC_PATHS)
    def test_no_delta_marker_appears(self, client: httpx.Client, path: str) -> None:
        body = client.get(path).text
        for marker in DELTA_MARKERS:
            assert marker not in body, f"{path} leaked Delta Retail content ({marker})"

    @pytest.mark.parametrize("path", PUBLIC_PATHS)
    def test_no_delta_identifier_appears(self, client: httpx.Client, path: str) -> None:
        body = client.get(path).text.lower()
        for term in ("delta retail", "delta-retail", "deltaretail.example"):
            assert term not in body, f"{path} names the other tenant ({term})"

    def test_niletech_content_is_actually_present(self, client: httpx.Client) -> None:
        """The positive control. If NileTech content were also absent, every
        assertion above would pass on an empty site."""
        body = client.get("/public/company").text
        assert "NileTech" in body


class TestTenantCannotBeSelected:
    @pytest.mark.parametrize("attempt", TENANT_SELECTION_ATTEMPTS)
    @pytest.mark.parametrize("path", PUBLIC_PATHS)
    def test_no_request_input_switches_tenant(
        self, client: httpx.Client, path: str, attempt: dict[str, dict[str, str]]
    ) -> None:
        response = client.get(path, **attempt)  # type: ignore[arg-type]
        assert response.status_code in {200, 400, 422}
        for marker in DELTA_MARKERS:
            assert marker not in response.text, f"{path} served Delta content when given {attempt}"

    @pytest.mark.parametrize("path", PUBLIC_PATHS)
    def test_the_response_is_unchanged_by_a_tenant_parameter(
        self, client: httpx.Client, path: str
    ) -> None:
        """Stronger than 'no leak': the parameter must have no effect at all. A
        response that changed shape would mean the input reached the query."""
        plain = client.get(path).text
        attempted = client.get(path, params={"company": "delta-retail"}).text
        assert plain == attempted


class TestDetailRoutesDoNotCrossTenants:
    def test_a_delta_slug_is_not_found(self, client: httpx.Client) -> None:
        """A slug for a record in the other tenant must resolve to nothing — the
        same answer as one that never existed, so a visitor learns nothing about
        whether it exists elsewhere (contracts/routes.md)."""
        listing = client.get("/public/news").json()
        items = listing.get("items", listing) if isinstance(listing, dict) else listing
        assert items, "no news to derive a comparison from"
        assert client.get("/public/news/delta-retail-announcement-000000").status_code == 404
