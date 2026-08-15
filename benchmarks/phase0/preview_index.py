"""A corpus-representative temporary preview index (FR-007a, FR-010, FR-011, FR-014b, FR-035a).

**Why the benchmark builds its own index.** Phase 2 — production ingestion — is gated *by*
the preview figure, so requiring Phase 2's output before measuring would be circular. The
benchmark therefore builds a uniquely named temporary collection, measures against it, and
drops it.

**Why it must be corpus-representative.** The temptation is one point per document: it is
fast, it is easy, and it produces a preview latency that is meaningless, because search cost
scales with the number of points and their payload shape. A 105-point index measured and
reported as the preview figure would understate the real one by an order of magnitude and
would pass a threshold the real system fails. So the builder chunks all 105 documents with
the **canonical** chunker, embeds with the **canonical** embedder, and carries the complete
production authorization payload with every index (FR-035p).

**Six validations before any sample**, because each is a way the index can be wrong while
still returning results (T027). A benchmark over a silently wrong index is worse than no
benchmark: it produces a number.

**Always drops its collection, including on failure.** A context manager, not a pair of
calls — an exception between them leaves a stray collection that the next run's uniquely
named collection will not clash with, and that nobody will ever delete.
"""

from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import json
import pathlib
import uuid
from collections.abc import Iterator
from typing import Any, Protocol

__all__ = [
    "PreviewIndex",
    "PreviewIndexManifest",
    "PreviewIndexValidationError",
    "build_preview_index",
]

#: Every filter field the production authorization filter uses (FR-014b). All of them are
#: indexed here, because a preview measured without a payload index measures a different
#: query plan from the one production runs.
#: Where the exact normalized chunk text lives. Not an authorization attribute — it is
#: the passage body, kept so passage selection never has to invent one.
TEXT_FIELD: str = "text"

#: The manifest file, written under the results directory once validation passes (T027).
MANIFEST_FILENAME: str = "preview-index-manifest.json"

REQUIRED_PAYLOAD_FIELDS: tuple[str, ...] = (
    "company_id",
    "classification",
    "department_id",
    "country",
    "allowed_roles",
    "owner_id",
    "document_id",
)


class PreviewIndexValidationError(RuntimeError):
    """A pre-measurement check failed. No sample is taken."""


class VectorStore(Protocol):
    """The slice of the vector store this builder needs."""

    def create_collection(self, name: str, *, dimension: int, distance: str) -> None: ...
    def create_payload_index(self, name: str, field: str) -> None: ...
    def upsert(self, name: str, points: list[dict[str, Any]]) -> None: ...
    def count(self, name: str) -> int: ...
    def collection_schema(self, name: str) -> dict[str, Any]: ...
    def drop_collection(self, name: str) -> None: ...
    def search(self, name: str, vector: list[float], *, limit: int) -> list[dict[str, Any]]: ...


