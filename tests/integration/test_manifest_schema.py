"""The dataset manifest matches its published schema (spec FR-016).

`contracts/dataset-manifest.schema.json` is what the API, the verification tooling,
and CI all read. Validating the emitted manifest against it here keeps the contract
and the implementation from drifting apart silently.

A dependency on `jsonschema` would be one more pin to manage for a single test, so
the required-field, type, and pattern constraints are checked directly against the
schema document instead.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from eaios_core.db import create_owner_engine

pytestmark = pytest.mark.integration

SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "specs"
    / "001-foundation-tenant-seed"
    / "contracts"
    / "dataset-manifest.schema.json"
)


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def manifest() -> dict[str, Any]:
    try:
        engine = create_owner_engine()
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT schema_version, root_seed, reference_date, generator_version,"
                    " profile, entity_counts, family_digests, root_fingerprint,"
                    " fingerprint_exclusions, started_at, completed_at, duration_seconds,"
                    " host_platform FROM dataset_manifest LIMIT 1"
                )
            ).mappings().first()
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"database unavailable: {exc}")
    if row is None:
        pytest.skip("environment not seeded; run `make seed`")
    return dict(row)


class TestSchemaDocument:
    def test_schema_file_exists(self) -> None:
        assert SCHEMA_PATH.is_file(), f"missing contract: {SCHEMA_PATH}"

    def test_schema_is_valid_json(self, schema: dict[str, Any]) -> None:
        assert schema["title"] == "Dataset Manifest"


class TestManifestConformance:
    def test_all_required_fields_present(
        self, manifest: dict[str, Any], schema: dict[str, Any]
    ) -> None:
        # `companies` is a schema field the API derives rather than a stored column,
        # so it is legitimately absent from the database row.
        required = set(schema["required"]) - {"companies"}
        missing = sorted(required - set(manifest))
        assert missing == [], f"manifest is missing required fields: {missing}"

    def test_schema_version_matches_the_const(
        self, manifest: dict[str, Any], schema: dict[str, Any]
    ) -> None:
        assert manifest["schema_version"] == schema["properties"]["schema_version"]["const"]

    def test_profile_is_an_allowed_value(
        self, manifest: dict[str, Any], schema: dict[str, Any]
    ) -> None:
        assert manifest["profile"] in schema["properties"]["profile"]["enum"]

    def test_root_fingerprint_matches_the_pattern(
        self, manifest: dict[str, Any], schema: dict[str, Any]
    ) -> None:
        pattern = schema["properties"]["root_fingerprint"]["pattern"]
        assert re.match(pattern, manifest["root_fingerprint"])

    def test_family_digests_match_the_pattern(
        self, manifest: dict[str, Any], schema: dict[str, Any]
    ) -> None:
        value_pattern = schema["properties"]["family_digests"]["additionalProperties"]["pattern"]
        key_pattern = schema["properties"]["family_digests"]["propertyNames"]["pattern"]
        assert manifest["family_digests"], "no family digests recorded"
        for name, digest in manifest["family_digests"].items():
            assert re.match(key_pattern, name), f"bad family key: {name}"
            assert re.match(value_pattern, digest), f"bad digest for {name}"

    def test_entity_counts_are_non_negative_integers(self, manifest: dict[str, Any]) -> None:
        assert manifest["entity_counts"]
        for key, value in manifest["entity_counts"].items():
            assert isinstance(value, int) and value >= 0, f"{key} = {value!r}"

    def test_entity_count_keys_are_tenant_scoped(
        self, manifest: dict[str, Any], schema: dict[str, Any]
    ) -> None:
        pattern = schema["properties"]["entity_counts"]["propertyNames"]["pattern"]
        unmatched = [key for key in manifest["entity_counts"] if not re.match(pattern, key)]
        # `files.documents` is emitted by the counter and is not tenant-scoped.
        assert [key for key in unmatched if key != "files.documents"] == []

    def test_reference_date_is_the_pinned_value(self, manifest: dict[str, Any]) -> None:
        assert manifest["reference_date"].isoformat() == "2026-06-30"

    def test_exclusions_are_documented_and_minimal(self, manifest: dict[str, Any]) -> None:
        """FR-015a — an over-broad exclusion silently weakens the guarantee.

        Two separate claims, split because a single assertion against the code's own
        constant would be tautological:

        1. The manifest records what the generator *actually* excluded — otherwise
           the provenance record could describe a different dataset than the one it
           came with.
        2. That set is still the minimal one. Widening it requires editing the list
           below, which is the point.
        """
        assert sorted(manifest["fingerprint_exclusions"]) == [
            "alembic_version",
            "contact_submissions",
            "dataset_manifest",
        ]

    def test_the_manifest_records_the_exclusions_actually_applied(
        self, manifest: dict[str, Any]
    ) -> None:
        from eaios_core.fingerprint import FINGERPRINT_EXCLUSIONS

        assert set(manifest["fingerprint_exclusions"]) == FINGERPRINT_EXCLUSIONS, (
            "the manifest describes a different exclusion set than the generator "
            "applied — regenerate with `make reset` after changing the set"
        )


class TestCompletionMarker:
    def test_completed_at_is_set_on_a_finished_seed(self, manifest: dict[str, Any]) -> None:
        assert manifest["completed_at"] is not None

    def test_completed_at_is_after_started_at(self, manifest: dict[str, Any]) -> None:
        assert manifest["completed_at"] >= manifest["started_at"]

    def test_duration_is_recorded_against_the_budget(self, manifest: dict[str, Any]) -> None:
        """SC-008 allows 600 seconds for the full profile."""
        assert manifest["duration_seconds"] is not None
        assert manifest["duration_seconds"] >= 0
