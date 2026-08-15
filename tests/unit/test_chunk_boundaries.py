"""Where the chunker is allowed to cut (FR-007a, FR-009, SC-033, CHK056, CHK058).

Five rules, in the order FR-007a states them:

1. Structure first, then sentence boundaries.
2. Never split a sentence — unless one sentence alone exceeds the budget.
3. An oversized sentence splits at the nearest preceding clause or whitespace boundary,
   reproducibly, never mid-word.
4. Overlap is complete trailing sentences where possible, and never exceeds 50 tokens.
5. No empty or whitespace-only chunk.

**Why rule 2 is the one that matters most.** It protects grounding. A fragment cut
mid-clause can invert its source's meaning — "the claim is returned rather than partially
approved" cut after "the claim is returned rather than" says something the document does not
say. A citation would then attest to it, which is a failure that reads as a success.

**A note on tokens.** These tests inject `FixedVocabularyTokenizer`, a deterministic stand-in,
so they stay pure and need no weights. The bound being checked is therefore "≤ max_tokens as
counted by the configured tokenizer" — which is the property the chunker can actually
guarantee. That the configured tokenizer *is* BGE-M3 in production is asserted separately,
in `test_chunk_identity.py::TestTheDefaultsAreTheSettledOnes`.
"""

from __future__ import annotations

import itertools
import re
from typing import Final

import pytest

from eaios_core.chunking import DEFAULT_CONFIG, chunk_document
from eaios_core.chunking.tokenizer import FixedVocabularyTokenizer

pytestmark = pytest.mark.unit

DOC: Final[str] = "cccccccc-0000-0000-0000-000000000003"

STRUCTURED: Final[str] = """# Security Policy

Access to production systems requires a named approver. Requests are recorded in the access
system. Standing access is reviewed quarterly.

## Credentials

Passwords are stored using Argon2id with per-credential salts. Shared accounts are
prohibited without exception. A credential suspected of exposure is rotated immediately and
the incident is recorded.

## Review

Quarterly review covers every standing grant. A grant whose owner has left the company is
revoked on the day the departure is recorded, not at the next review.
"""


def _chunks(text: str, **overrides: object):  # type: ignore[no-untyped-def]
    import dataclasses

    config = dataclasses.replace(DEFAULT_CONFIG, **overrides) if overrides else DEFAULT_CONFIG
    tokenizer = FixedVocabularyTokenizer(identity=config.tokenizer_identity)
    return chunk_document(DOC, text, config=config, tokenizer=tokenizer)


def _count(text: str) -> int:
    return FixedVocabularyTokenizer().count(text)


#: A sentence ends at `.`, `!`, or `?` followed by whitespace or end of string. Used only
#: to check the chunker's output, deliberately written independently of its implementation.
_SENTENCE_END = re.compile(r"[.!?](?:\s|$)")

#: A markdown heading line — the one legitimate way a chunk may end without a full stop.
_HEADING_LINE = re.compile(r"^\s{0,3}#{1,6}\s+\S")


class TestTheFixtureHasSubstance:
    def test_the_structured_sample_splits(self) -> None:
        assert len(_chunks(STRUCTURED, max_tokens=60)) >= 3, (
            "the sample did not split even at a 60-token budget; the boundary rules below"
            " would be checked against a single chunk"
        )


class TestTheBudgetHolds:
    @pytest.mark.parametrize("budget", [400, 200, 100, 60])
    def test_no_chunk_exceeds_the_budget(self, budget: int) -> None:
        oversized = [
            (c.ordinal, c.token_count)
            for c in _chunks(STRUCTURED, max_tokens=budget)
            if c.token_count > budget
        ]
        assert oversized == [], f"chunks over the {budget}-token budget: {oversized}"

    def test_the_reported_token_count_matches_the_text(self) -> None:
        for chunk in _chunks(STRUCTURED, max_tokens=100):
            assert chunk.token_count == _count(chunk.text), (
                f"chunk {chunk.ordinal} reports {chunk.token_count} tokens but its text"
                f" counts {_count(chunk.text)}; the budget check above would be checking"
                " a number unrelated to the content"
            )


class TestNoEmptyChunks:
    @pytest.mark.parametrize(
        "text",
        [
            STRUCTURED,
            "   \n\n\t  \n  ",
            "\n\n\n",
            "One sentence.\n\n\n\n\n\nAnother sentence.",
            "",
        ],
    )
    def test_no_chunk_is_empty_or_whitespace_only(self, text: str) -> None:
        empty = [c.ordinal for c in _chunks(text) if not c.text.strip()]
        assert empty == [], f"empty or whitespace-only chunks at ordinals {empty}"

    def test_whitespace_only_input_produces_no_chunks_at_all(self) -> None:
        assert _chunks("   \n\n\t ") == [], (
            "whitespace-only input produced chunks; an empty chunk embeds to a vector"
            " that matches everything weakly and nothing meaningfully"
        )


