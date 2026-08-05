"""Tenant-namespaced storage and cache keys (spec FR-039, FR-040).

These builders are the only sanctioned way to address an object or a cache entry.
A key without a tenant prefix is a cross-tenant leak waiting to happen, so the
builders refuse to produce one rather than relying on callers to remember.
"""

from __future__ import annotations

import pytest

from eaios_core import keys
from eaios_core.classification import Classification

pytestmark = pytest.mark.unit


class TestStorageKeys:
    def test_key_layout_is_tenant_then_classification_then_type(self) -> None:
        key = keys.storage_key("niletech", Classification.RESTRICTED, "POLICY", "payroll-2026.md")
        assert key == "niletech/RESTRICTED/POLICY/payroll-2026.md"

    def test_key_always_begins_with_the_tenant(self) -> None:
        for slug in ("niletech", "delta-retail"):
            key = keys.storage_key(slug, Classification.INTERNAL, "POLICY", "leave.md")
            assert key.startswith(f"{slug}/")

    def test_identical_documents_in_two_tenants_never_collide(self) -> None:
        a = keys.storage_key("niletech", Classification.INTERNAL, "POLICY", "leave.md")
        b = keys.storage_key("delta-retail", Classification.INTERNAL, "POLICY", "leave.md")
        assert a != b

    def test_unknown_company_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="unknown company"):
            keys.storage_key("acme", Classification.INTERNAL, "POLICY", "leave.md")

    @pytest.mark.parametrize("filename", ["../escape.md", "a/b.md", "", "  "])
    def test_path_traversal_and_empty_names_are_rejected(self, filename: str) -> None:
        with pytest.raises(ValueError):
            keys.storage_key("niletech", Classification.INTERNAL, "POLICY", filename)

    def test_tenant_prefix_round_trips(self) -> None:
        key = keys.storage_key("niletech", Classification.PUBLIC, "PUBLIC", "about.md")
        assert keys.company_of_storage_key(key) == "niletech"

    def test_a_key_without_a_tenant_prefix_is_not_attributable(self) -> None:
        with pytest.raises(ValueError):
            keys.company_of_storage_key("PUBLIC/about.md")


class TestCacheKeys:
    def test_cache_key_carries_every_scoping_component(self) -> None:
        key = keys.cache_key(
            company_slug="niletech",
            permission_fingerprint="hr-read-all",
            normalized_question="how many vacation days",
            data_version="v1",
        )
        assert key.startswith("eaios:cache:niletech:")
        assert "hr-read-all" in key

    def test_two_tenants_asking_the_same_question_get_different_keys(self) -> None:
        def build(slug: str) -> str:
            return keys.cache_key(
                company_slug=slug,
                permission_fingerprint="employee",
                normalized_question="how many vacation days",
                data_version="v1",
            )

        assert build("niletech") != build("delta-retail")

    def test_two_permission_scopes_get_different_keys(self) -> None:
        """An HR-scoped answer must never be served to an ordinary employee."""

        def build(scope: str) -> str:
            return keys.cache_key(
                company_slug="niletech",
                permission_fingerprint=scope,
                normalized_question="what is the payroll total",
                data_version="v1",
            )

        assert build("hr-read-all") != build("employee")

    def test_a_data_version_change_invalidates_the_key(self) -> None:
        def build(version: str) -> str:
            return keys.cache_key(
                company_slug="niletech",
                permission_fingerprint="employee",
                normalized_question="how many vacation days",
                data_version=version,
            )

        assert build("v1") != build("v2")

    def test_unknown_company_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="unknown company"):
            keys.cache_key(
                company_slug="acme",
                permission_fingerprint="employee",
                normalized_question="q",
                data_version="v1",
            )

    def test_namespace_is_scannable_per_tenant(self) -> None:
        assert keys.cache_namespace("niletech") == "eaios:cache:niletech:*"


class TestExhaustiveCollisionSweep:
    def test_no_storage_key_collides_across_the_full_matrix(self) -> None:
        generated = {
            keys.storage_key(slug, level, doc_type, "document.md")
            for slug in ("niletech", "delta-retail")
            for level in Classification
            for doc_type in ("POLICY", "CONTRACT", "REPORT", "PUBLIC")
        }
        assert len(generated) == 2 * len(Classification) * 4
