"""Log output is an isolation surface too (spec FR-043, Constitution X).

RLS stops a query crossing the tenant boundary. Logs are a separate channel that no
policy governs: a message carrying one tenant's content into a shared log is a leak
even though no query ever crossed a boundary. Structured logging also makes it easy
to attach an arbitrary object to an event and not notice what came with it.

Two properties are checked: that the tenant binding actually reaches the output so
lines are attributable, and that credentials never do.
"""

from __future__ import annotations

import json

import pytest

from eaios_core.logging import (
    bind_company,
    bind_request,
    clear_context,
    configure_logging,
    get_logger,
)
from eaios_core.settings import get_settings

pytestmark = [pytest.mark.security, pytest.mark.unit]


@pytest.fixture(autouse=True)
def _clean_context() -> None:
    clear_context()


def _emit(capsys: pytest.CaptureFixture[str], event: str, **fields: object) -> dict:
    configure_logging(json_output=True)
    get_logger("test").info(event, **fields)
    return json.loads(capsys.readouterr().err.strip().splitlines()[-1])


class TestTenantAttribution:
    def test_bound_company_reaches_the_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        bind_company("niletech")
        payload = _emit(capsys, "document.read")
        assert payload["company_id"] == "niletech"

    def test_context_does_not_survive_clearing(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A pooled context carrying the previous request's tenant is the log-side
        version of the session-scope leak in test_tenant_scope.py."""
        bind_company("niletech")
        bind_request("req-1")
        clear_context()
        payload = _emit(capsys, "next.request")
        assert "company_id" not in payload
        assert "request_id" not in payload

    def test_a_second_binding_replaces_the_first(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        bind_company("niletech")
        clear_context()
        bind_company("delta-retail")
        payload = _emit(capsys, "document.read")
        assert payload["company_id"] == "delta-retail"


class TestNoCredentialsInLogs:
    def test_settings_repr_carries_no_secrets(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Logging a settings object is a plausible mistake; SecretStr must make it
        harmless rather than catastrophic."""
        settings = get_settings()
        payload = _emit(capsys, "startup", settings=repr(settings))
        rendered = json.dumps(payload)
        for secret in (
            settings.postgres.owner_password.get_secret_value(),
            settings.postgres.app_password.get_secret_value(),
            settings.minio.secret_key.get_secret_value(),
        ):
            assert secret not in rendered

    def test_connection_urls_are_not_logged_by_default(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        settings = get_settings()
        payload = _emit(capsys, "db.connect", host=settings.postgres.host)
        rendered = json.dumps(payload)
        assert "postgresql+psycopg://" not in rendered
        assert settings.postgres.owner_password.get_secret_value() not in rendered

    @pytest.mark.parametrize(
        "field",
        ["password", "secret_key", "token", "authorization"],
    )
    def test_no_credential_shaped_field_is_emitted_by_the_app(self, field: str) -> None:
        """Nothing in the application logs a field with these names today. This
        fails the moment something starts to."""
        import pathlib

        roots = [
            pathlib.Path("packages/core/src/eaios_core"),
            pathlib.Path("apps/api/src/eaios_api"),
            pathlib.Path("services/worker/src/eaios_worker"),
            pathlib.Path("scripts/seed/src/eaios_seed"),
        ]
        offenders: list[str] = []
        for root in roots:
            if not root.exists():
                continue
            for path in root.rglob("*.py"):
                for number, line in enumerate(
                    path.read_text(encoding="utf-8").splitlines(), start=1
                ):
                    stripped = line.strip()
                    if (
                        (".info(" in stripped or ".warning(" in stripped or ".error(" in stripped)
                        and f"{field}=" in stripped
                    ):
                        offenders.append(f"{path}:{number}")
        assert offenders == [], f"credential-shaped log field {field!r}: {offenders}"


class TestHealthResponsesLeakNothing:
    def test_failure_detail_is_only_an_exception_type(self) -> None:
        """Health is unauthenticated, so its error detail must not carry a DSN."""
        from eaios_core.clients.stores import _safe_detail

        detail = _safe_detail(
            ConnectionRefusedError("could not connect to postgresql://user:pw@host/db")
        )
        assert detail == "ConnectionRefusedError"
        assert "pw" not in detail
        assert "postgresql" not in detail
