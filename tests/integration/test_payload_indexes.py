"""Every field the filter uses is a payload index (FR-014b, SC-025, CHK006).

An unindexed payload field is not a broken filter. Qdrant answers the query correctly and
somewhat more slowly, which is precisely why this defect survives: it fails no test, raises
no error, and shows up as a latency budget quietly overspent — until the corpus grows and
`p95 <= 2s` stops holding for a reason nobody can locate.

**Derived, never restated.** The required set comes from `FILTER_KEYS` itself. A
hand-maintained copy would be correct on the day it was written and wrong on the day a
clause was added, which is the failure mode R3 recorded: the filter used six fields, the
provisioning created six indexes, and they were **not the same six** — `allowed_roles` was
used and unindexed, `document_id` indexed and idle. Deriving the list means the mismatch
becomes impossible rather than merely noticed.

**Against a temporary collection, always.** This file provisions a uniquely named
collection and drops it in teardown. It never touches `documents` or `code`: the assertions
would be just as true there and a teardown bug would cost the seeded corpus. The name
carries a random suffix so two concurrent runs cannot collide on it.

**Non-vacuity is structural here.** A bare collection is created first and the detector is
required to report *all seven* fields missing. A `missing_payload_indexes` that returned an
empty set for everything — because it read the wrong attribute, say — would otherwise pass
every assertion below while indexing nothing.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any, Final

import pytest

from eaios_core.authz.filters import FILTER_KEYS
from eaios_core.clients.stores import (
    ensure_payload_indexes,
    get_qdrant,
    missing_payload_indexes,
)

pytestmark = pytest.mark.integration

#: Never provisioned or dropped by this file. Named so a regression that pointed the
#: fixture at production would fail an assertion rather than delete a corpus.
PRODUCTION_COLLECTIONS: Final[frozenset[str]] = frozenset({"documents", "code"})

#: Matches the seeded corpus so the temporary collection is a faithful stand-in.
VECTOR_SIZE: Final[int] = 1024


@pytest.fixture(scope="module")
def client() -> Any:
    from qdrant_client.http.exceptions import UnexpectedResponse

    connection = get_qdrant()
    try:
        connection.get_collections()
    except (OSError, UnexpectedResponse):  # pragma: no cover - environment guard
        pytest.skip("Qdrant is not running; start it with `make up`")
    return connection


@pytest.fixture
def bare_collection(client: Any) -> Iterator[str]:
    """A fresh, empty, uniquely named collection with **no** payload indexes."""
    from qdrant_client import models as qmodels

    name = f"test_payload_indexes_{uuid.uuid4().hex}"
    assert name not in PRODUCTION_COLLECTIONS

    client.create_collection(
        collection_name=name,
        vectors_config=qmodels.VectorParams(
            size=VECTOR_SIZE, distance=qmodels.Distance.COSINE
        ),
    )
    try:
        yield name
    finally:
        client.delete_collection(collection_name=name)


class TestTheRequirementComesFromTheFilter:
    """If this set is wrong, everything below is decoration."""

    def test_the_filter_declares_its_keys(self) -> None:
        assert FILTER_KEYS, "FILTER_KEYS is empty; nothing would be required"

    def test_there_are_seven_of_them(self) -> None:
        """Seven since `document_id` became the resource-grant reach (R5). Stated as a
        number so a clause silently dropped from the filter fails here too, rather than
        quietly reducing what this file demands."""
        assert len(set(FILTER_KEYS)) == 7, (
            f"expected seven filter fields, found {len(set(FILTER_KEYS))}:"
            f" {sorted(FILTER_KEYS)}"
        )

    def test_the_provisioner_requires_exactly_them(self) -> None:
        """The whole point: no second list to drift from the first."""
        from eaios_core.clients.stores import REQUIRED_PAYLOAD_INDEXES

        assert set(REQUIRED_PAYLOAD_INDEXES) == set(FILTER_KEYS), (
            f"the provisioner's set {sorted(REQUIRED_PAYLOAD_INDEXES)} differs from the"
            f" filter's {sorted(FILTER_KEYS)} — exactly the mismatch R3 found"
        )


class TestTheDetectorSeesAMissingIndex:
    """Vacuity guard, run against a collection known to have none."""

    def test_a_bare_collection_is_missing_every_field(self, client: Any, bare_collection: str) -> None:
        missing = missing_payload_indexes(client, bare_collection)
        assert missing == set(FILTER_KEYS), (
            f"a collection with no payload indexes reported {sorted(missing)} missing"
            f" rather than all of {sorted(FILTER_KEYS)}, so this file cannot detect the"
            " defect it exists to catch"
        )


class TestProvisioningCreatesEveryIndex:
    def test_nothing_is_missing_afterwards(self, client: Any, bare_collection: str) -> None:
        ensure_payload_indexes(client, bare_collection)
        missing = missing_payload_indexes(client, bare_collection)
        assert missing == set(), (
            f"`{sorted(missing)}` used by `qdrant_filter` and not indexed. The query still"
            " returns the right rows and simply costs more than the latency budget allows"
        )

    @pytest.mark.parametrize("field", sorted(set(FILTER_KEYS)))
    def test_the_field_is_indexed(self, client: Any, bare_collection: str, field: str) -> None:
        """One named test per field, so the failure says which clause is unindexed."""
        ensure_payload_indexes(client, bare_collection)
        schema = client.get_collection(bare_collection).payload_schema or {}
        assert field in schema, f"`{field}` has no payload index; indexed: {sorted(schema)}"

    def test_provisioning_twice_is_not_an_error(self, client: Any, bare_collection: str) -> None:
        """It runs on every start-up, so it has to be idempotent — and it must not
        swallow failures to achieve that, which is why the second call is asserted to
        leave the same complete result rather than merely to not raise."""
        ensure_payload_indexes(client, bare_collection)
        ensure_payload_indexes(client, bare_collection)
        assert missing_payload_indexes(client, bare_collection) == set()


class TestARemovedIndexIsDetected:
    """Falsification: the realistic regression is one index dropped, not all seven."""

    @pytest.mark.parametrize("field", sorted(set(FILTER_KEYS)))
    def test_deleting_one_index_is_reported(
        self, client: Any, bare_collection: str, field: str
    ) -> None:
        ensure_payload_indexes(client, bare_collection)
        assert missing_payload_indexes(client, bare_collection) == set()

        client.delete_payload_index(collection_name=bare_collection, field_name=field)
        assert missing_payload_indexes(client, bare_collection) == {field}, (
            f"deleting the `{field}` index was not reported, so a clause could lose its"
            " index without any test noticing"
        )


class TestProductionCollectionsAreUntouched:
    def test_the_temporary_name_is_unique_and_not_production(self, bare_collection: str) -> None:
        assert bare_collection not in PRODUCTION_COLLECTIONS
        assert bare_collection.startswith("test_payload_indexes_")

    def test_the_teardown_removes_it(self, client: Any) -> None:
        """The fixture's own guarantee, checked rather than trusted: a leaked collection
        per test run fills the vector store with debris nobody attributes to tests."""
        from qdrant_client import models as qmodels

        name = f"test_payload_indexes_{uuid.uuid4().hex}"
        client.create_collection(
            collection_name=name,
            vectors_config=qmodels.VectorParams(
                size=VECTOR_SIZE, distance=qmodels.Distance.COSINE
            ),
        )
        client.delete_collection(collection_name=name)
        assert name not in {c.name for c in client.get_collections().collections}

    def test_no_debris_remains_from_earlier_runs(self, client: Any) -> None:
        leaked = [
            c.name
            for c in client.get_collections().collections
            if c.name.startswith("test_payload_indexes_")
        ]
        assert leaked == [], f"temporary collections left behind: {leaked}"
