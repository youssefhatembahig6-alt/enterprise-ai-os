"""`LiveEnvironment` against the real stack, read-only (D1, D2, D3).

**Why this file had to exist.** Every other test of the Phase 0 harness injects a fake
environment — deliberately, so the deciding logic runs in ordinary CI. The consequence is
that `LiveEnvironment` itself, the one module that talks to PostgreSQL, MinIO and Qdrant,
had no test at all. It shipped with four schema mismatches and a hostname bug, all 674 unit
tests green, and could not complete a single probe.

So this file exercises the real thing. It is **read-only**: it counts, reads and stats. It
creates no collection, writes no row, uploads no object, and never runs ingestion.

**It is not ordinary CI.** It needs the seeded full-profile stack *and* the pinned local
BGE-M3 weights, neither of which ordinary CI has (FR-035b). It carries its own
`phase0_controlled` marker so `-m integration` does not select it, and it skips with a named
reason when the stack is absent — a developer without Docker sees why rather than a failure
they cannot act on.
"""

from __future__ import annotations

import os
import pathlib
from typing import Any, Final

import pytest

from benchmarks.phase0.config import MeasurementConfig, load_settings
from benchmarks.phase0.live_environment import LiveEnvironment, PhaseZeroProbeError

#: **Not** `integration`. Ordinary CI runs `-m integration` against a seeded stack, but
#: it is model-free and has no BGE-M3 weights, so these would fail there rather than
#: skip — and `EAIOS_NO_SKIPS` would turn a skip into a failure anyway. Opt in with
#: `-m phase0_controlled` once both prerequisites are provisioned.
pytestmark = pytest.mark.phase0_controlled

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[2]

EXPECTED_DOCUMENTS: Final[int] = 105
EXPECTED_PROFILE: Final[str] = "full"
PINNED_REVISION: Final[str] = "5617a9f61b028005a4858fdac845db406aefb181"
PINNED_CHECKSUM: Final[str] = (
    "b5e0ce3470abf5ef3831aa1bd5553b486803e83251590ab7ff35a117cf6aad38"
)


@pytest.fixture(scope="module")
def settings() -> MeasurementConfig:
    return load_settings([])


@pytest.fixture(scope="module")
def environment(settings: MeasurementConfig) -> LiveEnvironment:
    return LiveEnvironment(settings)


@pytest.fixture(scope="module")
def observed(environment: LiveEnvironment) -> dict[str, Any]:
    """One observation, shared. Skips with a named reason when the stack is absent."""
    try:
        return environment.observe()
    except PhaseZeroProbeError as unreachable:
        pytest.skip(f"the seeded stack is not available: {unreachable}")


class TestTheStoresAreReachableThroughHostEndpoints:
    """D1: the benchmark runs on the host; `.env` carries in-container hostnames."""

    @pytest.mark.parametrize("service", ["postgres", "minio", "qdrant"])
    def test_the_store_is_reachable(self, observed: dict[str, Any], service: str) -> None:
        assert observed[f"{service}_reachable"] is True, (
            f"{service} reported unreachable while the stack is up. The benchmark runs"
            " from the host, so it must resolve the compose-published endpoints rather"
            " than the in-container hostnames in .env"
        )

    def test_the_resolved_endpoints_are_host_reachable(
        self, environment: LiveEnvironment
    ) -> None:
        endpoints = environment.endpoints()
        assert endpoints.postgres_host not in ("postgres",), (
            f"postgres host resolved to {endpoints.postgres_host!r}, which does not"
            " resolve from the host"
        )
        assert endpoints.qdrant_host not in ("qdrant",)
        assert not endpoints.minio_endpoint.startswith("minio:")


