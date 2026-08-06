"""The browser's actual network path stores exactly one record (spec 002 SC-007).

**The gap this closes.** `tests/integration/test_contact_submission.py` proves the API
stores exactly one row, and says so deliberately: it "bypasses the browser entirely",
because FR-020 makes the server the control. That reasoning is sound and the coverage it
produced was still incomplete — it exercises `POST http://localhost:8000/public/contact`,
which is *not* the request a visitor's browser makes. The browser posted
`application/json` cross-origin, which needs a preflight, and the API answers
`OPTIONS /public/contact` with 405. Every submission from a real browser failed, and no
test in either suite could see it: the server-side tests skipped the browser, and the
browser tests stubbed the network with `page.route`.

So this exercises the third thing — the path itself. The request goes to the **site's**
origin, exactly as `submitContact` sends it, and the row is then counted in Postgres.

**Why here and not in Playwright.** `apps/web/e2e/contact-submission.spec.ts` covers what
a browser is uniquely needed for: real form fill, real success UI, and no cross-origin
request. It cannot make the "exactly one record" claim — there is no read path for
submissions (FR-023b), and the endpoint answers 202 for a stored row and a suppressed
duplicate alike, so nothing observable over HTTP distinguishes them. Counting rows needs
database access, which is here.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import httpx
import pytest
from sqlalchemy import Engine, text

pytestmark = pytest.mark.e2e

#: The site's own origin — the address the browser uses. Using the API's origin here
#: would reproduce the blind spot this file exists to remove.
WEB_URL = os.environ.get("WEB_BASE_URL", "http://localhost:3000")

BODY = {
    "sender_name": "Amina Farouk",
    "sender_email": "amina.farouk@example.com",
    "message": "We have twelve approval steps and no record of who signed what.",
}


@pytest.fixture(scope="module")
def site() -> Iterator[httpx.Client]:
    with httpx.Client(base_url=WEB_URL, timeout=20.0) as client:
        try:
            client.get("/")
        except httpx.HTTPError:  # pragma: no cover - environment guard
            pytest.skip("the site is not running; start it with `make up`")
        yield client


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    from eaios_core.db import create_owner_engine

    engine = create_owner_engine()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT count(*) FROM contact_submissions"))
    except Exception:  # pragma: no cover - environment guard
        pytest.skip("PostgreSQL is not reachable; start it with `make up`")
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def _clear_bound() -> None:
    """Drop the contact rate-limit counters so this file is repeatable.

    FR-024d bounds submissions at five per address per hour and this posts through the
    proxy, so without clearing, the fourth consecutive local run would fail with a 429
    that looks like a broken form. The bound itself is tested in
    `tests/security/test_rate_limits.py`; weakening it is not in scope here, and only the
    `contact` bucket is touched.
    """
    from eaios_core.clients.stores import get_redis
    from eaios_core.keys import RATE_LIMIT_PREFIX

    try:
        redis = get_redis()
        for key in redis.scan_iter(match=f"{RATE_LIMIT_PREFIX}:contact:*"):
            redis.delete(key)
    except Exception:  # pragma: no cover - environment guard
        pytest.skip("Redis is not reachable; start it with `make up`")


def _count(engine: Engine, subject: str) -> int:
    with engine.connect() as conn:
        return int(
            conn.execute(
                text("SELECT count(*) FROM contact_submissions WHERE subject = :s"),
                {"s": subject},
            ).scalar_one()
        )


class TestTheBrowsersPathStoresExactlyOneRecord:
    def test_a_submission_to_the_site_origin_is_accepted(
        self, site: httpx.Client, engine: Engine
    ) -> None:
        subject = f"network-path {uuid.uuid4()}"

        response = site.post(
            "/api/contact",
            json={**BODY, "subject": subject},
            headers={"content-type": "application/json"},
        )

        assert response.status_code == 202, (
            "the site's own origin did not accept the submission — this is the failure"
            f" a visitor met, reported as {response.status_code}: {response.text[:300]}"
        )
        assert _count(engine, subject) == 1, (
            "SC-007 requires exactly one stored record; the request was accepted but the"
            " row is not there"
        )

    def test_the_count_would_notice_a_missing_row(self, engine: Engine) -> None:
        """Anti-vacuity guard. If the query above matched loosely — or matched nothing
        and returned a count from somewhere else — the assertion would be measuring the
        table rather than the submission. A subject never sent must count zero."""
        assert _count(engine, f"never-submitted {uuid.uuid4()}") == 0

    def test_the_same_content_again_does_not_add_a_second_row(
        self, site: httpx.Client, engine: Engine
    ) -> None:
        """FR-022's suppression, over the path that now carries real traffic.

        Also the reason the Playwright suite cannot make this claim: both responses are
        202, so the difference is visible only in the table.
        """
        subject = f"network-path duplicate {uuid.uuid4()}"
        payload = {**BODY, "subject": subject}

        first = site.post("/api/contact", json=payload)
        second = site.post("/api/contact", json=payload)

        assert (first.status_code, second.status_code) == (202, 202)
        assert _count(engine, subject) == 1, (
            "the duplicate created a second row; suppression did not survive the proxy"
        )


class TestTheProxyDoesNotWidenTheSurface:
    def test_it_forwards_only_the_contact_endpoint(self, site: httpx.Client) -> None:
        """The route handler exists to carry one request, not to become an open relay.

        Without this, `/api/contact` is a same-origin door to the API and the next
        endpoint added behind it inherits the site's origin — including the portal's
        cookie — with no authorization of its own.
        """
        assert site.get("/api/contact").status_code in (404, 405)

    def test_a_malformed_body_is_refused_rather_than_forwarded_blindly(
        self, site: httpx.Client
    ) -> None:
        response = site.post("/api/contact", json={"sender_name": "only a name"})
        assert response.status_code == 422, response.text[:300]