class TestSentencesSurviveIntact:
    def test_no_chunk_starts_mid_sentence(self) -> None:
        for chunk in _chunks(STRUCTURED, max_tokens=80):
            text = chunk.text.strip()
            assert text[:1].isupper() or text[:1] in "#-*0123456789", (
                f"chunk {chunk.ordinal} starts mid-sentence: {text[:70]!r}"
            )

    @staticmethod
    def _ends_a_sentence(text: str) -> bool:
        """Whether `text` ends at a sentence boundary.

        There is deliberately **no newline escape**. The earlier version accepted any
        chunk containing a newline, which is nearly all of them — the assertion could not
        fail for a multi-line chunk no matter where it was cut. A heading-only tail is the
        one legitimate non-sentence ending, and it is matched explicitly.
        """
        stripped = text.rstrip()
        if _SENTENCE_END.search(stripped[-2:]):
            return True
        # A chunk may legitimately end on a heading line — a section title has no full stop.
        last_line = stripped.splitlines()[-1] if stripped else ""
        return bool(_HEADING_LINE.match(last_line))

    def test_no_chunk_ends_mid_sentence(self) -> None:
        for chunk in _chunks(STRUCTURED, max_tokens=80):
            assert self._ends_a_sentence(chunk.text), (
                f"chunk {chunk.ordinal} ends mid-sentence: {chunk.text.strip()[-70:]!r}"
            )

    @pytest.mark.parametrize("budget", [400, 200, 100, 80, 60])
    def test_it_holds_at_every_budget(self, budget: int) -> None:
        for chunk in _chunks(STRUCTURED, max_tokens=budget):
            assert self._ends_a_sentence(chunk.text), (
                f"at budget {budget}, chunk {chunk.ordinal} ends mid-sentence:"
                f" {chunk.text.strip()[-70:]!r}"
            )

    def test_the_assertion_catches_a_planted_mid_sentence_multiline_chunk(self) -> None:
        """Falsification of the assertion itself.

        This text is multi-line and stops mid-clause. Under the old `or "\\n" in text`
        escape it was accepted; it must now be rejected, or the assertion above is
        decorative.
        """
        planted = "## Review\n\nQuarterly review covers every standing grant, and a grant whose"
        assert not self._ends_a_sentence(planted), (
            "a multi-line chunk cut mid-clause was accepted as ending a sentence; the"
            " newline escape is still in force somewhere"
        )

    def test_the_assertion_still_accepts_a_legitimate_heading_tail(self) -> None:
        assert self._ends_a_sentence("Standing access is reviewed quarterly.")
        assert self._ends_a_sentence("Some prose here.\n\n## Review")

    def test_every_sentence_appears_whole_in_some_chunk(self) -> None:
        """The strongest form: no sentence is only ever seen in pieces."""
        chunks = _chunks(STRUCTURED, max_tokens=80)
        sentences = [
            s.strip()
            for s in re.split(r"(?<=[.!?])\s+", re.sub(r"^#+ .*$", "", STRUCTURED, flags=re.M))
            if len(s.strip()) > 20
        ]
        assert sentences, "the fixture yielded no sentences to check"
        for sentence in sentences:
            flat = " ".join(sentence.split())
            assert any(flat in " ".join(c.text.split()) for c in chunks), (
                f"no chunk contains this sentence whole: {flat[:90]!r}"
            )


class TestStructureIsRespected:
    def test_a_heading_starts_a_chunk_rather_than_ending_one(self) -> None:
        chunks = _chunks(STRUCTURED, max_tokens=80)
        for chunk in chunks:
            lines = [line for line in chunk.text.splitlines() if line.strip()]
            if len(lines) > 1:
                headings = [i for i, line in enumerate(lines) if line.lstrip().startswith("#")]
                assert all(i == 0 for i in headings), (
                    f"chunk {chunk.ordinal} carries a heading in the middle, so a section"
                    f" boundary was crossed rather than respected: {lines}"
                )


