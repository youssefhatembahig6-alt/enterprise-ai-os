"""The public contact form (spec 002 FR-019 – FR-024c, SC-006, SC-007).

Every request here bypasses the browser entirely. That is the point: FR-020 makes
the **server** the control and the client rules a convenience, so a test that drove
the form would prove the convenience and nothing else.

SC-007 requires proving "exactly one stored record". FR-023b forbids a public read
path for submissions, so this reads the database directly — the privileged
verification the specification names (amended in the checklist-remediation session).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from typing import ClassVar

import httpx
import pytest
from sqlalchemy import Engine, text

pytestmark = pytest.mark.integration

BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

#: Emitted through the application logger to prove the capture is live.
_CAPTURE_MARKER = "capture-marker-4c1e7b"

VALID = {
    "sender_name": "Amina Farouk",
    "sender_email": "amina.farouk@example.com",
    "subject": "Automation for our approvals process",
    "message": "We have twelve approval steps and no record of who signed what.",
}


@pytest.fixture(scope="module")
def client() -> httpx.Client:
    with httpx.Client(base_url=BASE_URL, timeout=15.0) as session:
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
            conn.execute(text("SELECT count(*) FROM contact_submissions"))
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"database unavailable: {exc}")
    return engine


@pytest.fixture(autouse=True)
def _reset_rate_limit() -> Iterator[None]:
    """Clear FR-024d's per-address counter around every test in this module.

    Autouse and deliberate. These tests exercise *submission behaviour* — validation,
    duplicate suppression, audit, storage — and collectively submit far more than the
    five-per-hour bound the module has no interest in. Without this they began
    failing with 429 the moment the bound landed, which is the bound working, not a
    regression in what they check.

    `tests/security/test_rate_limits.py` is where the bound itself is asserted; it
    clears the same counters and then deliberately exhausts them.
    """
    from eaios_core.clients.stores import get_redis

    def purge() -> None:
        try:
            redis = get_redis()
            keys = list(redis.scan_iter(match="eaios:ratelimit:*", count=500))
            if keys:
                redis.delete(*keys)
        except Exception:  # pragma: no cover - environment guard
            pass

    purge()
    yield
    purge()


@pytest.fixture
def clean(engine: Engine) -> Iterator[None]:
    """Remove anything this module writes, before and after."""

    def purge() -> None:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM contact_submissions WHERE sender_email LIKE '%@example.com'")
            )

    purge()
    yield
    purge()


def _count(engine: Engine, email: str) -> int:
    with engine.connect() as conn:
        return int(
            conn.execute(
                text("SELECT count(*) FROM contact_submissions WHERE sender_email = :e"),
                {"e": email},
            ).scalar_one()
        )


class TestServerSideValidationIsTheControl:
    """SC-006 — 0% of invalid submissions accepted when the browser is bypassed."""

    @pytest.mark.parametrize(
        ("payload", "field"),
        [
            ({**VALID, "sender_name": ""}, "sender_name"),
            ({**VALID, "sender_email": "not-an-email"}, "sender_email"),
            ({**VALID, "subject": ""}, "subject"),
            ({**VALID, "message": ""}, "message"),
            ({**VALID, "sender_name": "x" * 121}, "sender_name"),
            ({**VALID, "message": "x" * 4001}, "message"),
        ],
    )
    def test_invalid_input_is_refused(
        self, client: httpx.Client, clean: None, payload: dict[str, str], field: str
    ) -> None:
        response = client.post("/public/contact", json=payload)
        assert response.status_code == 422
        fields = {error["field"] for error in response.json()["errors"]}
        assert field in fields, f"error not addressed to {field}: {fields}"

    def test_a_refused_submission_stores_nothing(
        self, client: httpx.Client, engine: Engine, clean: None
    ) -> None:
        client.post("/public/contact", json={**VALID, "sender_email": "bad"})
        assert _count(engine, VALID["sender_email"]) == 0

    def test_errors_carry_a_message_a_visitor_can_act_on(
        self, client: httpx.Client, clean: None
    ) -> None:
        """FR-021 — the message must say what is expected. Pydantic's raw
        "String should have at least 1 character" does not."""
        body = client.post("/public/contact", json={**VALID, "sender_name": ""}).json()
        message = next(e["message"] for e in body["errors"] if e["field"] == "sender_name")
        assert "String should have" not in message
        assert message.endswith(".") and len(message) > 10

    def test_the_response_shape_matches_the_contract(
        self, client: httpx.Client, clean: None
    ) -> None:
        body = client.post("/public/contact", json={**VALID, "subject": ""}).json()
        assert set(body) == {"title", "status", "errors"}
        assert all(set(error) == {"field", "message"} for error in body["errors"])

    def test_no_submitted_value_is_echoed_back(
        self, client: httpx.Client, clean: None
    ) -> None:
        """FR-024c — submitted personal data must not travel further than the row."""
        payload = {**VALID, "subject": ""}
        body = client.post("/public/contact", json=payload).text
        assert payload["sender_email"] not in body
        assert payload["message"] not in body


class TestAcceptedSubmissions:
    def test_a_valid_submission_is_accepted(self, client: httpx.Client, clean: None) -> None:
        response = client.post("/public/contact", json=VALID)
        assert response.status_code == 202
        assert response.json() == {"status": "accepted"}

    def test_it_stores_exactly_one_record(
        self, client: httpx.Client, engine: Engine, clean: None
    ) -> None:
        """SC-007, verified through privileged database access because FR-023b
        forbids a public read path."""
        client.post("/public/contact", json=VALID)
        assert _count(engine, VALID["sender_email"]) == 1

    def test_a_duplicate_creates_no_second_record(
        self, client: httpx.Client, engine: Engine, clean: None
    ) -> None:
        """FR-022 — the same message twice in quick succession is one intent. The
        visitor is told success either way; telling them otherwise invites a third."""
        first = client.post("/public/contact", json=VALID)
        second = client.post("/public/contact", json=VALID)
        assert first.status_code == 202
        assert second.status_code == 202
        assert _count(engine, VALID["sender_email"]) == 1

    def test_a_different_message_is_a_different_submission(
        self, client: httpx.Client, engine: Engine, clean: None
    ) -> None:
        """Guards the duplicate rule from swallowing genuine second enquiries."""
        client.post("/public/contact", json=VALID)
        client.post("/public/contact", json={**VALID, "message": "A different question."})
        assert _count(engine, VALID["sender_email"]) == 2

    def test_the_record_is_scoped_to_niletech(
        self, client: httpx.Client, engine: Engine, clean: None
    ) -> None:
        """Constitution Principle I — the tenant comes from the server, never the
        request."""
        client.post("/public/contact", json=VALID)
        with engine.connect() as conn:
            slug = conn.execute(
                text(
                    "SELECT c.slug FROM contact_submissions s"
                    " JOIN companies c ON c.id = s.company_id"
                    " WHERE s.sender_email = :e"
                ),
                {"e": VALID["sender_email"]},
            ).scalar_one()
        assert slug == "niletech"

    def test_an_audit_entry_is_written(
        self, client: httpx.Client, engine: Engine, clean: None
    ) -> None:
        """Constitution Principle X."""
        with engine.connect() as conn:
            before = conn.execute(
                text("SELECT count(*) FROM audit_logs WHERE action = 'contact.submit'")
            ).scalar_one()

        client.post("/public/contact", json=VALID)

        with engine.connect() as conn:
            after = conn.execute(
                text("SELECT count(*) FROM audit_logs WHERE action = 'contact.submit'")
            ).scalar_one()
        assert after == before + 1

    def test_the_audit_entry_carries_no_personal_data(
        self, client: httpx.Client, engine: Engine, clean: None
    ) -> None:
        """FR-024c — the row is the only place the sender's details live."""
        client.post("/public/contact", json=VALID)
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT reason, resource_id FROM audit_logs"
                    " WHERE action = 'contact.submit' ORDER BY created_at DESC LIMIT 1"
                )
            ).one()
        blob = " ".join(str(value) for value in row)
        assert VALID["sender_email"] not in blob
        assert VALID["sender_name"] not in blob
        assert VALID["message"] not in blob


