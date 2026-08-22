"""Refuse to ingest into a collection that cannot serve the filter (contracts IC §1, CHK061).

Two defects motivate this, and they fail very differently.

A **dimension mismatch** fails loudly — Qdrant rejects the vectors — but only after the run
has started, so the operator learns about it partway through a batch rather than before it.

A **missing payload index** does not fail at all. Every query returns exactly the right
rows; they merely cost more than the latency budget allows, for as long as the corpus lives.
R3 found precisely this: `allowed_roles` was used by `qdrant_filter` and indexed nowhere,
and nothing in the system noticed. That is why the check runs *before* the first write and
why the refusal is total — a partially ingested corpus behind a mis-provisioned collection
is worse than no corpus, because it looks finished.

**Every refusal names the item.** "Preflight failed" costs an engineer the afternoon this
module exists to save, so the message carries the field, the dimension found and expected,
or the underlying error — and the original exception is chained rather than swallowed.

**Requirements are derived, never restated.** `required_indexes()` reads `FILTER_KEYS`, the
same source `ensure_payload_indexes` provisions from. A clause added to the filter is
therefore refused here until someone indexes it, which is the behaviour R3's defect needed
and did not have.
"""

from __future__ import annotations

from typing import Any, Final, Protocol

from eaios_core.clients.stores import REQUIRED_PAYLOAD_INDEXES

__all__ = ["EXPECTED_DIMENSION", "PreflightError", "preflight", "required_indexes"]

#: BGE-M3's output width. Pinned rather than read from the settings: a collection built for
#: another width cannot hold this embedder's output at all, so there is nothing to
#: configure — only something to check.
EXPECTED_DIMENSION: Final[int] = 1024


class PreflightError(RuntimeError):
    """Ingestion refused. No point was written."""


class _SupportsInspection(Protocol):
    def get_collection(self, collection_name: str) -> Any: ...


def required_indexes() -> tuple[str, ...]:
    """Payload fields that must be indexed before ingestion.

    Derived from the retrieval filter's own key set, so this cannot drift from what the
    search layer actually constrains.
    """
    return tuple(REQUIRED_PAYLOAD_INDEXES)


def preflight(client: _SupportsInspection, collection: str) -> None:
    """Verify `collection` can serve the filter, or refuse.

    Args:
        client: A Qdrant client, or anything exposing `get_collection`.
        collection: The collection ingestion is about to write into.

    Raises:
        PreflightError: The schema is unreadable, the vector dimension is not
            `EXPECTED_DIMENSION`, or any required payload index is absent. The message
            names the specific problem; the original exception, where there was one, is
            chained as `__cause__`.

    Writes nothing on any path, including the successful one. This function checks; the
    caller ingests.
    """
    try:
        info = client.get_collection(collection)
    except Exception as exc:
        raise PreflightError(
            f"cannot verify the schema of collection {collection!r}: {exc}."
            " An unverifiable collection is refused rather than assumed sound — the"
            " check that cannot see is the check that must not pass"
        ) from exc

    _check_dimension(info, collection)
    _check_indexes(info, collection)


def _check_dimension(info: Any, collection: str) -> None:
    vectors = getattr(getattr(info, "config", None), "params", None)
    vectors = getattr(vectors, "vectors", None)
    found = getattr(vectors, "size", None)

    if found is None:
        raise PreflightError(
            f"collection {collection!r} reports no vector dimension, so it cannot be"
            f" confirmed to accept {EXPECTED_DIMENSION}-dimension embeddings"
        )
    if found != EXPECTED_DIMENSION:
        raise PreflightError(
            f"collection {collection!r} has dimension {found}, but the pinned embedder"
            f" produces {EXPECTED_DIMENSION}. Every vector would be rejected"
        )


def _check_indexes(info: Any, collection: str) -> None:
    indexed = set(getattr(info, "payload_schema", None) or {})
    missing = sorted(set(required_indexes()) - indexed)
    if not missing:
        return

    listed = ", ".join(f"`{field}`" for field in missing)
    raise PreflightError(
        f"collection {collection!r} is missing {len(missing)} payload"
        f" {'index' if len(missing) == 1 else 'indexes'}: {listed}."
        " The filter constrains these fields, so an unindexed one does not fail a query —"
        " it makes every query cost more, permanently and invisibly"
    )