class TestTheOversizedSentenceException:
    """The only case where a sentence may be cut, and how."""

    #: One sentence, no internal full stop, far over any reasonable budget.
    LONG: Final[str] = (
        "The reimbursement procedure applies to every employee of every subsidiary, "
        + "including contractors engaged directly and agency staff placed on assignment, "
        + "and covers airfare, rail fare, accommodation, ground transport, meals, " * 30
        + "and incidental expenses recorded against the appropriate cost centre."
    )

    def test_the_long_sentence_is_actually_oversized(self) -> None:
        assert _count(self.LONG) > 400, (
            f"the fixture sentence counts {_count(self.LONG)} tokens; it must exceed the"
            " 400-token budget or this class checks a case that never occurs"
        )

    def test_it_is_split_rather_than_dropped(self) -> None:
        chunks = _chunks(self.LONG)
        assert len(chunks) > 1, "an oversized sentence was not split; refusing to split it"
        assert all(c.token_count <= 400 for c in chunks)

    def test_no_split_lands_mid_word(self) -> None:
        for chunk in _chunks(self.LONG):
            text = chunk.text
            assert text == text.strip(), f"chunk {chunk.ordinal} has edge whitespace"
            assert not re.match(r"^\w", text) or text.split()[0] in self.LONG.split(), (
                f"chunk {chunk.ordinal} starts with a word fragment: {text[:40]!r}"
            )
            assert text[-1] not in "abcdefghijklmnopqrstuvwxyz" or text.split()[-1] in (
                self.LONG.split()
            ), f"chunk {chunk.ordinal} ends with a word fragment: {text[-40:]!r}"

    def test_the_split_is_reproducible(self) -> None:
        assert [c.text for c in _chunks(self.LONG)] == [c.text for c in _chunks(self.LONG)]

    def test_it_prefers_a_clause_boundary(self) -> None:
        """Comma boundaries exist in this sentence; the cut should use them."""
        chunks = _chunks(self.LONG)
        interior = chunks[:-1]
        at_clause = sum(1 for c in interior if c.text.rstrip().endswith(","))
        assert at_clause >= len(interior) // 2, (
            f"only {at_clause} of {len(interior)} interior cuts landed on a clause"
            " boundary, so the fallback is cutting at whitespace where a comma was"
            " available"
        )


class TestOverlap:
    def test_overlap_never_exceeds_the_configured_bound(self) -> None:
        config_overlap = DEFAULT_CONFIG.overlap_tokens
        chunks = _chunks(STRUCTURED, max_tokens=80)
        for previous, current in itertools.pairwise(chunks):
            shared = _shared_suffix_prefix(previous.text, current.text)
            assert _count(shared) <= config_overlap, (
                f"chunks {previous.ordinal}→{current.ordinal} share {_count(shared)}"
                f" tokens, over the {config_overlap}-token bound: {shared[:80]!r}"
            )

    def test_overlap_is_whole_sentences_where_it_exists(self) -> None:
        chunks = _chunks(STRUCTURED, max_tokens=80)
        for previous, current in itertools.pairwise(chunks):
            shared = _shared_suffix_prefix(previous.text, current.text).strip()
            if not shared:
                continue
            assert shared[:1].isupper(), (
                f"overlap between {previous.ordinal} and {current.ordinal} begins"
                f" mid-sentence: {shared[:80]!r}"
            )

    def test_no_chunk_is_wholly_contained_in_another(self) -> None:
        """Overlap must add a lead-in, never duplicate a whole chunk.

        The failure this catches is specific: applying overlap at the end of a section,
        where nothing follows, emits a chunk that is a strict subset of its predecessor.
        Both then sit in the index, both match the same queries, and the duplicate
        crowds out a genuinely different passage in the five-passage budget.
        """
        for text, budget in ((STRUCTURED, 80), (STRUCTURED, 60), (STRUCTURED, 400)):
            chunks = _chunks(text, max_tokens=budget)
            for outer in chunks:
                contained = [
                    inner.ordinal
                    for inner in chunks
                    if inner.ordinal != outer.ordinal
                    and inner.start_offset >= outer.start_offset
                    and inner.end_offset <= outer.end_offset
                ]
                assert contained == [], (
                    f"at budget {budget}, chunk(s) {contained} are wholly inside chunk"
                    f" {outer.ordinal}; the index would hold the same text twice"
                )

    def test_zero_overlap_is_honoured(self) -> None:
        chunks = _chunks(STRUCTURED, max_tokens=80, overlap_tokens=0)
        for previous, current in itertools.pairwise(chunks):
            assert not _shared_suffix_prefix(previous.text, current.text).strip(), (
                "overlap was produced under an overlap_tokens=0 configuration"
            )


def _shared_suffix_prefix(left: str, right: str) -> str:
    """The longest suffix of `left` that is also a prefix of `right`."""
    left_words, right_words = left.split(), right.split()
    for size in range(min(len(left_words), len(right_words)), 0, -1):
        if left_words[-size:] == right_words[:size]:
            return " ".join(right_words[:size])
    return ""
