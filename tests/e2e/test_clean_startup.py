"""Clean-checkout startup (spec FR-002, FR-004, SC-001; US1).

Exercises the promise `make up` actually makes: one command, from a torn-down
state, to a system where every service reports healthy.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.e2e

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "infrastructure" / "docker-compose.yml"
BASE_URL = "http://localhost:8000"

#: SC-001 allows 15 minutes including image pulls on a first run.
STARTUP_BUDGET_SECONDS = 900


def _compose(*args: str, timeout: int = STARTUP_BUDGET_SECONDS) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def _docker_available() -> bool:
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


pytestmark = [pytestmark, pytest.mark.skipif(not _docker_available(), reason="Docker unavailable")]


class TestOneCommandStartup:
    def test_stack_reaches_healthy_within_budget(self) -> None:
        _compose("down", "-v")

        started = time.monotonic()
        result = subprocess.run(
            ["make", "up"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=STARTUP_BUDGET_SECONDS,
        )
        elapsed = time.monotonic() - started

        assert result.returncode == 0, f"`make up` failed:\n{result.stderr[-2000:]}"
        assert elapsed < STARTUP_BUDGET_SECONDS

        body = httpx.get(f"{BASE_URL}/health/ready", timeout=30).json()
        assert body["status"] == "ready", body

    def test_restart_returns_to_the_same_healthy_state(self) -> None:
        """FR-004 — stop and start must need no manual repair, and must not
        silently discard the volumes (that is what `make clean` is for)."""
        assert _compose("stop").returncode == 0
        assert _compose("start").returncode == 0

        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            try:
                if httpx.get(f"{BASE_URL}/health/ready", timeout=10).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(3)

        pytest.fail("stack did not return to healthy after a stop/start cycle")

    def test_health_endpoint_reports_every_backing_service(self) -> None:
        """US1/AC3 lists five: the relational store, vector store, cache, object
        store, and the background worker."""
        body = httpx.get(f"{BASE_URL}/health/ready", timeout=30).json()
        assert {dep["name"] for dep in body["dependencies"]} == {
            "postgres",
            "redis",
            "qdrant",
            "minio",
            "worker",
        }
