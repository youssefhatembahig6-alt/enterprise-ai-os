# Performance Requirements Quality Checklist: Permission-Aware Knowledge Retrieval

**Purpose**: Validate that the latency requirement and its controlled measurement
environment are specified precisely enough to be reproduced or disputed
**Created**: 2026-08-11
**Feature**: [spec.md](../spec.md)

## ✅ Resolved 2026-08-11: reference environment declared, latency split in two

The blocking finding is closed. The hardware audit found **no discrete GPU** on the
reference machine (Intel UHD integrated only, no CUDA stack), which made a 2-second
time-to-first-token unreachable for local 3B generation. The deployment decision moved
generation to a declared **T4-class GPU, 16 GiB VRAM** — the latency *reference class*,
not a floor (FR-043a) — and split latency into two
measures — **local preview p95 ≤ 2 s** (no tunnel involved) and **first generated token
p95 ≤ 5 s** (through the tunnel). FR-035a now declares every attribute this section asked
for.

- [x] CHK119 **Is a reference machine declared at all?** [Resolved, Spec §FR-035a] — GPU class, VRAM floor, model state, corpus, concurrency, warm-up, sample size, and percentile method are all stated.

## Declared Environment — Required Attributes

Each item below asks whether the spec **states the value**, not whether the value is good.

- [x] CHK120 Is the **CPU** stated — model, core count, and base clock? [Gap, Spec §FR-035a]
- [x] CHK121 Is the **RAM** stated, as a quantity available to the stack rather than installed in the host? [Gap, Spec §FR-035a]
- [x] CHK122 Is the presence or absence of a **GPU** stated, and if present its model and **VRAM**? [Gap, Spec §FR-035a]
- [x] CHK123 Is the inference condition stated rather than left implicit? [Resolved, Spec §FR-035a] — a T4-class GPU is declared, and a CPU-only allocation is explicitly an **invalid** run (FR-035c).
- [x] CHK124 Is the **runtime environment** stated on both sides — the local stack's OS/container backend for the preview measure, and the Colab runtime for the generation measure? [Gap, Spec §FR-035a, §FR-028n] [**Resolved by design**, research R12, data-model `evaluation_runs`] — the local CPU-only environment is named for the preview figure and the T4 Colab runtime for the first-token figure, and both are recorded per run.
- [x] CHK125 Is the **model warm/cold state** stated — are weights already resident, or does the measurement include load time? [Gap, Spec §FR-035a]
- [x] CHK126 Is the **corpus size and profile** stated, since retrieval cost scales with index size and the smoke and full profiles differ by an order of magnitude? [Gap, Spec §FR-035a, §Assumptions]
- [x] CHK127 Is the **concurrency** stated — how many simultaneous questions the p95 is measured under? [Gap, Spec §FR-035a]
- [x] CHK128 Is the **measurement method** stated — sample count, warm-up policy, and how the percentile is computed? [Gap, Measurability, Spec §FR-035a]
- [x] CHK129 Are **both** measurement boundaries defined — what marks the end of the retrieval preview, and what counts as the first generated token? [Ambiguity, Spec §SC-010, §SC-010a] [**Resolved by design**, RC §1, §2] — the preview boundary is the `sources` event and the generation boundary is the first `token` event.

## Evidence

- [x] CHK130 Is the local preview threshold's status and verification route defined? [**Requirement resolved** — *implementation evidence pending*, Spec §FR-035e, §FR-035f, §SC-020] — stated as an acceptance threshold, not a demonstrated result, with a Phase 0 benchmark, declared parameters, and a blocking failure action. **The benchmark has not been run.**
- [x] CHK131 Does the spec state what happens if the declared hardware cannot meet the threshold — is the threshold revised, the model changed, or the phase blocked indefinitely? [Gap, Exception Flow, Spec §FR-043] [**Resolved by design**, plan Phase 0 outcome gate] — a preview failure blocks Phase 2 and a first-token failure blocks Phase 4; no threshold is relaxed without a specification clarification and checklist revalidation.
- [ ] CHK132 Is the reference environment required to be reproducible by a reviewer, or may it be a machine only the author possesses? [Gap, Measurability]

