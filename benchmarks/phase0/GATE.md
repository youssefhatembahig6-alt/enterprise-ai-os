# Phase 0 gate record

The machine-readable gate. **T056 reads the `preview` row before Phase 2 starts; T112 reads
the `first_token` row before Phase 4 starts** (FR-035f).

| Row | Status | Threshold | Measured p95 | Gates | Recorded |
|-----|--------|-----------|--------------|-------|----------|
| `preview` | `NOT RUN` | ≤ 2.0 s | — | Phase 2 — deterministic ingestion | — |
| `first_token` | `NOT RUN` | ≤ 5.0 s | — | Phase 4 — generation and streaming | — |

## How to read this

`NOT RUN` means **not measured**. It is not a provisional pass, not a pending result, and
not an estimate. Neither threshold has been measured on the declared environment.

The two thresholds are **acceptance thresholds, not demonstrated results** (FR-035e). No
document, report, or interface may describe either as achieved while its row here says
`NOT RUN`. `tests/unit/test_phase0_gate_not_claimed.py` fails the build on any such claim.

## Statuses

| Status | Meaning |
|--------|---------|
| `NOT RUN` | No measurement has been taken. |
| `PASS` | Measured on the declared environment, within the threshold. Unblocks its phase. |
| `FAIL` | Measured, over the threshold. Its phase is blocked. |
| `INVALID` | Measured under conditions that make the figure unattributable — a non-T4 allocation, unverified weights, a missing prerequisite. **Never a pass.** |
| `UNSUPPORTED_CONFIGURATION` | The runtime cannot enforce deterministic settings. |

`INVALID` includes a **faster** GPU than the declared T4. The T4 is the latency reference
class, not a floor: a figure measured on an A100 describes hardware the threshold was never
defined against, so it cannot satisfy the gate (FR-035c, FR-043a).

## Updating this file

From a run record under `results/`, never by hand from memory. Copy the row's outcome, its
p95, and the run id into the table above. A row may only read `PASS` when the corresponding
record says `PASS` and carries its raw timings.
