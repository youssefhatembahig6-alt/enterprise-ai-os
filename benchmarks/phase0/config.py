"""The declared measurement parameters (FR-035a, FR-035f).

Every value here is a decision recorded in the spec, not a tunable. Changing one changes
what the resulting figure means, so they live in one module that the results record copies
verbatim — a figure and the parameters that produced it should never be separable.

Nothing here reads the environment for a *measurement* parameter. Endpoint and token come
from the environment because they are secrets and must not be committed; sample size,
warm-up count and concurrency do not, because a benchmark whose sample size depends on an
ambient variable produces numbers nobody can compare.
"""

from __future__ import annotations

import dataclasses
import os
import pathlib
from typing import Final

__all__ = ["MeasurementConfig", "PassageBudget", "Thresholds", "load_settings"]

#: Discarded before the first measured sample. A cold cache, a cold JIT and a cold
#: allocator are not what production steady-state looks like.
WARMUP_REQUESTS: Final[int] = 5

#: Below 30 the nearest-rank p95 is decided by one or two samples, and the figure moves
#: between runs for reasons that have nothing to do with the system.
MINIMUM_SAMPLES: Final[int] = 30

#: One. The declared environment measures latency, not throughput under load, and a
#: concurrent measurement on a single T4 would report queueing rather than generation.
CONCURRENCY: Final[int] = 1

#: Revision-stamped identity of the pinned generation tokenizer, matching
#: `docs/models.md`. Stamped onto every count so a budget measured with the wrong
#: tokenizer cannot be mistaken for one measured with the right one.
GENERATION_TOKENIZER_IDENTITY: Final[str] = (
    "qwen2.5-3b-instruct@7dabda4d13d513e3e842b20f0d435c732f172cbe"
)


@dataclasses.dataclass(frozen=True, slots=True)
class PassageBudget:
    """The production prompt shape the first-token measurement must reproduce."""

    passages: int = 5
    tokens_per_passage: int = 400
    total_passage_tokens: int = 2000


@dataclasses.dataclass(frozen=True, slots=True)
class Thresholds:
    """Acceptance thresholds — **not** demonstrated results (FR-035e).

    Neither has been measured. They are what a measurement will be compared against.
    """

    preview_p95_seconds: float = 2.0
    first_token_p95_seconds: float = 5.0


@dataclasses.dataclass(frozen=True, slots=True)
class MeasurementConfig:
    """Everything one Phase 0 run needs."""

    warmup_requests: int = WARMUP_REQUESTS
    minimum_samples: int = MINIMUM_SAMPLES
    concurrency: int = CONCURRENCY
    passage_budget: PassageBudget = dataclasses.field(default_factory=PassageBudget)
    thresholds: Thresholds = dataclasses.field(default_factory=Thresholds)

    #: Provisioning-supplied, never committed. Absent is a normal state: the preview
    #: measurement does not need them, so a run with no tunnel still produces one figure.
    generation_url: str | None = None
    generation_service_token: str | None = None

    #: Where provisioning put the BGE weights.
    weights_directory: pathlib.Path = pathlib.Path("models/bge-m3")

    #: The **pinned generation tokenizer**. FR-028b2 counts the passage budget in the
    #: generator's tokens, so this is not interchangeable with the embedding tokenizer.
    #: Absent means the first-token row records NOT RUN — never a substitute count.
    generation_tokenizer_directory: pathlib.Path = pathlib.Path("models/qwen2.5-3b-instruct")
    generation_tokenizer_identity: str = GENERATION_TOKENIZER_IDENTITY

    #: Where immutable per-run results are written.
    results_directory: pathlib.Path = pathlib.Path("benchmarks/phase0/results")


def load_settings(argv: list[str] | None = None) -> MeasurementConfig:
    """Build the run configuration.

    Only the two secrets and the two paths are environment-derived. Measurement parameters
    are not overridable, deliberately: a sample size that varies by shell is a sample size
    nobody can reproduce.
    """
    del argv  # accepted so `main` can pass its arguments through unchanged
    return MeasurementConfig(
        generation_url=os.environ.get("GENERATION_URL") or None,
        generation_service_token=os.environ.get("GENERATION_SERVICE_TOKEN") or None,
        weights_directory=pathlib.Path(os.environ.get("BGE_WEIGHTS_DIR", "models/bge-m3")),
        results_directory=pathlib.Path(
            os.environ.get("PHASE0_RESULTS_DIR", "benchmarks/phase0/results")
        ),
    )
