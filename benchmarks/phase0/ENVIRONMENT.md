# Declared measurement environment

Both Phase 0 figures are measured here and nowhere else. A latency number without the
machine that produced it is not a measurement, so this file is a precondition of the
benchmark rather than a note about it (FR-035a).

The values below are **copied from the Feature 004 spec Assumptions**, measured 2026-08-11.
If the machine changes, this file changes first and the recorded figures are invalidated —
not reinterpreted.

---

## Local environment — embedding and preview retrieval

| Attribute | Declared value |
|-----------|----------------|
| CPU | Intel Core i5-13420H |
| Cores / threads | 8 cores / 12 threads |
| RAM | 15.7 GB |
| Docker VM limit | 7.61 GB |
| GPU | Intel UHD integrated graphics |
| CUDA | **absent** — no CUDA stack on this machine |
| Stack | the existing Docker Compose environment |
| Corpus profile | **full** — 105 documents |
| Embedding model state | warm |
| Concurrency | 1 |
| Warm-up | 5 requests, discarded |
| Sample size | ≥ 30 measured requests |
| Percentile method | nearest-rank p95 |

The absence of a discrete GPU is the reason generation is remote at all. It is also why the
local half of the latency budget is the half that can be promised: embedding and vector
search on this machine are the parts whose cost does not depend on a session someone else
schedules.

## Remote environment — generation

| Attribute | Declared value |
|-----------|----------------|
| GPU | NVIDIA **T4**, **16 GiB VRAM** |
| Provider | Google Colab session |
| Transport | authenticated HTTPS ngrok tunnel |
| Model | Qwen2.5-3B-Instruct, Q4_K_M (GGUF) |
| Runtime | `llama.cpp` server |
| Model state | **warm** — weights resident before the first measured sample |
| Concurrency | 1 |
| Warm-up | 5 requests, discarded |
| Sample size | ≥ 30 measured requests |
| Percentile method | nearest-rank p95 |

### The T4 is a reference class, not a floor

This matters enough to state separately, because the two readings lead to opposite
conclusions (FR-043a).

The T4 is the **latency reference class**: the hardware the threshold is defined against.
It is **not a minimum bar to clear**. A session that allocates a faster GPU — an A100, an
L4 — does **not** produce a comparable figure and does **not** satisfy the gate. It proves
the answer quality is reachable; it says nothing about whether the threshold holds on the
declared class.

So a faster allocation is treated the same way as a slower one: the run is recorded
`INVALID` for the latency figure rather than passing on a number that describes a machine
nobody promised. An unidentified or CPU-only allocation is likewise `INVALID`, never a pass
(FR-035c).

---

## Status

**Nothing has been measured.** This file declares where the measurement will happen. Both
rows in `GATE.md` read `NOT RUN`, and no figure exists yet for either threshold.
