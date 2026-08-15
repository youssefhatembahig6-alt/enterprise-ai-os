"""The percentile is nearest-rank, and the rank is right (FR-035a, CHK128, CHK189).

**Why this has its own test file.** The p95 is the single number the Phase 0 gate turns on.
An off-by-one in its rank does not crash, does not look wrong, and moves the reported
figure downward — so the failure mode is a benchmark that passes when it should not. That
is precisely the class of bug that needs a test written against the definition rather than
against the implementation's own output.

Two specific traps:

* **`int(0.95 * n)` instead of `ceil`.** At n=30 that is index 28 → the 28th smallest,
  which is the p93.3 reported as the p95.
* **0-indexing the rank.** `ordered[rank]` instead of `ordered[rank - 1]` reads one sample
  too high, and at the top of the series it reads past the end or reports the maximum.

Both are checked against hand-computed expectations, not against what the code returns.
"""

from __future__ import annotations

import math

import pytest

from benchmarks.phase0.config import MINIMUM_SAMPLES
from benchmarks.phase0.measure import Samples, measure_series, nearest_rank_p95

pytestmark = pytest.mark.unit


class TestTheDefinition:
    def test_rank_is_ceil_of_95_percent(self) -> None:
        """n=30 → ceil(28.5) = 29 → the 29th smallest, 1-indexed."""
        series = [float(i) for i in range(1, 31)]  # 1..30
        assert nearest_rank_p95(series) == 29.0, (
            "expected the 29th of 30 sorted samples. 28.0 means `int()` was used where"
            " `ceil()` is required; 30.0 means the rank was not converted to a 0-based"
            " index"
        )

    @pytest.mark.parametrize(
        ("n", "expected_rank"),
        [(1, 1), (2, 2), (10, 10), (20, 19), (21, 20), (30, 29), (40, 38), (100, 95)],
    )
    def test_the_rank_matches_the_formula(self, n: int, expected_rank: int) -> None:
        assert math.ceil(0.95 * n) == expected_rank
        series = [float(i) for i in range(1, n + 1)]
        assert nearest_rank_p95(series) == float(expected_rank)

    def test_the_off_by_one_case_is_not_the_maximum(self) -> None:
        """At n=30 exactly one sample may exceed the p95. If the p95 *is* the maximum,
        the rank is one too high and a slow tail is being hidden inside the figure."""
        series = [1.0] * 29 + [99.0]
        assert nearest_rank_p95(series) == 1.0, (
            "the single outlier was reported as the p95; the rank is one too high"
        )

    def test_the_other_off_by_one_case(self) -> None:
        series = [1.0] * 28 + [50.0, 99.0]
        assert nearest_rank_p95(series) == 50.0, (
            "expected the 29th sample (50.0). 1.0 means the rank is one too low"
        )


class TestItReturnsAnObservedValue:
    """Nearest-rank never interpolates; an interpolated figure is one nobody measured."""

    @pytest.mark.parametrize(
        "series",
        [
            [0.1, 0.2, 0.3],
            [1.5] * 30,
            [float(i) * 0.37 for i in range(1, 45)],
            [9.0, 1.0, 5.0, 3.0, 7.0],
        ],
    )
    def test_the_result_is_one_of_the_samples(self, series: list[float]) -> None:
        assert nearest_rank_p95(series) in series

    def test_order_does_not_matter(self) -> None:
        ascending = [float(i) for i in range(1, 31)]
        assert nearest_rank_p95(ascending) == nearest_rank_p95(list(reversed(ascending)))


class TestEmptySeries:
    def test_it_refuses_rather_than_returning_zero(self) -> None:
        """Zero would be a *passing* latency derived from no data."""
        with pytest.raises(ValueError, match="empty|zero samples"):
            nearest_rank_p95([])


class TestTheMinimumSampleSize:
    def test_the_declared_minimum_is_thirty(self) -> None:
        assert MINIMUM_SAMPLES == 30

    def test_an_undersized_series_refuses_to_report(self) -> None:
        samples = Samples(
            durations_seconds=tuple(float(i) for i in range(1, 12)),
            warmups_discarded=5,
            minimum_required=30,
        )
        assert samples.sufficient is False
        with pytest.raises(ValueError, match="below the declared minimum"):
            _ = samples.p95_seconds

    def test_a_sufficient_series_reports(self) -> None:
        samples = Samples(
            durations_seconds=tuple(float(i) for i in range(1, 31)),
            warmups_discarded=5,
            minimum_required=30,
        )
        assert samples.sufficient is True
        assert samples.p95_seconds == 29.0

    def test_exactly_the_minimum_is_enough(self) -> None:
        """A `>` where `>=` belongs would reject the declared sample size itself."""
        samples = Samples(
            durations_seconds=tuple(1.0 for _ in range(MINIMUM_SAMPLES)),
            warmups_discarded=5,
            minimum_required=MINIMUM_SAMPLES,
        )
        assert samples.sufficient is True


class TestWarmupsAreDiscarded:
    def test_warmup_iterations_do_not_enter_the_series(self) -> None:
        """The classic version of this bug reports the cold-start time as the p95."""
        timeline = iter([float(i) for i in range(1000)])
        observed: list[int] = []

        samples = measure_series(
            observed.append,
            warmups=5,
            samples=30,
            clock=lambda: next(timeline),
        )

        assert len(observed) == 35, "warm-ups did not run"
        assert samples.count == 30, f"expected 30 measured samples, got {samples.count}"
        assert samples.warmups_discarded == 5

    def test_the_measured_durations_come_from_the_clock(self) -> None:
        """Falsification of the harness: a clock that never advances yields zeros, and a
        test that cannot tell zeros from real timings is not measuring anything."""
        ticks = iter([0.0, 2.5] * 100)
        samples = measure_series(
            lambda _index: None, warmups=0, samples=3, clock=lambda: next(ticks)
        )
        assert samples.durations_seconds == (2.5, 2.5, 2.5)
