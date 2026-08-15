"""The live observers — the only module here that touches the stack (FR-035a).

Everything else in `benchmarks/phase0/` decides; this module observes. The split is what
lets the deciding logic run in ordinary CI with no Docker, no weights and no tunnel, which
is the code whose failure modes are worth exercising on every commit (FR-035b).

**Three defects shaped this file, and each left a rule behind.**

*The benchmark runs on the host, not in the network.* `.env` carries in-container hostnames
— `postgres`, `qdrant`, `minio:9000` — because that is what the containers use to reach each
other. None resolve from the host. The test suite compensates in `tests/conftest.py`; this
module now resolves its own endpoints instead, defaulting to the compose-published host
ports and accepting explicit `PHASE0_*` overrides. It never rewrites the application's
values: `.env` is correct for the containers and is left alone.

*The schema is the one that exists.* There is no `documents.corpus` column and no
`documents.allowed_roles` column. Text documents are counted from `documents`; the code
corpus is a **Qdrant collection**, deliberately empty since Feature 001, and is verified
there. Objects are addressed by `storage_key` in the **configured** bucket. Role grants are
derived from `document_acl`.

*A failed probe is a failure, not a zero.* The previous version wrapped every query in
`except Exception: return 0`, which turned four hard SQL errors into "found 0 text
documents" — a verification failure wearing the costume of a verified result. Every probe
now raises `PhaseZeroProbeError`, named, and "verified empty" carries a separate flag from
"could not verify". Diagnostics carry no credential and no document content.
"""

from __future__ import annotations

import dataclasses
import os
import pathlib
from typing import Any, Final

from .config import MeasurementConfig
from .first_token_benchmark import ROW_NAME as FIRST_TOKEN_ROW
from .first_token_benchmark import (
    PromptNotProductionShapedError,
    production_shaped_prompt,
    run_first_token_benchmark,
)
from .preview_benchmark import run_preview_benchmark
from .results import Outcome, RowResult

__all__ = [
    "EndpointConfigurationError",
    "Endpoints",
    "LiveEnvironment",
    "PhaseZeroProbeError",
    "load_generation_tokenizer",
    "measure_both",
    "open_preview_index",
]

#: Queries rotated through the preview measurement. Several, not one: a single repeated
#: query is answered from the same cache lines every time and measures the cache.
PREVIEW_QUERIES: tuple[str, ...] = (
    "who approves travel booked less than five days before departure?",
    "what happens to a claim missing a required receipt?",
    "how are expenses in a foreign currency converted?",
    "when is standing production access reviewed?",
    "what is the rule for shared accounts?",
)

#: The Qdrant collection Feature 001 created empty and this feature leaves empty (FR-001a).
CODE_COLLECTION: str = "code"

#: Compose publishes these on the host. Defaults, not impositions — `PHASE0_*` wins.
DEFAULT_POSTGRES_HOST: str = "localhost"
DEFAULT_POSTGRES_PORT: int = 5432
DEFAULT_QDRANT_HOST: str = "localhost"
DEFAULT_QDRANT_PORT: int = 6333
DEFAULT_MINIO_ENDPOINT: str = "localhost:9000"


class PhaseZeroProbeError(RuntimeError):
    """A live probe could not be completed.

    Raised rather than defaulted. The whole point is that preflight can tell "the code
    collection holds zero points" apart from "the code collection could not be read", and
    a handler that returns `0` for both destroys that distinction permanently.
    """


@dataclasses.dataclass(frozen=True, slots=True)
class Endpoints:
    """Where the benchmark reaches the stack from the host."""

    postgres_host: str
    postgres_port: int
    postgres_database: str
    postgres_user: str
    postgres_password: str
    qdrant_host: str
    qdrant_port: int
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_secure: bool
    minio_bucket: str

    def redacted(self) -> dict[str, Any]:
        """Everything safe to print. Secrets are named, never valued."""
        return {
            "postgres": f"{self.postgres_host}:{self.postgres_port}/{self.postgres_database}",
            "qdrant": f"{self.qdrant_host}:{self.qdrant_port}",
            "minio": f"{self.minio_endpoint} bucket={self.minio_bucket}",
        }


