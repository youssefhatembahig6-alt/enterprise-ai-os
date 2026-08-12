# Evaluation Requirements Quality Checklist: Permission-Aware Knowledge Retrieval

**Purpose**: Validate that retrieval, grounding, citation, abstention, and phase-gate
requirements are defined precisely enough to produce a figure someone can dispute
**Created**: 2026-08-11
**Feature**: [spec.md](../spec.md)

## Measure Definitions

- [x] CHK091 Is "the expected supporting document" in recall@5 defined as exactly one document per question, or may a question have several acceptable sources? [Ambiguity, Spec §FR-032, §SC-016] [**Resolved by design**, IC §6, data-model.md] — a question carries `expected_document_ids[]` — a set, not a single document — and recall@5 is satisfied when an expected document appears.
- [x] CHK092 Is recall@5 measured over retrieved *chunks* or retrieved *documents*, given that five chunks may come from one document? [Clarity, Spec §FR-032] [**Resolved by design**, IC §6] — the top 5 retrieved **chunks**, reduced to their documents.
- [ ] CHK093 Is "substantive claim" defined well enough that two reviewers would segment the same answer identically? [Measurability, Spec §FR-019, §SC-002]
- [x] CHK094 Is grounding measured per answer (all-or-nothing) or per claim, and does the spec state which? [Clarity, Spec §SC-002] [**Resolved by design**, spec §FR-032a, IC §6] — **per claim** — the judge schema returns a per-claim `grounded｜not_grounded` decision with an enumerated reason code, not one verdict per answer.
- [x] CHK095 Is "actually support the claim" in citation precision defined by a stated adjudication procedure — automated, human, or model-judged? [Measurability, Spec §SC-002a] [**Resolved by design**, spec §FR-032a, §FR-032b, research R22] — model-judged by the same pinned model in a separate temperature-0 invocation with a versioned prompt and strict schema, **plus** a ≥ 90% calibration gate against a committed manually labelled set, **plus** the deterministic structural checks of FR-032c alongside it.
- [x] CHK096 If an LLM judges grounding or citation precision, is the judge's model and prompt pinned and recorded like any other configuration? [Gap, Spec §FR-011b] [**Resolved by design**, IC §6] — grounding and citation precision are adjudicated by a pinned judge whose model and prompt are recorded like any other configuration.
- [ ] CHK097 Is "correctly refused" defined so that a refusal for the wrong reason does not count as correct abstention? [Clarity, Spec §SC-009]
- [ ] CHK098 Are the **seven** measures stated as independent, with no measure's denominator depending on another's outcome? [Consistency, Spec §FR-032]

## Evaluation Set Quality

- [x] CHK099 Does the spec state a minimum size for the evaluation set, so a percentage threshold is statistically meaningful? [Gap, Measurability, Spec §FR-031] [**Resolved by design**, IC §5] — ≥ 40 questions, with the reason stated — below that a 90% threshold moves by more than a point per question.
- [x] CHK100 Are requirements defined for the *composition* of the set — how many questions must be unanswerable, cross-tenant, or permission-split? [Gap, Spec §FR-031] [**Resolved by design**, IC §5] — ≥ 8 unanswerable, ≥ 8 permission-split pairs, ≥ 4 cross-tenant, ≥ 1 ACL-only plus its negative twin.
- [x] CHK101 Is there a requirement that the set contain questions each persona *can* answer, so a leakage figure of zero cannot be achieved by a persona who can reach nothing? [Anti-vacuity, Gap, Spec §FR-031] [**Resolved by design**, IC §5] — every persona must be able to answer at least one question, so a zero-leakage figure cannot come from a persona who reaches nothing.
- [x] CHK102 Are requirements defined for how ground truth is authored and reviewed, so the expected sources are not simply whatever the system returned? [Gap, Spec §FR-031] [**Resolved by design**, IC §5] — ground truth is authored from the corpus and reviewed, never harvested from system output.
- [x] CHK103 Is the evaluation set required to be version-controlled and versioned alongside the recorded configuration? [Gap, Spec §FR-011b, §FR-034] [**Resolved by design**, IC §5] — version-controlled and versioned alongside the recorded configuration.

## Thresholds and Gating

- [ ] CHK104 Is each of the **seven** thresholds attached to exactly one measure with one comparison operator, leaving no ambiguity about pass or fail? [Clarity, Spec §FR-032]
- [x] CHK105 Does the spec state which checks block **every build** and which gate **only the phase**, without overlap or omission? [Consistency, Spec §FR-035, §FR-035a] [**Resolved by design**, IC §4, plan phases] — the build-blocking set is enumerated in the contract and the phase gates in the plan, with no overlap.
- [ ] CHK106 Is the rationale for sub-100% grounding, citation, and abstention thresholds — versus zero leakage — stated as a requirement-level distinction rather than an aside? [Clarity, Spec §FR-033]
- [ ] CHK107 Are requirements defined for what happens when a measure falls *below* threshold: does the build fail, the phase stall, or both, and for which measures? [Gap, Spec §FR-035]
- [ ] CHK108 Is "deterministic retrieval blocks the build" defined by a stated comparison across runs, and is the tolerance zero? [Measurability, Spec §FR-034, §FR-035]

## The Three-Run Gate

