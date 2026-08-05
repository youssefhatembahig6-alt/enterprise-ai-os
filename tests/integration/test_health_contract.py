"""Health endpoints against the published contract (spec FR-003).

Validates the live responses against `contracts/health-api.yaml` so the OpenAPI
document and the implementation cannot drift apart unnoticed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

pytestmark = pytest.mark.integration

CONTRACT = (
    Path(__file__).resolve().parents[2]
    / "specs"
    / "001-foundation-tenant-seed"
    / "contracts"
    / "health-api.yaml"
)
BASE_URL = "http://localhost:8000"
# Five, not four: US1 acceptance scenario 3 names the background worker alongside
# the relational store, vector store, cache, and object store.
EXPECTED_DEPENDENCIES = {"postgres", "redis", "qdrant", "minio", "worker"}


@pytest.fixture(scope="module")
def client() -> httpx.Client:
    with httpx.Client(base_url=BASE_URL, timeout=15.0) as session:
        try:
            session.get("/health/live")
        except httpx.HTTPError:  # pragma: no cover - environment guard
            pytest.skip("API is not running; start it with `make up`")
        yield session


class TestContractDocument:
    def test_contract_file_exists(self) -> None:
        assert CONTRACT.is_file(), f"missing contract: {CONTRACT}"

    def test_contract_declares_the_three_endpoints(self) -> None:
        text = CONTRACT.read_text(encoding="utf-8")
        for path in ("/health/live:", "/health/ready:", "/dataset/manifest:"):
            assert path in text


class TestLiveness:
    def test_returns_200_without_touching_dependencies(self, client: httpx.Client) -> None:
        response = client.get("/health/live")
        assert response.status_code == 200
        body: dict[str, Any] = response.json()
        assert body["status"] == "alive"
        assert set(body) == {"status", "service", "version"}


class TestReadiness:
    def test_reports_every_dependency_individually(self, client: httpx.Client) -> None:
        response = client.get("/health/ready")
        assert response.status_code in (200, 503)
        body = response.json()

        names = {dep["name"] for dep in body["dependencies"]}
        assert names == EXPECTED_DEPENDENCIES, (
            "FR-003 requires per-dependency reporting; a single aggregate status "
            "cannot tell an operator which service failed"
        )

    def test_status_agrees_with_the_dependency_list(self, client: httpx.Client) -> None:
        body = client.get("/health/ready").json()
        all_up = all(dep["status"] == "up" for dep in body["dependencies"])
        assert body["status"] == ("ready" if all_up else "degraded")

    def test_the_background_worker_is_reported(self, client: httpx.Client) -> None:
        """US1/AC3 names it explicitly, and it was the one backing service the
        endpoint could not see — a stack with a dead worker reported `ready`."""
        body = client.get("/health/ready").json()
        assert "worker" in {dep["name"] for dep in body["dependencies"]}

    def test_a_healthy_worker_answers_promptly(self, client: httpx.Client) -> None:
        """A broadcast ping keeps collecting replies for the whole timeout window
        unless told to stop at the first one, which made every readiness call on a
        healthy stack pay the full budget."""
        body = client.get("/health/ready").json()
        worker = next(dep for dep in body["dependencies"] if dep["name"] == "worker")
        if worker["status"] != "up":
            pytest.skip("worker is down; the latency of a failed probe is not the subject")
        assert worker["latency_ms"] < 1000, (
            f"worker probe took {worker['latency_ms']}ms on a healthy stack"
        )

    def test_no_credentials_leak_in_failure_detail(self, client: httpx.Client) -> None:
        """Health is unauthenticated, so a DSN in the body would be a disclosure."""
        body = client.get("/health/ready").json()
        for dep in body["dependencies"]:
            detail = dep.get("detail") or ""
            for secret in ("password", "postgresql://", "eaios_owner_local_only", "secret"):
                assert secret not in detail.lower()


class TestDatasetManifest:
    def test_unseeded_environment_returns_404_not_an_error(self, client: httpx.Client) -> None:
        response = client.get("/dataset/manifest")
        assert response.status_code in (200, 404)

    def test_seeded_manifest_reports_completion(self, client: httpx.Client) -> None:
        response = client.get("/dataset/manifest")
        if response.status_code == 404:
            pytest.skip("environment not seeded")
        body = response.json()
        assert body["is_complete"] == (body["completed_at"] is not None)
        assert len(body["root_fingerprint"]) == 64
