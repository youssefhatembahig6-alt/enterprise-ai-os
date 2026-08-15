"""The preview-retrieval measurement (FR-035a, FR-035f).

Measures **only** the declared source-preview path: embed the query, run the
authorization-filtered search, return references. Indexing and all five warm-ups complete
before the first measured sample, so the figure describes steady-state retrieval rather
than a cold index — which is the state a user's second question meets, and every question
after it.

What is deliberately **not** inside the measured window: building the collection, loading
the model, and the warm-ups themselves. Including any of them would fold one-off costs into
a per-request figure and produce a number that improves as the run gets longer.
"""

from __future__ import annotations

from typing import Any

from .config import MeasurementConfig
from .measure import Samples, measure_series
from .preview_index import PreviewIndex
from .results import Outcome, RowResult

__all__ = ["ROW_NAME", "run_preview_benchmark"]

ROW_NAME = "preview"


def run_preview_benchmark(
    index: PreviewIndex,
    embedder: Any,
    queries: list[str],
    config: MeasurementConfig,
) -> RowResult:
    """Measure preview retrieval against an already-built, already-validated index.

    Args:
        index: A validated preview index. Building it is outside the measured window.
        embedder: The canonical embedder, already loaded.
        queries: Rotated through so the measurement is not one query repeated — a single
            query would be answered from the same cache lines every time and would
            measure the cache rather than the search.
        config: Declared warm-up count, sample count and threshold.
    """
    if not queries:
        raise ValueError("no queries supplied; a preview measurement over zero queries is not one")

    def one_request(iteration: int) -> None:
        query = queries[iteration % len(queries)]
        vector = embedder.embed_query(query)
        index.store.search(index.collection_name, vector, limit=5)

    samples: Samples = measure_series(
        one_request,
        warmups=config.warmup_requests,
        samples=config.minimum_samples,
    )

    threshold = config.thresholds.preview_p95_seconds
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
            else f"preview p95 {p95:.3f}s exceeds the {threshold:.3f}s threshold;"
            " Phase 2 is blocked"
        ),
    )
