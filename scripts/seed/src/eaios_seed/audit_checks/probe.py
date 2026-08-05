"""Cross-tenant leak probe across every populated store (spec FR-045, SC-004).

Searches for one tenant's distinctive marker phrases from within another tenant's
scope. The markers exist precisely so this can produce a definite answer: ordinary
generated prose will never contain "QUIXOTIC-BASALT-MANIFEST" by chance, so a hit
is unambiguously a leak rather than a coincidence.

The relational leg runs as the RLS-enforced application role — searching as the
owner would prove nothing, since the owner is meant to see across tenants.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import text

from eaios_core.clients.stores import get_minio, get_qdrant
from eaios_core.db import create_app_engine, session_scope, tenant_scope
from eaios_core.settings import Settings, get_settings

from ..generators.markers import foreign_markers

__all__ = ["ProbeResult", "probe_object_storage", "probe_relational", "probe_vector_store"]

#: Text-bearing columns worth searching. Chosen because they carry generated prose
#: that could plausibly contain a leaked phrase.
_SEARCH_TARGETS: tuple[tuple[str, str], ...] = (
    ("documents", "title"),
    ("contracts", "counterparty_name"),
    ("news_items", "headline"),
    ("news_items", "body"),
    ("services", "description"),
    ("public_products", "description"),
    ("vacancies", "description"),
    ("performance_reviews", "summary"),
    ("audit_logs", "reason"),
)


@dataclass
class ProbeResult:
    store: str
    hits: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.hits

    def describe(self) -> str:
        if self.clean:
            return f"OK   {self.store}: no foreign markers reachable"
        return f"FAIL {self.store}:\n" + "\n".join(f"     {hit}" for hit in self.hits)


def probe_relational(
    company_slug: str, company_id: uuid.UUID, settings: Settings | None = None
) -> ProbeResult:
    """Search, as the app role scoped to one tenant, for the other's markers."""
    result = ProbeResult(store="postgres")
    phrases = foreign_markers(company_slug)
    engine = create_app_engine(settings or get_settings())

    with session_scope(engine) as session, tenant_scope(session, company_id) as scoped:
        for table, column in _SEARCH_TARGETS:
            for phrase in phrases:
                count = scoped.execute(
                    text(f"SELECT count(*) FROM {table} WHERE {column} ILIKE :needle"),
                    {"needle": f"%{phrase}%"},
                ).scalar_one()
                if count:
                    result.hits.append(f"{table}.{column} matched {phrase!r} ({count} row(s))")
    return result


def probe_object_storage(company_slug: str, settings: Settings | None = None) -> ProbeResult:
    """Read every object under this tenant's prefix and scan for foreign markers."""
    cfg = settings or get_settings()
    result = ProbeResult(store="minio")
    phrases = [phrase.encode() for phrase in foreign_markers(company_slug)]
    client = get_minio(cfg)

    if not client.bucket_exists(cfg.minio.bucket):
        return result

    for obj in client.list_objects(cfg.minio.bucket, prefix=f"{company_slug}/", recursive=True):
        if not obj.object_name:
            continue
        response = client.get_object(cfg.minio.bucket, obj.object_name)
        try:
            content = response.read()
        finally:
            response.close()
            response.release_conn()
        for phrase in phrases:
            if phrase in content:
                result.hits.append(f"{obj.object_name} contains {phrase.decode()!r}")
    return result


def probe_vector_store(settings: Settings | None = None) -> ProbeResult:
    """Assert the collections exist, are tenant-filterable, and are empty.

    Decision D2 defers indexing, so there is no content to leak yet. The *semantic*
    version of this probe — similarity search returning nothing across tenants — is
    a required acceptance test of the ingestion feature, recorded in the spec's
    carry-forward list. Asserting emptiness here keeps the gap honest rather than
    letting a vacuous pass look like a real one.

    "Tenant-filterable" was previously only a claim in this docstring: the checks
    below covered existence and point count and nothing else, so an unindexed
    `company_id` would have passed. With the collections empty by design, the
    payload index is the only structural guarantee FR-041 has in this feature —
    which makes it the one thing here most worth verifying.
    """
    from ..loaders.stores import QDRANT_COLLECTIONS, missing_payload_indexes

    cfg = settings or get_settings()
    result = ProbeResult(store="qdrant")
    client = get_qdrant(cfg)

    collections = {c.name for c in client.get_collections().collections}
    for name in QDRANT_COLLECTIONS:
        if name not in collections:
            result.hits.append(f"collection {name!r} is missing")
            continue

        missing = missing_payload_indexes(client, name)
        if missing:
            result.hits.append(
                f"collection {name!r} lacks payload indexes {sorted(missing)};"
                " tenant filtering would run unindexed (FR-041)"
            )

        points = int(client.count(name).count)
        if points:
            result.hits.append(
                f"collection {name!r} holds {points} points but indexing is deferred (D2);"
                " the semantic probe must be enabled before content is added"
            )
    return result
