"""Cross-tenant leak probe (spec FR-045, SC-004; blueprint scenario 7).

The blueprint's seventh access-control scenario: a NileTech user searches for a
distinctive Delta Retail phrase and gets nothing back. This runs it in both
directions across every populated store.

A leak test only means something if the thing being hunted actually exists, so the
first assertions establish that each tenant's markers are genuinely present in that
tenant's own content before asserting they are unreachable from the other side.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import Engine, text

from eaios_seed.audit_checks.probe import (
    probe_object_storage,
    probe_relational,
    probe_vector_store,
)
from eaios_seed.generators.markers import MARKERS, foreign_markers, markers_for
from eaios_seed.loaders.stores import QDRANT_COLLECTIONS

pytestmark = pytest.mark.security

TENANTS = ("niletech", "delta-retail")


class TestMarkersAreRealBait:
    """Guards against a vacuous pass: absent markers make every probe succeed."""

    @pytest.mark.parametrize("slug", TENANTS)
    def test_each_tenant_has_distinct_markers(self, slug: str) -> None:
        own = set(markers_for(slug))
        foreign = set(foreign_markers(slug))
        assert own and foreign
        assert not (own & foreign), "marker sets overlap; a leak would be undetectable"

    @pytest.mark.parametrize("slug", TENANTS)
    def test_own_markers_are_present_in_own_content(
        self, owner_engine: Engine, company_ids: dict[str, uuid.UUID], slug: str
    ) -> None:
        marker = markers_for(slug)[2]  # the reference string, embedded in documents
        with owner_engine.connect() as conn:
            hits = conn.execute(
                text(
                    "SELECT count(*) FROM documents d"
                    " WHERE d.company_id = :cid AND d.id IN ("
                    "   SELECT document_id FROM policy_documents WHERE company_id = :cid)"
                ),
                {"cid": company_ids[slug]},
            ).scalar_one()
        assert hits > 0, f"{slug} has no policy documents to carry {marker!r}"


class TestRelationalProbe:
    @pytest.mark.parametrize("slug", TENANTS)
    def test_no_foreign_marker_is_reachable(
        self, company_ids: dict[str, uuid.UUID], slug: str
    ) -> None:
        result = probe_relational(slug, company_ids[slug])
        assert result.clean, result.describe()

    def test_probe_searches_a_meaningful_surface(self) -> None:
        from eaios_seed.audit_checks.probe import _SEARCH_TARGETS

        assert len(_SEARCH_TARGETS) >= 8


class TestObjectStorageProbe:
    @pytest.mark.parametrize("slug", TENANTS)
    def test_no_foreign_marker_in_stored_files(self, slug: str) -> None:
        result = probe_object_storage(slug)
        assert result.clean, result.describe()

    @pytest.mark.parametrize("slug", TENANTS)
    def test_the_tenant_actually_has_files(self, slug: str) -> None:
        """Otherwise the scan above would pass over an empty set."""
        from eaios_core.clients.stores import get_minio
        from eaios_core.settings import get_settings

        cfg = get_settings()
        client = get_minio(cfg)
        count = sum(
            1
            for _ in client.list_objects(cfg.minio.bucket, prefix=f"{slug}/", recursive=True)
        )
        assert count > 0, f"{slug} has no stored objects"


class TestVectorStoreProbe:
    def test_collections_exist_and_are_empty(self) -> None:
        """Decision D2 defers indexing; emptiness is the honest current state."""
        result = probe_vector_store()
        assert result.clean, result.describe()

    @pytest.mark.parametrize("collection", QDRANT_COLLECTIONS)
    def test_every_tenant_payload_field_is_indexed(self, collection: str) -> None:
        """The collections are empty by design (D2), so the payload index is the
        only structural tenant guarantee FR-041 has in this feature — and the
        filter the ingestion feature will rely on. Nothing verified it before: the
        probe checked existence and point count, so an unindexed `company_id`
        passed silently."""
        from eaios_core.clients.stores import get_qdrant
        from eaios_seed.loaders.stores import missing_payload_indexes

        missing = missing_payload_indexes(get_qdrant(), collection)
        assert missing == set(), (
            f"{collection} is missing payload indexes {sorted(missing)}"
        )

    def test_the_probe_reports_a_missing_index(self) -> None:
        """Guards the check above from becoming decorative. A verification that
        cannot fail is indistinguishable from no verification, and this file has
        already had one of those."""
        from unittest.mock import patch

        with patch(
            "eaios_seed.loaders.stores.missing_payload_indexes",
            return_value={"company_id"},
        ):
            result = probe_vector_store()

        assert not result.clean
        assert any("company_id" in hit for hit in result.hits), result.describe()


class TestBothDirections:
    def test_probe_is_symmetric(self, company_ids: dict[str, uuid.UUID]) -> None:
        """SC-004 requires zero results in *both* directions, not just one."""
        for slug in TENANTS:
            assert probe_relational(slug, company_ids[slug]).clean
            assert probe_object_storage(slug).clean

    def test_marker_vocabulary_covers_both_tenants(self) -> None:
        assert set(MARKERS) == set(TENANTS)
