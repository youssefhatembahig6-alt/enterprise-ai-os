"""The anonymous write paths are bounded (spec 002 FR-024d, FR-047b, SC-016).

The public surface lets an unauthenticated caller cause database writes on two
paths, and until FR-024d and FR-047b neither was bounded. The refusal audit is the
one worth dwelling on: Constitution Principle X requires recording every denial, so
a loop against `/admin` grew `audit_logs` without limit. The audit requirement
produced its own denial-of-service surface, and volume like that buries the signal
the trail exists to carry.

**What each assertion checks, and why the status code is not enough.** SC-016 asks
for the *effect*: zero further stored records past the submission bound, and one
coalesced audit entry rather than one per request past the audit bound. A test that
only read status codes would pass against an implementation that refused the caller
and wrote the row anyway.

**Two properties that must not be broken by the bounds themselves**, each with its
own case below: every request past the audit bound is still *refused* — FR-047b
governs recording, never enforcement — and public reads stay unbounded, because they
have no side effects and throttling them would punish ordinary browsing and crawlers.

The bounds are per client address, so every test here shares one bucket. Each class
clears its own counters first rather than assuming a clean Redis; a leftover key from
an earlier run would otherwise make the first assertion fail for the wrong reason.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import httpx
import pytest
from sqlalchemy import Engine, text

pytestmark = pytest.mark.security

BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

#: Mirrors `apps/api/src/eaios_api/public/rate_limit.py`. Duplicated rather than
#: imported: the test asserts the *contract* the specification states, so importing
#: the constant would make a change to the limit invisible here.
CONTACT_LIMIT = 5
REFUSAL_AUDIT_LIMIT = 60

PROBE_DOMAIN = "ratelimit-probe.example.com"


@pytest.fixture(scope="module")
def client() -> Iterator[httpx.Client]:
    with httpx.Client(base_url=BASE_URL, timeout=20.0) as session:
        try:
            session.get("/health/live")
        except httpx.HTTPError:  # pragma: no cover - environment guard
            pytest.skip("API is not running; start it with `make up`")
        yield session


@pytest.fixture(scope="module")
def engine() -> Engine:
    from eaios_core.db import create_owner_engine

    engine = create_owner_engine()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"database unavailable: {exc}")
    return engine


@pytest.fixture
def clean_counters() -> Iterator[None]:
    """Drop every rate-limit key so a run starts at zero, and again afterwards.

    Reaching into Redis is deliberate. The alternative — waiting out a one-hour
    window — is not a test, and lowering the window for tests would mean the suite
    verified a configuration nobody runs.
    """
    from eaios_core.clients.stores import get_redis

    def purge() -> None:
        try:
            redis = get_redis()
            keys = list(redis.scan_iter(match="eaios:ratelimit:*", count=500))
            if keys:
                redis.delete(*keys)
        except Exception as exc:  # pragma: no cover - environment guard
            pytest.skip(f"redis unavailable: {exc}")

    purge()
    yield
    purge()


@pytest.fixture
def clean_submissions(engine: Engine) -> Iterator[None]:
    def purge() -> None:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM contact_submissions WHERE sender_email LIKE :pattern"),
                {"pattern": f"%@{PROBE_DOMAIN}"},
            )

    purge()
    yield
    purge()


def _submission(index: int) -> dict[str, str]:
    """A *distinct* message each time.

    Distinct on purpose: FR-022's duplicate suppression would absorb repeats, so a
    probe sending the same text would be stopped by the wrong mechanism and the
    bound would appear to work when it had never been consulted.
    """
    token = uuid.uuid4().hex[:8]
    return {
        "sender_name": f"Rate Probe {index}",
        "sender_email": f"probe-{index}@{PROBE_DOMAIN}",
        "subject": f"Enquiry {index} {token}",
        "message": f"Distinct enquiry number {index} with token {token} for the bound probe.",
    }


def _stored(engine: Engine) -> int:
    with engine.connect() as conn:
        return int(
            conn.execute(
                text("SELECT count(*) FROM contact_submissions WHERE sender_email LIKE :p"),
                {"p": f"%@{PROBE_DOMAIN}"},
            ).scalar_one()
        )


def _refusal_entries(engine: Engine) -> int:
    with engine.connect() as conn:
        return int(
            conn.execute(
                text("SELECT count(*) FROM audit_logs WHERE action = 'public.refused'")
            ).scalar_one()
        )


class TestTheContactBound:
    def test_submissions_are_accepted_up_to_the_limit(
        self, client: httpx.Client, clean_counters: None, clean_submissions: None
    ) -> None:
        codes = [
            client.post("/public/contact", json=_submission(i)).status_code
            for i in range(CONTACT_LIMIT)
        ]
        assert codes == [202] * CONTACT_LIMIT

    def test_the_next_submission_is_refused(
        self, client: httpx.Client, clean_counters: None, clean_submissions: None
    ) -> None:
        for i in range(CONTACT_LIMIT):
            client.post("/public/contact", json=_submission(i))
        assert client.post("/public/contact", json=_submission(99)).status_code == 429

    def test_a_refused_submission_stores_nothing(
        self, client: httpx.Client, engine: Engine, clean_counters: None, clean_submissions: None
    ) -> None:
        """SC-016's actual claim. A status code says the caller was told no; this
        says no row was written, which is the property that matters."""
        for i in range(CONTACT_LIMIT):
            client.post("/public/contact", json=_submission(i))
        assert _stored(engine) == CONTACT_LIMIT

        for i in range(10):
            assert client.post("/public/contact", json=_submission(100 + i)).status_code == 429

        assert _stored(engine) == CONTACT_LIMIT

    def test_the_refusal_is_not_reported_as_success(
        self, client: httpx.Client, clean_counters: None, clean_submissions: None
    ) -> None:
        """FR-024d — a caller past the bound must not be told the message arrived.
        Duplicate suppression already returns 202 for a repeat, so "accepted" is a
        response this endpoint genuinely gives; the bound must not reuse it."""
        for i in range(CONTACT_LIMIT):
            client.post("/public/contact", json=_submission(i))

        response = client.post("/public/contact", json=_submission(200))
        body = response.json()

        assert response.status_code == 429
        assert body.get("status") == 429
        assert "accepted" not in response.text.lower()

    def test_the_refusal_discloses_neither_the_limit_nor_the_window(
        self, client: httpx.Client, clean_counters: None, clean_submissions: None
    ) -> None:
        """Telling a script the threshold is telling it how to stay under it."""
        for i in range(CONTACT_LIMIT):
            client.post("/public/contact", json=_submission(i))

        text_body = client.post("/public/contact", json=_submission(201)).text.lower()
        for leak in (str(CONTACT_LIMIT), "3600", "hour", "limit", "rate"):
            assert leak not in text_body, f"the refusal disclosed {leak!r}"


class TestTheRefusalAuditBound:
    def test_refusals_are_audited_individually_up_to_the_limit(
        self, client: httpx.Client, engine: Engine, clean_counters: None
    ) -> None:
        before = _refusal_entries(engine)
        for i in range(REFUSAL_AUDIT_LIMIT):
            client.get(f"/internal/bound-probe-{i}")
        assert _refusal_entries(engine) == before + REFUSAL_AUDIT_LIMIT

    def test_beyond_the_limit_one_coalesced_entry_replaces_the_rest(
        self, client: httpx.Client, engine: Engine, clean_counters: None
    ) -> None:
        """The property FR-047b states: 70 refusals produce 61 entries, not 70."""
        before = _refusal_entries(engine)
        for i in range(REFUSAL_AUDIT_LIMIT + 10):
            client.get(f"/internal/bound-probe-{i}")

        written = _refusal_entries(engine) - before
        assert written == REFUSAL_AUDIT_LIMIT + 1, (
            f"{written} entries written for {REFUSAL_AUDIT_LIMIT + 10} refusals;"
            f" expected {REFUSAL_AUDIT_LIMIT} individual plus one coalesced"
        )

    def test_the_coalesced_entry_says_what_happened(
        self, client: httpx.Client, engine: Engine, clean_counters: None
    ) -> None:
        for i in range(REFUSAL_AUDIT_LIMIT + 5):
            client.get(f"/internal/bound-probe-{i}")

        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT resource_id, reason, decision FROM audit_logs"
                    " WHERE action = 'public.refused' ORDER BY created_at DESC LIMIT 1"
                )
            ).one()

        assert "COALESCED" in row.resource_id
        assert "bound reached" in row.reason
        assert row.decision == "DENY"

    def test_every_request_past_the_bound_is_still_refused(
        self, client: httpx.Client, clean_counters: None
    ) -> None:
        """The line FR-047b draws: the bound governs *recording*, never enforcement.
        An implementation that stopped refusing once it stopped auditing would be a
        far worse defect than the unbounded audit it replaced."""
        for i in range(REFUSAL_AUDIT_LIMIT + 5):
            client.get(f"/internal/bound-probe-{i}")

        codes = {client.get(f"/internal/past-the-bound-{i}").status_code for i in range(10)}
        assert codes <= {401, 403, 404, 405}, f"a request past the bound was served: {codes}"

    def test_public_reads_are_never_bounded(
        self, client: httpx.Client, clean_counters: None
    ) -> None:
        """FR-024d and FR-047b bound the write paths only. Reads have no side
        effects, and throttling them would punish ordinary browsing and crawlers —
        and would put SC-014's timing criterion at risk under parallel test load."""
        for _ in range(REFUSAL_AUDIT_LIMIT + 20):
            client.get("/internal/read-bound-probe")

        codes = {client.get(path).status_code for path in ("/public/services", "/public/news")}
        assert codes == {200}


class TestTheChecksCanFail:
    """Guards above from passing on an inert probe or an already-exhausted counter."""

    def test_the_counter_starts_clean(self, client: httpx.Client, clean_counters: None) -> None:
        # If the fixture did not clear Redis, the first submission in every test
        # above could already be over the bound and "refused" would prove nothing.
        assert client.post("/public/contact", json=_submission(300)).status_code == 202

    def test_refusals_write_entries_at_all(
        self, client: httpx.Client, engine: Engine, clean_counters: None
    ) -> None:
        before = _refusal_entries(engine)
        client.get("/internal/can-this-fail")
        assert _refusal_entries(engine) == before + 1

    def test_distinct_probes_are_not_duplicates(self) -> None:
        # The bound is only exercised if FR-022's suppression does not absorb the
        # traffic first, which requires every probe message to differ.
        messages = {_submission(i)["message"] for i in range(20)}
        assert len(messages) == 20
