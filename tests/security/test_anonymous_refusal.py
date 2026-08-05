"""Anonymous callers reach only the public surface (spec 002 FR-046, FR-047, FR-051).

FR-047a classifies every endpoint into three sets, because "non-public" is
otherwise undefined and this check would have no population to test:

* **public** — `/public/*`, serving the website's content.
* **operational** — health and the dataset manifest. Anonymous *by design*, they
  predate this feature, and the status route depends on them. They carry liveness
  and provenance, never tenant-owned business data.
* **non-public** — everything else. Refused.

The anti-vacuity assertions in `TestTheSetsAreReal` are deliberate. Feature 001
shipped a security suite that silently skipped 69 tests and reported success; a
refusal test whose subject set is empty passes by having nothing to check.

Written before the endpoints exist (Constitution Principle VIII).
"""

from __future__ import annotations

import os

import httpx
import pytest
from sqlalchemy import Engine, text

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

#: Anonymous by design (FR-047a). Adding to this set widens the anonymous surface
#: and must be a deliberate, reviewed decision.
OPERATIONAL_PATHS = (
    "/health/live",
    "/health/ready",
    "/dataset/manifest",
)

#: Must be refused. These are the shapes an anonymous caller would try if they
#: guessed at an internal API.
NON_PUBLIC_PATHS = (
    "/internal/documents",
    "/internal/users",
    "/api/documents",
    "/api/users",
    "/api/contracts",
    "/documents",
    "/users",
    "/employees",
    "/payroll",
    "/audit",
    "/admin",
    "/portal/api/me",
)

REFUSED_CODES = {401, 403, 404, 405}


@pytest.fixture(scope="module")
def client() -> httpx.Client:
    with httpx.Client(base_url=BASE_URL, timeout=15.0, follow_redirects=False) as session:
        try:
            session.get("/health/live")
        except httpx.HTTPError:  # pragma: no cover - environment guard
            pytest.skip("API is not running; start it with `make up`")
        yield session


class TestTheSetsAreReal:
    """Guards every assertion below from passing on an empty population."""

    def test_the_non_public_set_is_not_empty(self) -> None:
        assert NON_PUBLIC_PATHS

    def test_the_public_set_is_not_empty(self) -> None:
        assert PUBLIC_PATHS

    def test_the_sets_do_not_overlap(self) -> None:
        assert not (set(PUBLIC_PATHS) & set(NON_PUBLIC_PATHS))
        assert not (set(OPERATIONAL_PATHS) & set(NON_PUBLIC_PATHS))

    def test_public_endpoints_actually_serve(self, client: httpx.Client) -> None:
        """If the public surface were also refused, every refusal assertion would
        pass while the site was entirely broken."""
        serving = [p for p in PUBLIC_PATHS if client.get(p).status_code == 200]
        assert serving == list(PUBLIC_PATHS), (
            f"public endpoints not serving: {sorted(set(PUBLIC_PATHS) - set(serving))}"
        )


class TestNonPublicIsRefused:
    @pytest.mark.parametrize("path", NON_PUBLIC_PATHS)
    def test_anonymous_access_is_refused(self, client: httpx.Client, path: str) -> None:
        response = client.get(path)
        assert response.status_code in REFUSED_CODES, (
            f"{path} answered {response.status_code} to an anonymous caller"
        )

    @pytest.mark.parametrize("path", NON_PUBLIC_PATHS)
    def test_the_refusal_carries_no_internal_detail(self, client: httpx.Client, path: str) -> None:
        body = client.get(path).text.lower()
        for secret in ("traceback", "postgresql://", "psycopg", "sqlalchemy", "eaios_owner"):
            assert secret not in body, f"{path} leaked {secret!r} in its refusal"

    @pytest.mark.parametrize("path", NON_PUBLIC_PATHS)
    def test_refusal_is_not_a_redirect(self, client: httpx.Client, path: str) -> None:
        """A redirect to a private route would reveal structure the caller was
        refused (FR-046)."""
        assert client.get(path).status_code not in (301, 302, 307, 308)


