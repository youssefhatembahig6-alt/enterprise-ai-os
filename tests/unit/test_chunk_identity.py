"""Chunk identity is derived from the procedure, not only from the text (FR-007b).

The identifier is::

    sha256(document_id ‖ normalized_content_hash ‖ chunk_ordinal
           ‖ tokenizer_identity ‖ max_tokens ‖ overlap_tokens ‖ chunker_version) → UUID

**Why the last four inputs are there.** Without them, "identical chunk identifiers" in
SC-007 would mean *the text matched*. With them it means *the same procedure produced it*.
That difference decides what happens when the chunker changes: two runs that agree on text
but disagree on tokenizer would otherwise look identical, and the index would silently hold
two chunk generations at once — chunks whose boundaries were computed under different rules,
indistinguishable by identifier, and therefore un-reingestible without dropping everything.

**Why document identity is there.** Two documents can legitimately contain the same
sentence. If identity were content-only, one would overwrite the other's chunk, and a
citation would resolve to whichever document was ingested last.
"""

from __future__ import annotations

import dataclasses
import hashlib
import uuid
from typing import Final

import pytest

from eaios_core.chunking import DEFAULT_CONFIG, chunk_document
from eaios_core.chunking.config import ChunkerConfig
from eaios_core.chunking.tokenizer import FixedVocabularyTokenizer

pytestmark = pytest.mark.unit

DOC_A: Final[str] = "aaaaaaaa-0000-0000-0000-000000000001"
DOC_B: Final[str] = "bbbbbbbb-0000-0000-0000-000000000002"

TEXT: Final[str] = (
    "Approval is recorded in the travel system. Requests submitted late require director"
    " approval. Receipts are mandatory above the minimum threshold. A claim missing a"
    " receipt is returned rather than partially approved."
)


def _ids(document_id: str, text: str = TEXT, config: ChunkerConfig = DEFAULT_CONFIG) -> list[str]:
    tokenizer = FixedVocabularyTokenizer(identity=config.tokenizer_identity)
    return [
        str(c.chunk_id)
        for c in chunk_document(document_id, text, config=config, tokenizer=tokenizer)
    ]


class TestTheFixtureHasSubstance:
    def test_the_text_produces_at_least_one_chunk(self) -> None:
        assert _ids(DOC_A), "no chunks produced; every assertion below would be vacuous"


class TestTheDerivation:
    """The identifier is reproducible from its declared inputs and nothing else."""

    def test_the_identifier_matches_the_documented_formula(self) -> None:
        tokenizer = FixedVocabularyTokenizer(identity=DEFAULT_CONFIG.tokenizer_identity)
        chunks = chunk_document(DOC_A, TEXT, config=DEFAULT_CONFIG, tokenizer=tokenizer)

        for chunk in chunks:
            payload = "‖".join(
                (
                    DOC_A,
                    chunk.normalized_content_hash,
                    str(chunk.ordinal),
                    DEFAULT_CONFIG.tokenizer_identity,
                    str(DEFAULT_CONFIG.max_tokens),
                    str(DEFAULT_CONFIG.overlap_tokens),
                    DEFAULT_CONFIG.chunker_version,
                )
            )
            digest = hashlib.sha256(payload.encode("utf-8")).digest()
            assert chunk.chunk_id == uuid.UUID(bytes=digest[:16], version=5), (
                f"chunk {chunk.ordinal} identity does not match the documented derivation;"
                " a caller cannot recompute it, so it is not verifiable"
            )

    def test_the_identifier_is_a_uuid(self) -> None:
        for value in _ids(DOC_A):
            assert uuid.UUID(value), f"{value} is not a UUID"


class TestTextAloneDoesNotDecideIdentity:
    def test_two_documents_with_identical_text_get_different_ids(self) -> None:
        assert _ids(DOC_A) != _ids(DOC_B), (
            "the same text in two documents produced the same chunk identifiers. One"
            " document's chunks would overwrite the other's, and a citation would resolve"
            " to whichever was ingested last"
        )

    def test_the_same_document_and_text_get_the_same_ids(self) -> None:
        assert _ids(DOC_A) == _ids(DOC_A)


