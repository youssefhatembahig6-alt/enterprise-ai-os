# Phase 0 feasibility benchmark

**This harness is not a test.** It is never invoked by CI, it is not part of `make test`,
and it needs three things ordinary CI deliberately does not have: a seeded Docker stack,
local BGE-M3 weights, and a provisioned Colab T4 behind an authenticated tunnel. Ordinary
CI stays network-free and model-free (FR-035b); this is the lane that is allowed to be the
opposite, which is exactly why it is run by hand and gated on its own record.

```bash
make benchmark-phase0
```

That target runs `python -m benchmarks.phase0`, which resolves to `__main__.py` — the entry
point that calls preflight first.

---

## What the preview figure is, and what it is not

The preview figure is a **corpus-representative benchmark over an isolated temporary
index**. The harness builds its own uniquely named Qdrant collection from all 105 seeded
text documents, using the canonical chunker and the canonical embedder, carrying the
complete production authorization payload with every index — then measures against it, then
drops it.

**It is not evidence that the Phase 2 production ingestion path has run.** Those are
different code paths with different failure modes. A passing preview figure says retrieval
latency is achievable on the declared machine over a representative index; it says nothing
about whether `eaios-seed index` works, whether idempotency holds, or whether the production
collection is correctly populated. Phase 2 has its own tests for all of that.

The reason the benchmark builds its own index at all is ordering: Phase 2 is gated **by**
this figure, so requiring Phase 2's output before measuring would be circular (FR-035a).

## Why it must be corpus-representative

One point per document would be fast, easy, and meaningless. Search cost scales with the
number of points and the shape of their payload, so a 105-point index would understate the
real figure by roughly an order of magnitude — and would pass a threshold the real system
fails. Seven validations run **before any sample is taken** — every one completes before
sampling begins — each covering a way the index can be wrong while still returning results:

1. all 105 documents represented
2. no code or binary content — the code corpus is deliberately empty this feature
3. nonzero chunk count, and more points than documents
4. every point carries every required authorization attribute
5. every point carries a **non-empty normalized passage body**
6. vector dimension and distance metric match production
7. every filter field has a payload index

Validation 5 exists because of a defect that reached this harness: the payload carried no
passage text at all, so the first-token prompt was assembled from five empty strings. The
length guard counted five of them and passed, and the measured prompt was a few dozen tokens
instead of two thousand. Prefill dominates time-to-first-token, so the run would have
reported a comfortable figure for a request production never sends.

A failure raises `PreviewIndexValidationError` and **no sample is taken**. A benchmark over a
silently wrong index is worse than no benchmark, because it produces a number.

## Ordering

```
make up && make seed && make credentials        stack, full profile
   ↓
infrastructure/colab/generation_server.ipynb    weights · endpoint · token · verified T4
   ↓
make benchmark-phase0                           preview + first-token
   ↓  preview row = PASS
Phase 2 production ingestion                    eaios-seed index
```

`eaios-seed index` is **not** a prerequisite of this benchmark. See above.

## What the exit code means

| Code | Meaning |
|-----:|---------|
| 0 | every row passed |
| 1 | a threshold was missed, or a row was never measured |
| 2 | preflight failed — the environment is not ready, nothing ran |
| 3 | `INVALID` — measured under conditions that make the figure unattributable |
| 4 | `UNSUPPORTED_CONFIGURATION` — the runtime cannot enforce deterministic settings |

They are distinguished because "the environment is not ready" and "the system is too slow"
call for completely different responses, and a single nonzero code makes them look alike.

## Results

One immutable JSON file per run under `results/`, never overwritten — a colliding run id is
an error, not a replacement. Each carries both figures, the **raw per-request timings**, the
provenance record, and a verdict. A p95 whose samples were discarded cannot be re-derived or
checked, which would make it an assertion rather than a measurement.

## Status

**No figure exists yet.** Both rows in `GATE.md` read `NOT RUN`. Neither latency threshold
has been measured, and `tests/unit/test_phase0_gate_not_claimed.py` fails the build if any
user-facing document says otherwise (FR-035e).
