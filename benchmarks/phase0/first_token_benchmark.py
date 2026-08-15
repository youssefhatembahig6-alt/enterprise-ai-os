"""The first-token measurement (FR-035a, FR-035c, FR-035o, SC-055).

Clocks a production-shaped prompt — five passages, inside the 2,000-token budget — from
request to the **first `token` event**. Not to completion: what a reader experiences as
responsiveness is when text starts appearing, and total generation time is dominated by
answer length, which is a different question.

**It refuses to record `PASS` unless all seven prerequisites were verified** (FR-035o).
That refusal is the point of this module. A first-token figure taken against an
unidentified GPU or unverified weights is a number attributed to nothing, and a number
attributed to nothing is worse than a blank: the blank invites a question, the number
closes it.
"""

from __future__ import annotations

from typing import Any, Final, Protocol

from eaios_core.chunking.tokenizer import Tokenizer

from .config import MeasurementConfig
from .measure import measure_series
from .results import Outcome, RowResult
from .server_provisioning import ProvisioningReport, Verdict

__all__ = [
    "MINIMUM_PRODUCTION_TOKENS",
    "ROW_NAME",
    "PromptNotProductionShapedError",
    "production_shaped_prompt",
    "run_first_token_benchmark",
]

ROW_NAME = "first_token"


class GenerationClient(Protocol):
    """The slice of the generation server this measurement needs."""

    def first_token(self, prompt: str) -> None:
        """Send `prompt` and return as soon as the first token event arrives."""


def run_first_token_benchmark(
    client: GenerationClient,
    prompt: str,
    provisioning: ProvisioningReport,
    config: MeasurementConfig,
) -> RowResult:
    """Measure time to first token, or record why it was not measured.

    The provisioning report is a parameter rather than something fetched here, so the
    refusal below cannot be bypassed by calling this function differently.
    """
    if not provisioning.permits_measurement:
        # Not measured, and recorded as such. `INVALID` when something was provisioned and
        # is the wrong thing — a non-T4 allocation, a malformed revision — and `NOT RUN`
        # when it simply is not there. Neither is a pass (SC-055).
        outcome = Outcome.INVALID if provisioning.verdict is Verdict.INVALID else Outcome.NOT_RUN
        return RowResult(
            name=ROW_NAME,
            outcome=outcome,
            threshold_seconds=config.thresholds.first_token_p95_seconds,
            detail=provisioning.describe(),
        )

    def one_request(_iteration: int) -> None:
        client.first_token(prompt)

    samples = measure_series(
        one_request,
        warmups=config.warmup_requests,
        samples=config.minimum_samples,
    )

    threshold = config.thresholds.first_token_p95_seconds
    p95 = samples.p95_seconds
    passed = p95 <= threshold

    return RowResult(
        name=ROW_NAME,
        outcome=Outcome.PASS if passed else Outcome.FAIL,
        threshold_seconds=threshold,
        p95_seconds=p95,
        raw_timings_seconds=samples.durations_seconds,
        warmups_discarded=samples.warmups_discarded,
        sample_count=samples.count,
        detail=(
            ""
            if passed
            else f"first-token p95 {p95:.3f}s exceeds the {threshold:.3f}s threshold;"
            " Phase 4 is blocked"
        ),
    )


class PromptNotProductionShapedError(ValueError):
    """The assembled prompt does not match what production would send.

    Raised rather than measured. A prompt that is shorter than production's understates
    prefill, and prefill is most of time-to-first-token — so the figure would be a real
    measurement of the wrong thing, which is the hardest kind of wrong number to notice.
    """


#: Below this, a "five-passage" prompt is a placeholder rather than a corpus prompt. The
#: settled budget is 2,000 passage tokens; anything under a quarter of that could not have
#: come from five real chunks and is rejected on sight.
MINIMUM_PRODUCTION_TOKENS: Final[int] = 500


def production_shaped_prompt(
    passages: list[str],
    question: str,
    budget: Any,
    tokenizer: Tokenizer,
) -> str:
    """Assemble the prompt production would send, and refuse anything else.

    Args:
        passages: Real corpus passage bodies.
        question: The question they are retrieved for.
        budget: The settled passage budget — 5 passages, 400 tokens each, 2,000 total.
        tokenizer: **The pinned generation tokenizer.** FR-028b2 counts the budget in the
            generator's tokens, so counting in any other tokenizer measures a different
            budget. There is no default: a wrong tokenizer here is silent.

    Raises:
        PromptNotProductionShapedError: Too few passages, an empty passage, a passage over
            the per-passage bound, a total over the budget, or a prompt too small to have
            come from real corpus text.
    """
    selected = passages[: budget.passages]

    if len(selected) < budget.passages:
        raise PromptNotProductionShapedError(
            f"needs {budget.passages} passages, got {len(selected)}; a shorter prompt"
            " understates prefill and so understates time to first token"
        )

    blank = [index for index, text in enumerate(selected) if not text.strip()]
    if blank:
        raise PromptNotProductionShapedError(
            f"passages {blank} are empty. An empty passage contributes no prefill, so a"
            " prompt padded with them measures a request production never sends"
        )

    oversized = [
        (index, tokenizer.count(text))
        for index, text in enumerate(selected)
        if tokenizer.count(text) > budget.tokens_per_passage
    ]
    if oversized:
        raise PromptNotProductionShapedError(
            f"passages over the {budget.tokens_per_passage}-token bound: {oversized}."
            " Production trims these before sending; measuring untrimmed passages"
            " overstates prefill in the other direction"
        )

    total = sum(tokenizer.count(text) for text in selected)
    if total > budget.total_passage_tokens:
        raise PromptNotProductionShapedError(
            f"{total} passage tokens exceeds the {budget.total_passage_tokens}-token"
            " budget; production would not send this prompt"
        )
    if total < MINIMUM_PRODUCTION_TOKENS:
        raise PromptNotProductionShapedError(
            f"{total} passage tokens is below {MINIMUM_PRODUCTION_TOKENS}; five real"
            " corpus chunks do not add up to this little, so these are placeholders"
        )

    body = "\n\n".join(f"[{index + 1}] {text}" for index, text in enumerate(selected))
    return (
        "Answer the question using only the passages below. If they do not contain the"
        " answer, say so.\n\n"
        f"{body}\n\nQuestion: {question}\nAnswer:"
    )
