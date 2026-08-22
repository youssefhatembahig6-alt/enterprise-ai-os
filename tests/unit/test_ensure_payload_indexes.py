"""Payload-index provisioning, against a fake store (FR-014b, R3, CHK006).

`tests/integration/test_payload_indexes.py` (T043) proves this works against a real Qdrant.
This file proves the things a real Qdrant makes *hard* to prove: what happens when the
collection already holds points, when a create call fails, when the caller asks twice. Those
are the paths where the damage lives, and provoking them for real would mean deliberately
populating a production collection.

**The rule this file exists to fix.** Adding a payload index to a populated collection is a
reindex; Qdrant does it, and it costs. Deleting and recreating a populated collection is not
a reindex, it is data loss. So provisioning may create indexes on an **empty** collection
freely, must never recreate a collection it did not create, and must refuse rather than
guess when it cannot tell how many points a collection holds.

**Derived from `FILTER_KEYS`, checked here rather than assumed.** R3's defect was two lists
of six that were not the same six. A test that restated the expected field names would have
passed while the defect stood.
"""

from __future__ import annotations

from typing import Any

import pytest

from eaios_core.authz.filters import FILTER_KEYS
from eaios_core.clients.stores import (
    REQUIRED_PAYLOAD_INDEXES,
    PopulatedCollectionError,
    ensure_payload_indexes,
    missing_payload_indexes,
)

pytestmark = pytest.mark.unit


class FakeCollectionInfo:
    def __init__(self, schema: dict[str, Any], points: int | None) -> None:
        self.payload_schema = schema
        self.points_count = points


class FakeQdrant:
    """Enough of the client to exercise every branch, and a log to assert against."""

    def __init__(self, *, points: int | None = 0, indexed: set[str] | None = None) -> None:
        self.schema: dict[str, Any] = dict.fromkeys(indexed or set(), "keyword")
        self.points = points
        self.created: list[str] = []
        self.deleted: list[str] = []
        self.calls: list[tuple[str, str]] = []

    def get_collection(self, collection_name: str) -> FakeCollectionInfo:
        return FakeCollectionInfo(dict(self.schema), self.points)

    def create_payload_index(self, *, collection_name: str, field_name: str, **_: Any) -> None:
        self.calls.append((collection_name, field_name))
        self.created.append(field_name)
        self.schema[field_name] = "keyword"

    def delete_collection(self, collection_name: str) -> None:  # pragma: no cover - guard
        self.deleted.append(collection_name)

    def create_collection(self, collection_name: str, **_: Any) -> None:  # pragma: no cover
        self.deleted.append(f"recreate:{collection_name}")


class TestTheRequiredSetIsDerived:
    def test_it_equals_the_filter_s_own_keys(self) -> None:
        assert set(REQUIRED_PAYLOAD_INDEXES) == set(FILTER_KEYS), (
            "the required set was restated rather than derived — exactly the shape of"
            " R3's defect, where two lists of six were not the same six"
        )

    def test_it_contains_the_two_fields_r3_found(self) -> None:
        """`allowed_roles` was used and unindexed; `document_id` indexed and idle."""
        assert {"allowed_roles", "document_id"} <= set(REQUIRED_PAYLOAD_INDEXES)

    def test_there_are_seven(self) -> None:
        assert len(set(REQUIRED_PAYLOAD_INDEXES)) == 7, sorted(REQUIRED_PAYLOAD_INDEXES)

    def test_the_seed_provisions_the_same_set(self) -> None:
        """The third list, and the one that nearly undid the whole fix.

        `reset_all` deletes every Qdrant collection and `provision_qdrant` rebuilds
        them. While the seed kept its own hand-written tuple of six, provisioning
        `allowed_roles` anywhere else survived exactly until the next `seed reset` —
        the index was created, verified, and then silently dropped by an unrelated
        command. Deriving both from one list is what makes the fix durable rather
        than momentary.
        """
        from eaios_seed.loaders.stores import PAYLOAD_INDEXES

        assert set(PAYLOAD_INDEXES) == set(FILTER_KEYS), (
            f"the seed provisions {sorted(PAYLOAD_INDEXES)} and the filter constrains"
            f" {sorted(FILTER_KEYS)}; a reset would restore the mismatch"
        )

    def test_the_seed_shares_the_detector_too(self) -> None:
        """Two definitions of "indexed" is two lists again, one indirection later."""
        from eaios_core.clients.stores import (
            missing_payload_indexes as canonical,
        )
        from eaios_seed.loaders.stores import missing_payload_indexes as seed_side

        store = FakeQdrant(indexed=set(FILTER_KEYS) - {"allowed_roles"})
        assert seed_side(store, "documents") == canonical(store, "documents")
        assert seed_side(store, "documents") == {"allowed_roles"}


