"""Phase 0 entry point — `python -m benchmarks.phase0` (FR-035a, FR-035f).

**Preflight is the first call, and every heavy import happens after it.** That ordering is
the whole design of this file. An import at module scope executes before `main()` is
entered, so an embedder imported at the top is loaded before preflight could refuse — and
preflight's careful message about a missing weight file arrives a minute late, behind a
`FileNotFoundError` raised from inside a model loader. The evaluation lane already works
this way; this is the same discipline for the benchmark lane.

`tests/unit/test_phase0_preflight.py` enforces it, and T025 falsifies it by moving the
embedder construction above the preflight call.

**Nothing here can record a pass it did not measure.** A missed threshold exits nonzero
naming the threshold and the measured value; a CPU-only or unidentified GPU exits `INVALID`;
a runtime that cannot enforce deterministic settings exits `UNSUPPORTED_CONFIGURATION`; and
a row that was never measured stays `NOT RUN`.
"""

from __future__ import annotations

import pathlib
import sys
import uuid
from typing import Any

from . import preflight
from .config import MeasurementConfig, load_settings
from .results import Outcome, RowResult, RunRecord, write_record

__all__ = ["VALIDATION_ARTEFACT_FILENAME", "main"]

#: Written when the preview index is rejected. Content-free by construction.
VALIDATION_ARTEFACT_FILENAME = "preview-index-validation.json"

#: Exit codes, distinguished so a caller can tell *why* it stopped. A single nonzero code
#: would make "the environment is not ready" and "the system is too slow" look alike, and
#: they call for completely different responses.
EXIT_OK = 0
EXIT_THRESHOLD_MISSED = 1
EXIT_PREFLIGHT_FAILED = 2
EXIT_INVALID = 3
EXIT_UNSUPPORTED_CONFIGURATION = 4


def gather_environment(settings: MeasurementConfig) -> Any:
    """Observe the live stack and weights.

    Imports its store clients lazily, so importing this module never opens a connection
    and never requires the stack to exist.
    """
    from .live_environment import LiveEnvironment

    return LiveEnvironment(settings)


def load_embedder(settings: MeasurementConfig) -> Any:
    """Construct the canonical embedder. Called only after preflight passes."""
    from eaios_core.embedding.bge_m3 import BgeM3Embedder

    return BgeM3Embedder(settings.weights_directory)


def build_preview_index(embedder: Any, settings: MeasurementConfig) -> Any:
    """Build the validated temporary preview collection. Only after preflight passes."""
    from .live_environment import open_preview_index

    return open_preview_index(embedder, settings)


def measure(embedder: Any, index: Any, settings: MeasurementConfig) -> tuple[RowResult, RowResult]:
    """Run both measurements and return their rows."""
    from .live_environment import measure_both

    return measure_both(embedder, index, settings)


def main(argv: list[str] | None = None) -> int:
    """Run the Phase 0 benchmark, or explain why it did not run."""
    settings = load_settings(argv)

    # ---- preflight, before anything it gates -------------------------------------
    report = preflight.run(gather_environment(settings))
    if not report.ok:
        print(report.describe(), file=sys.stderr)
        return EXIT_PREFLIGHT_FAILED

    # ---- only now may the heavy things be imported and constructed ---------------
    from .preview_index import PreviewIndexValidationError

    embedder = load_embedder(settings)
    try:
        index = build_preview_index(embedder, settings)
        preview_row, first_token_row = measure(embedder, index, settings)
    except PreviewIndexValidationError as invalid:
        # A validation failure is a *result*, not a crash. It used to escape as an
        # uncaught traceback: no record, no artefact, and an exit code that says nothing
        # about which of the seven checks refused. The collection is already gone — the
        # builder drops it in `finally`, including on this path.
        preview_row, first_token_row = _validation_failure_rows(settings, invalid)
        artefact = _write_validation_artefact(settings, invalid)
        print(f"preview index rejected; validation record at {artefact}", file=sys.stderr)
        return _finish(settings, (preview_row, first_token_row))

    return _finish(settings, (preview_row, first_token_row))


