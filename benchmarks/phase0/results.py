"""Immutable per-run result records (FR-035a, FR-035e, FR-035f).

**One file per run, never overwritten.** A results file that is rewritten in place cannot
be compared with itself, and the run that mattered — the one before someone changed a
parameter — is the one that gets lost. Writing is therefore exclusive: a colliding name is
an error, not an overwrite.

**Raw timings travel with the figure.** A p95 whose samples were discarded cannot be
re-derived or re-checked, which makes it an assertion rather than a measurement.

**A row is `NOT RUN` until it is measured.** There is no default of `PASS`, no "assumed
passing", and no way to record a figure without the provenance that attributes it. A run
missing its provisioning prerequisites records `NOT RUN` or `INVALID` — never a pass
(SC-055).
"""

from __future__ import annotations

import dataclasses
import enum
import json
import pathlib
from typing import Any

__all__ = ["Outcome", "RowResult", "RunRecord", "write_record"]


class Outcome(enum.StrEnum):
    """What a measured row concluded.

    `NOT_RUN` and `INVALID` are both non-passes and are deliberately distinct: the first
    means no measurement was taken, the second that one was taken under conditions that
    make it unattributable. Collapsing them would lose the difference between "nobody ran
    it" and "it ran on the wrong hardware".
    """

    NOT_RUN = "NOT RUN"
    PASS = "PASS"
    FAIL = "FAIL"
    INVALID = "INVALID"
    UNSUPPORTED_CONFIGURATION = "UNSUPPORTED_CONFIGURATION"


@dataclasses.dataclass(frozen=True, slots=True)
class RowResult:
    """One measured threshold: its figure, its samples, and how it was judged."""

    name: str
    outcome: Outcome = Outcome.NOT_RUN
    threshold_seconds: float | None = None
    p95_seconds: float | None = None
    raw_timings_seconds: tuple[float, ...] = ()
    warmups_discarded: int = 0
    sample_count: int = 0
    detail: str = ""

    def __post_init__(self) -> None:
        if self.outcome is Outcome.PASS and self.p95_seconds is None:
            raise ValueError(
                f"row {self.name!r} is PASS with no measured figure. A pass without a"
                " number is the exact claim FR-035e forbids"
            )
        if self.outcome is Outcome.PASS and not self.raw_timings_seconds:
            raise ValueError(
                f"row {self.name!r} is PASS with no raw timings, so its figure cannot be"
                " re-derived or checked"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "outcome": self.outcome.value,
            "threshold_seconds": self.threshold_seconds,
            "p95_seconds": self.p95_seconds,
            "sample_count": self.sample_count,
            "warmups_discarded": self.warmups_discarded,
            "raw_timings_seconds": list(self.raw_timings_seconds),
            "detail": self.detail,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class RunRecord:
    """Everything one Phase 0 run produced, including what it could not measure."""

    run_id: str
    rows: tuple[RowResult, ...]
    provenance: dict[str, Any]

    @property
    def verdict(self) -> Outcome:
        """The run's overall outcome — the worst of its rows.

        Ordered so that any non-pass dominates: a run with one `PASS` and one `NOT RUN`
        has not passed, and must not be reportable as though it had.
        """
        severity = {
            Outcome.UNSUPPORTED_CONFIGURATION: 4,
            Outcome.INVALID: 3,
            Outcome.FAIL: 2,
            Outcome.NOT_RUN: 1,
            Outcome.PASS: 0,
        }
        return max(
            (row.outcome for row in self.rows), key=severity.__getitem__, default=Outcome.NOT_RUN
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "verdict": self.verdict.value,
            "rows": [row.as_dict() for row in self.rows],
            "provenance": self.provenance,
            "disclaimer": (
                "Rows recorded NOT RUN have not been measured. No figure in this file may"
                " be described as an achieved threshold unless its outcome is PASS"
                " (FR-035e)."
            ),
        }


def write_record(record: RunRecord, directory: pathlib.Path) -> pathlib.Path:
    """Write one run to `directory`, refusing to overwrite.

    Raises:
        FileExistsError: A record with this run id already exists. Two runs writing the
            same path would silently destroy the earlier one — usually the one someone
            wanted to compare against.
    """
    directory = pathlib.Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{record.run_id}.json"

    payload = json.dumps(record.as_dict(), indent=2, sort_keys=True) + "\n"
    # "x" is the whole point: exclusive creation turns a collision into an error rather
    # than a silent replacement.
    with destination.open("x", encoding="utf-8") as handle:
        handle.write(payload)
    return destination
