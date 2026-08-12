# Streaming Experience Requirements Quality Checklist: Permission-Aware Knowledge Retrieval

**Purpose**: Validate that streaming, cancellation, and surface-state requirements are
complete, unambiguous, and consistent with the portal's established state rules
**Created**: 2026-08-11
**Feature**: [spec.md](../spec.md)

## Progressive Delivery

- [x] CHK137 Is "delivered progressively" specified as an observable property, or could a single final write satisfy the wording? [Ambiguity, Spec §FR-025] [**Resolved by design**, RC §2] — progressive delivery is observable as a stream of `token` events preceded by `sources`; a single final write would not produce them.
- [x] CHK138 Are requirements defined for what the person sees between asking and the first content arriving, given that the portal's loading state is a shared boundary? [Gap, Spec §FR-025, §FR-027] [**Resolved by design**, RC §1, §8] — the `sources` event is the milestone between asking and first content, and the surface inherits feature 003's loading boundary for the interval before it.
- [x] CHK139 Is the point at which citations become visible specified — with the claim, at the end, or progressively? [Gap, Spec §FR-020, §FR-025] [**Resolved by design**, RC §2] — `citation` events carry a `claim_ordinal` and arrive with the claim, not at the end.
- [ ] CHK140 Are requirements defined for content that arrives out of order or must be revised mid-stream? [Gap, Edge Case]

## Cancellation

- [x] CHK141 Is "stoppable" defined with respect to what stops — the display, the generation, or the underlying work? [Ambiguity, Spec §FR-025] [**Resolved by design**, spec §FR-025a, RC §2a, research R29] — **end-to-end cancellation**: emission halts, cancellation propagates to the provider and stops token generation, the stream closes within **2 seconds**, request-scoped content is released, and no continuation follows — with a required test proving that stopping only the display is a **failure**.
- [x] CHK142 Does the spec state whether a stopped response's partial content is retained, discarded, or retained-and-marked, consistently in every place it is mentioned? [Consistency, Spec §FR-025, §SC-010] [**Resolved by design**, spec §FR-025a] — **retained and marked** — stated once and consistently: partial text is retained, the answer is marked incomplete, and the turn is recorded with `answer_state = STOPPED`.
- [x] CHK143 Are requirements defined for whether a stopped response is recorded in conversation history, and whether it can be resumed? [Gap, Coverage] [**Resolved by design**, spec §FR-025a, data-model] — a stopped turn **is recorded** in conversation history and is **not resumable** — a resumed answer would be a new turn under a new access context (FR-012a).
- [x] CHK144 Is the audit obligation for a cancelled generation stated, given that FR-036 requires every generation to be audited? [Consistency, Gap, Spec §FR-036] [**Resolved by design**, spec §FR-025a, §FR-036] — a cancelled generation **is audited exactly as any other generation is**; the cancellation adds `provider_cancel_status`, which is content-free.
- [x] CHK145 Are requirements defined for a person navigating away mid-stream, as distinct from explicitly stopping? [Gap, Edge Case] [**Resolved by design**, spec §FR-025b, RC §2a Client disconnect, research R31] — a disconnect is an **implicit cancellation**: mechanically identical to an explicit stop (upstream cancelled, 2-second cleanup, `provider_cancel_unconfirmed` handling, content released, no continuation), but recorded **`INCOMPLETE｜CLIENT_DISCONNECT`**, never `STOPPED`, and with no terminal SSE event required because the connection is gone.

## Incompleteness and Failure

- [x] CHK146 Is "marked incomplete" specified as a stated, perceivable distinction rather than an internal flag? [Measurability, Spec §FR-025] [**Resolved by design**, RC §2] — the mandatory terminal `done` event carries the state, so incompleteness is perceivable rather than an internal flag.
- [x] CHK147 Are the two incomplete cases — stopped by the person, failed by the system — required to be distinguishable to the reader? [Clarity, Spec §FR-025] [**Resolved by design**, RC §2] — `stopped` and `incomplete` are distinct `done` states, and distinct `answer_state` values in the record.
- [ ] CHK148 Does the spec state what happens to citations already shown when a response then fails? [Gap, Edge Case]
- [ ] CHK149 Are requirements defined for a partial answer whose visible claims are unsupported because their citations had not yet arrived? [Gap, Consistency, Spec §FR-019]

## Surface States

- [x] CHK150 Is the assistant surface's state set stated by reference to the portal's existing rule, so the two cannot drift? [Traceability, Spec §FR-027] [**Resolved by design**, RC §8] — the surface joins the existing `(authed)` group and inherits the shell, loading and error boundaries by reference.
- [x] CHK151 Are the states the assistant *cannot* reach identified with reasons, as the portal contract now requires, rather than assumed to be a full cross-product? [Consistency, Spec §FR-027] [**Resolved by design**, RC §8] — its classification is added to `portal-states.test.tsx`, whose matrix fails on any unclassified cell.
- [ ] CHK152 Is the empty state distinguished from the abstention outcome — "you have no conversations" versus "your documents cannot answer this"? [Clarity, Gap]
- [ ] CHK153 Are requirements defined for the access-denied state on the assistant surface, given that any authenticated user may ask questions? [Gap, Coverage]
- [ ] CHK154 Is the conversation-history scoping requirement stated with an outcome for the cross-owner case, not only the rule? [Completeness, Spec §FR-026]

## Consistency With Existing Behaviour

- [ ] CHK155 Is the requirement that no existing portal behaviour weakens stated as a checkable obligation rather than an intention? [Measurability, Spec §FR-024, §FR-041]
- [ ] CHK156 Are accessibility obligations for a live-updating region stated, given that streamed content changes under a reader? [Gap, Coverage]

## Generation-Service Availability (added 2026-08-11)

- [x] CHK200 Is the "generation temporarily unavailable" state defined as distinct from empty, error, access-denied, and expired, with stated wording that does not reveal the endpoint? [Clarity, Spec §FR-028l] [**Resolved by design**, RC §6, §8] — `generation_unavailable` is its own `done` state and its own matrix cell — explicitly not folded into `error` — and the tunnel URL is never sent to the browser.
- [ ] CHK201 Does the spec state that ingestion, authorization, and retrieval stay operational while generation is unavailable, as an observable property? [Measurability, Spec §FR-028l]
- [x] CHK202 Is the availability check required *before* streaming begins, with a stated outcome if the check itself times out? [Completeness, Spec §FR-028k] [**Resolved by design**, spec §FR-028k, RC §6, research R19] — the local API checks health with a **2-second deadline**, and timeout, DNS failure, TLS failure, authentication refusal, malformed response and unhealthy status all resolve to the same *unavailable* outcome.
- [x] CHK203 Is the mid-stream tunnel failure path distinguished from a user cancellation in both the interface and the record? [Consistency, Spec §FR-028m, §FR-025] [**Resolved by design**, RC §2, data-model] — the `done` state and the stored `answer_state` both separate `STOPPED` from `INCOMPLETE`.
- [ ] CHK204 Are requirements defined for whether a person may retry after an unavailable state, and whether retrieval results are preserved across the retry? [Gap, Recovery Flow]
- [x] CHK205 Is the retrieval-ready source preview specified as a user-visible milestone, given that SC-010 now measures it? [Clarity, Spec §SC-010] [**Resolved by design**, RC §1] — the `sources` event is the user-visible retrieval-ready milestone SC-010 measures.
