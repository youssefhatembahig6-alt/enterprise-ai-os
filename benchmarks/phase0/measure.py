"""Sampling and the nearest-rank p95 (FR-035a).

**Why nearest-rank rather than an interpolated percentile.** Interpolating invents a value
between two observations and reports it as if it were measured. At n=30 the p95 sits
between the 28th and 29th samples, and an interpolated figure can land below every value
actually observed — a latency nobody experienced, published as the latency. Nearest-rank
always returns a real sample.

The rank is `ceil(0.95 × n)`, 1-indexed. At n=30 that is sample 29 of 30 sorted ascending,
so exactly one observation may exceed it.

**Raw timings are retained.** A percentile without its samples cannot be re-derived, cannot
be re-percentiled, and cannot be checked. Keeping them is what makes the recorded figure
evidence rather than an assertion (FR-035a).
"""

from __future__ import annotations

import dataclasses
import math
import time
from collections.abc import Callable, Iterator
from typing import Final

__all__ = ["Samples", "measure_series", "nearest_rank_p95"]

#: Nearest-rank, as declared. Not configurable: a percentile method chosen per run is a
#: figure that cannot be compared with the previous run.
PERCENTILE: Final[float] = 0.95


def nearest_rank_p95(samples: list[float]) -> float:
    """The nearest-rank p95 of `samples`.

    Args:
        samples: Observed durations. Order does not matter; they are sorted here.

    Returns:
        A value that is one of the observations, never an interpolation between two.

    Raises:
        ValueError: `samples` is empty. A percentile over nothing is not zero, and
            returning zero would be a passing latency figure derived from no data.
    """
    if not samples:
        raise ValueError(
            "nearest_rank_p95 of an empty series. A percentile over zero samples has no"
            " value; returning one would report a passing figure derived from no data"
        )
    ordered = sorted(samples)
    # `ceil` and 1-indexing together are the definition. `int(0.95 * n)` is the classic
    # off-by-one here: at n=30 it gives 28, which is the p93.3, reported as the p95.
    rank = math.ceil(PERCENTILE * len(ordered))
    return ordered[rank - 1]


@dataclasses.dataclass(frozen=True, slots=True)
class Samples:
    """One measured series, with everything needed to re-derive its figure."""

    durations_seconds: tuple[float, ...]
    warmups_discarded: int
    minimum_required: int

    @property
    def count(self) -> int:
        return len(self.durations_seconds)

    @property
    def sufficient(self) -> bool:
        return self.count >= self.minimum_required

    @property
    def p95_seconds(self) -> float:
        """Refuses on an undersized series rather than reporting a fragile figure."""
        if not self.sufficient:
            raise ValueError(
                f"{self.count} samples is below the declared minimum of"
                f" {self.minimum_required}; at this size the p95 is decided by one or two"
                " observations and moves between runs for reasons unrelated to the system"
            )
        return nearest_rank_p95(list(self.durations_seconds))


def measure_series(
    operation: Callable[[int], None],
    *,
    warmups: int,
    samples: int,
    clock: Callable[[], float] = time.perf_counter,
) -> Samples:
    """Run `operation` and time it, discarding the warm-ups.

    Args:
        operation: Called with the iteration index. Timed end to end.
        warmups: Iterations run and discarded before measurement begins.
        samples: Measured iterations.
        clock: Monotonic clock. `perf_counter`, not `time()`: a wall-clock adjustment
            mid-run can otherwise produce a negative duration.
    """
    for index in _counted(warmups):
        operation(index)

    durations: list[float] = []
    for index in _counted(samples):
        started = clock()
        operation(warmups + index)
        durations.append(clock() - started)

    return Samples(
        durations_seconds=tuple(durations),
        warmups_discarded=warmups,
        minimum_required=samples,
    )


def _counted(total: int) -> Iterator[int]:
    yield from range(total)