class EndpointConfigurationError(PhaseZeroProbeError):
    """An explicitly supplied endpoint is not usable.

    A subclass of `PhaseZeroProbeError` so `__main__` renders it as a named preflight
    refusal with exit 2, rather than letting it escape as an uncontrolled traceback.
    """


#: Distinguishes "not supplied" from "supplied as something falsy". `None` cannot serve:
#: a caller passing `None` is still a caller who said something.
_UNSET: Final[object] = object()


def _from_environment(name: str) -> object:
    """An explicit `PHASE0_*` value, or `_UNSET`.

    Absent and whitespace-only both mean *not supplied*. That is deliberate and
    unchanged: `PHASE0_QDRANT_HOST=` in a script is how a shell spells "leave it alone",
    and treating it as a real endpoint would surprise the person who wrote it.
    """
    raw = os.environ.get(f"PHASE0_{name}")
    if raw is None or not raw.strip():
        return _UNSET
    return raw.strip()


def _select(supplied: dict[str, Any], key: str, environment: str, default: Any) -> Any:
    """Resolve one endpoint field by **presence**, not truthiness.

    The bug this replaces used `or`, which asks *is this truthy* — so an explicit
    `postgres_port=0` or an explicit empty host fell through to the compose default and
    the benchmark measured somewhere the caller never named. Presence is the right
    question: a key that is there was supplied, whatever its value, and a degenerate
    value is an error rather than an invitation to substitute.
    """
    if key in supplied:
        return supplied[key]
    from_environment = _from_environment(environment)
    if from_environment is not _UNSET:
        return from_environment
    return default