- [x] CHK109 Is "three consecutive full evaluation runs" defined with respect to *what must be unchanged between them* — corpus, configuration, code, or all three? [Ambiguity, Spec §FR-043, §SC-017] [**Resolved by design**, IC §7] — the same declared GPU class and pinned configuration across all three runs.
- [x] CHK110 Does the spec state whether the three runs must be on distinct occasions, or may be three repetitions in a single job? [Clarity, Spec §SC-017] [**Resolved by design**, spec §FR-043c, IC §7 What counts as a run, research R33] — **three isolated executions**, never in-process iterations: each starts after the previous reaches a terminal result, re-runs the full preflight, gets its own run id, manifest, raw results and samples, and starts with empty caches. Same day and same T4 session are permitted; one orchestration command may spawn three isolated children; a loop inside one process does not count however many rows it writes.
- [x] CHK111 Is the effect of an intervening change specified — does a code change reset the count to zero? [Gap, Spec §FR-043] [**Resolved by design**, IC §7] — a change of GPU class, quantization, runtime, or prompt version starts a new sequence.
- [x] CHK112 Are the three-run results required to be recorded and citable, so the gate's satisfaction is evidence rather than a claim? [Gap, Traceability, Spec §FR-043] [**Resolved by design**, IC §7, data-model `evaluation_runs`] — results are recorded rows and are citable evidence, not a claim.
- [ ] CHK113 Is it stated who or what enforces FR-043 — a check, a review, or a convention — given that a spec cannot stop work by itself? [Gap, Measurability]
- [x] CHK114 Does the spec state whether *all seven* measures must pass in each of the three runs, or the aggregate across them? [Ambiguity, Spec §SC-017] [**Resolved by design**, spec §FR-034a, IC §7] — **each** of the three runs must independently meet every threshold; averaging across runs to reach a threshold is explicitly forbidden.

## Continuous Integration

- [x] CHK115 Is the evaluation's CI cost bounded? [Resolved, Spec §FR-035b, §FR-035d] — the full-model evaluation is no longer part of ordinary CI; CI runs fixtures and a stub.
- [x] CHK116 Are requirements defined for which profile the evaluation runs against, given that the smoke corpus is a fraction of the full one and recall figures will differ? [Gap, Consistency, Spec §Assumptions] [**Resolved by design**, spec §FR-035d, IC §4] — the controlled evaluation runs the **complete 105-document seeded corpus**; ordinary CI runs the committed fixture subset only.
- [ ] CHK117 Is SC-013's "an induced leak fails the build" specified with a stated induction method, so the control itself is checkable? [Measurability, Spec §SC-013]
- [x] CHK118 Is there a requirement that the evaluation fail loudly when it is *unable* to run, rather than reporting zero questions as a pass? [Anti-vacuity, Gap] [**Resolved by design**, spec §FR-035i, IC §10, research R17] — the evaluator exits **nonzero before computing any metric** on five named conditions — zero questions, an empty required partition, counts disagreeing with the manifest, a zero denominator, or an expected document outside the corpus.

## Split CI and Remote Evaluation (added 2026-08-11)

- [x] CHK212 Is the committed-fixture set defined precisely — which embeddings, which chunks, and how they are regenerated when the embedder changes? [Completeness, Spec §FR-035b] [**Resolved by design**, IC §3, §4] — the fixture set is chunk texts plus vectors plus the nine-field manifest, regenerated only by `eaios-seed fixtures regenerate` in the controlled environment.
- [x] CHK213 Is there a requirement that the fixtures stay consistent with the real embedder, so CI cannot pass against stale vectors? [**Requirement resolved**, Spec §FR-035g, §FR-035h, §SC-022] — a nine-field fixture manifest, CI failure on disagreement with the embedder/dimension/chunker/source hashes, and regeneration only in the controlled environment by explicit command with a reviewable diff and a passing retrieval evaluation.
- [x] CHK214 Is the stubbed generator specified well enough that streaming and cancellation behaviour is genuinely exercised rather than trivially satisfied? [Anti-vacuity, Spec §FR-035b] [**Resolved by design**, IC §4] — the stub emits tokens with delays and honours cancellation, stated explicitly so the streaming checks are not trivially satisfied.
- [x] CHK215 Does the spec state which measures are impossible in ordinary CI, so their absence there is deliberate rather than an oversight? [Clarity, Spec §FR-035b, §FR-035d] [**Resolved by design**, IC §4] — the two-lane table states that ordinary CI measures none of FR-032, so the absence is deliberate.
- [x] CHK216 Is the invalid-run outcome distinguished from a failed run in the three-run sequence, with a stated effect on the count? [Clarity, Spec §FR-035c, §FR-043] [**Resolved by design**, IC §7] — `INVALID` runs are neither pass nor fail and do not continue the sequence.
- [x] CHK217 Are requirements defined for how the evaluation behaves when the tunnel drops part-way through a run — is the run void, partial, or failed? [Gap, Exception Flow] [**Resolved by design**, spec §FR-035o, RC §6, research R34] — the generation server is **Phase 0 provisioning**: weights, endpoint, token, verified T4, runtime identity, health endpoint and streaming protocol are all verified before the first sample, and a missing prerequisite leaves the row `NOT RUN` or `INVALID` rather than producing a partial or passing figure.
- [x] CHK218 Is the corpus profile for the controlled evaluation stated as the full 105 documents, and is the smoke/full recall difference acknowledged? [Consistency, Spec §FR-035a] [**Resolved by design**, spec §FR-035b, §FR-035d, IC §4] — the corpus profile is stated per lane, and ordinary CI may not report or imply a full-corpus quality figure; the corpus fingerprint on every output is what keeps the two apart afterwards.
