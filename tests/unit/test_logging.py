"""Structured logging actually emits (Constitution Principle X).

This file exists because of a real failure. The original configuration paired
``structlog.stdlib.add_logger_name`` — which reads ``logger.name`` — with
``PrintLoggerFactory``, whose ``PrintLogger`` has no such attribute. Nothing caught
it, because no test ever called ``.info()``. The API imported cleanly, passed type
checking, started, and then died on its first log line inside the lifespan hook:

    AttributeError: 'PrintLogger' object has no attribute 'name'

Importing a logging module proves nothing. These tests emit.
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

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clean_context() -> None:
    clear_context()


class TestItActuallyEmits:
    def test_info_does_not_raise(self, capsys: pytest.CaptureFixture[str]) -> None:
        """The regression test. Configure, then log — the exact sequence that failed."""
        configure_logging(level="info", json_output=True)
        get_logger(__name__).info("api.startup", service="eaios-api", environment="local")

        captured = capsys.readouterr()
        assert "api.startup" in captured.err

    def test_output_is_valid_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        configure_logging(level="info", json_output=True)
        get_logger("test").info("event.happened", count=3)

        line = capsys.readouterr().err.strip().splitlines()[-1]
        payload = json.loads(line)
        assert payload["event"] == "event.happened"
        assert payload["count"] == 3
        assert payload["level"] == "info"

    def test_logger_name_is_carried_as_a_field(self, capsys: pytest.CaptureFixture[str]) -> None:
        """The name still reaches the output — just bound rather than read off the
        underlying logger, so it works with any factory."""
        configure_logging(json_output=True)
        get_logger("eaios_api.main").info("named")

        payload = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
        assert payload["logger"] == "eaios_api.main"

    def test_anonymous_logger_still_works(self, capsys: pytest.CaptureFixture[str]) -> None:
        configure_logging(json_output=True)
        get_logger().info("anonymous")
        assert "anonymous" in capsys.readouterr().err

    def test_console_renderer_also_emits(self, capsys: pytest.CaptureFixture[str]) -> None:
        """The local-development path (LOG_JSON=false) must work too."""
        configure_logging(json_output=False)
        get_logger("dev").info("readable.output")
        assert "readable.output" in capsys.readouterr().err

    def test_exception_logging_does_not_raise(self, capsys: pytest.CaptureFixture[str]) -> None:
        configure_logging(json_output=True)
        try:
            raise ValueError("boom")
        except ValueError:
            get_logger("test").exception("operation.failed")
        assert "operation.failed" in capsys.readouterr().err


class TestContextBinding:
    def test_request_id_appears_in_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        configure_logging(json_output=True)
        bind_request("req-123")
        get_logger("test").info("handled")

        payload = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
        assert payload["request_id"] == "req-123"

    def test_company_id_appears_in_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Unused until authentication exists (decision D1), but the binding point
        must work now — otherwise every later log line would need retrofitting."""
        configure_logging(json_output=True)
        bind_company("niletech")
        get_logger("test").info("scoped")

        payload = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
        assert payload["company_id"] == "niletech"

    def test_clear_context_removes_bindings(self, capsys: pytest.CaptureFixture[str]) -> None:
        """A pooled context that keeps one request's tenant is the log-side version
        of the session-scope leak covered in test_tenant_scope.py."""
        configure_logging(json_output=True)
        bind_company("niletech")
        bind_request("req-1")
        clear_context()
        get_logger("test").info("after.clear")

        payload = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
        assert "company_id" not in payload
        assert "request_id" not in payload


class TestLevelFiltering:
    def test_debug_is_suppressed_at_info_level(self, capsys: pytest.CaptureFixture[str]) -> None:
        configure_logging(level="info", json_output=True)
        get_logger("test").debug("should.not.appear")
        assert "should.not.appear" not in capsys.readouterr().err

    def test_warning_passes_at_info_level(self, capsys: pytest.CaptureFixture[str]) -> None:
        configure_logging(level="info", json_output=True)
        get_logger("test").warning("should.appear")
        assert "should.appear" in capsys.readouterr().err
