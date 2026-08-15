"""The live observers — the only module here that touches the stack (FR-035a).

Everything else in `benchmarks/phase0/` decides; this module observes. The split is what
lets the deciding logic run in ordinary CI with no Docker, no weights and no tunnel, which
is the code whose failure modes are worth exercising on every commit (FR-035b).

Nothing in this file is imported until preflight has passed, and preflight cannot pass
until this file has reported. That is not circular: `gather_environment` is called first
and reads only what is cheap to read — reachability, counts, checksums — while the
expensive constructions behind `open_preview_index` and `measure_both` happen afterwards.
"""

from __future__ import annotations

import dataclasses
import pathlib
from typing import Any

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
    "LiveEnvironment",
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


@dataclasses.dataclass(frozen=True, slots=True)
class LiveEnvironment:
    """Observes the running stack and the local weights."""

    settings: MeasurementConfig

    def observe(self) -> dict[str, Any]:
        return {
            "postgres_reachable": self._postgres_reachable(),
            "minio_reachable": self._minio_reachable(),
            "qdrant_reachable": self._qdrant_reachable(),
            "active_profile": self._active_profile(),
            "text_document_count": self._document_count("documents"),
            "code_document_count": self._document_count("code"),
            "unreadable_objects": self._unreadable_objects(),
            "weights_revision": self._weights_revision(),
            "weights_checksum": self._weights_checksum(),
        }

    # -- stores ---------------------------------------------------------------------

    def _postgres_reachable(self) -> bool:
        return self._dependency_up("postgres")

    def _minio_reachable(self) -> bool:
        return self._dependency_up("minio")

    def _qdrant_reachable(self) -> bool:
        return self._dependency_up("qdrant")

    @staticmethod
    def _dependency_up(name: str) -> bool:
        """Reuse the project's own health probes.

        A second, hand-rolled reachability check would drift from the one the API
        reports on, and then preflight and `/health` could disagree about whether the
        stack is up — with no way to tell which is right.
        """
        from eaios_core.clients import stores

        try:
            probe = {
                "postgres": stores.check_postgres,
                "minio": stores.check_minio,
                "qdrant": stores.check_qdrant,
            }[name]
            return probe().status == "up"
        except Exception:
            return False

    def _active_profile(self) -> str:
        try:
            from sqlalchemy import text

            from eaios_core.db import create_owner_engine

            with create_owner_engine().connect() as connection:
                row = connection.execute(
                    text("SELECT profile FROM dataset_manifest LIMIT 1")
                ).first()
            return str(row[0]) if row and row[0] else ""
        except Exception:
            return ""

    def _document_count(self, corpus: str) -> int:
        try:
            from sqlalchemy import text

            from eaios_core.db import create_owner_engine

            with create_owner_engine().connect() as connection:
                row = connection.execute(
                    text("SELECT count(*) FROM documents WHERE corpus = :corpus"),
                    {"corpus": corpus},
                ).first()
            return int(row[0]) if row else 0
        except Exception:
            return 0

    def _unreadable_objects(self) -> tuple[str, ...]:
        """Source objects the benchmark would need and cannot read.

        Checked here rather than discovered mid-measurement: a read failure at sample 17
        invalidates the series and wastes the whole run.
        """
        try:
            from sqlalchemy import text

            from eaios_core.clients.stores import get_minio
            from eaios_core.db import create_owner_engine

            with create_owner_engine().connect() as connection:
                keys = [
                    str(row[0])
                    for row in connection.execute(
                        text("SELECT object_key FROM documents WHERE corpus = 'documents'")
                    )
                ]
            client = get_minio()
            unreadable: list[str] = []
            for key in keys:
                try:
                    client.stat_object("documents", key)
                except Exception:
                    unreadable.append(key)
            return tuple(unreadable)
        except Exception:
            return ()

    # -- weights --------------------------------------------------------------------

    def _weights_revision(self) -> str | None:
        marker = pathlib.Path(self.settings.weights_directory) / ".revision"
        return marker.read_text(encoding="utf-8").strip() if marker.is_file() else None

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


def open_preview_index(embedder: Any, settings: MeasurementConfig) -> Any:
    """Build the validated temporary preview collection from the seeded corpus."""
    from eaios_core.chunking import DEFAULT_CONFIG, load_bge_m3

    from .preview_index import build_preview_index

    documents = _load_corpus()
    tokenizer = load_bge_m3(settings.weights_directory, DEFAULT_CONFIG.tokenizer_identity)
    return build_preview_index(
        _QdrantAdapter(),
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
    # from the already-built index rather than from a similarity query. The previous
    # version searched with a zero vector, which has no defined cosine ranking, against a
    # payload that carried no text at all: five empty strings every time.
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

    def __init__(self) -> None:
        from eaios_core.clients.stores import get_qdrant

        self._client = get_qdrant()

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

        self._client.upsert(
            collection_name=name,
            points=[
                PointStruct(id=p["id"], vector=p["vector"], payload=p["payload"]) for p in points
            ],
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


def _load_corpus() -> list[dict[str, Any]]:
    """The 105 seeded text documents, with their authorization attributes."""
    from sqlalchemy import text

    from eaios_core.clients.stores import get_minio
    from eaios_core.db import create_owner_engine

    client = get_minio()
    documents: list[dict[str, Any]] = []
    with create_owner_engine().connect() as connection:
        rows = connection.execute(
            text(
                "SELECT id, object_key, company_id, classification, department_id,"
                " country, allowed_roles, owner_id, corpus FROM documents"
                " WHERE corpus = 'documents' ORDER BY id"
            )
        )
        for row in rows:
            mapping = row._mapping
            body = client.get_object("documents", str(mapping["object_key"])).read()
            documents.append(
                {
                    "document_id": mapping["id"],
                    "content": body.decode("utf-8"),
                    "company_id": mapping["company_id"],
                    "classification": mapping["classification"],
                    "department_id": mapping["department_id"],
                    "country": mapping["country"],
                    "allowed_roles": mapping["allowed_roles"],
                    "owner_id": mapping["owner_id"],
                    "corpus": mapping["corpus"],
                }
            )
    return documents