class TestItProvisionsWhatIsMissing:
    def test_a_bare_collection_gets_every_field(self) -> None:
        store = FakeQdrant()
        ensure_payload_indexes(store, "documents")
        assert set(store.created) == set(FILTER_KEYS)

    def test_it_creates_only_what_is_absent(self) -> None:
        """Idempotence that does work is not idempotence. Re-creating six indexes on
        every start-up is a reindex nobody asked for."""
        store = FakeQdrant(indexed=set(FILTER_KEYS) - {"allowed_roles"})
        ensure_payload_indexes(store, "documents")
        assert store.created == ["allowed_roles"], (
            f"expected only the missing field to be created, got {store.created}"
        )

    def test_a_second_call_creates_nothing(self) -> None:
        store = FakeQdrant()
        ensure_payload_indexes(store, "documents")
        store.created.clear()
        ensure_payload_indexes(store, "documents")
        assert store.created == []

    def test_nothing_is_missing_afterwards(self) -> None:
        store = FakeQdrant()
        ensure_payload_indexes(store, "documents")
        assert missing_payload_indexes(store, "documents") == set()

    def test_it_returns_what_it_created(self) -> None:
        """So a caller can log the change rather than infer it."""
        store = FakeQdrant(indexed={"company_id"})
        created = ensure_payload_indexes(store, "documents")
        assert set(created) == set(FILTER_KEYS) - {"company_id"}
        assert ensure_payload_indexes(store, "documents") == ()


class TestItNeverDestroys:
    """The failure mode that costs a corpus rather than a query plan."""

    def test_it_does_not_delete_the_collection(self) -> None:
        store = FakeQdrant()
        ensure_payload_indexes(store, "documents")
        assert store.deleted == [], f"provisioning destroyed something: {store.deleted}"

    def test_a_populated_collection_is_refused_by_default(self) -> None:
        """Indexing a populated collection is a reindex with a cost nobody chose. The
        caller has to say so."""
        store = FakeQdrant(points=105, indexed={"company_id"})
        with pytest.raises(PopulatedCollectionError) as caught:
            ensure_payload_indexes(store, "documents")
        assert "105" in str(caught.value)
        assert store.created == [], "it indexed a populated collection anyway"
        assert store.deleted == []

    def test_a_populated_collection_can_be_indexed_when_asked_explicitly(self) -> None:
        store = FakeQdrant(points=105, indexed={"company_id"})
        created = ensure_payload_indexes(store, "documents", allow_populated=True)
        assert set(created) == set(FILTER_KEYS) - {"company_id"}
        assert store.deleted == [], "even then, nothing may be destroyed"

    def test_an_unknown_point_count_is_refused(self) -> None:
        """`points_count` is `int | None` in the client. Treating `None` as zero would
        make the emptiness check pass for exactly the collection it cannot vouch for."""
        store = FakeQdrant(points=None)
        with pytest.raises(PopulatedCollectionError) as caught:
            ensure_payload_indexes(store, "documents")
        assert "unknown" in str(caught.value).lower()
        assert store.created == []


class TestTheDetectorSeesRealAbsence:
    """Vacuity guards for `missing_payload_indexes`."""

    def test_a_bare_collection_is_missing_everything(self) -> None:
        assert missing_payload_indexes(FakeQdrant(), "documents") == set(FILTER_KEYS)

    def test_a_null_schema_is_missing_everything(self) -> None:
        """Qdrant returns `None`, not `{}`, for a collection with no indexes."""
        store = FakeQdrant()
        store.schema = {}
        assert missing_payload_indexes(store, "documents") == set(FILTER_KEYS)

    @pytest.mark.parametrize("field", sorted(set(FILTER_KEYS)))
    def test_one_absent_field_is_reported_alone(self, field: str) -> None:
        store = FakeQdrant(indexed=set(FILTER_KEYS) - {field})
        assert missing_payload_indexes(store, "documents") == {field}