class TestTheProcedureDecidesIdentity:
    """Each of the four procedure inputs must move every identifier, text unchanged."""

    def test_changing_the_tokenizer_identity_changes_every_id(self) -> None:
        other = dataclasses.replace(DEFAULT_CONFIG, tokenizer_identity="some-other-tokenizer@v9")
        before, after = _ids(DOC_A), _ids(DOC_A, config=other)
        assert set(before).isdisjoint(after), (
            "changing the tokenizer left identifiers unchanged. Two chunk generations"
            f" computed under different tokenizers would collide: {before} vs {after}"
        )

    def test_changing_the_max_tokens_bound_changes_every_id(self) -> None:
        other = dataclasses.replace(DEFAULT_CONFIG, max_tokens=256)
        assert set(_ids(DOC_A)).isdisjoint(_ids(DOC_A, config=other))

    def test_changing_the_overlap_bound_changes_every_id(self) -> None:
        other = dataclasses.replace(DEFAULT_CONFIG, overlap_tokens=25)
        assert set(_ids(DOC_A)).isdisjoint(_ids(DOC_A, config=other))

    def test_changing_the_chunker_version_changes_every_id(self) -> None:
        other = dataclasses.replace(DEFAULT_CONFIG, chunker_version="test-only-v999")
        assert set(_ids(DOC_A)).isdisjoint(_ids(DOC_A, config=other))

    def test_the_bounds_move_ids_even_when_the_text_is_short_enough_not_to_resplit(self) -> None:
        """The sharp version of the rule.

        A short text chunks to one chunk under both 400 and 256 tokens — the boundaries do
        not move, so a text-only identity would produce the same id. The identifier must
        still change, because the *procedure* differs.
        """
        short = "One short sentence."
        wide = _ids(DOC_A, text=short)
        narrow = _ids(DOC_A, text=short, config=dataclasses.replace(DEFAULT_CONFIG, max_tokens=256))
        assert len(wide) == len(narrow) == 1, "the fixture resplit; it no longer isolates the rule"
        assert wide != narrow, (
            "identical boundaries under different bounds produced identical identifiers,"
            " so identity encodes the text rather than the procedure that produced it"
        )


class TestOrdinalIsPartOfIdentity:
    def test_repeated_text_within_one_document_gets_distinct_ids(self) -> None:
        repeated = "Alcohol is not reimbursable. " * 12
        ids = _ids(DOC_A, text=repeated)
        assert len(set(ids)) == len(ids), (
            f"a document repeating one sentence produced colliding identifiers: {ids}"
        )


class TestConfigHash:
    """`chunker_config_hash` is what an index records to detect a chunker change."""

    def test_the_hash_covers_every_identity_input(self) -> None:
        baseline = DEFAULT_CONFIG.chunker_config_hash
        for field, value in (
            ("tokenizer_identity", "other@v1"),
            ("max_tokens", 256),
            ("overlap_tokens", 25),
            ("chunker_version", "v999"),
            ("strategy", "flat"),
        ):
            changed = dataclasses.replace(DEFAULT_CONFIG, **{field: value})
            assert changed.chunker_config_hash != baseline, (
                f"changing `{field}` did not change `chunker_config_hash`, so an index"
                " recorded under the old configuration cannot detect the change"
            )

    def test_the_hash_is_stable_for_an_unchanged_configuration(self) -> None:
        assert (
            DEFAULT_CONFIG.chunker_config_hash
            == dataclasses.replace(DEFAULT_CONFIG).chunker_config_hash
        )


class TestTheDefaultsAreTheSettledOnes:
    """400 and 50 are decisions (FR-007a, R21), not incidental values."""

    def test_max_tokens_is_400(self) -> None:
        assert DEFAULT_CONFIG.max_tokens == 400

    def test_overlap_tokens_is_50(self) -> None:
        assert DEFAULT_CONFIG.overlap_tokens == 50

    def test_the_tokenizer_identity_names_bge_m3(self) -> None:
        assert "bge-m3" in DEFAULT_CONFIG.tokenizer_identity.lower(), (
            "the default tokenizer identity must name BGE-M3; the 400-token bound is"
            f" defined in that tokenizer's tokens: {DEFAULT_CONFIG.tokenizer_identity!r}"
        )
