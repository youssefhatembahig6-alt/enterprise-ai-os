"""Partial-outage reporting (spec FR-003, US1 acceptance scenario 3).

The requirement is not "reports unhealthy" — it is that a partially started
environment is *immediately visible*, naming which dependency is down while the
others are still reported up. This test stops one store and asserts exactly that.

It restores the stopped service afterwards, including on failure.
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.integration

COMPOSE_FILE = (
    Path(__file__).resolve().parents[2] / "infrastructure" / "docker-compose.yml"
)
BASE_URL = "http://localhost:8000"
TARGET = "qdrant"  # safe to stop: nothing else in this feature depends on it


def _compose(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), *args],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def stopped_dependency() -> Iterator[str]:
    if _compose("ps", "-q", TARGET).stdout.strip() == "":
        pytest.skip("stack is not running; start it with `make up`")

    _compose("stop", TARGET)
    try:
        yield TARGET
    finally:
        _compose("start", TARGET)
        # Give readiness a moment to recover so a later test does not see a
        # transient failure caused by this one.
        for _ in range(30):
            try:
                if httpx.get(f"{BASE_URL}/health/ready", timeout=5).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)


class TestDegradedReadiness:
    def test_returns_503_when_one_dependency_is_down(self, stopped_dependency: str) -> None:
        response = httpx.get(f"{BASE_URL}/health/ready", timeout=20)
        assert response.status_code == 503
        assert response.json()["status"] == "degraded"

    def test_names_the_failing_dependency_and_only_that_one(
        self, stopped_dependency: str
    ) -> None:
        body = httpx.get(f"{BASE_URL}/health/ready", timeout=20).json()
        statuses = {dep["name"]: dep["status"] for dep in body["dependencies"]}

        assert statuses[stopped_dependency] in {"down", "timeout"}

        others = {name: state for name, state in statuses.items() if name != stopped_dependency}
        assert all(state == "up" for state in others.values()), (
            f"one dependency being down must not mask the others: {others}"
        )

    def test_liveness_stays_green_during_a_dependency_outage(
        self, stopped_dependency: str
    ) -> None:
        """Otherwise Compose would restart-loop the API while a store is recovering."""
        assert httpx.get(f"{BASE_URL}/health/live", timeout=10).status_code == 200
