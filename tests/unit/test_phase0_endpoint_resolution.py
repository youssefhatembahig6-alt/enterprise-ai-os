"""An explicitly supplied endpoint is never silently replaced (D1, F1).

**The defect this pins down.** `resolve_endpoints` chained its sources with `or`:

    supplied.get("postgres_port") or _override("POSTGRES_PORT") or DEFAULT_POSTGRES_PORT

`or` asks *is this truthy*, not *was this supplied*. So an explicit `postgres_port=0` or an
explicit empty host fell through to the compose default — and the benchmark would have
measured `localhost:5432` while its caller believed it had pointed somewhere else. A figure
attributed to the wrong machine is exactly what the endpoint machinery exists to prevent,
and it would have failed silently, with a passing run.

Two rules follow, and this file holds both to them:

* **Presence, not truthiness.** A key present in the overrides is honoured whatever its
  value; a key absent falls through. `PHASE0_*` keeps its existing meaning — absent or
  whitespace-only is *not supplied*, because an exported-but-empty variable is how shells
  represent "unset" often enough that treating it as a real value would surprise people.
* **A degenerate explicit value is an error, not a fallback.** Port 0 is not an endpoint.
  It must produce a named failure before any socket is opened, never a quiet connection to
  the default.

Everything here is pure: it resolves configuration and asserts. No socket, no stack.
"""

from __future__ import annotations

import pytest