def _require_host(value: Any, field: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise EndpointConfigurationError(
            f"{field} was supplied as {value!r}, which is not a host. It is not replaced"
            " with a default: an endpoint nobody named is a figure attributed to the"
            " wrong machine"
        )
    return text


def _require_port(value: Any, field: str) -> int:
    try:
        port = int(str(value).strip())
    except (TypeError, ValueError):
        raise EndpointConfigurationError(
            f"{field} was supplied as {value!r}, which is not a port number"
        ) from None
    if not 1 <= port <= 65535:
        raise EndpointConfigurationError(
            f"{field} was supplied as {value!r}; a port must be between 1 and 65535."
            " It is not replaced with a default"
        )
    return port


def _require_endpoint(value: Any, field: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise EndpointConfigurationError(
            f"{field} was supplied as {value!r}, which is not an endpoint. It is not"
            " replaced with a default"
        )
    return text


def resolve_endpoints(
    settings: MeasurementConfig, overrides: dict[str, Any] | None = None
) -> Endpoints:
    """Host-side endpoints: explicit override, then `PHASE0_*`, then compose defaults.

    The application's own settings supply the *credentials and bucket* — those are correct
    in both contexts — while only the reachable address is substituted. `.env` is read,
    never written.

    Raises:
        EndpointConfigurationError: An explicitly supplied value is not a usable endpoint.
            Never silently replaced, and raised before any socket is opened.
    """
    from eaios_core.settings import get_settings

    application = get_settings()
    supplied = dict(overrides or {})

    return Endpoints(
        postgres_host=_require_host(
            _select(supplied, "postgres_host", "POSTGRES_HOST", DEFAULT_POSTGRES_HOST),
            "postgres_host",
        ),
        postgres_port=_require_port(
            _select(supplied, "postgres_port", "POSTGRES_PORT", DEFAULT_POSTGRES_PORT),
            "postgres_port",
        ),
        postgres_database=application.postgres.db,
        postgres_user=application.postgres.owner_user,
        postgres_password=application.postgres.owner_password.get_secret_value(),
        qdrant_host=_require_host(
            _select(supplied, "qdrant_host", "QDRANT_HOST", DEFAULT_QDRANT_HOST),
            "qdrant_host",
        ),
        qdrant_port=_require_port(
            _select(supplied, "qdrant_port", "QDRANT_PORT", DEFAULT_QDRANT_PORT),
            "qdrant_port",
        ),
        minio_endpoint=_require_endpoint(
            _select(supplied, "minio_endpoint", "MINIO_ENDPOINT", DEFAULT_MINIO_ENDPOINT),
            "minio_endpoint",
        ),
        minio_access_key=application.minio.access_key,
        minio_secret_key=application.minio.secret_key.get_secret_value(),
        minio_secure=application.minio.secure,
        minio_bucket=application.minio.bucket,
    )


@dataclasses.dataclass(frozen=True, slots=True)
class LiveEnvironment:
    """Observes the running stack and the local weights, from the host."""

    settings: MeasurementConfig
    endpoint_overrides: dict[str, Any] | None = None

    def endpoints(self) -> Endpoints:
        return resolve_endpoints(self.settings, self.endpoint_overrides)

    def open_connection(self) -> Any:
        """A PostgreSQL connection on the resolved host endpoint.

        Public so a controlled test can corroborate what the loader reports against
        the database directly, without reaching into a private attribute.
        """
        return self._engine(self.endpoints()).connect()

    def observe(self) -> dict[str, Any]:
        """Every prerequisite, or an explicit failure naming what could not be read."""
        endpoints = self.endpoints()

        postgres_ok = self._probe_postgres(endpoints)
        minio_ok = self._probe_minio(endpoints)
        qdrant_ok = self._probe_qdrant(endpoints)

        code_points = self._code_collection_points(endpoints)

        return {
            "postgres_reachable": postgres_ok,
            "minio_reachable": minio_ok,
            "qdrant_reachable": qdrant_ok,
            "active_profile": self._active_profile(endpoints),
            "text_document_count": self._text_document_count(endpoints),
            "code_document_count": code_points,
            "code_collection_verified": True,
            "unreadable_objects": self._unreadable_objects(endpoints),
            "weights_revision": self._weights_revision(),
            "weights_checksum": self._weights_checksum(),
        }

    # -- connections -----------------------------------------------------------------

    def _engine(self, endpoints: Endpoints) -> Any:
        from sqlalchemy import create_engine

        url = (
            f"postgresql+psycopg://{endpoints.postgres_user}:{endpoints.postgres_password}"
            f"@{endpoints.postgres_host}:{endpoints.postgres_port}/{endpoints.postgres_database}"
        )
        return create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 5})

    def _minio(self, endpoints: Endpoints) -> Any:
        from minio import Minio

        return Minio(
            endpoints.minio_endpoint,
            access_key=endpoints.minio_access_key,
            secret_key=endpoints.minio_secret_key,
            secure=endpoints.minio_secure,
        )

    def _qdrant(self, endpoints: Endpoints) -> Any:
        from qdrant_client import QdrantClient

        return QdrantClient(host=endpoints.qdrant_host, port=endpoints.qdrant_port, timeout=10)

    @staticmethod
    def _fail(service: str, endpoint: str, error: Exception) -> PhaseZeroProbeError:
        """One failure shape, carrying the address and the error class — never a secret.

        `type(error).__name__` and a truncated message: enough to tell a refused
        connection from a missing table, without pasting a password or a document body
        into whatever ticket this ends up in.
        """
        detail = str(error).splitlines()[0][:200] if str(error) else ""
        return PhaseZeroProbeError(
            f"{service} probe failed at {endpoint}: {type(error).__name__}: {detail}"
        )

    # -- probes ----------------------------------------------------------------------

    def _probe_postgres(self, endpoints: Endpoints) -> bool:
        from sqlalchemy import text

        try:
            with self._engine(endpoints).connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception as error:
            raise self._fail(
                "postgres", f"{endpoints.postgres_host}:{endpoints.postgres_port}", error
            ) from None
        return True

    def _probe_minio(self, endpoints: Endpoints) -> bool:
        try:
            if not self._minio(endpoints).bucket_exists(endpoints.minio_bucket):
                raise PhaseZeroProbeError(
                    f"minio bucket {endpoints.minio_bucket!r} does not exist at"
                    f" {endpoints.minio_endpoint}"
                )
        except PhaseZeroProbeError:
            raise
        except Exception as error:
            raise self._fail("minio", endpoints.minio_endpoint, error) from None
        return True

    def _probe_qdrant(self, endpoints: Endpoints) -> bool:
        try:
            self._qdrant(endpoints).get_collections()
        except Exception as error:
            raise self._fail(
                "qdrant", f"{endpoints.qdrant_host}:{endpoints.qdrant_port}", error
            ) from None
        return True

    # -- corpus ----------------------------------------------------------------------

    def _active_profile(self, endpoints: Endpoints) -> str:
        from sqlalchemy import text

        try:
            with self._engine(endpoints).connect() as connection:
                row = connection.execute(
                    text("SELECT profile FROM dataset_manifest LIMIT 1")
                ).first()
        except Exception as error:
            raise self._fail("dataset_manifest read", endpoints.postgres_host, error) from None
        if row is None or not row[0]:
            raise PhaseZeroProbeError(
                "dataset_manifest holds no profile row; the environment is not seeded"
            )
        return str(row[0])

    def _text_document_count(self, endpoints: Endpoints) -> int:
        """Every row in `documents`.

        There is no `corpus` column to filter on — this feature's corpus *is* the
        `documents` table, and the code corpus lives in Qdrant (see below).
        """
        from sqlalchemy import text

        try:
            with self._engine(endpoints).connect() as connection:
                row = connection.execute(text("SELECT count(*) FROM documents")).first()
        except Exception as error:
            raise self._fail("documents count", endpoints.postgres_host, error) from None
        if row is None:
            raise PhaseZeroProbeError("counting documents returned no row")
        return int(row[0])

    def _code_collection_points(self, endpoints: Endpoints) -> int:
        """Points in the `code` collection — verified, not assumed.

        FR-001a keeps this corpus empty for this feature. Proving that means reading the
        collection; a missing collection is a *different* state from an empty one and is
        reported as such rather than counted as zero.
        """
        client = self._qdrant(endpoints)
        try:
            names = {c.name for c in client.get_collections().collections}
        except Exception as error:
            raise self._fail(
                "qdrant collections", f"{endpoints.qdrant_host}:{endpoints.qdrant_port}", error
            ) from None

        if CODE_COLLECTION not in names:
            raise PhaseZeroProbeError(
                f"the {CODE_COLLECTION!r} collection does not exist, so its emptiness"
                " cannot be verified. Feature 001 provisions it empty"
            )
        try:
            return int(client.count(collection_name=CODE_COLLECTION).count)
        except Exception as error:
            raise self._fail(f"{CODE_COLLECTION} count", endpoints.qdrant_host, error) from None

    def _storage_keys(self, endpoints: Endpoints) -> list[str]:
        from sqlalchemy import text

        try:
            with self._engine(endpoints).connect() as connection:
                return [
                    str(row[0])
                    for row in connection.execute(text("SELECT storage_key FROM documents"))
                ]
        except Exception as error:
            raise self._fail("storage_key read", endpoints.postgres_host, error) from None

    def _unreadable_objects(self, endpoints: Endpoints) -> tuple[str, ...]:
        """Source objects the benchmark needs and cannot read.

        Checked here rather than discovered mid-measurement: a read failure at sample 17
        invalidates the series and wastes the whole run. A transport failure raises; only
        a genuine per-object miss is collected.
        """
        client = self._minio(endpoints)
        unreadable: list[str] = []
        for key in self._storage_keys(endpoints):
            try:
                client.stat_object(endpoints.minio_bucket, key)
            except Exception as error:
                if type(error).__name__ in ("S3Error", "NoSuchKey", "MinioException"):
                    unreadable.append(key)
                else:
                    raise self._fail("minio stat_object", endpoints.minio_endpoint, error) from None
        return tuple(unreadable)

    # -- weights ---------------------------------------------------------------------

    def _weights_revision(self) -> str | None:
        """The marker written by `benchmarks/provision_bge.py` after it verifies.

        Absent means *not provisioned*, which is a real and reportable state — distinct
        from a probe that could not run.
        """
        marker = pathlib.Path(self.settings.weights_directory) / ".revision"
        if not marker.is_file():
            return None
        return marker.read_text(encoding="utf-8").strip() or None

    def _weights_checksum(self) -> str | None:
        # `eaios_core.checksums`, never `eaios_core.embedding`: preflight decides
        # whether the embedder may be constructed, so importing it here would
        # invert the ordering this whole gate exists to enforce (T022).
        from eaios_core.checksums import sha256_of

        for name in ("pytorch_model.bin", "model.safetensors"):
            candidate = pathlib.Path(self.settings.weights_directory) / name
            if candidate.is_file():
                return sha256_of(candidate)
        return None

    # -- corpus loading ---------------------------------------------------------------

    def load_corpus(self) -> list[dict[str, Any]]:
        """The seeded documents with their authorization attributes and bodies.

        `allowed_roles` is **derived**: `document_acl` records grants as
        (`principal_type`, `principal_id`, `permission`), so a document's readable roles
        are the role principals whose permission allows reading. There is no
        `documents.allowed_roles` column to select.
        """
        from sqlalchemy import text

        endpoints = self.endpoints()
        client = self._minio(endpoints)

        try:
            with self._engine(endpoints).connect() as connection:
                rows = list(
                    connection.execute(
                        text(
                            "SELECT d.id, d.storage_key, d.company_id, d.classification,"
                            " d.department_id, d.country, d.owner_id, d.document_type,"
                            " COALESCE("
                            "   array_agg(DISTINCT a.principal_id::text)"
                            "     FILTER (WHERE a.principal_type = 'ROLE'"
                            "             AND a.permission IN ('READ', 'WRITE', 'OWNER')),"
                            "   '{}'"
                            " ) AS acl_role_ids,"
                            " COALESCE("
                            "   array_agg(DISTINCT a.principal_id::text)"
                            "     FILTER (WHERE a.principal_type = 'USER'"
                            "             AND a.permission IN ('READ', 'WRITE', 'OWNER')),"
                            "   '{}'"
                            " ) AS acl_user_ids"
                            " FROM documents d"
                            " LEFT JOIN document_acl a ON a.document_id = d.id"
                            " GROUP BY d.id"
                            " ORDER BY d.id"
                        )
                    )
                )
        except Exception as error:
            raise self._fail("corpus query", endpoints.postgres_host, error) from None

        documents: list[dict[str, Any]] = []
        for row in rows:
            mapping = row._mapping
            key = str(mapping["storage_key"])
            try:
                response = client.get_object(endpoints.minio_bucket, key)
                body = response.read()
                response.close()
                response.release_conn()
            except Exception as error:
                raise self._fail(
                    f"reading object for document {mapping['id']}", endpoints.minio_endpoint, error
                ) from None

            documents.append(
                {
                    "document_id": mapping["id"],
                    "content": body.decode("utf-8"),
                    "company_id": mapping["company_id"],
                    "classification": str(mapping["classification"]),
                    "department_id": mapping["department_id"],
                    "country": mapping["country"],
                    "owner_id": mapping["owner_id"],
                    # Role grants and user grants are different layers of FR-014 and are
                    # kept apart. This corpus happens to carry only user grants, so
                    # `allowed_roles` is legitimately empty throughout — which is a fact
                    # about the seed, not a broken join. `explicit_grant_user_ids` is what
                    # proves the join ran.
                    "allowed_roles": list(mapping["acl_role_ids"] or []),
                    "explicit_grant_user_ids": list(mapping["acl_user_ids"] or []),
                    "document_type": str(mapping["document_type"]),
                }
            )
        return documents


