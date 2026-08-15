"""The first-token prompt is production-shaped, or no sample is taken (T030, FR-028b2).

**The failure this prevents, which actually happened.** Passage selection searched with a
zero vector against a payload that carried no text, so it returned five empty strings. The
length guard counted five of them and passed. The measured prompt was a few dozen tokens
instead of two thousand — and since prefill dominates time-to-first-token, the benchmark
would have reported a comfortable figure for a request production never sends. A real
measurement of the wrong thing is the hardest kind of wrong number to notice.

So every property of the prompt is now checked before a sample is taken, and each check
has a case here proving it can fail.

**The tokenizer is the pinned generation tokenizer**, never a substitute. FR-028b2 counts
the budget in the generator's tokens; counting in the embedding tokenizer would measure a
different budget and do it silently.
"""

from __future__ import annotations

import pytest

from benchmarks.phase0.config import PassageBudget
from benchmarks.phase0.first_token_benchmark import (
    MINIMUM_PRODUCTION_TOKENS,
    PromptNotProductionShapedError,
    production_shaped_prompt,
)
from eaios_core.chunking.tokenizer import FixedVocabularyTokenizer

pytestmark = pytest.mark.unit

BUDGET = PassageBudget()
TOKENIZER = FixedVocabularyTokenizer(identity="stand-in-for-the-pinned-qwen-tokenizer")

#: ~120 tokens of real-shaped prose. Five of these clear the production floor.
PASSAGE = (
    "All travel must be approved in advance by the employee's direct manager, and the"
    " approval is recorded in the travel system rather than by email. Requests submitted"
    " less than five working days before departure require director approval as well."
    " Economy airfare, standard rail fare and mid-tier hotel accommodation are"
    " reimbursable, and meals are reimbursed against receipts up to the daily limit for"
    " the destination country. Alcohol is not reimbursable under any circumstances, and"
    " personal detours are excluded from every category of ground transport."
)


def _prompt(passages: list[str]) -> str:
    return production_shaped_prompt(passages, "who approves late travel?", BUDGET, TOKENIZER)


class TestTheFixtureHasSubstance:
    def test_five_passages_clear_the_production_floor(self) -> None:
        total = sum(TOKENIZER.count(PASSAGE) for _ in range(5))
        assert total >= MINIMUM_PRODUCTION_TOKENS, (
            f"the fixture totals {total} tokens, below the {MINIMUM_PRODUCTION_TOKENS}"
            " floor — every positive case below would be rejected for the wrong reason"
        )

    def test_one_passage_is_within_the_per_passage_bound(self) -> None:
        assert TOKENIZER.count(PASSAGE) <= BUDGET.tokens_per_passage


class TestTheProductionShapedCase:
    """Without this, a builder that rejects everything would pass the whole file."""

    def test_five_real_passages_are_accepted(self) -> None:
        prompt = _prompt([PASSAGE] * 5)
        assert "who approves late travel?" in prompt
        assert prompt.count("[1]") == 1 and "[5]" in prompt

    def test_the_prompt_carries_every_passage(self) -> None:
        prompt = _prompt([PASSAGE] * 5)
        assert prompt.count(PASSAGE[:40]) == 5


class TestEmptyPassagesAreRejected:
    """The exact defect: five empty strings counted as five passages."""

    def test_all_empty_is_rejected(self) -> None:
        with pytest.raises(PromptNotProductionShapedError, match="empty"):
            _prompt(["", "", "", "", ""])

    def test_one_empty_among_four_real_is_rejected(self) -> None:
        with pytest.raises(PromptNotProductionShapedError, match="empty"):
            _prompt([PASSAGE, PASSAGE, "", PASSAGE, PASSAGE])

    def test_whitespace_only_counts_as_empty(self) -> None:
        with pytest.raises(PromptNotProductionShapedError, match="empty"):
            _prompt([PASSAGE, "   \n\t ", PASSAGE, PASSAGE, PASSAGE])


class TestUndersizedPlaceholdersAreRejected:
    def test_five_tiny_passages_are_rejected(self) -> None:
        with pytest.raises(PromptNotProductionShapedError, match="below"):
            _prompt(["yes."] * 5)

    def test_the_floor_is_what_rejects_them(self) -> None:
        tiny = ["short passage."] * 5
        total = sum(TOKENIZER.count(text) for text in tiny)
        assert total < MINIMUM_PRODUCTION_TOKENS, "the fixture is not actually undersized"


class TestTooFewPassagesAreRejected:
    @pytest.mark.parametrize("count", [0, 1, 3, 4])
    def test_fewer_than_five_is_rejected(self, count: int) -> None:
        with pytest.raises(PromptNotProductionShapedError, match="passages"):
            _prompt([PASSAGE] * count)


class TestOversizedPassagesAreRejected:
    def test_a_passage_over_the_per_passage_bound_is_rejected(self) -> None:
        oversized = PASSAGE * 6  # comfortably over 400 tokens
        assert TOKENIZER.count(oversized) > BUDGET.tokens_per_passage
        with pytest.raises(PromptNotProductionShapedError, match="token bound"):
            _prompt([oversized, PASSAGE, PASSAGE, PASSAGE, PASSAGE])

    def test_the_total_check_is_a_backstop_under_the_settled_budget(self) -> None:
        """Worth stating plainly: with 5 × 400 = 2000, the total can never be exceeded
        by passages that each pass the per-passage bound. The check is defensive, and a
        test that pretended otherwise would be fiction."""
        assert BUDGET.passages * BUDGET.tokens_per_passage == BUDGET.total_passage_tokens

    def test_a_total_over_a_tighter_budget_is_rejected(self) -> None:
        """The branch, exercised through a configuration where it is reachable.

        A tighter total than `passages × tokens_per_passage` is a legitimate setting —
        it is how the budget would be narrowed without changing the passage count.
        """
        tighter = PassageBudget(passages=5, tokens_per_passage=400, total_passage_tokens=300)
        total = TOKENIZER.count(PASSAGE) * 5
        assert total > tighter.total_passage_tokens, "the fixture does not exceed the budget"
        with pytest.raises(PromptNotProductionShapedError, match="budget"):
            production_shaped_prompt([PASSAGE] * 5, "q", tighter, TOKENIZER)


class TestTheBudgetIsCountedInTheSuppliedTokenizer:
    def test_the_tokenizer_is_required(self) -> None:
        """No default. A wrong tokenizer here would be silent."""
        with pytest.raises(TypeError):
            production_shaped_prompt([PASSAGE] * 5, "q", BUDGET)  # type: ignore[call-arg]

    def test_a_stricter_tokenizer_changes_the_verdict(self) -> None:
        """Proves the count comes from the tokenizer rather than from a hard-coded rule."""

        class Inflating:
            identity = "inflating"

            def count(self, text: str) -> int:
                return TOKENIZER.count(text) * 10

        with pytest.raises(PromptNotProductionShapedError):
            production_shaped_prompt([PASSAGE] * 5, "q", BUDGET, Inflating())