from benchmarks.phase0.config import load_settings
from benchmarks.phase0.live_environment import (
    DEFAULT_MINIO_ENDPOINT,
    DEFAULT_POSTGRES_HOST,
    DEFAULT_POSTGRES_PORT,
    DEFAULT_QDRANT_HOST,
    DEFAULT_QDRANT_PORT,
    EndpointConfigurationError,
    resolve_endpoints,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def settings():  # type: ignore[no-untyped-def]
    return load_settings([])


class TestTheDefaultsStillApplyWhenNothingIsSupplied:
    """The behaviour that must survive the fix."""

    def test_no_overrides_yields_the_compose_published_endpoints(self, settings) -> None:  # type: ignore[no-untyped-def]
        endpoints = resolve_endpoints(settings)
        assert endpoints.postgres_host == DEFAULT_POSTGRES_HOST
        assert endpoints.postgres_port == DEFAULT_POSTGRES_PORT
        assert endpoints.qdrant_host == DEFAULT_QDRANT_HOST
        assert endpoints.qdrant_port == DEFAULT_QDRANT_PORT
        assert endpoints.minio_endpoint == DEFAULT_MINIO_ENDPOINT

    def test_an_empty_dict_is_not_a_supplied_value(self, settings) -> None:  # type: ignore[no-untyped-def]
        assert resolve_endpoints(settings, {}).postgres_port == DEFAULT_POSTGRES_PORT


class TestAbsentAndWhitespacePhaseZeroVariablesKeepTheirMeaning:
    """`PHASE0_*` semantics are deliberately unchanged by the fix."""

    def test_an_unset_variable_falls_through(self, settings, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.delenv("PHASE0_POSTGRES_HOST", raising=False)
        assert resolve_endpoints(settings).postgres_host == DEFAULT_POSTGRES_HOST

    @pytest.mark.parametrize("blank", ["", "   ", "\t", "\n"])
    def test_a_whitespace_only_variable_falls_through(
        self, settings, monkeypatch, blank: str
    ) -> None:  # type: ignore[no-untyped-def]
        """An exported-but-empty variable means 'unset' in practice, and treating it as a
        real endpoint would surprise anyone who wrote `PHASE0_QDRANT_HOST=` in a script."""
        monkeypatch.setenv("PHASE0_QDRANT_HOST", blank)
        assert resolve_endpoints(settings).qdrant_host == DEFAULT_QDRANT_HOST

    def test_a_real_variable_wins(self, settings, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setenv("PHASE0_QDRANT_HOST", "qdrant.example")
        monkeypatch.setenv("PHASE0_QDRANT_PORT", "16333")
        endpoints = resolve_endpoints(settings)
        assert endpoints.qdrant_host == "qdrant.example"
        assert endpoints.qdrant_port == 16333

    def test_the_string_zero_is_a_supplied_value_not_an_absence(
        self, settings, monkeypatch
    ) -> None:  # type: ignore[no-untyped-def]
        """`PHASE0_POSTGRES_PORT=0` is degenerate, but it *was* supplied — so it must be
        rejected, never replaced by 5432."""
        monkeypatch.setenv("PHASE0_POSTGRES_PORT", "0")
        with pytest.raises(EndpointConfigurationError, match="port"):
            resolve_endpoints(settings)


class TestExplicitFalsyOverridesAreNeverSilentlyReplaced:
    """The regression itself, one case per degenerate value."""

    def test_postgres_port_zero_is_rejected_not_defaulted(self, settings) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises(EndpointConfigurationError) as raised:
            resolve_endpoints(settings, {"postgres_port": 0})
        message = str(raised.value)
        assert "postgres" in message.lower() and "port" in message.lower()
        assert str(DEFAULT_POSTGRES_PORT) not in message.split("got")[0], (
            "the failure suggests the default, which is what the caller did not ask for"
        )

    def test_empty_postgres_host_is_rejected_not_defaulted(self, settings) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises(EndpointConfigurationError, match="postgres"):
            resolve_endpoints(settings, {"postgres_host": ""})

    def test_empty_minio_endpoint_is_rejected_not_defaulted(self, settings) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises(EndpointConfigurationError, match="minio"):
            resolve_endpoints(settings, {"minio_endpoint": ""})

    def test_qdrant_port_zero_is_rejected_not_defaulted(self, settings) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises(EndpointConfigurationError, match="qdrant"):
            resolve_endpoints(settings, {"qdrant_port": 0})

    def test_empty_qdrant_host_is_rejected_not_defaulted(self, settings) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises(EndpointConfigurationError, match="qdrant"):
            resolve_endpoints(settings, {"qdrant_host": ""})

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("postgres_host", "   "),
            ("qdrant_host", "\t"),
            ("minio_endpoint", "  "),
        ],
    )
    def test_whitespace_only_explicit_values_are_rejected(
        self, settings, field: str, value: str
    ) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises(EndpointConfigurationError):
            resolve_endpoints(settings, {field: value})

    @pytest.mark.parametrize("port", [-1, 65536, 99999])
    def test_out_of_range_ports_are_rejected(self, settings, port: int) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises(EndpointConfigurationError, match="port"):
            resolve_endpoints(settings, {"postgres_port": port})

    def test_a_non_numeric_port_is_rejected_by_name(self, settings) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises(EndpointConfigurationError, match="port"):
            resolve_endpoints(settings, {"qdrant_port": "not-a-port"})


class TestNoDegenerateValueEverReachesTheDefault:
    """The property, stated once over every field rather than case by case."""

    DEGENERATE = ("", "   ", "\t")

    @pytest.mark.parametrize("field", ["postgres_host", "qdrant_host", "minio_endpoint"])
    def test_no_blank_string_resolves_to_a_default(self, settings, field: str) -> None:  # type: ignore[no-untyped-def]
        for value in self.DEGENERATE:
            try:
                resolved = getattr(resolve_endpoints(settings, {field: value}), field)
            except EndpointConfigurationError:
                continue
            pytest.fail(
                f"{field}={value!r} resolved to {resolved!r} instead of failing; an"
                " explicit value was silently replaced"
            )

    @pytest.mark.parametrize("field", ["postgres_port", "qdrant_port"])
    def test_no_zero_port_resolves_to_a_default(self, settings, field: str) -> None:  # type: ignore[no-untyped-def]
        try:
            resolved = getattr(resolve_endpoints(settings, {field: 0}), field)
        except EndpointConfigurationError:
            return
        pytest.fail(f"{field}=0 resolved to {resolved!r} instead of failing")


class TestValidExplicitValuesStillWin:
    """The other half — rejecting degenerate values must not reject good ones."""

    def test_a_supplied_host_and_port_are_honoured(self, settings) -> None:  # type: ignore[no-untyped-def]
        endpoints = resolve_endpoints(
            settings, {"postgres_host": "db.internal", "postgres_port": 15432}
        )
        assert endpoints.postgres_host == "db.internal"
        assert endpoints.postgres_port == 15432

    def test_port_one_is_valid_and_is_what_the_tests_use(self, settings) -> None:  # type: ignore[no-untyped-def]
        """`1` is a legitimate closed port and is how the controlled tests force a
        deterministic refusal. Rejecting it would break that mechanism."""
        assert resolve_endpoints(settings, {"postgres_port": 1}).postgres_port == 1

    def test_supplying_one_field_leaves_the_others_at_their_defaults(self, settings) -> None:  # type: ignore[no-untyped-def]
        endpoints = resolve_endpoints(settings, {"qdrant_port": 7777})
        assert endpoints.qdrant_port == 7777
        assert endpoints.postgres_port == DEFAULT_POSTGRES_PORT
        assert endpoints.minio_endpoint == DEFAULT_MINIO_ENDPOINT


class TestTheFailureIsAPreflightFailureNotACrash:
    def test_it_is_catchable_as_a_probe_error(self) -> None:
        """`__main__` already renders `PhaseZeroProbeError` as a named preflight refusal
        with exit 2. Subclassing means a bad endpoint takes that same path rather than
        escaping as an uncontrolled traceback."""
        from benchmarks.phase0.live_environment import PhaseZeroProbeError

        assert issubclass(EndpointConfigurationError, PhaseZeroProbeError)

    def test_the_message_names_the_field_and_the_value(self, settings) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises(EndpointConfigurationError) as raised:
            resolve_endpoints(settings, {"postgres_port": 0})
        message = str(raised.value)
        assert "postgres_port" in message, f"the field is not named: {message}"
        assert "0" in message, f"the offending value is not shown: {message}"