def open_preview_index(embedder: Any, settings: MeasurementConfig) -> Any:
    """Build the validated temporary preview collection from the seeded corpus."""
    from eaios_core.chunking import DEFAULT_CONFIG, load_bge_m3

    from .preview_index import build_preview_index

    environment = LiveEnvironment(settings)
    documents = environment.load_corpus()
    tokenizer = load_bge_m3(settings.weights_directory, DEFAULT_CONFIG.tokenizer_identity)
    return build_preview_index(
        _QdrantAdapter(environment.endpoints()),
        documents,
        embedder=embedder,
        chunker_config=DEFAULT_CONFIG,
        tokenizer=tokenizer,
        results_directory=settings.results_directory,
    )


def measure_both(
    embedder: Any, index_context: Any, settings: MeasurementConfig
) -> tuple[RowResult, RowResult]:
    """Run the preview measurement, then the first-token measurement.

    The preview row is measured whether or not a tunnel exists — retrieval does not depend
    on generation, so a missing Colab session must not cost both figures (FR-028l).
    """
    with index_context as index:
        preview_row = run_preview_benchmark(index, embedder, list(PREVIEW_QUERIES), settings)
        first_token_row = _measure_first_token(index, settings)
    return preview_row, first_token_row


def _measure_first_token(index: Any, settings: MeasurementConfig) -> RowResult:
    from .server_provisioning import verify

    if not settings.generation_url or not settings.generation_service_token:
        return RowResult(
            name=FIRST_TOKEN_ROW,
            outcome=Outcome.NOT_RUN,
            threshold_seconds=settings.thresholds.first_token_p95_seconds,
            detail=(
                "GENERATION_URL or GENERATION_SERVICE_TOKEN is absent, so no generation"
                " server was provisioned. Run infrastructure/colab/generation_server.ipynb"
                " and copy both values into your ignored .env (FR-035o)"
            ),
        )

    # The budget is counted in the *generation* tokenizer's tokens (FR-028b2). Counting
    # in any other tokenizer measures a different budget, and does so silently, so there
    # is no fallback: without the pinned tokenizer the row is NOT RUN.
    try:
        generation_tokenizer = load_generation_tokenizer(settings)
    except FileNotFoundError as absent:
        return RowResult(
            name=FIRST_TOKEN_ROW,
            outcome=Outcome.NOT_RUN,
            threshold_seconds=settings.thresholds.first_token_p95_seconds,
            detail=str(absent),
        )

    client = _GenerationAdapter(settings)
    report = verify(client)

    # Deterministic, real, and taken **outside** the measured window — the passages come
    # from the already-built index rather than from a similarity query.
    passages = index.deterministic_passages(settings.passage_budget.passages)

    try:
        prompt = production_shaped_prompt(
            passages,
            "who approves travel booked less than five days before departure?",
            settings.passage_budget,
            generation_tokenizer,
        )
    except PromptNotProductionShapedError as wrong_shape:
        return RowResult(
            name=FIRST_TOKEN_ROW,
            outcome=Outcome.NOT_RUN,
            threshold_seconds=settings.thresholds.first_token_p95_seconds,
            detail=f"prompt is not production-shaped, so no sample was taken: {wrong_shape}",
        )

    return run_first_token_benchmark(client, prompt, report, settings)