## Consistency

- [x] CHK133 Is the exclusion of latency from ordinary CI stated consistently everywhere it appears, with no criterion implying the shared runner must meet it? [Consistency, Spec §FR-035a, §SC-010, §FR-035] [**Resolved by design**, IC §4, plan phases] — the controlled evaluation is marked as not blocking the build, and latency gates the phase rather than the shared runner.
- [x] CHK134 Does any other criterion impose an implicit timing constraint that would bind the shared runner despite FR-035a? [Conflict, Spec §SC-001, §SC-010, §SC-010a] [**Resolved by design**, spec §FR-035a, §FR-017a, §FR-025a, §FR-028k] — no. Every timing constraint in the specification now states its lane explicitly: the two latency thresholds gate the phase (FR-035a), the indistinguishability p95 gates stabilization (FR-017a), and the only deadlines binding ordinary CI are the two **local** ones — the 2-second health check (FR-028k) and the 2-second cancellation close (FR-025a) — neither of which depends on a GPU or a tunnel.
- [ ] CHK135 Are requirements defined for degradation under load — what the system does when it cannot meet the target — or only for the target itself? [Gap, Coverage]
- [x] CHK136 Is there a stated relationship between retrieval breadth and latency? [**Requirement resolved**, Spec §FR-028b1, §FR-035f] — the passage budget is fixed at 5 passages / 2,000 tokens, and the benchmark measures first-token latency at exactly that budget, so the two are bound to one another.

## Split Latency Model (added 2026-08-11)

- [x] CHK186 Is "retrieval-ready source preview" defined as a perceivable milestone, so the 2-second measure has an observable end point? [Ambiguity, Spec §SC-010] [**Resolved by design**, RC §1] — the `sources` event is the perceivable end point of the preview measure.
- [x] CHK187 Is the boundary of the 5-second measure stated — does the clock start at the question, or at the outbound generation request? [Clarity, Spec §SC-010a] [**Resolved by design**, RC §2, IC §6] — the first-token clock ends at the first `token` event, measured nearest-rank.
- [ ] CHK188 Are requirements defined for how tunnel latency and jitter are recorded, given that a shared tunnel's variance is not the system's? [Gap, Spec §FR-028n]
- [x] CHK189 Is the exclusion of cold-start and download time specified with a stated rule for identifying a cold request? [Measurability, Spec §FR-035c] [**Resolved by design**, plan Phase 0] — 5 warm-ups discarded, ≥ 30 measured — the stated rule for what counts as a cold request.
- [x] CHK190 Is "T4, 16 GiB VRAM minimum" stated as a floor with a rule for *faster* allocations — does a better GPU break comparability across the three runs? [Ambiguity, Spec §FR-035a, §FR-043] [**Resolved by design**, spec §FR-043a, IC §7, research R20] — T4 16 GiB is the **latency reference class, not a floor**; a faster GPU is valid for quality evidence, invalid for either latency threshold, and recorded in a separate named series that never mixes into a T4 sequence.
- [x] CHK191 Are requirements defined for detecting that Colab silently allocated CPU-only or a different GPU, so an invalid run is recognised rather than recorded as a result? [Gap, Spec §FR-035c, §SC-018d] [**Resolved by design**, spec §FR-028n, §FR-043a, data-model `evaluation_runs`] — every run records the actual GPU model and its series; CPU-only and unidentified-GPU allocations become `INVALID_NO_GPU` / `INVALID_UNKNOWN_GPU`, which are neither pass nor fail and do not continue the sequence.
- [x] CHK192 Is the first-token threshold's status and verification route defined? [**Requirement resolved** — *implementation evidence pending*, Spec §FR-035e, §FR-035f, §SC-020] — same treatment: acceptance threshold, verified Colab T4, five passages, 5 warm-ups, ≥ 30 samples, nearest-rank p95, failure blocks the subsystem. **The benchmark has not been run.**
