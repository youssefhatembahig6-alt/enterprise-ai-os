"""Dependency failure classification (spec FR-003; converge finding F6).

`contracts/health-api.yaml` documents three statuses — `up`, `down`, `timeout` —
and the two failure statuses carry different operational meaning: a refused
connection usually means the service is not running, while a timeout usually means
it is running but saturated or wedged. Before this, every failure collapsed to
`down`, leaving a documented value that no code path could produce.
"""

from __future__ import annotations

import pytest

from eaios_core.clients.stores import DependencyStatus, _classify

pytestmark = pytest.mark.unit


class RedisTimeoutError(Exception):
    """Stands in for redis.TimeoutError without importing the driver's hierarchy."""


class ConnectionTimeoutError(Exception):
    """A driver-specific timeout type that does not inherit from TimeoutError."""


class QdrantResponseError(Exception):
    """Stands in for a non-timeout driver failure."""


class TestTimeoutDetection:
    @pytest.mark.parametrize(
        "exc",
        [
            TimeoutError("timed out"),
            ConnectionTimeoutError("read timed out"),
            RedisTimeoutError("Timeout connecting to server"),
        ],
    )
    def test_timeout_shaped_failures_classify_as_timeout(self, exc: Exception) -> None:
        assert _classify(exc) == "timeout"

    def test_oserror_with_timeout_message_classifies_as_timeout(self) -> None:
        assert _classify(OSError("connection timed out")) == "timeout"


class TestDownDetection:
    @pytest.mark.parametrize(
        "exc",
        [
            ConnectionRefusedError("refused"),
            QdrantResponseError("bad gateway"),
            ValueError("misconfigured"),
            OSError("host unreachable"),
        ],
    )
    def test_other_failures_classify_as_down(self, exc: Exception) -> None:
        assert _classify(exc) == "down"

    def test_a_refused_connection_is_not_a_timeout(self) -> None:
        """The distinction only helps if it is actually discriminating."""
        assert _classify(ConnectionRefusedError("refused")) != "timeout"


class TestStatusesMatchTheContract:
    def test_every_produced_status_is_one_the_contract_declares(self) -> None:
        declared = {"up", "down", "timeout"}
        produced = {
            "up",
            _classify(ConnectionRefusedError()),
            _classify(TimeoutError()),
        }
        assert produced <= declared
        # And the reverse: all three are now reachable, which is the point.
        assert produced == declared

    def test_dependency_status_accepts_timeout(self) -> None:
        status = DependencyStatus("redis", "timeout", 2000, "TimeoutError")
        assert status.status == "timeout"