class TestTheCorpusIsTheDeclaredOne:
    def test_the_active_profile_is_full(self, observed: dict[str, Any]) -> None:
        assert observed["active_profile"] == EXPECTED_PROFILE

    def test_there_are_exactly_105_text_documents(self, observed: dict[str, Any]) -> None:
        assert observed["text_document_count"] == EXPECTED_DOCUMENTS, (
            f"found {observed['text_document_count']} documents; the declared measurement"
            f" is over exactly {EXPECTED_DOCUMENTS}"
        )

    def test_the_code_collection_is_empty(self, observed: dict[str, Any]) -> None:
        """D2: emptiness proven against the real `code` Qdrant collection.

        There is no `corpus` column. The code corpus is a *collection*, and Feature 001
        created it empty on purpose.
        """
        assert observed["code_document_count"] == 0

    def test_empty_is_distinguishable_from_unverified(
        self, observed: dict[str, Any]
    ) -> None:
        """D3: the count is a number that was read, not a number that was defaulted."""
        assert observed["code_collection_verified"] is True, (
            "the code collection count is zero because it was not checked, which is not"
            " the same claim as zero because it was checked"
        )


class TestEverySourceObjectIsReadable:
    def test_no_object_is_unreadable(self, observed: dict[str, Any]) -> None:
        assert observed["unreadable_objects"] == (), (
            f"{len(observed['unreadable_objects'])} source object(s) could not be read"
            " from the configured bucket"
        )

    def test_the_configured_bucket_was_used(self, environment: LiveEnvironment) -> None:
        assert environment.endpoints().minio_bucket == "eaios", (
            "the bucket must come from settings; a hardcoded 'documents' bucket does not"
            " exist in this environment"
        )


class TestTheCorpusCarriesRealAclDerivedRoles:
    """D2: `allowed_roles` is not a column — it is derived from `document_acl`."""

    @pytest.fixture(scope="class")
    def corpus(self, environment: LiveEnvironment) -> list[dict[str, Any]]:
        try:
            return environment.load_corpus()
        except PhaseZeroProbeError as unreachable:
            pytest.skip(f"the seeded stack is not available: {unreachable}")

    def test_the_corpus_has_every_document(self, corpus: list[dict[str, Any]]) -> None:
        assert len(corpus) == EXPECTED_DOCUMENTS

    def test_every_document_carries_every_authorization_attribute(
        self, corpus: list[dict[str, Any]]
    ) -> None:
        from benchmarks.phase0.preview_index import REQUIRED_PAYLOAD_FIELDS

        for document in corpus:
            missing = [f for f in REQUIRED_PAYLOAD_FIELDS if f not in document]
            assert missing == [], f"{document['document_id']} is missing {missing}"

    def test_allowed_roles_is_a_list_derived_from_the_acl(
        self, corpus: list[dict[str, Any]]
    ) -> None:
        for document in corpus:
            assert isinstance(document["allowed_roles"], list), (
                f"{document['document_id']} allowed_roles is"
                f" {type(document['allowed_roles'])}, not a list"
            )

    def test_the_acl_join_reproduces_the_database(
        self, corpus: list[dict[str, Any]], environment: LiveEnvironment
    ) -> None:
        """Vacuity guard, stated against reality rather than against a hope.

        This corpus carries **no ROLE grants at all** — `document_acl` holds four rows,
        every one `principal_type='USER'`, `permission='READ'`. So an assertion that some
        document has a non-empty `allowed_roles` would be asserting something false about
        the seed, and "fixing" it would have meant loosening a correct query.

        What can be proven is that the join *ran and agrees*: the grants the loader
        surfaces must equal the grants the table holds.
        """
        from sqlalchemy import text

        with environment.open_connection() as connection:
            rows = connection.execute(
                text(
                    "SELECT principal_type, count(DISTINCT (document_id, principal_id))"
                    " FROM document_acl WHERE permission IN ('READ','WRITE','OWNER')"
                    " GROUP BY principal_type"
                )
            ).all()
        expected = {str(name): int(count) for name, count in rows}

        observed_roles = sum(len(d["allowed_roles"]) for d in corpus)
        observed_users = sum(len(d["explicit_grant_user_ids"]) for d in corpus)

        assert observed_roles == expected.get("ROLE", 0), (
            f"loader surfaced {observed_roles} role grants, the table holds"
            f" {expected.get('ROLE', 0)}"
        )
        assert observed_users == expected.get("USER", 0), (
            f"loader surfaced {observed_users} user grants, the table holds"
            f" {expected.get('USER', 0)}"
        )

    def test_the_join_surfaced_something(
        self, corpus: list[dict[str, Any]]
    ) -> None:
        """At least one grant of *some* kind, or the join is not executing at all."""
        total = sum(
            len(d["allowed_roles"]) + len(d["explicit_grant_user_ids"]) for d in corpus
        )
        assert total > 0, (
            "the loader surfaced no ACL grant of any kind. `document_acl` is not empty,"
            " so the join is not running"
        )

    def test_every_document_has_readable_content(self, corpus: list[dict[str, Any]]) -> None:
        empty = [d["document_id"] for d in corpus if not str(d["content"]).strip()]
        assert empty == [], f"{len(empty)} document(s) fetched with empty content"


