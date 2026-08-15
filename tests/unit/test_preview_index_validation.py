"""The preview index is validated before it is measured (T027, T030, T034, SC-025).

Three properties, and the middle one is the one that was missing:

* **On success** a manifest is written with every field, so the figure that follows can be
  attributed to the index that produced it.
* **On every failure** no manifest exists. A manifest describing an index that failed
  validation is a record of something never fit to measure, and nothing downstream could
  tell the two apart.
* **A rejection is a result, not a crash.** It records `FAIL`, never `PASS`, writes a
  content-free validation artefact, exits nonzero, and leaves no collection behind.

Everything runs against an in-memory store. The point is the validation logic, and a check
of the checking needs no Qdrant — which is what lets it block ordinary CI (FR-035b).
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
from typing import Any

import pytest

from benchmarks.phase0.preview_index import (
    MANIFEST_FILENAME,
    REQUIRED_PAYLOAD_FIELDS,
    TEXT_FIELD,
    PreviewIndexValidationError,
    build_preview_index,
)
from eaios_core.chunking import DEFAULT_CONFIG
from eaios_core.chunking.tokenizer import FixedVocabularyTokenizer

pytestmark = pytest.mark.unit

DOCUMENT_COUNT = 6

BODY = (
    "Access to production systems requires a named approver. Requests are recorded in the"
    " access system. Standing access is reviewed quarterly. A grant whose owner has left"
    " the company is revoked on the day the departure is recorded."
)


class FakeStore:
    """An in-memory stand-in that records what was asked of it."""

    def __init__(self, *, dimension: int = 1024, distance: str = "Cosine") -> None:
        self.collections: dict[str, list[dict[str, Any]]] = {}
        self.indexes: dict[str, set[str]] = {}
        self.dropped: list[str] = []
        self._dimension = dimension
        self._distance = distance

    def create_collection(self, name: str, *, dimension: int, distance: str) -> None:
        self.collections[name] = []
        self.indexes[name] = set()

    def create_payload_index(self, name: str, field: str) -> None:
        self.indexes[name].add(field)

    def upsert(self, name: str, points: list[dict[str, Any]]) -> None:
        self.collections[name].extend(points)

    def count(self, name: str) -> int:
        return len(self.collections[name])

    def collection_schema(self, name: str) -> dict[str, Any]:
        return {
            "dimension": self._dimension,
            "distance": self._distance,
            "payload_indexes": tuple(self.indexes[name]),
        }

    def drop_collection(self, name: str) -> None:
        self.dropped.append(name)
        self.collections.pop(name, None)

    def search(self, name: str, vector: list[float], *, limit: int) -> list[dict[str, Any]]:
        return [
            {"id": p["id"], "score": 1.0, "payload": p["payload"]}
            for p in self.collections[name][:limit]
        ]


class FakeEmbedder:
    identity = dataclasses.replace(
        __import__("eaios_core.embedding", fromlist=["declared_identity"]).declared_identity()
    )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * 1024 for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [0.1] * 1024


def _documents(count: int = DOCUMENT_COUNT, **overrides: Any) -> list[dict[str, Any]]:
    documents = []
    for index in range(count):
        document = {
            "document_id": f"doc-{index:03d}",
            "content": f"# Section {index}\n\n{BODY}",
            "company_id": "company-a",
            "classification": "internal",
            "department_id": "dept-1",
            "country": "EG",
            "allowed_roles": ["employee"],
            "owner_id": f"user-{index}",
            "corpus": "documents",
        }
        document.update(overrides)
        documents.append(document)
    return documents


#: A budget small enough that the fixture documents split.
#:
#: Validation 3 rejects one-point-per-document, correctly — so a fixture that produces one
#: chunk each is rejected before any other case can be reached. Shrinking the budget is
#: the honest fix; padding the documents to 400+ tokens each would make every failure
#: message in this file harder to read for no gain.
TEST_CONFIG = dataclasses.replace(DEFAULT_CONFIG, max_tokens=60)


def _build(store: FakeStore, documents: list[dict[str, Any]], results: pathlib.Path | None):
    return build_preview_index(
        store,
        documents,
        embedder=FakeEmbedder(),
        chunker_config=TEST_CONFIG,
        tokenizer=FixedVocabularyTokenizer(identity=TEST_CONFIG.tokenizer_identity),
        expected_document_count=len(documents),
        results_directory=results,
    )


class TestTheFixtureHasSubstance:
    def test_the_documents_chunk_to_more_points_than_documents(self) -> None:
        store = FakeStore()
        with _build(store, _documents(), None) as index:
            assert index.manifest.point_count > DOCUMENT_COUNT, (
                "one point per document would trip validation 3 and every failure case"
                " below would be checking the wrong rejection"
            )


class TestOnSuccessTheManifestIsWritten:
    def test_the_manifest_file_appears(self, tmp_path: pathlib.Path) -> None:
        with _build(FakeStore(), _documents(), tmp_path):
            pass
        assert (tmp_path / MANIFEST_FILENAME).is_file()

    def test_it_carries_every_required_field(self, tmp_path: pathlib.Path) -> None:
        with _build(FakeStore(), _documents(), tmp_path):
            pass
        payload = json.loads((tmp_path / MANIFEST_FILENAME).read_text(encoding="utf-8"))
        for field in (
            "collection_name",
            "source_fingerprint",
            "chunker_config_hash",
            "embedding_identity",
            "point_count",
            "payload_distribution",
            "collection_schema",
        ):
            assert field in payload, f"manifest is missing `{field}`"
        assert payload["point_count"] > 0
        assert payload["embedding_identity"]["dimension"] == 1024

    def test_it_is_written_before_the_index_is_yielded(self, tmp_path: pathlib.Path) -> None:
        """Written by the builder, so no caller ordering can lose it."""
        with _build(FakeStore(), _documents(), tmp_path):
            assert (tmp_path / MANIFEST_FILENAME).is_file(), (
                "the manifest did not exist while the index was live, so it is being"
                " written by a caller rather than by the builder"
            )

    def test_nothing_is_written_when_no_directory_is_given(self) -> None:
        with _build(FakeStore(), _documents(), None) as index:
            assert index.manifest.point_count > 0


class TestEveryValidationFailureLeavesNoManifest:
    """One case per validation, each proving both the rejection and the absence."""

    @staticmethod
    def _expect_rejection(store: FakeStore, documents: list, results: pathlib.Path) -> str:
        with (
            pytest.raises(PreviewIndexValidationError) as raised,
            _build(store, documents, results),
        ):
            pytest.fail("validation passed on an index that should have been rejected")
        assert not (results / MANIFEST_FILENAME).exists(), (
            "a manifest was written for an index that failed validation"
        )
        assert store.dropped, "the temporary collection was not dropped on the failure path"
        return str(raised.value)

    def test_missing_documents(self, tmp_path: pathlib.Path) -> None:
        store = FakeStore()
        documents = _documents()
        with (
            pytest.raises(PreviewIndexValidationError) as raised,
            build_preview_index(
                store,
                documents,
                embedder=FakeEmbedder(),
                chunker_config=TEST_CONFIG,
                tokenizer=FixedVocabularyTokenizer(identity=TEST_CONFIG.tokenizer_identity),
                expected_document_count=DOCUMENT_COUNT + 3,
                results_directory=tmp_path,
            ),
        ):
            pass
        assert "documents represented" in str(raised.value)
        assert not (tmp_path / MANIFEST_FILENAME).exists()
        assert store.dropped

    def test_non_text_corpus_present(self, tmp_path: pathlib.Path) -> None:
        message = self._expect_rejection(FakeStore(), _documents(corpus="code"), tmp_path)
        assert "non-text" in message

    def test_empty_passage_text(self, tmp_path: pathlib.Path, monkeypatch) -> None:
        """The defect that made the first-token prompt five empty strings (T030)."""
        import benchmarks.phase0.preview_index as module

        original = module.TEXT_FIELD
        monkeypatch.setattr(module, "TEXT_FIELD", original)

        # Strip the text the way a payload without a text field would.
        class Blanking(FakeStore):
            def upsert(self, name: str, points: list[dict[str, Any]]) -> None:
                for point in points:
                    point["payload"][TEXT_FIELD] = ""
                super().upsert(name, points)

        blanking = Blanking()
        message = self._expect_rejection(blanking, _documents(), tmp_path)
        assert "no passage text" in message

    def test_wrong_dimension(self, tmp_path: pathlib.Path) -> None:
        message = self._expect_rejection(FakeStore(dimension=768), _documents(), tmp_path)
        assert "dimension" in message

    def test_wrong_distance_metric(self, tmp_path: pathlib.Path) -> None:
        message = self._expect_rejection(FakeStore(distance="Euclid"), _documents(), tmp_path)
        assert "distance metric" in message

    def test_unindexed_filter_field(self, tmp_path: pathlib.Path) -> None:
        class Forgetful(FakeStore):
            def create_payload_index(self, name: str, field: str) -> None:
                if field != "allowed_roles":
                    super().create_payload_index(name, field)

        message = self._expect_rejection(Forgetful(), _documents(), tmp_path)
        assert "allowed_roles" in message

    def test_missing_authorization_attribute(self, tmp_path: pathlib.Path) -> None:
        class Stripping(FakeStore):
            def upsert(self, name: str, points: list[dict[str, Any]]) -> None:
                for point in points:
                    point["payload"].pop("owner_id", None)
                super().upsert(name, points)

        message = self._expect_rejection(Stripping(), _documents(), tmp_path)
        assert "owner_id" in message


class TestThePayloadKeepsItsAuthorizationAttributes:
    """Adding passage text must not have weakened the authorization payload."""

    def test_every_point_carries_every_required_field(self) -> None:
        store = FakeStore()
        with _build(store, _documents(), None) as index:
            points = store.collections[index.collection_name]
            for point in points:
                missing = [f for f in REQUIRED_PAYLOAD_FIELDS if f not in point["payload"]]
                assert missing == [], f"point lost authorization attributes: {missing}"

    def test_text_is_an_addition_not_a_replacement(self) -> None:
        store = FakeStore()
        with _build(store, _documents(), None) as index:
            point = store.collections[index.collection_name][0]
            assert point["payload"][TEXT_FIELD].strip()
            assert point["payload"]["classification"] == "internal"


class TestDeterministicPassages:
    def test_passages_are_real_non_empty_corpus_text(self) -> None:
        with _build(FakeStore(), _documents(), None) as index:
            passages = index.deterministic_passages(5)
            assert len(passages) == 5
            assert all(p.strip() for p in passages)
            assert any("approver" in p for p in passages)

    def test_the_selection_is_stable_across_builds(self) -> None:
        with _build(FakeStore(), _documents(), None) as first:
            a = first.deterministic_passages(5)
        with _build(FakeStore(), _documents(), None) as second:
            b = second.deterministic_passages(5)
        assert a == b, "passage selection is not deterministic between runs"

    def test_selection_performs_no_search(self) -> None:
        """No Qdrant operation, so it cannot enter a measured window."""

        class Refusing(FakeStore):
            def search(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
                raise AssertionError("passage selection issued a search")

        refusing = Refusing()
        with _build(refusing, _documents(), None) as index:
            assert index.deterministic_passages(5)


class TestARejectedIndexIsAResultNotACrash:
    """T034: what `main()` does when the builder refuses.

    It used to do nothing at all — the exception escaped as an uncaught traceback, so
    there was no record, no artefact, and an exit code that said nothing about which
    check refused.
    """

    @pytest.fixture
    def rejecting(self, monkeypatch, tmp_path: pathlib.Path):
        from benchmarks.phase0 import __main__ as entry

        monkeypatch.setenv("PHASE0_RESULTS_DIR", str(tmp_path / "results"))
        monkeypatch.setattr(entry, "gather_environment", lambda _s: _PassingEnvironment())
        monkeypatch.setattr(entry, "load_embedder", lambda *a, **k: FakeEmbedder())

        def refuse(*_a: Any, **_k: Any) -> Any:
            raise PreviewIndexValidationError(
                "preview index failed pre-measurement validation; no sample was taken:\n"
                "  3 point(s) carry no passage text"
            )

        monkeypatch.setattr(entry, "build_preview_index", refuse)
        return entry, tmp_path / "results"

    def test_it_exits_nonzero(self, rejecting) -> None:
        entry, _ = rejecting
        assert entry.main([]) != 0

    def test_it_raises_no_traceback(self, rejecting) -> None:
        entry, _ = rejecting
        entry.main([])  # would raise if the exception still escaped

    def test_the_preview_row_is_fail_never_pass(self, rejecting) -> None:
        from benchmarks.phase0.results import Outcome

        entry, results = rejecting
        entry.main([])
        record = json.loads(next(results.glob("*.json")).read_text(encoding="utf-8"))
        rows = {row["name"]: row for row in record["rows"]}
        assert rows["preview"]["outcome"] == Outcome.FAIL.value
        assert rows["preview"]["p95_seconds"] is None, "a rejected index reported a figure"
        assert record["verdict"] != Outcome.PASS.value

    def test_the_first_token_row_is_not_run(self, rejecting) -> None:
        from benchmarks.phase0.results import Outcome

        entry, results = rejecting
        entry.main([])
        record = json.loads(next(results.glob("*.json")).read_text(encoding="utf-8"))
        rows = {row["name"]: row for row in record["rows"]}
        assert rows["first_token"]["outcome"] == Outcome.NOT_RUN.value

    def test_a_validation_artefact_is_written(self, rejecting) -> None:
        from benchmarks.phase0.__main__ import VALIDATION_ARTEFACT_FILENAME

        entry, results = rejecting
        entry.main([])
        artefact = results / VALIDATION_ARTEFACT_FILENAME
        assert artefact.is_file(), "no validation artefact was written"
        payload = json.loads(artefact.read_text(encoding="utf-8"))
        assert payload["outcome"] == "REJECTED"
        assert any("no passage text" in reason for reason in payload["reasons"])

    def test_the_artefact_carries_no_corpus_content(self, rejecting) -> None:
        """It is written on a failure path — exactly when someone pastes it into a ticket."""
        from benchmarks.phase0.__main__ import VALIDATION_ARTEFACT_FILENAME

        entry, results = rejecting
        entry.main([])
        text = (results / VALIDATION_ARTEFACT_FILENAME).read_text(encoding="utf-8")
        assert BODY[:40] not in text, "corpus text leaked into the validation artefact"
        assert "named approver" not in text

    def test_no_preview_manifest_is_written(self, rejecting) -> None:
        entry, results = rejecting
        entry.main([])
        assert not (results / MANIFEST_FILENAME).exists()


class _PassingEnvironment:
    """A stack that satisfies preflight, so the rejection path is the one under test."""

    def observe(self) -> dict[str, Any]:
        return {
            "postgres_reachable": True,
            "minio_reachable": True,
            "qdrant_reachable": True,
            "active_profile": "full",
            "text_document_count": 105,
            "code_document_count": 0,
            "unreadable_objects": (),
            "weights_revision": "5617a9f61b028005a4858fdac845db406aefb181",
            "weights_checksum": (
                "b5e0ce3470abf5ef3831aa1bd5553b486803e83251590ab7ff35a117cf6aad38"
            ),
        }


class TestTheCollectionIsAlwaysDropped:
    def test_dropped_on_success(self) -> None:
        store = FakeStore()
        with _build(store, _documents(), None) as index:
            name = index.collection_name
        assert store.dropped == [name]

    def test_dropped_when_the_body_raises(self) -> None:
        store = FakeStore()
        with pytest.raises(RuntimeError), _build(store, _documents(), None):
            raise RuntimeError("measurement blew up")
        assert store.dropped, "an exception during measurement left the collection behind"