class TestOperationalRemainsAnonymous:
    """These are exempt by FR-047a, and that exemption has to keep holding — the
    status route reads them, and feature 001's health tests depend on them."""

    @pytest.mark.parametrize("path", OPERATIONAL_PATHS)
    def test_operational_endpoint_answers(self, client: httpx.Client, path: str) -> None:
        # 503 from readiness and 404 from an unseeded manifest are both valid
        # answers; what matters is that the caller is not refused for being anonymous.
        assert client.get(path).status_code in {200, 404, 503}

    def test_operational_endpoints_carry_no_business_data(self, client: httpx.Client) -> None:
        """The condition on which the exemption rests.

        Matched against data *shapes*, not vocabulary. An earlier version of this
        test searched for the word "contract" and flagged the manifest's entity
        counts — `"niletech.contracts": 60` is a table name in a provenance record,
        not business content. Feature 001 hit the same class of false positive when
        its public-content scanner matched the word "budget" in a job advert.

        What would actually constitute a leak here is a *value*: an address, a
        person's name, a monetary figure, or a paragraph of generated prose.
        """
        import re

        email = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
        money = re.compile(r"\b\d{1,3}(?:,\d{3})+(?:\.\d{2})?\b")

        for path in OPERATIONAL_PATHS:
            body = client.get(path).text
            assert not email.search(body), f"{path} exposes an email address"
            assert not money.search(body), f"{path} exposes a monetary figure"
            # Generated prose is long; provenance values are short identifiers,
            # digests, dates, and counts.
            longest = max((len(v) for v in re.findall(r'"([^"]*)"', body)), default=0)
            assert longest <= 64, f"{path} carries a {longest}-character free-text value"

    def test_the_business_data_check_can_fail(self) -> None:
        """Guards the assertion above from being satisfiable by any response."""
        import re

        email = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
        assert email.search('{"owner": "mariam.lotfy@niletech.example"}')


class TestWriteMethodsOnPublicEndpoints:
    @pytest.mark.parametrize("path", PUBLIC_PATHS)
    def test_public_reads_reject_writes(self, client: httpx.Client, path: str) -> None:
        """The public content surface is read-only; only the contact endpoint
        accepts a write."""
        assert client.post(path, json={}).status_code in {404, 405, 422}


class TestSubmissionsAreNotReadable:
    """FR-023b — the site writes contact submissions and must never serve them."""

    @pytest.mark.parametrize(
        "path",
        ["/public/contact", "/public/contacts", "/public/submissions", "/public/messages"],
    )
    def test_no_public_read_path_exists(self, client: httpx.Client, path: str) -> None:
        assert client.get(path).status_code in REFUSED_CODES


class TestRefusalsAreAudited:
    """FR-047 and Constitution X — a refusal must be *recorded*, not only returned.

    Every assertion above this class checks a status code, and all of them passed
    while no refusal wrote an audit entry at all: `audit_logs` held the same count
    before and after a request to a non-public path. A boundary test that only
    asks "was it refused?" cannot notice that half the requirement is missing.
    """

    @staticmethod
    def _count(engine: Engine, action: str = "public.refused") -> int:
        with engine.connect() as conn:
            return int(
                conn.execute(
                    text("SELECT count(*) FROM audit_logs WHERE action = :a"), {"a": action}
                ).scalar_one()
            )

    def test_a_refusal_writes_an_audit_entry(
        self, client: httpx.Client, owner_engine: Engine
    ) -> None:
        before = self._count(owner_engine)
        assert client.get("/internal/documents").status_code in REFUSED_CODES
        assert self._count(owner_engine) == before + 1

    def test_the_entry_records_what_was_attempted(
        self, client: httpx.Client, owner_engine: Engine
    ) -> None:
        probe = "/internal/a-path-nobody-should-reach"
        client.get(probe)

        with owner_engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT resource_id, decision, actor_type FROM audit_logs"
                    " WHERE action = 'public.refused' ORDER BY created_at DESC LIMIT 1"
                )
            ).one()

        assert probe in row.resource_id
        assert row.resource_id.startswith("GET ")
        assert row.decision == "DENY"

    def test_the_entry_carries_no_request_content(
        self, client: httpx.Client, owner_engine: Engine
    ) -> None:
        """FR-024c — a probe's body must not be copied into a table someone reads."""
        client.post("/internal/secrets", json={"password": "hunter2", "note": "sensitive"})

        with owner_engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT resource_id, reason FROM audit_logs"
                    " WHERE action = 'public.refused' ORDER BY created_at DESC LIMIT 1"
                )
            ).one()

        blob = f"{row.resource_id} {row.reason}"
        assert "hunter2" not in blob
        assert "sensitive" not in blob

    def test_public_not_found_is_not_audited_as_a_refusal(
        self, client: httpx.Client, owner_engine: Engine
    ) -> None:
        """A 404 under /public/ means *no such record* — a mistyped slug or a stale
        bookmark. Recording those would bury the real signal in ordinary browsing."""
        before = self._count(owner_engine)
        assert client.get("/public/news/no-such-article-000000").status_code == 404
        assert self._count(owner_engine) == before

    def test_operational_endpoints_produce_no_refusal_entries(
        self, client: httpx.Client, owner_engine: Engine
    ) -> None:
        before = self._count(owner_engine)
        for path in OPERATIONAL_PATHS:
            client.get(path)
        assert self._count(owner_engine) == before

    def test_a_served_public_request_produces_no_entry(
        self, client: httpx.Client, owner_engine: Engine
    ) -> None:
        before = self._count(owner_engine)
        assert client.get("/public/services").status_code == 200
        assert self._count(owner_engine) == before