class TestUntrustedContent:
    def test_markup_is_stored_inertly(
        self, client: httpx.Client, engine: Engine, clean: None
    ) -> None:
        """FR-024 — stored without being executed or interpreted, and never rendered
        as active content.

        Stored verbatim rather than sanitised on write: sanitising loses what was
        actually sent, and safety comes from never rendering it as markup.
        """
        marker = uuid.uuid4().hex[:8]
        payload = {**VALID, "message": f"<script>{marker}</script> please call me"}
        assert client.post("/public/contact", json=payload).status_code == 202

        with engine.connect() as conn:
            stored = conn.execute(
                text("SELECT message FROM contact_submissions WHERE sender_email = :e"),
                {"e": VALID["sender_email"]},
            ).scalar_one()

        assert marker in stored
        assert "<script>" in stored

    def test_oversized_input_is_refused_not_truncated(
        self, client: httpx.Client, engine: Engine, clean: None
    ) -> None:
        """Silent truncation would store something the sender did not write."""
        response = client.post("/public/contact", json={**VALID, "message": "x" * 5000})
        assert response.status_code == 422
        assert _count(engine, VALID["sender_email"]) == 0


class TestSubmittedDataNeverReachesLogs:
    """FR-024c — the sender's name, address, and message stay out of the logs.

    `test_the_audit_entry_carries_no_personal_data` above checks the audit *row*.
    Logs are a separate channel, governed by no policy and read by more people: a
    single `logger.info("contact", payload=body)` anywhere in the submission path
    would satisfy every other assertion in this module while shipping the sender's
    message to stdout, the log aggregator, and anyone with access to either.

    The request is made **in-process** rather than over the published port, because
    a container's stderr is not reachable from here and reading `docker logs` would
    make the check skip wherever Docker is absent — the failure mode this project
    has hit repeatedly, where a check passes by having nothing to check. In-process
    exercises the same router, the same validation, and the same query layer; what
    it does not cover is the ASGI server's own access log, which is asserted
    separately by `test_the_access_log_does_not_carry_the_body`.
    """

    #: Values chosen so a substring match cannot be satisfied by ordinary log text.
    PROBE: ClassVar[dict[str, str]] = {
        "sender_name": "Zaynab Q-Distinctive",
        "sender_email": "zaynab.q.distinctive@example.com",
        "subject": "Subject-Token-8f21a6",
        "message": "Message-Token-3d90c4: our approvals process has twelve steps.",
    }

    @pytest.fixture
    def app_client(self) -> Iterator[object]:
        from fastapi.testclient import TestClient

        from eaios_api.main import create_app

        with TestClient(create_app(), raise_server_exceptions=False) as session:
            yield session

    @staticmethod
    def _submit_and_capture(
        app_client: object, capsys: pytest.CaptureFixture[str], payload: dict[str, str]
    ) -> tuple[int, str]:
        """Returns the status and everything written to stderr during the request."""
        from eaios_core.logging import configure_logging, get_logger

        # Configured *inside* the capture so structlog's print factory binds to the
        # replaced stream. Without this the events go to the real stderr and the
        # captured text is empty — which every assertion below would pass on.
        configure_logging(json_output=True)
        capsys.readouterr()  # discard startup output

        response = app_client.post("/public/contact", json=payload)  # type: ignore[attr-defined]

        # The control line. If this marker is missing from the capture, the capture
        # is not working and the absence of the payload proves nothing.
        get_logger("test").info("capture.control", marker=_CAPTURE_MARKER)
        logged = capsys.readouterr().err

        # Rebind the print factory to the real stderr before the captured stream is
        # torn down. Without this the app's shutdown event — emitted when the client
        # fixture closes — writes to a closed file and errors the test in teardown.
        with capsys.disabled():
            configure_logging(json_output=True)

        return response.status_code, logged

    def test_the_capture_would_have_seen_a_leak(
        self, app_client: object, capsys: pytest.CaptureFixture[str], clean: None
    ) -> None:
        """Anti-vacuity guard for every assertion in this class."""
        _, logged = self._submit_and_capture(app_client, capsys, dict(self.PROBE))
        assert _CAPTURE_MARKER in logged, "stderr capture is not observing the log stream"

    def test_an_accepted_submission_logs_no_personal_data(
        self, app_client: object, capsys: pytest.CaptureFixture[str], clean: None
    ) -> None:
        status, logged = self._submit_and_capture(app_client, capsys, dict(self.PROBE))
        assert status == 202
        for field, value in self.PROBE.items():
            assert value not in logged, f"{field} reached the logs"

    def test_a_refused_submission_logs_no_personal_data(
        self, app_client: object, capsys: pytest.CaptureFixture[str], clean: None
    ) -> None:
        """The rejection path is the more likely leak: a validation failure is
        exactly the moment a developer reaches for "log what came in"."""
        payload = dict(self.PROBE, sender_email="not-an-address")
        status, logged = self._submit_and_capture(app_client, capsys, payload)
        assert status == 422
        for value in (self.PROBE["sender_name"], self.PROBE["message"], "not-an-address"):
            assert value not in logged

    def test_the_access_log_does_not_carry_the_body(
        self, client: httpx.Client, clean: None
    ) -> None:
        """A POST body is not part of a request line, and nothing should put it
        there. Asserted against the deployed service's own output when that output
        is reachable, since this is the one property in-process cannot show."""
        import shutil
        import subprocess

        if shutil.which("docker") is None:
            pytest.skip("docker CLI unavailable; the in-process assertions still ran")

        client.post("/public/contact", json=dict(self.PROBE))
        result = subprocess.run(
            ["docker", "compose", "-f", "infrastructure/docker-compose.yml", "logs", "--tail", "200", "api"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        output = result.stdout + result.stderr
        assert "/public/contact" in output, "no access log found; nothing was checked"
        for value in self.PROBE.values():
            assert value not in output


class TestNothingIsDelivered:
    """FR-023a and SC-007 — the submission is stored and audited, and goes nowhere.

    "Zero messages are delivered anywhere" was asserted in exactly one place: a
    docstring in `apps/api/src/eaios_api/public/router.py`. `grep -rn "deliver"
    tests/` returned nothing. A change that enqueued a notification, posted a
    webhook, or opened an SMTP connection would have passed every test in this file.

    The prohibition is not incidental. Constitution Principle VII gates irreversible
    send actions on human approval, and a public site has no approver — so *not
    sending* is the only correct behaviour available, and it needs a check that
    would notice if it changed.
    """

    @staticmethod
    def _queue_depths() -> dict[str, int]:
        """Depth of every Celery queue key currently in Redis."""
        import redis

        from eaios_core.settings import get_settings

        client = redis.Redis.from_url(get_settings().redis.url)
        # Celery pushes to a list named after the queue; "celery" is the default.
        # Reading every list-typed key means a task routed elsewhere is still seen.
        depths: dict[str, int] = {}
        for key in client.scan_iter(count=500):
            if client.type(key) == b"list":
                depths[key.decode()] = int(client.llen(key))
        return depths

    @pytest.fixture
    def redis_available(self) -> None:
        try:
            self._queue_depths()
        except Exception as exc:  # pragma: no cover - environment guard
            pytest.skip(f"redis unavailable: {exc}")

    def test_the_queue_probe_can_see_a_task(self, redis_available: None) -> None:
        """Anti-vacuity guard. If the probe read the wrong key — or no key — the
        assertion below would pass because it was looking at nothing."""
        import redis

        from eaios_core.settings import get_settings

        client = redis.Redis.from_url(get_settings().redis.url)
        probe_key = "eaios-test-delivery-probe"
        try:
            client.rpush(probe_key, "x")
            assert self._queue_depths().get(probe_key) == 1
        finally:
            client.delete(probe_key)

    def test_an_accepted_submission_enqueues_no_task(
        self, client: httpx.Client, redis_available: None, clean: None
    ) -> None:
        before = self._queue_depths()
        assert client.post("/public/contact", json=VALID).status_code == 202
        after = self._queue_depths()

        grew = {
            key: (before.get(key, 0), depth)
            for key, depth in after.items()
            if depth > before.get(key, 0)
        }
        assert grew == {}, f"a submission enqueued work: {grew}"

    def test_no_outbound_http_or_mail_is_attempted(
        self, capsys: pytest.CaptureFixture[str], clean: None
    ) -> None:
        """Run in-process so the delivery clients can be replaced with tripwires.

        Only the *delivery* transports are blocked. PostgreSQL and Redis speak their
        own protocols through their own drivers, so the request still completes
        normally — a blanket socket ban would fail for reasons unrelated to the
        requirement.

        The tripwire sits on httpx's **network transports**, not on `Client.send`.
        The first version patched `send` and tripped immediately: `TestClient` is
        itself an `httpx.Client`, so it was catching the test harness rather than the
        application. `ASGITransport` — what `TestClient` dispatches through — is
        untouched, while a real outbound request would go through the transports
        patched below.
        """
        import smtplib
        import urllib.request
        from unittest import mock

        from fastapi.testclient import TestClient

        from eaios_api.main import create_app

        def tripwire(*_args: object, **_kwargs: object):  # type: ignore[no-untyped-def]
            raise AssertionError("the submission path attempted an outbound delivery")

        with (
            mock.patch.object(httpx.HTTPTransport, "handle_request", tripwire),
            mock.patch.object(httpx.AsyncHTTPTransport, "handle_async_request", tripwire),
            mock.patch.object(urllib.request, "urlopen", tripwire),
            mock.patch.object(smtplib.SMTP, "__init__", tripwire),
            TestClient(create_app()) as app_client,
        ):
            response = app_client.post("/public/contact", json=VALID)

        assert response.status_code == 202

    def test_the_submission_path_imports_no_delivery_client(self) -> None:
        """A static companion to the runtime checks: the module cannot send what it
        never imported, and this fails at review time rather than at runtime."""
        import pathlib

        package = pathlib.Path(__file__).resolve().parents[2] / "apps/api/src/eaios_api/public"
        forbidden = ("smtplib", "aiosmtplib", "requests", "celery", "boto3", "sendgrid")

        offenders = [
            f"{path.name}: {name}"
            for path in package.glob("*.py")
            for name in forbidden
            if f"import {name}" in path.read_text(encoding="utf-8")
        ]
        assert offenders == [], f"the public API package imports a delivery client: {offenders}"

    def test_the_import_scan_reads_real_files(self) -> None:
        """Guards the scan above from passing on an empty directory."""
        import pathlib

        package = pathlib.Path(__file__).resolve().parents[2] / "apps/api/src/eaios_api/public"
        modules = sorted(path.name for path in package.glob("*.py"))
        assert "router.py" in modules
        assert "queries.py" in modules

    def test_the_tripwire_fires_on_a_real_outbound_request(self) -> None:
        """Guards the assertion above. A patch that caught nothing — the wrong class,
        the wrong method name after an httpx upgrade — would leave a test that
        accepts any behaviour at all."""
        import urllib.request
        from unittest import mock

        def tripwire(*_args: object, **_kwargs: object):  # type: ignore[no-untyped-def]
            raise AssertionError("outbound")

        with (
            mock.patch.object(httpx.HTTPTransport, "handle_request", tripwire),
            mock.patch.object(urllib.request, "urlopen", tripwire),
        ):
            with pytest.raises(AssertionError, match="outbound"):
                httpx.Client().get("http://example.invalid/hook")
            with pytest.raises(AssertionError, match="outbound"):
                urllib.request.urlopen("http://example.invalid/hook")