def _finish(settings: MeasurementConfig, rows: tuple[RowResult, ...]) -> int:
    """Write the run record and choose the exit code. Every path ends here."""
    record = RunRecord(
        run_id=uuid.uuid4().hex,
        rows=rows,
        provenance={
            "warmup_requests": settings.warmup_requests,
            "minimum_samples": settings.minimum_samples,
            "concurrency": settings.concurrency,
            "passage_budget": {
                "passages": settings.passage_budget.passages,
                "tokens_per_passage": settings.passage_budget.tokens_per_passage,
                "total_passage_tokens": settings.passage_budget.total_passage_tokens,
            },
            "environment_declaration": "benchmarks/phase0/ENVIRONMENT.md",
        },
    )
    destination = write_record(record, settings.results_directory)
    print(f"recorded {destination}")
    return _report_outcome(rows)


def _validation_failure_rows(
    settings: MeasurementConfig, invalid: Exception
) -> tuple[RowResult, RowResult]:
    """Rows for a rejected preview index: `FAIL`, never `PASS`, never a figure."""
    return (
        RowResult(
            name="preview",
            outcome=Outcome.FAIL,
            threshold_seconds=settings.thresholds.preview_p95_seconds,
            detail=f"preview index failed pre-measurement validation: {invalid}",
        ),
        RowResult(
            name="first_token",
            outcome=Outcome.NOT_RUN,
            threshold_seconds=settings.thresholds.first_token_p95_seconds,
            detail="not attempted: the preview index was rejected before any sample",
        ),
    )


def _write_validation_artefact(settings: MeasurementConfig, invalid: Exception) -> str:
    """Record *why* the index was rejected, carrying no corpus content.

    The validator reports field names and counts — "3 point(s) carry no passage text",
    "filter fields without a payload index: [...]" — never document bodies. That is
    deliberate: this file is written on a failure path, which is exactly when someone is
    most likely to paste it into an issue tracker.
    """
    import json

    directory = pathlib.Path(settings.results_directory)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / VALIDATION_ARTEFACT_FILENAME
    payload = {
        "outcome": "REJECTED",
        "reasons": [line.strip() for line in str(invalid).splitlines() if line.strip()],
        "note": (
            "Field names and counts only — no corpus content. No sample was taken and no"
            " preview-index-manifest.json was written."
        ),
    }
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(destination)


def _report_outcome(rows: tuple[RowResult, ...]) -> int:
    """Print each row and choose the exit code. No row defaults to passing."""
    exit_code = EXIT_OK

    for row in rows:
        figure = "—" if row.p95_seconds is None else f"{row.p95_seconds:.3f}s"
        threshold = "—" if row.threshold_seconds is None else f"{row.threshold_seconds:.3f}s"
        print(f"{row.name:<12} {row.outcome.value:<26} p95={figure:>8}  threshold={threshold:>8}")
        if row.detail:
            print(f"  {row.detail}")

        if row.outcome is Outcome.UNSUPPORTED_CONFIGURATION:
            exit_code = max(exit_code, EXIT_UNSUPPORTED_CONFIGURATION)
        elif row.outcome is Outcome.INVALID:
            exit_code = max(exit_code, EXIT_INVALID)
        elif row.outcome is Outcome.FAIL:
            # Named threshold and measured value, both already in `detail`.
            exit_code = max(exit_code, EXIT_THRESHOLD_MISSED)
        elif row.outcome is Outcome.NOT_RUN:
            # A row that was never measured is not a pass and must not exit zero, or a
            # caller reading only the exit code would treat an absence as a success.
            exit_code = max(exit_code, EXIT_THRESHOLD_MISSED)

    print(
        "\nNo figure above may be described as an achieved threshold unless its row reads"
        " PASS (FR-035e). Update benchmarks/phase0/GATE.md from this record."
    )
    return exit_code


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main(sys.argv[1:]))
