"""A data change is visible on the very next request (spec 002 FR-006b, plan R7).

FR-006b requires every displayed record to be rendered from the dataset **at request
time** rather than copied into the presentation layer at build time, "so a reseed is
immediately visible". `research.md` R7 chose dynamic rendering for exactly that
reason, calling build-time prerendering "the exact class of staleness feature 001
spent five convergence passes eliminating".

The whole implementation is `cache: "no-store"` on one line of `apps/web/lib/api.ts`,
and until this file existed nothing mentioned it. That is the dangerous shape: every
other check reads a site whose content happens to match the database it was built
against, so deleting that option — or Next deciding to prerender a page that stopped
using a dynamic API — would freeze the site and leave the entire suite green.

**Why this is a Python test rather than a Playwright one.** The check needs to write
to PostgreSQL and then read HTTP. The web workspace has no database client, and
adding one to ship a single test is a worse trade than reaching for the owner engine
that already exists here.

**The mutation is always reverted.** A failure mid-test that left the dataset altered
would break the fingerprint check and report a determinism defect that is really this
file's fault, so the restore lives in a fixture rather than at the end of the test
body.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import httpx
import pytest
from sqlalchemy import Engine, text

pytestmark = pytest.mark.integration

SITE_URL = os.environ.get("SITE_URL", "http://localhost:3000")
API_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

#: Distinctive enough that finding it in a page cannot be a coincidence.
PROBE = "ZZ Reseed Probe 7f3a2c"

#: The site serves this tenant only (FR-009a), so the probe has to be written to it.
NILETECH = "niletech"


@pytest.fixture(scope="module")
def engine() -> Engine:
    from eaios_core.db import create_owner_engine

    engine = create_owner_engine()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT count(*) FROM services"))
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"database unavailable: {exc}")
    return engine


@pytest.fixture(scope="module")
def site() -> Iterator[httpx.Client]:
    """The public site.

    A skip here would be the failure mode this project keeps hitting, so note what
    covers it: the same CI job runs the full Playwright suite against this host, and
    that suite fails loudly if the site is down. This skip therefore cannot hide a
    broken deployment — only an incomplete local stack.
    """
    with httpx.Client(base_url=SITE_URL, timeout=20.0) as client:
        try:
            client.get("/")
        except httpx.HTTPError:  # pragma: no cover - environment guard
            pytest.skip("the website is not running; start it with `make up`")
        yield client


@pytest.fixture
def mutable_service(engine: Engine) -> Iterator[str]:
    """Rename one service for the duration of a test, then put it back.

    Yields the original name so the test can assert the restore as well as the
    change — a site that showed the probe and then kept showing it would satisfy
    "the change was visible" while being just as stale.
    """
    # Scoped to NileTech and fully ordered, both deliberately. `ORDER BY
    # display_order LIMIT 1` picked either tenant's row at random — both companies
    # have a service at display_order 0 — and renaming Delta Retail's is invisible to
    # a site that serves NileTech only (FR-009a). Two of these tests failed and one
    # passed on the same code, which is what an unordered selection looks like.
    with engine.connect() as conn:
        original = conn.execute(
            text(
                "SELECT s.name FROM services s JOIN companies c ON c.id = s.company_id"
                " WHERE c.slug = :slug ORDER BY s.display_order, s.name LIMIT 1"
            ),
            {"slug": NILETECH},
        ).scalar_one()

    def rename(before: str, after: str) -> None:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE services SET name = :after WHERE name = :before"
                    " AND company_id = (SELECT id FROM companies WHERE slug = :slug)"
                ),
                {"before": before, "after": after, "slug": NILETECH},
            )

    rename(original, PROBE)
    try:
        yield str(original)
    finally:
        rename(PROBE, str(original))


class TestTheSiteReadsAtRequestTime:
    def test_the_api_serves_the_change_immediately(
        self, site: httpx.Client, mutable_service: str
    ) -> None:
        """Checked first so a failure downstream can be attributed. If the API were
        the stale layer, the page assertion below would fail for a reason that has
        nothing to do with how the site renders."""
        with httpx.Client(base_url=API_URL, timeout=20.0) as api:
            body = api.get("/public/services").text
        assert PROBE in body

    def test_the_page_serves_the_change_immediately(
        self, site: httpx.Client, mutable_service: str
    ) -> None:
        assert PROBE in site.get("/services").text, (
            "the services page did not reflect a change already visible in the API — "
            "the page is being served from a build-time snapshot or a cache (FR-006b)"
        )

    def test_the_home_page_summary_reads_at_request_time_too(
        self, site: httpx.Client, mutable_service: str
    ) -> None:
        """The home page renders the same records through a different path (FR-005
        summaries), so it can go stale independently of the listing page."""
        assert PROBE in site.get("/").text

    def test_the_change_disappears_when_it_is_reverted(
        self, engine: Engine, site: httpx.Client, mutable_service: str
    ) -> None:
        """The other direction, and the one that makes this test mean something.

        A page that showed the probe *and kept showing it* would pass every
        assertion above while being exactly as frozen as a build-time snapshot.
        """
        original = mutable_service
        assert PROBE in site.get("/services").text

        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE services SET name = :after WHERE name = :before"
                    " AND company_id = (SELECT id FROM companies WHERE slug = :slug)"
                ),
                {"before": PROBE, "after": original, "slug": NILETECH},
            )

        body = site.get("/services").text
        assert PROBE not in body
        assert original in body

        # Put the probe back so the fixture's restore is a no-op rather than an error.
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE services SET name = :after WHERE name = :before"
                    " AND company_id = (SELECT id FROM companies WHERE slug = :slug)"
                ),
                {"before": original, "after": PROBE, "slug": NILETECH},
            )


class TestTheCheckCanFail:
    """Guards every assertion above from passing on an absent probe or a dead site."""

    def test_the_probe_is_not_present_without_the_mutation(self, site: httpx.Client) -> None:
        # No `mutable_service` fixture here, deliberately.
        assert PROBE not in site.get("/services").text

    def test_the_page_under_test_serves_real_content(self, site: httpx.Client) -> None:
        body = site.get("/services").text
        assert len(body) > 2000
        assert "eaios-card" in body

    def test_the_dataset_is_left_as_it_was_found(self, engine: Engine) -> None:
        """Runs after the mutating tests in file order. If a restore ever failed, the
        fingerprint check would fail later in the suite and blame the generator."""
        with engine.connect() as conn:
            leaked = conn.execute(
                text("SELECT count(*) FROM services WHERE name = :p"), {"p": PROBE}
            ).scalar_one()
        assert leaked == 0, "a probe rename survived; the dataset has been altered"
