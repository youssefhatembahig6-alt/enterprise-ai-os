"""Document prose names only things that exist in that company (spec FR-036).

A policy that mentions a department the company does not have, or an office it does
not occupy, is exactly the kind of incoherence that discredits a demo — and it is
invisible to schema-level checks because the reference lives in prose, not in a
foreign key.

Documents are read back from object storage rather than regenerated, so this tests
what a reader would actually see.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, text

from eaios_core.clients.stores import get_minio
from eaios_core.settings import get_settings
from eaios_seed.generators.organization import DEPARTMENTS, OFFICES

pytestmark = pytest.mark.integration

TENANTS = ("niletech", "delta-retail")


@pytest.fixture(scope="module")
def engine() -> Engine:
    from eaios_core.db import create_owner_engine

    engine = create_owner_engine()
    try:
        with engine.connect() as conn:
            seeded = conn.execute(text("SELECT count(*) FROM documents")).scalar_one()
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"database unavailable: {exc}")
    if not seeded:
        pytest.skip("environment not seeded; run `make up && make seed`")
    return engine


@pytest.fixture(scope="module")
def documents() -> dict[str, str]:
    """storage_key -> decoded text, for every stored document."""
    cfg = get_settings()
    client = get_minio(cfg)
    if not client.bucket_exists(cfg.minio.bucket):
        pytest.skip("object storage bucket missing; run `make seed`")

    out: dict[str, str] = {}
    for obj in client.list_objects(cfg.minio.bucket, recursive=True):
        if not obj.object_name:
            continue
        response = client.get_object(cfg.minio.bucket, obj.object_name)
        try:
            out[obj.object_name] = response.read().decode("utf-8")
        finally:
            response.close()
            response.release_conn()
    if not out:
        pytest.skip("no stored documents; run `make seed`")
    return out


class TestCorpus:
    def test_documents_were_read_back(self, documents: dict[str, str]) -> None:
        assert len(documents) >= 20

    def test_every_document_has_content(self, documents: dict[str, str]) -> None:
        empty = [key for key, text_ in documents.items() if len(text_.strip()) < 40]
        assert empty == [], f"suspiciously short documents: {empty[:5]}"

    def test_no_unrendered_placeholders(self, documents: dict[str, str]) -> None:
        """A template that failed to substitute would ship braces or 'None'."""
        offenders = [
            key
            for key, body in documents.items()
            if "{{" in body or "{}" in body or "TODO" in body or "lorem ipsum" in body.lower()
        ]
        assert offenders == [], f"unrendered content in: {offenders[:5]}"


class TestReferencesRealEntities:
    def test_no_document_names_a_department_its_company_lacks(
        self, documents: dict[str, str]
    ) -> None:
        """Delta Retail has no Engineering and no Legal; its documents must not
        mention them as though they exist (FR-022, FR-036)."""
        all_departments = {name for depts in DEPARTMENTS.values() for name in depts}
        offenders: list[str] = []

        for key, body in documents.items():
            slug = key.split("/")[0]
            own = set(DEPARTMENTS[slug])
            foreign = all_departments - own
            for name in foreign:
                if name in body:
                    offenders.append(f"{key} mentions {name!r}, which {slug} does not have")
        assert offenders == [], "\n".join(offenders[:10])

    def test_no_document_names_a_city_its_company_lacks(
        self, documents: dict[str, str]
    ) -> None:
        all_cities = {office["city"] for offices in OFFICES.values() for office in offices}
        offenders: list[str] = []

        for key, body in documents.items():
            slug = key.split("/")[0]
            own = {office["city"] for office in OFFICES[slug]}
            for city in all_cities - own:
                if city in body:
                    offenders.append(f"{key} mentions {city!r}, where {slug} has no office")
        assert offenders == [], "\n".join(offenders[:10])

    def test_public_pages_list_the_companys_actual_cities(
        self, documents: dict[str, str]
    ) -> None:
        for slug in TENANTS:
            key = f"{slug}/PUBLIC/PUBLIC/about.md"
            assert key in documents, f"missing public page for {slug}"
            body = documents[key]
            for office in OFFICES[slug]:
                assert office["city"] in body, f"{key} omits {office['city']}"


class TestStoredContentMatchesMetadata:
    def test_recorded_digest_matches_the_stored_bytes(
        self, engine: Engine, documents: dict[str, str]
    ) -> None:
        import hashlib

        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT storage_key, content_sha256, byte_size FROM documents")
            ).all()

        mismatched: list[str] = []
        for key, digest, size in rows:
            body = documents.get(key)
            if body is None:
                mismatched.append(f"{key}: no stored object")
                continue
            raw = body.encode("utf-8")
            if hashlib.sha256(raw).hexdigest() != digest:
                mismatched.append(f"{key}: digest mismatch")
            elif len(raw) != size:
                mismatched.append(f"{key}: size {len(raw)} != recorded {size}")
        assert mismatched == [], "\n".join(mismatched[:10])


class TestPolicyProseMatchesStatedValues:
    def test_the_leave_policy_prints_its_entitlement(
        self, engine: Engine, documents: dict[str, str]
    ) -> None:
        """The number a reader sees must be the number the records use (FR-035)."""
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT d.storage_key, p.stated_values -> 'annual_leave_days' AS days"
                    " FROM policy_documents p JOIN documents d ON d.id = p.document_id"
                    " WHERE p.policy_type = 'LEAVE'"
                )
            ).all()

        assert rows, "no leave policies found"
        for key, days in rows:
            body = documents[key]
            for country, value in days.items():
                assert f"{value} days" in body, (
                    f"{key} does not state {value} days for {country}"
                )