def load_generation_tokenizer(settings: MeasurementConfig) -> Any:
    """The pinned Qwen tokenizer, from local files only.

    Raises:
        FileNotFoundError: It is not provisioned. Raised rather than substituting the
            embedding tokenizer, which would count a different budget and report a
            number nobody could attribute.
    """
    from eaios_core.chunking import load_bge_m3

    directory = pathlib.Path(settings.generation_tokenizer_directory)
    if not directory.is_dir():
        raise FileNotFoundError(
            f"the pinned generation tokenizer is not at {directory}. FR-028b2 counts the"
            " passage budget in the generator's tokens, so the measurement cannot be"
            " assembled without it. Download the tokenizer files for"
            f" {settings.generation_tokenizer_identity} (see docs/models.md); no"
            " substitute is accepted"
        )
    # `load_bge_m3` is a misnomer for this call and nothing more: it is a thin,
    # local-files-only `AutoTokenizer.from_pretrained`, and the identity string it stamps
    # is what keeps the two tokenizers distinguishable.
    return load_bge_m3(directory, settings.generation_tokenizer_identity)


class _QdrantAdapter:
    """Adapts the project's Qdrant client to the narrow `VectorStore` protocol."""

    def __init__(self, endpoints: Endpoints) -> None:
        from qdrant_client import QdrantClient

        self._client = QdrantClient(
            host=endpoints.qdrant_host, port=endpoints.qdrant_port, timeout=60
        )

    def create_collection(self, name: str, *, dimension: int, distance: str) -> None:
        from qdrant_client.models import Distance, VectorParams

        self._client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=dimension, distance=Distance[distance.upper()]),
        )

    def create_payload_index(self, name: str, field: str) -> None:
        self._client.create_payload_index(
            collection_name=name, field_name=field, field_schema="keyword"
        )

    def upsert(self, name: str, points: list[dict[str, Any]]) -> None:
        from qdrant_client.models import PointStruct

        batch = 256
        for start in range(0, len(points), batch):
            self._client.upsert(
                collection_name=name,
                points=[
                    PointStruct(id=p["id"], vector=p["vector"], payload=p["payload"])
                    for p in points[start : start + batch]
                ],
                wait=True,
            )

    def count(self, name: str) -> int:
        return int(self._client.count(collection_name=name).count)

    def collection_schema(self, name: str) -> dict[str, Any]:
        info = self._client.get_collection(collection_name=name)
        vectors = info.config.params.vectors
        return {
            "dimension": int(getattr(vectors, "size", 0)),
            "distance": str(getattr(vectors, "distance", "")).split(".")[-1],
            "payload_indexes": tuple(info.payload_schema or ()),
        }

    def drop_collection(self, name: str) -> None:
        self._client.delete_collection(collection_name=name)

    def search(self, name: str, vector: list[float], *, limit: int) -> list[dict[str, Any]]:
        hits = self._client.search(collection_name=name, query_vector=vector, limit=limit)
        return [{"id": h.id, "score": h.score, "payload": h.payload or {}} for h in hits]