class TestTheWeightsAreThePinnedOnes:
    def test_the_revision_is_reported(self, observed: dict[str, Any]) -> None:
        assert observed["weights_revision"] == PINNED_REVISION, (
            f"weights revision is {observed['weights_revision']!r}. Run the provisioning"
            " helper in verify-only mode to write the marker after checking the checksum"
        )

    def test_the_checksum_matches(self, observed: dict[str, Any]) -> None:
        assert observed["weights_checksum"] == PINNED_CHECKSUM


class TestPreflightPassesAgainstTheRealStack:
    def test_every_prerequisite_is_satisfied(self, observed: dict[str, Any]) -> None:
        from benchmarks.phase0 import preflight

        class _Fixed:
            def observe(self) -> dict[str, Any]:
                return observed

        report = preflight.run(_Fixed())
        assert report.ok, report.describe()


class TestFailuresCannotBecomePlausibleZeros:
    """D3, behaviourally: every probe failure must be named, never defaulted."""

    def test_an_unreachable_postgres_raises_rather_than_counting_zero(
        self, settings: MeasurementConfig
    ) -> None:
        broken = LiveEnvironment(settings, endpoint_overrides={"postgres_port": 1})
        with pytest.raises(PhaseZeroProbeError) as raised:
            broken.observe()
        assert "postgres" in str(raised.value).lower()

    def test_an_unreachable_qdrant_raises_rather_than_reporting_an_empty_collection(
        self, settings: MeasurementConfig
    ) -> None:
        broken = LiveEnvironment(settings, endpoint_overrides={"qdrant_port": 1})
        with pytest.raises(PhaseZeroProbeError):
            broken.observe()

    def test_an_unreachable_minio_raises_rather_than_reporting_nothing_unreadable(
        self, settings: MeasurementConfig
    ) -> None:
        broken = LiveEnvironment(settings, endpoint_overrides={"minio_endpoint": "127.0.0.1:1"})
        with pytest.raises(PhaseZeroProbeError):
            broken.observe()

    def test_a_missing_revision_marker_is_absent_not_invented(
        self, settings: MeasurementConfig, tmp_path: pathlib.Path
    ) -> None:
        import dataclasses

        elsewhere = dataclasses.replace(settings, weights_directory=tmp_path)
        observed = LiveEnvironment(elsewhere).observe()
        assert observed["weights_revision"] is None
        assert observed["weights_checksum"] is None

    def test_the_diagnostics_expose_no_credentials(self, settings: MeasurementConfig) -> None:
        """A probe failure is pasted into tickets; it must carry no secret."""
        broken = LiveEnvironment(settings, endpoint_overrides={"postgres_port": 1})
        try:
            broken.observe()
        except PhaseZeroProbeError as failure:
            message = str(failure)
        else:  # pragma: no cover - the probe is expected to fail
            pytest.fail("the broken probe did not fail")

        secret = os.environ.get("POSTGRES_PASSWORD") or "eaios_owner_password"
        assert secret not in message, "the failure message leaked a credential"
        assert "password" not in message.lower()
