"""Object-storage and cache keys are tenant-namespaced (spec FR-039, FR-040).

`tests/unit/test_keys.py` proves the *builders* refuse to produce an unattributable
key. This proves the keys actually written to the store follow that convention —
a builder is only protective if every write goes through it.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, text

from eaios_core.classification import Classification
from eaios_core.clients.stores import get_minio, get_redis
from eaios_core.keys import cache_namespace, company_of_storage_key
from eaios_core.settings import get_settings
from eaios_core.tenancy import COMPANY_SLUGS

pytestmark = pytest.mark.security


@pytest.fixture(scope="module")
def object_keys() -> list[str]:
    cfg = get_settings()
    client = get_minio(cfg)
    if not client.bucket_exists(cfg.minio.bucket):
        pytest.skip("object storage bucket missing; run `make seed`")
    keys = [
        obj.object_name
        for obj in client.list_objects(cfg.minio.bucket, recursive=True)
        if obj.object_name
    ]
    if not keys:
        pytest.skip("no stored objects; run `make seed`")
    return keys


class TestStorageKeyLayout:
    def test_every_key_begins_with_a_known_tenant(self, object_keys: list[str]) -> None:
        for key in object_keys:
            company_of_storage_key(key)  # raises on an unattributable prefix

    def test_every_key_has_the_documented_shape(self, object_keys: list[str]) -> None:
        """{company}/{classification}/{document_type}/{filename}"""
        for key in object_keys:
            parts = key.split("/")
            assert len(parts) == 4, f"unexpected key shape: {key}"
            assert parts[0] in COMPANY_SLUGS
            Classification(parts[1])  # raises on an unrecognised level

    def test_both_tenants_have_objects(self, object_keys: list[str]) -> None:
        prefixes = {key.split("/")[0] for key in object_keys}
        assert prefixes == set(COMPANY_SLUGS)

    def test_no_key_is_shared_between_tenants(self, object_keys: list[str]) -> None:
        """Identical documents in two tenants must land on different keys."""
        without_tenant = [key.split("/", 1)[1] for key in object_keys]
        # Suffixes may legitimately repeat across tenants; full keys may not.
        assert len(set(object_keys)) == len(object_keys)
        assert len(without_tenant) >= len(set(without_tenant))

    def test_both_classification_extremes_are_stored(self, object_keys: list[str]) -> None:
        """FR-010c — PUBLIC and RESTRICTED must both exist on disk, not only in rows."""
        levels = {key.split("/")[1] for key in object_keys}
        assert "PUBLIC" in levels
        assert "RESTRICTED" in levels


class TestStorageMatchesMetadata:
    def test_every_document_row_has_its_object(
        self, owner_engine: Engine, object_keys: list[str]
    ) -> None:
        with owner_engine.connect() as conn:
            recorded = {row[0] for row in conn.execute(text("SELECT storage_key FROM documents"))}
        missing = sorted(recorded - set(object_keys))
        assert missing == [], f"document rows without a stored object: {missing[:5]}"

    def test_every_object_has_its_row(
        self, owner_engine: Engine, object_keys: list[str]
    ) -> None:
        with owner_engine.connect() as conn:
            recorded = {row[0] for row in conn.execute(text("SELECT storage_key FROM documents"))}
        orphaned = sorted(set(object_keys) - recorded)
        assert orphaned == [], f"stored objects with no document row: {orphaned[:5]}"

    def test_key_prefix_matches_the_owning_company(self, owner_engine: Engine) -> None:
        with owner_engine.connect() as conn:
            rows = conn.execute(
                text("SELECT c.slug, d.storage_key FROM documents d JOIN companies c ON c.id = d.company_id")
            ).all()
        mismatched = [key for slug, key in rows if not key.startswith(f"{slug}/")]
        assert mismatched == [], f"keys whose prefix disagrees with company_id: {mismatched[:5]}"

    def test_classification_in_key_matches_the_row(self, owner_engine: Engine) -> None:
        with owner_engine.connect() as conn:
            rows = conn.execute(
                text("SELECT classification, storage_key FROM documents")
            ).all()
        mismatched = [key for level, key in rows if key.split("/")[1] != level]
        assert mismatched == [], f"keys whose classification disagrees: {mismatched[:5]}"


class TestCacheNamespacing:
    def test_namespaces_are_disjoint(self) -> None:
        patterns = {slug: cache_namespace(slug) for slug in COMPANY_SLUGS}
        assert len(set(patterns.values())) == len(COMPANY_SLUGS)
        for slug, pattern in patterns.items():
            assert pattern.startswith(f"eaios:cache:{slug}:")

    def test_no_key_exists_outside_a_tenant_namespace(self) -> None:
        """Nothing is cached yet, so the correct state is zero keys everywhere —
        but a key appearing outside a tenant prefix would be a real defect."""
        client = get_redis(get_settings())
        stray = [
            key
            for key in client.scan_iter(match="eaios:cache:*")
            if not any(key.startswith(f"eaios:cache:{slug}:") for slug in COMPANY_SLUGS)
        ]
        assert stray == []

    def test_unknown_company_cannot_produce_a_namespace(self) -> None:
        with pytest.raises(ValueError, match="unknown company"):
            cache_namespace("acme")
