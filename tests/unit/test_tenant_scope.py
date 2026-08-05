"""The RLS tenant session scope (spec FR-009d, Constitution Principle VIII).

`tests/security/test_rls.py` proves the database *policy* works. This proves the
application reliably enters and leaves the tenant scope — a different property, and
the one that actually fails in production.

The failure this guards against: a pooled session that keeps a previous request's
``app.company_id``. The policy would still be doing its job; it would simply be
enforcing the wrong tenant. That is a cross-tenant read path with no failing policy
to reveal it, which is why clearing on exit — including on exception — is tested
here rather than assumed.

A recording double is used instead of a live database so this runs in the fast unit
lane and cannot be skipped when Postgres is unavailable.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from eaios_core.db import TENANT_SETTING, tenant_scope

pytestmark = pytest.mark.unit

NILETECH = uuid.UUID("91fc82ba-df24-510d-9fc4-8922fd2c55fa")
DELTA = uuid.UUID("7ac4fdde-9397-50cc-85b0-0d1f1d9b4a4c")


class RecordingSession:
    """Minimal stand-in that records every statement and parameter set."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def execute(self, statement: Any, params: dict[str, Any] | None = None) -> None:
        self.calls.append((str(statement), params or {}))

    @property
    def statements(self) -> list[str]:
        return [sql for sql, _ in self.calls]

    def company_values(self) -> list[str]:
        return [params["company_id"] for _, params in self.calls if "company_id" in params]


class TestScopeIsEntered:
    def test_sets_the_tenant_setting_on_entry(self) -> None:
        session = RecordingSession()
        with tenant_scope(session, NILETECH):
            pass
        assert TENANT_SETTING in session.statements[0]

    def test_binds_the_company_id_as_a_parameter_not_by_interpolation(self) -> None:
        """String-interpolating a tenant into SQL would be an injection point on the
        single value the whole isolation model depends on."""
        session = RecordingSession()
        with tenant_scope(session, NILETECH):
            pass
        assert session.company_values() == [str(NILETECH)]
        assert str(NILETECH) not in session.statements[0]

    def test_accepts_a_string_company_id(self) -> None:
        session = RecordingSession()
        with tenant_scope(session, str(DELTA)):
            pass
        assert session.company_values() == [str(DELTA)]

    def test_setting_is_transaction_local(self) -> None:
        """`set_config(..., true)` scopes the setting to the transaction, so it
        cannot outlive a rollback."""
        session = RecordingSession()
        with tenant_scope(session, NILETECH):
            pass
        assert "true" in session.statements[0]


class TestScopeIsAlwaysLeft:
    def test_clears_the_setting_on_normal_exit(self) -> None:
        session = RecordingSession()
        with tenant_scope(session, NILETECH):
            pass
        assert len(session.calls) == 2
        assert TENANT_SETTING in session.statements[1]
        assert session.calls[1][1].get("company_id") is None

    def test_clears_the_setting_when_the_body_raises(self) -> None:
        """The important case. An exception mid-request must not leave the tenant
        bound to a session that returns to the pool."""
        session = RecordingSession()
        with pytest.raises(RuntimeError, match="boom"), tenant_scope(session, NILETECH):
            raise RuntimeError("boom")

        assert len(session.calls) == 2, "cleanup did not run on the exception path"
        assert TENANT_SETTING in session.statements[1]

    def test_clears_on_early_return(self) -> None:
        session = RecordingSession()

        def use_scope() -> str:
            with tenant_scope(session, NILETECH):
                return "early"

        assert use_scope() == "early"
        assert len(session.calls) == 2


class TestNoTenantBleedBetweenScopes:
    def test_sequential_scopes_do_not_share_state(self) -> None:
        session = RecordingSession()
        with tenant_scope(session, NILETECH):
            pass
        with tenant_scope(session, DELTA):
            pass

        # set(niletech) → clear → set(delta) → clear
        assert len(session.calls) == 4
        assert session.company_values() == [str(NILETECH), str(DELTA)]

    def test_a_second_scope_cannot_inherit_the_first_tenant(self) -> None:
        session = RecordingSession()
        with tenant_scope(session, NILETECH):
            pass
        first_clear = session.calls[1]

        with tenant_scope(session, DELTA):
            pass
        second_set = session.calls[2]

        assert first_clear[1].get("company_id") is None
        assert second_set[1]["company_id"] == str(DELTA)

    def test_nested_scopes_still_clear(self) -> None:
        """Nesting is not an expected pattern, but if it happens the inner exit must
        not leave the outer tenant silently unset in a way nobody notices."""
        session = RecordingSession()
        with tenant_scope(session, NILETECH), tenant_scope(session, DELTA):
            pass
        assert len(session.calls) == 4