@dataclasses.dataclass(frozen=True, slots=True)
class PreviewIndexManifest:
    """What was built, recorded before anything is measured against it."""

    collection_name: str
    source_fingerprint: str
    chunker_config_hash: str
    embedding_identity: dict[str, Any]
    point_count: int
    payload_distribution: dict[str, int]
    collection_schema: dict[str, Any]

    def write(self, path: pathlib.Path) -> pathlib.Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(dataclasses.asdict(self), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return path


@dataclasses.dataclass(frozen=True, slots=True)
class PreviewIndex:
    """A built, validated temporary index."""

    collection_name: str
    manifest: PreviewIndexManifest
    store: VectorStore
    #: Every indexed passage body, ordered by chunk identifier. Deterministic and
    #: available **without a search**, so the first-token prompt can be assembled from
    #: real corpus text outside the measured window and without a similarity query
    #: (which, against a zero vector, has no defined ranking at all).
    passage_texts: tuple[str, ...] = ()

    def deterministic_passages(self, count: int) -> list[str]:
        """The first `count` non-empty passages, in a stable order."""
        return [text for text in self.passage_texts if text.strip()][:count]


def _source_fingerprint(documents: list[dict[str, Any]]) -> str:
    """Identity of the corpus that was indexed, order-independent.

    Sorted by document id so two runs that read the corpus in different orders produce the
    same fingerprint — otherwise the manifest would record a difference that is not one.
    """
    digest = hashlib.sha256()
    for document in sorted(documents, key=lambda d: str(d["document_id"])):
        digest.update(str(document["document_id"]).encode("utf-8"))
        digest.update(hashlib.sha256(document["content"].encode("utf-8")).digest())
    return digest.hexdigest()


@contextlib.contextmanager
def build_preview_index(
    store: VectorStore,
    documents: list[dict[str, Any]],
    *,
    embedder: Any,
    chunker_config: Any,
    tokenizer: Any,
    expected_document_count: int = 105,
    results_directory: pathlib.Path | None = None,
) -> Iterator[PreviewIndex]:
    """Build a validated temporary preview collection, and always drop it.

    Args:
        results_directory: Where `preview-index-manifest.json` is written. Written
            **only after every validation has passed** — a manifest describing an index
            that failed validation would be a record of something that was never fit to
            measure, and the next reader has no way to tell the two apart.

    Yields:
        The built index, once all six pre-measurement validations have passed.

    Raises:
        PreviewIndexValidationError: A validation failed. No measurement may proceed and
            no manifest is written.
    """
    from eaios_core.chunking import chunk_document

    # Unique per run. Two benchmarks running at once must not share a collection, and a
    # stray collection from a crashed run must not be silently reused as if it were fresh.
    collection = f"phase0_preview_{uuid.uuid4().hex}"
    identity = embedder.identity

    try:
        store.create_collection(collection, dimension=identity.dimension, distance="Cosine")
        for field in REQUIRED_PAYLOAD_FIELDS:
            store.create_payload_index(collection, field)

        points: list[dict[str, Any]] = []
        for document in documents:
            chunks = chunk_document(
                str(document["document_id"]),
                document["content"],
                config=chunker_config,
                tokenizer=tokenizer,
            )
            vectors = embedder.embed_documents([chunk.text for chunk in chunks])
            for chunk, vector in zip(chunks, vectors, strict=True):
                points.append(
                    {
                        "id": str(chunk.chunk_id),
                        "vector": vector,
                        # The complete production authorization payload. A preview whose
                        # points carry fewer attributes filters differently, and so
                        # measures a query the real system never runs (FR-010).
                        "payload": {field: document.get(field) for field in REQUIRED_PAYLOAD_FIELDS}
                        | {
                            "document_id": str(document["document_id"]),
                            "ordinal": chunk.ordinal,
                            # The exact normalized chunk text. Added *alongside* the
                            # authorization attributes, never in place of any of them:
                            # the first-token measurement needs real passages to be
                            # production-shaped, and a payload without text forced the
                            # prompt builder to fabricate empty ones (T030).
                            TEXT_FIELD: chunk.text,
                        },
                    }
                )

        if points:
            store.upsert(collection, points)

        manifest = _validate(
            store,
            collection,
            documents,
            points,
            identity=identity,
            chunker_config=chunker_config,
            expected_document_count=expected_document_count,
        )

        # Past this line every validation has passed, so the manifest describes an index
        # that was fit to measure. Written here rather than by the caller, so there is no
        # ordering in which a manifest can outlive a failed validation.
        if results_directory is not None:
            manifest.write(pathlib.Path(results_directory) / MANIFEST_FILENAME)

        # Sorted by chunk identifier: a stable order that does not depend on corpus read
        # order, so the first-token prompt is assembled from the same passages every run.
        passages = tuple(
            str(point["payload"][TEXT_FIELD])
            for point in sorted(points, key=lambda p: str(p["id"]))
        )
        yield PreviewIndex(
            collection_name=collection,
            manifest=manifest,
            store=store,
            passage_texts=passages,
        )
    finally:
        # Including on failure. A stray preview collection is invisible: uniquely named,
        # so nothing collides with it, and nothing ever cleans it up either.
        with contextlib.suppress(Exception):
            store.drop_collection(collection)


def _validate(
    store: VectorStore,
    collection: str,
    documents: list[dict[str, Any]],
    points: list[dict[str, Any]],
    *,
    identity: Any,
    chunker_config: Any,
    expected_document_count: int,
) -> PreviewIndexManifest:
    """The six checks that run before any sample is taken (T027, SC-025)."""
    failures: list[str] = []

    # 1 — all 105 documents represented.
    represented = {point["payload"]["document_id"] for point in points}
    if len(represented) != expected_document_count:
        failures.append(
            f"{len(represented)} documents represented, expected {expected_document_count}"
        )

    # 2 — no code or binary content.
    code_like = [
        document["document_id"]
        for document in documents
        if str(document.get("corpus", "documents")) != "documents"
    ]
    if code_like:
        failures.append(f"{len(code_like)} non-text documents present; the code corpus is excluded")

    # 3 — nonzero chunk count, more than one point per document.
    if len(points) <= len(represented):
        failures.append(
            f"{len(points)} points for {len(represented)} documents — one point per"
            " document is not corpus-representative, and the resulting latency would"
            " understate the real index by an order of magnitude"
        )

    # 4 — every point carries every required authorization attribute.
    missing_attributes = sorted(
        {
            field
            for point in points
            for field in REQUIRED_PAYLOAD_FIELDS
            if field not in point["payload"]
        }
    )
    if missing_attributes:
        failures.append(f"points are missing authorization attributes: {missing_attributes}")

    # 4b — every point carries a non-empty passage body.
    #
    # Added after the first-token prompt was found to be assembled from five empty
    # strings: the payload had no text at all, the prompt builder's length guard counted
    # five of them and passed, and the measured prompt was a few dozen tokens instead of
    # two thousand. Prefill dominates time-to-first-token, so that understates the figure
    # the gate turns on (T030).
    blank = sum(1 for point in points if not str(point["payload"].get(TEXT_FIELD, "")).strip())
    if blank:
        failures.append(
            f"{blank} point(s) carry no passage text. The first-token prompt is built"
            " from these, and an empty passage makes the measured prompt shorter than"
            " production's — which understates prefill and so understates the figure"
        )

    # 5 — dimension and distance metric match production.
    schema = store.collection_schema(collection)
    if int(schema.get("dimension", 0)) != identity.dimension:
        failures.append(
            f"collection dimension {schema.get('dimension')} != embedder {identity.dimension}"
        )
    if str(schema.get("distance", "")).lower() != "cosine":
        failures.append(f"distance metric is {schema.get('distance')!r}, expected Cosine")

    # 6 — every filter field indexed.
    indexed = set(schema.get("payload_indexes", ()))
    unindexed = [field for field in REQUIRED_PAYLOAD_FIELDS if field not in indexed]
    if unindexed:
        failures.append(
            f"filter fields without a payload index: {unindexed}. An unindexed filter"
            " field changes the query plan, so the measured latency is not production's"
        )

    if failures:
        raise PreviewIndexValidationError(
            "preview index failed pre-measurement validation; no sample was taken:\n  "
            + "\n  ".join(failures)
        )

    distribution: dict[str, int] = {}
    for point in points:
        key = str(point["payload"].get("classification", "<none>"))
        distribution[key] = distribution.get(key, 0) + 1

    return PreviewIndexManifest(
        collection_name=collection,
        source_fingerprint=_source_fingerprint(documents),
        chunker_config_hash=chunker_config.chunker_config_hash,
        embedding_identity=dataclasses.asdict(identity),
        point_count=len(points),
        payload_distribution=dict(sorted(distribution.items())),
        collection_schema=dict(schema),
    )