class _GenerationAdapter:
    """Talks to the provisioned Colab server, and reports what it observed."""

    def __init__(self, settings: MeasurementConfig) -> None:
        self._url = str(settings.generation_url).rstrip("/")
        self._token = str(settings.generation_service_token)

    def observe(self) -> dict[str, Any]:
        """Read `/health` and probe the stream, for the seven-prerequisite check."""
        import json
        import urllib.request

        observed: dict[str, Any] = {
            "endpoint_url": self._url,
            "service_token": self._token,
            "health_ok": False,
            "streams_first_token": False,
        }
        try:
            with urllib.request.urlopen(f"{self._url}/health", timeout=30) as response:
                observed["health_ok"] = response.status == 200
                health = json.loads(response.read())
            observed["weights_revision"] = health.get("model_revision")
            observed["weights_checksum"] = health.get("weights_sha256")
            observed["gpu_name"] = health.get("gpu_name")
            observed["runtime_identity"] = health.get("runtime_identity")
            observed["quantization"] = health.get("quantization")
            self.first_token("Reply with the single word: ready.")
            observed["streams_first_token"] = True
        except Exception:
            # Left as observed-so-far. The verifier reports what is missing by name; a
            # thrown exception here would replace seven specific findings with a stack
            # trace (FR-035o).
            pass
        return observed

    def first_token(self, prompt: str) -> None:
        import json
        import urllib.request

        request = urllib.request.Request(
            f"{self._url}/generate",
            data=json.dumps({"prompt": prompt, "max_tokens": 64}).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            for raw in response:
                if raw.startswith(b"event: token"):
                    return
        raise RuntimeError("the generation server closed the stream without a token event")
