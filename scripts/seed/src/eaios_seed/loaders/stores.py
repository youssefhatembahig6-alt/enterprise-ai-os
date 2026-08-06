"""Loaders for all four stores, plus the emptiness pre-flight (spec FR-013, FR-014).

Relational writes go through one transaction so a failure rolls back cleanly.
Object storage and the vector store are not transactional, which is exactly why the
manifest's completion marker exists: content may survive a crash, but without the
marker the environment is unambiguously incomplete.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client import models as qmodels
from sqlalchemy import Engine, text

from eaios_core.clients.stores import get_minio, get_qdrant, get_redis
from eaios_core.db import create_owner_engine
from eaios_core.keys import cache_namespace, rate_limit_namespace
from eaios_core.settings import Settings, get_settings
from eaios_core.tenancy import COMPANY_SLUGS

from ..dataset import Dataset
from ..pipeline import INSERT_ORDER

__all__ = [
    "PAYLOAD_INDEXES",
    "QDRANT_COLLECTIONS",
    "RUNTIME_TABLES",
    "StoreCounts",
    "inspect_stores",
    "load_objects",
    "load_relational",
    "missing_payload_indexes",
    "provision_qdrant",
    "provision_redis",
    "reset_all",
]

#: Provisioned with tenant-scoped structure but left empty (decision D2).
QDRANT_COLLECTIONS: tuple[str, ...] = ("documents", "code")

#: Tenant-owned tables written at runtime rather than by the generator, so they
#: appear in neither `INSERT_ORDER` nor the fingerprint (spec 002, research R8).
#:
#: They still have to be counted and truncated. The pre-flight iterates
#: `INSERT_ORDER`, which lists seeded tables only — so without this, a contact
#: submission written before seeding would leave the environment non-empty in a
#: way the pre-flight could not see, and `seed` would proceed against a dirty
#: database. That is precisely the state FR-014 exists to refuse.
#: `sessions` and `user_credentials` join for the same reason (spec 003). Credentials
#: are written by a step that runs *after* seeding, so a re-seed of an environment that
#: still held them would leave rows pointing at users that no longer exist.
RUNTIME_TABLES: tuple[str, ...] = ("contact_submissions", "sessions", "user_credentials")

#: Payload fields indexed up front. Adding company_id to a populated collection
#: later is a reindex, and the filter path must exist before any content does.
#: Public because the cross-tenant probe verifies against this same list.
PAYLOAD_INDEXES: tuple[str, ...] = (
    "company_id", "department_id", "classification", "country", "owner_id", "document_id",
)


@dataclass(frozen=True, slots=True)
class StoreCounts:
    postgres_rows: int
    postgres_tables: int
    minio_objects: int
    qdrant_points: int
    redis_keys: int

    @property
    def is_empty(self) -> bool:
        return (
            self.postgres_rows == 0
            and self.minio_objects == 0
            and self.qdrant_points == 0
            and self.redis_keys == 0
        )

    def describe(self) -> str:
        return (
            f"  postgres: {self.postgres_rows:,} rows across {self.postgres_tables} tables\n"
            f"  minio:    {self.minio_objects:,} objects\n"
            f"  qdrant:   {self.qdrant_points:,} points\n"
            f"  redis:    {self.redis_keys:,} keys"
        )


def inspect_stores(settings: Settings | None = None) -> StoreCounts:
    """Count what currently exists. Used by the seed pre-flight and by reset."""
    cfg = settings or get_settings()
    engine = create_owner_engine(cfg)

    rows = 0
    tables = 0
    with engine.connect() as conn:
        for table in (*INSERT_ORDER, *RUNTIME_TABLES):
            try:
                count = conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
            except Exception:  # table may not exist before migrations run
                continue
            if count:
                rows += int(count)
                tables += 1

    client = get_minio(cfg)
    objects = (
        sum(1 for _ in client.list_objects(cfg.minio.bucket, recursive=True))
        if client.bucket_exists(cfg.minio.bucket)
        else 0
    )

    qdrant = get_qdrant(cfg)
    points = 0
    for collection in qdrant.get_collections().collections:
        points += int(qdrant.count(collection.name).count)

    redis_client = get_redis(cfg)
    keys = sum(
        len(list(redis_client.scan_iter(match=cache_namespace(slug))))
        for slug in COMPANY_SLUGS
    )

    return StoreCounts(rows, tables, objects, points, keys)


def load_relational(dataset: Dataset, manifest_row: dict[str, Any], engine: Engine) -> int:
    """Insert everything in one transaction, in FK-safe order.

    The manifest is written first with ``completed_at`` unset and updated at the
    end, inside the same transaction — so either the whole dataset and its
    completion marker land together, or neither does.
    """
    inserted = 0
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO dataset_manifest (id, schema_version, root_seed, reference_date,"
                " generator_version, profile, entity_counts, family_digests, root_fingerprint,"
                " fingerprint_exclusions, started_at, completed_at, duration_seconds, host_platform)"
                " VALUES (:id, :schema_version, :root_seed, :reference_date, :generator_version,"
                " :profile, CAST(:entity_counts AS jsonb), CAST(:family_digests AS jsonb),"
                " :root_fingerprint, CAST(:fingerprint_exclusions AS jsonb), :started_at,"
                " NULL, NULL, :host_platform)"
            ),
            _jsonify(manifest_row, exclude={"completed_at", "duration_seconds"}),
        )

        for table in INSERT_ORDER:
            rows = dataset.rows.get(table)
            if not rows:
                continue

            # departments.head_user_id and users.department_id reference each other,
            # so neither table can be inserted with both sides populated. The head is
            # deferred and applied below, which is precisely what the nullable column
            # in the model exists for (data-model.md §2).
            payload = (
                [dict(row, head_user_id=None) for row in rows]
                if table == "departments"
                else rows
            )

            columns = list(payload[0])
            placeholders = ", ".join(f":{column}" for column in columns)
            statement = text(
                f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
            )
            conn.execute(statement, [_jsonify(row) for row in payload])
            inserted += len(payload)

            if table == "users":
                # Users now exist; close the circular reference.
                conn.execute(
                    text("UPDATE departments SET head_user_id = :head_user_id WHERE id = :id"),
                    [
                        {"id": dept["id"], "head_user_id": dept["head_user_id"]}
                        for dept in dataset.rows.get("departments", [])
                        if dept.get("head_user_id") is not None
                    ],
                )

        # Completion marker last (FR-014b).
        conn.execute(
            text(
                "UPDATE dataset_manifest SET completed_at = :completed_at,"
                " duration_seconds = :duration_seconds WHERE id = :id"
            ),
            {
                "id": manifest_row["id"],
                "completed_at": manifest_row["completed_at"],
                "duration_seconds": manifest_row["duration_seconds"],
            },
        )
    return inserted


def _jsonify(row: dict[str, Any], exclude: set[str] | None = None) -> dict[str, Any]:
    """Serialize dict/list values so psycopg can bind them as JSONB text."""
    import json

    skip = exclude or set()
    out: dict[str, Any] = {}
    for key, value in row.items():
        if key in skip:
            continue
        out[key] = json.dumps(value, default=str) if isinstance(value, dict | list) else value
    return out


def load_objects(dataset: Dataset, settings: Settings | None = None) -> int:
    cfg = settings or get_settings()
    client = get_minio(cfg)
    if not client.bucket_exists(cfg.minio.bucket):
        client.make_bucket(cfg.minio.bucket)

    for key, content in sorted(dataset.files.items()):
        client.put_object(
            cfg.minio.bucket,
            key,
            io.BytesIO(content),
            length=len(content),
            content_type="text/markdown; charset=utf-8",
        )
    return len(dataset.files)


def provision_qdrant(settings: Settings | None = None) -> int:
    """Create tenant-scoped collections and leave them empty (decision D2).

    The payload indexes are the point of this function. Decision D2 leaves the
    collections empty, so the index is the *only* structural tenant guarantee
    FR-041 has in this feature, and the ingestion work that follows builds its
    filter on it.

    Index creation used to be wrapped in `except Exception: continue`, which was
    there to tolerate re-running against an already-indexed collection — but it
    equally swallowed a genuine failure, so every index could fail to be created
    and the seed would still report success. Now the result is read back and a
    missing index raises: provisioning that silently provisions nothing is worse
    than provisioning that fails.
    """
    cfg = settings or get_settings()
    client = get_qdrant(cfg)
    existing = {c.name for c in client.get_collections().collections}

    for name in QDRANT_COLLECTIONS:
        if name not in existing:
            client.create_collection(
                collection_name=name,
                vectors_config=qmodels.VectorParams(
                    size=cfg.qdrant.vector_size,
                    distance=qmodels.Distance[cfg.qdrant.distance.upper()],
                ),
            )
        for field in PAYLOAD_INDEXES:
            client.create_payload_index(
                collection_name=name,
                field_name=field,
                field_schema=qmodels.PayloadSchemaType.KEYWORD,
            )

        missing = missing_payload_indexes(client, name)
        if missing:
            raise RuntimeError(
                f"qdrant collection {name!r} is missing payload indexes {sorted(missing)}; "
                "tenant filtering would run unindexed (FR-041)"
            )
    return len(QDRANT_COLLECTIONS)


def missing_payload_indexes(client: QdrantClient, collection: str) -> set[str]:
    """Payload fields that should be indexed on `collection` but are not.

    Shared with the cross-tenant probe so provisioning and verification cannot
    disagree about what "indexed" means.
    """
    indexed = set(client.get_collection(collection).payload_schema or {})
    return set(PAYLOAD_INDEXES) - indexed


def provision_redis(settings: Settings | None = None) -> int:
    """No cached values yet; this only asserts reachability and clears namespaces."""
    cfg = settings or get_settings()
    client = get_redis(cfg)
    client.ping()
    return 0


def reset_all(settings: Settings | None = None) -> None:
    """Destroy everything. Only reachable through the guarded `reset` command."""
    cfg = settings or get_settings()

    engine = create_owner_engine(cfg)
    with engine.begin() as conn:
        tables = (
            ", ".join(reversed(INSERT_ORDER))
            + ", dataset_manifest, "
            + ", ".join(RUNTIME_TABLES)
        )
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))

    client = get_minio(cfg)
    if client.bucket_exists(cfg.minio.bucket):
        for obj in list(client.list_objects(cfg.minio.bucket, recursive=True)):
            if obj.object_name:
                client.remove_object(cfg.minio.bucket, obj.object_name)

    qdrant = get_qdrant(cfg)
    for collection in qdrant.get_collections().collections:
        qdrant.delete_collection(collection.name)

    redis_client = get_redis(cfg)
    for slug in COMPANY_SLUGS:
        keys = list(redis_client.scan_iter(match=cache_namespace(slug)))
        if keys:
            redis_client.delete(*keys)

    # The anonymous write bounds (spec 002 FR-024d, FR-047b). Cleared here because
    # `make reset` promises to destroy every cache entry in the environment, and
    # these were left behind: they are keyed under a different prefix and are
    # deliberately not tenant-scoped, so the per-tenant scan above never matched
    # them. A developer resetting for a clean environment kept whatever bound they
    # had accumulated, for up to an hour.
    bounds = list(redis_client.scan_iter(match=rate_limit_namespace()))
    if bounds:
        redis_client.delete(*bounds)
