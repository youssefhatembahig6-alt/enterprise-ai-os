"""Ingestion refuses before it writes, and says what is wrong (CHK061, FR-014b).

Preflight exists because of the order of costs. Writing points into a collection whose
`allowed_roles` field is unindexed produces a corpus that *works* — every query returns the
right rows — and quietly overspends the latency budget for as long as it lives. Writing
points into a collection built for 768 dimensions when the embedder produces 1024 fails
loudly, but only after the first batch. Both are cheap to prevent and expensive to undo, so
the check runs first and the refusal is total: **no point is written**.

Three refusals, and the third is the one usually forgotten:

* the collection's vector **dimension** is not 1024;
* any **filter index** is missing — each one independently, because "some index is missing"
  sends an engineer looking through seven fields;
* the schema **cannot be read at all**. An unverifiable collection is refused rather than
  assumed good, which is the same reasoning that makes `points_count is None` a refusal in
  `ensure_payload_indexes`: the check that cannot see is the check that must not pass.

**Naming the missing item is a requirement, not a nicety.** A refusal that says "preflight
failed" costs a person the afternoon this function was written to save.
"""

from __future__ import annotations

from typing import Any, Final

import pytest

from eaios_core.authz.filters import FILTER_KEYS
from eaios_seed.indexing.preflight import (
    EXPECTED_DIMENSION,
    PreflightError,
    preflight,
)

pytestmark = pytest.mark.unit


class FakeVectors:
    def __init__(self, size: int) -> None:
        self.size = size


class FakeConfig:
    def __init__(self, size: int | None) -> None:
        self.params = type("P", (), {"vectors": FakeVectors(size) if size else None})()


class FakeInfo:
    def __init__(self, size: int | None, indexed: set[str], points: int | None = 0) -> None:
        self.config = FakeConfig(size)
        self.payload_schema = dict.fromkeys(indexed, "keyword")
        self.points_count = points


class FakeQdrant:
    """A store whose collection can be made wrong in exactly one way at a time."""

    def __init__(
        self,
        *,
        size: int | None = 1024,
        indexed: set[str] | None = None,
        raises: Exception | None = None,
    ) -> None:
        self._info = FakeInfo(size, set(FILTER_KEYS) if indexed is None else indexed)
        self._raises = raises
        self.writes: list[Any] = []

    def get_collection(self, collection_name: str) -> FakeInfo:
        if self._raises is not None:
            raise self._raises
        return self._info

    def upsert(self, **kwargs: Any) -> None:  # pragma: no cover - must never be reached
        self.writes.append(kwargs)


HEALTHY: Final[dict[str, Any]] = {}


class TestAHealthyCollectionPasses:
    """Without this the refusals below would be indistinguishable from a check that
    refuses everything."""

    def test_it_returns_without_raising(self) -> None:
        preflight(FakeQdrant(), "documents")

    def test_the_expected_dimension_is_1024(self) -> None:
        """Pinned: BGE-M3 produces 1024, and a collection built for anything else cannot
        hold its output at all."""
        assert EXPECTED_DIMENSION == 1024


class TestItRefusesTheWrongDimension:
    @pytest.mark.parametrize("size", [384, 768, 1536, 0])
    def test_any_other_dimension_is_refused(self, size: int) -> None:
        store = FakeQdrant(size=size or None)
        with pytest.raises(PreflightError):
            preflight(store, "documents")
        assert store.writes == [], "preflight wrote points before refusing"

    def test_the_refusal_names_both_dimensions(self) -> None:
        with pytest.raises(PreflightError) as caught:
            preflight(FakeQdrant(size=768), "documents")
        message = str(caught.value)
        assert "768" in message and "1024" in message, (
            f"the refusal must name what was found and what was expected: {message!r}"
        )

    def test_an_unreadable_dimension_is_refused(self) -> None:
        """A collection with no vector config is not a collection with the right one."""
        with pytest.raises(PreflightError) as caught:
            preflight(FakeQdrant(size=None), "documents")
        assert "dimension" in str(caught.value).lower()

    def test_an_absent_dimension_is_not_reported_as_a_mismatch(self) -> None:
        """The two cases must stay distinguishable. Falling through to the mismatch
        branch produces "has dimension None", which reads as a collection built for a
        width it was never built for — and hides that the config is unreadable."""
        with pytest.raises(PreflightError) as caught:
            preflight(FakeQdrant(size=None), "documents")
        message = str(caught.value)
        assert "None" not in message, f"the refusal reported a nonexistent value: {message!r}"
        assert "reports no vector dimension" in message


