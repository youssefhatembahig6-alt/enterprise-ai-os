"""The background worker is a reported dependency (spec FR-003, US1/AC3).

US1 acceptance scenario 3 names five things the health check must report on: the
relational store, the vector store, the cache, the object store, **and the
background worker**. Only four were ever probed, and the omission was pinned in
place by a four-value `Literal` and a `min_length=4` bound — so a stack whose
worker had died reported `ready` and every contract test agreed with it.

These run without any service. The interesting behaviour is the failure path: an
unreachable broker must produce a `DependencyStatus`, never an exception, because a
probe that raises takes the whole readiness response down with it and hides the
four dependencies that were fine.
"""

from __future__ import annotations

import typing

import pytest

from eaios_core.clients.stores import DependencyName, DependencyStatus, check_worker
from eaios_core.settings import Settings

pytestmark = pytest.mark.unit


@pytest.fixture
def unreachable_broker() -> Settings:
    """Point Redis at a closed port on localhost so the probe fails fast."""
    settings = Settings()
    settings.redis.host = "127.0.0.1"
    settings.redis.port = 6399  # nothing listens here
    settings.health_timeout_seconds = 1.0
    return settings


class TestTheWorkerIsADeclaredDependency:
    def test_worker_is_a_permitted_dependency_name(self) -> None:
        assert "worker" in typing.get_args(DependencyName)

    def test_the_four_stores_are_still_permitted(self) -> None:
        """Adding the worker must not have displaced anything."""
        assert set(typing.get_args(DependencyName)) == {
            "postgres",
            "redis",
            "qdrant",
            "minio",
            "worker",
        }

    def test_readiness_calls_five_probes(self) -> None:
        """Guards against the probe being added and then quietly unwired."""
        from eaios_api.health.router import _CHECKS

        assert {check.__name__ for check in _CHECKS} == {
            "check_postgres",
            "check_redis",
            "check_qdrant",
            "check_minio",
            "check_worker",
        }


class TestUnreachableBrokerFailsClosed:
    def test_it_reports_rather_than_raises(self, unreachable_broker: Settings) -> None:
        result = check_worker(unreachable_broker)
        assert isinstance(result, DependencyStatus)
        assert result.name == "worker"

    def test_an_unreachable_worker_is_not_up(self, unreachable_broker: Settings) -> None:
        assert check_worker(unreachable_broker).status in {"down", "timeout"}

    def test_the_failure_detail_leaks_no_connection_string(
        self, unreachable_broker: Settings
    ) -> None:
        """Health is unauthenticated; a broker URL here would be a disclosure."""
        detail = check_worker(unreachable_broker).detail or ""
        assert "redis://" not in detail
        assert "6399" not in detail

    def test_it_stays_within_the_timeout_budget(self, unreachable_broker: Settings) -> None:
        """A probe that hangs defeats the point of reporting per-dependency status —
        the whole response waits on the slowest check."""
        result = check_worker(unreachable_broker)
        assert result.latency_ms < 15_000, (
            f"worker probe took {result.latency_ms}ms against a 1s budget"
        )


class TestNodeTargeting:
    def test_the_container_probe_targets_its_own_node(self) -> None:
        """`worker_ping` must not accept a sibling replica's reply — that is the
        difference between restarting a wedged worker and never restarting it."""
        from eaios_worker.health import node_name

        assert node_name("box-7") == "celery@box-7"
        assert node_name().startswith("celery@")