class TestItRefusesEachMissingIndexIndependently:
    @pytest.mark.parametrize("field", sorted(set(FILTER_KEYS)))
    def test_the_missing_field_is_named(self, field: str) -> None:
        store = FakeQdrant(indexed=set(FILTER_KEYS) - {field})
        with pytest.raises(PreflightError) as caught:
            preflight(store, "documents")
        assert field in str(caught.value), (
            f"`{field}` was missing and the refusal did not name it: {caught.value!r}."
            " A refusal that says only 'an index is missing' costs an afternoon of"
            " looking through seven fields"
        )
        assert store.writes == []

    @pytest.mark.parametrize("field", sorted(set(FILTER_KEYS)))
    def test_no_other_field_is_blamed(self, field: str) -> None:
        """Otherwise the message names all seven every time and names nothing."""
        store = FakeQdrant(indexed=set(FILTER_KEYS) - {field})
        with pytest.raises(PreflightError) as caught:
            preflight(store, "documents")
        innocent = set(FILTER_KEYS) - {field}
        blamed = {name for name in innocent if name in str(caught.value)}
        assert blamed == set(), f"the refusal also blamed {sorted(blamed)}"

    def test_several_missing_fields_are_all_named(self) -> None:
        store = FakeQdrant(indexed=set(FILTER_KEYS) - {"allowed_roles", "document_id"})
        with pytest.raises(PreflightError) as caught:
            preflight(store, "documents")
        assert "allowed_roles" in str(caught.value)
        assert "document_id" in str(caught.value)

    def test_a_collection_with_no_indexes_at_all_is_refused(self) -> None:
        store = FakeQdrant(indexed=set())
        with pytest.raises(PreflightError):
            preflight(store, "documents")
        assert store.writes == []


class TestItRefusesAnUnverifiableSchema:
    """The check that cannot see must not pass."""

    def test_an_unreachable_collection_is_refused(self) -> None:
        store = FakeQdrant(raises=ConnectionError("qdrant is not listening"))
        with pytest.raises(PreflightError) as caught:
            preflight(store, "documents")
        assert "documents" in str(caught.value)
        assert store.writes == []

    def test_a_missing_collection_is_refused(self) -> None:
        store = FakeQdrant(raises=ValueError("Collection `documents` doesn't exist!"))
        with pytest.raises(PreflightError):
            preflight(store, "documents")

    def test_the_underlying_cause_is_preserved(self) -> None:
        """So the operator sees the connection error, not only our summary of it."""
        cause = ConnectionError("connection refused")
        with pytest.raises(PreflightError) as caught:
            preflight(FakeQdrant(raises=cause), "documents")
        assert caught.value.__cause__ is cause


class TestItWritesNothingOnAnyPath:
    """The property that makes preflight worth having, asserted across every refusal."""

    @pytest.mark.parametrize(
        "store",
        [
            FakeQdrant(size=768),
            FakeQdrant(size=None),
            FakeQdrant(indexed=set()),
            FakeQdrant(indexed=set(FILTER_KEYS) - {"allowed_roles"}),
            FakeQdrant(raises=ConnectionError("down")),
        ],
        ids=["wrong-dimension", "no-dimension", "no-indexes", "one-index", "unreachable"],
    )
    def test_no_point_is_written(self, store: FakeQdrant) -> None:
        with pytest.raises(PreflightError):
            preflight(store, "documents")
        assert store.writes == []

    def test_the_healthy_path_writes_nothing_either(self) -> None:
        """Preflight checks; it does not ingest."""
        store = FakeQdrant()
        preflight(store, "documents")
        assert store.writes == []


class TestTheRequirementIsDerived:
    def test_it_checks_every_filter_key(self) -> None:
        """Not a restated list — the same derivation `ensure_payload_indexes` uses, so a
        clause added to the filter is refused here until it is indexed."""
        from eaios_seed.indexing.preflight import required_indexes

        assert set(required_indexes()) == set(FILTER_KEYS)
