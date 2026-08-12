# Authorization Requirements Quality Checklist: Permission-Aware Knowledge Retrieval

**Purpose**: Validate that the authorization requirements are complete, unambiguous, and
measurable — before any of them is implemented
**Created**: 2026-08-11
**Feature**: [spec.md](../spec.md)

These items test the **requirements**, not a running system. Each asks whether something is
*written down well enough to build and to disprove*. An item fails when the spec is silent,
vague, or self-contradictory — not when code misbehaves.

## Authorization Before Search

- [ ] CHK001 Is "as a constraint on the search itself, not a filter over its results" defined precisely enough to tell a compliant design from a non-compliant one? [Clarity, Spec §FR-013]
- [ ] CHK002 Does the spec state what evidence would *demonstrate* a violation of FR-013 — i.e. how a reviewer distinguishes a filtered-after search from a constrained one? [Measurability, Spec §FR-013]
- [ ] CHK003 Are the five layers of FR-014 each defined with the attribute they read and the outcome they produce, or only named? [Completeness, Spec §FR-014]
- [ ] CHK004 Is the ordering requirement in FR-014 stated as *observable* behaviour (which layer's denial is reported) rather than as an internal implementation sequence? [Measurability, Spec §FR-014]
- [x] CHK005 Does the spec define what "transiently" excludes in FR-013 — for example whether a candidate set may be computed and discarded inside the store? [Ambiguity, Spec §FR-013] [**Resolved by design**, spec §FR-013a, research R24] — "transiently" is bounded as a **lifetime**: request-scoped memory only, from authorized retrieval to the terminal SSE event or abort cleanup, then released — with an enumerated sink list and the index explicitly exempt as the source rather than a downstream copy.
- [x] CHK006 Are requirements defined for the case where the vector store cannot express a required filter, so authorization *cannot* be pushed into the search? [Gap, Exception Flow] [**Resolved by design**, RC §3 Filter shape, IC §1] — the must/should shape is expressible in Qdrant, and `index` refuses to run when any filter field lacks a payload index — an inexpressible filter fails before any content exists.

## Zero Leakage

- [ ] CHK007 Is "unauthorized content exposure" defined as a countable event, with a stated unit (chunk? claim? citation? token?) so a figure of zero is checkable? [Measurability, Spec §FR-033, §SC-003]
- [ ] CHK008 Does the spec enumerate the channels through which exposure could occur — answer text, citations, counts, ordering, timing, error wording — so coverage of SC-003 is bounded? [Completeness, Spec §FR-015, §FR-017]
- [ ] CHK009 Is the indistinguishability requirement in FR-017 specified against a stated comparison (equality with the unauthorized-free response) rather than as "reveals nothing"? [Clarity, Spec §FR-017]
- [x] CHK010 Are timing-based disclosure requirements quantified, or does "no difference in latency-shaped behaviour" remain unmeasurable? [Ambiguity, Spec §FR-017] [**Resolved by design**, spec §FR-017a, RC §7a, research R25] — five identical observable properties checked as **control flow** in ordinary CI, plus a controlled timing measure of **≥ 50 warm samples per case** with a **p95 time-to-terminal difference ≤ max(100 ms, 20%)** that gates stabilization rather than the shared runner.
- [ ] CHK011 Does the spec state that a *permitted* document quoting an unreadable one is not a leak, and is that boundary written as a requirement rather than only as an edge-case note? [Consistency, Spec §Edge Cases]
- [ ] CHK012 Is there a requirement that the leakage measure be non-vacuous — that the evaluation set contains questions whose answers genuinely sit behind a boundary? [Anti-vacuity, Spec §FR-031]

## Tenant, Classification, Department and Resource Filters

- [x] CHK013 Are the chunk's authorization attributes enumerated and matched one-to-one against the layers that consume them, with an index for each? [**Requirement resolved**, Spec §FR-014b, §SC-025] — every filter attribute must have a payload index and be tested; the missing `allowed_roles` index must be added before any point is written.
- [x] CHK014 Is the behaviour specified for a chunk whose source document has a *null* department or country? [**Requirement resolved**, Spec §FR-014a, §SC-024] — null means company-wide, never unfiltered and never match-all; a caller with a value reaches matching plus company-wide, a caller without one reaches company-wide only unless owner/role/ACL authorizes; company and classification always apply.
- [ ] CHK015 Are the four classification levels and their ordering stated in this spec, or only inherited by implication from feature 001? [Completeness, Traceability]
- [ ] CHK016 Are requirements defined for resource-level grants of both principal types and both permissions that `document_acl` allows, or only for the read case? [Coverage, Gap]
- [ ] CHK017 Is the cross-tenant outcome specified as *absent* rather than *forbidden*, consistently with the existing tenant-boundary rule, and is that consistency stated? [Consistency, Spec §FR-014, §SC-005]
- [ ] CHK018 Does the spec define what happens when a document's classification changes *after* its chunks are indexed, as a requirement and not only as an edge case? [Gap, Spec §Edge Cases]
- [ ] CHK019 Are requirements defined for a chunk whose source document has been deleted between indexing and retrieval? [Coverage, Spec §Edge Cases]

## Cache Isolation

- [ ] CHK020 Is "scoped such that it can never be served to a caller whose permissions differ" expressed as a stated key composition requirement, or left to interpretation? [Clarity, Spec §FR-018]
- [x] CHK021 Does the spec define what constitutes "differing permissions" for cache purposes — the permission set, the full access context, or a derived fingerprint? [Ambiguity, Spec §FR-018] [**Resolved by design**, spec §FR-018a, research R2, R23] — the permission fingerprint decides "differing permissions"; `data_version` is the company-scoped active corpus manifest checksum, so the key varies with permissions **and** with what is retrievable, and neither is left to the caller.
- [x] CHK022 Are cache requirements stated for *every* cacheable stage (embedding of a query, retrieval results, generated answer, citation resolution), or only generically? [Completeness, Spec §FR-018] [**Resolved by design**, research R2] — `cache_key(company_slug, permission_fingerprint, normalized_question, data_version)` keys every cacheable stage; no stage is left generic.
- [x] CHK023 Is there a requirement covering cache invalidation when a person's permissions change mid-session? [Gap, Spec §FR-016] [**Resolved by design**, research R2] — a changed permission set yields a different fingerprint and therefore a different key, so the stale entry becomes unreachable rather than needing invalidation.
- [ ] CHK024 Does the spec state whether any cache may be shared across tenants at all, under any key? [Gap, Coverage]

## Identity and Trust Boundary

- [x] CHK025 Is "the immutable access context" identified by a stable reference to the existing spec so the two cannot drift apart? [Traceability, Spec §FR-012] [**Resolved by design**, research R1, plan Phase 1] — the plan consumes `eaios_core.authz.filters.qdrant_filter` — the same function the policy engine derives from — rather than re-deriving access, and its unit tests are Phase 1 task 1.
- [ ] CHK026 Are the prohibitions in FR-028 stated as an enumerated list of forbidden behaviours (accept, parse, validate, hold the key) rather than a general principle? [Clarity, Spec §FR-028]
- [ ] CHK027 Does the spec define how a component receives the access context in a way that cannot be forged by the caller, without naming a mechanism? [Completeness, Spec §FR-029]
- [ ] CHK028 Are requirements defined for what a background job does when its authorization context is absent or expired at execution time, distinct from being absent at submission? [Gap, Spec §FR-030]
- [ ] CHK029 Is the requirement that a question cannot widen access stated as a requirement, or only as an edge case? [Consistency, Spec §Edge Cases]

## Per-Request Evaluation

- [x] CHK030 Is "per request" defined against a stated boundary — per question, per retrieval, per citation open — so FR-016 is unambiguous for multi-step flows? [Ambiguity, Spec §FR-016] [**Resolved by design**, spec §FR-012a, RC §3, research R30] — **one logical user question — one turn**: a newly built access-context snapshot per turn, reusable only within it; follow-ups, regenerated answers and resumed conversations build a new one; FR-022 citation authorization stays independently required for opens that happen outside any turn.
- [ ] CHK031 Are requirements defined for permissions that change *during* a single streaming response? [Gap, Edge Case]
- [ ] CHK032 Is the re-authorization requirement for opening a citation consistent with the retrieval-time requirement, including the outcome shape? [Consistency, Spec §FR-022, §FR-016]

## Acceptance Criteria Quality

- [ ] CHK033 Can every authorization success criterion be evaluated without inspecting implementation internals? [Measurability, Spec §SC-003, §SC-004, §SC-005]
- [ ] CHK034 Is SC-004's "indistinguishable" backed by a stated comparison procedure? [Measurability, Spec §SC-004]
- [ ] CHK035 Do the authorization requirements state which of them block every build, distinctly from those that gate the phase? [Clarity, Spec §FR-035]

## Remote Generation Boundary (added 2026-08-11)

- [ ] CHK193 Is the forbidden-payload list in FR-028a exhaustive, and is it stated as a list a reviewer can check a captured request against? [Completeness, Spec §FR-028a]
- [x] CHK194 Is "the minimum authorized passages required to answer the current question" defined by a stated selection rule rather than left to judgement? [Ambiguity, Spec §FR-028b] [**Resolved by design**, spec §FR-028b1] — a stated selection rule rather than judgement: at most 5 passages, 400 pinned-tokenizer tokens per passage, 2,000 tokens in total, taken from the top-ranked authorized results.
- [x] CHK195 Does the spec state that the generator cannot widen its own context, and is that expressed as a property of the request rather than a promise about the model? [Clarity, Spec §FR-028c] [**Resolved by design**, spec §FR-012a, §FR-028a] — stated as a property of the **request**: the outbound payload carries only `question`, `passages`, `max_tokens`, `temperature` — no access-context object — and no worker or provider may create, validate, widen or reuse a context across turns.
- [ ] CHK196 Are requirements defined for what happens if the generator returns a citation to a passage it was never sent? [Coverage, Spec §Edge Cases, §FR-028c]
- [ ] CHK197 Is the prohibition on the browser contacting the tunnel stated as an architectural requirement with a checkable consequence? [Measurability, Spec §FR-028d]
- [x] CHK198 Is conversation history excluded from the outbound payload unless re-retrieved under current permissions, consistently with FR-026? [Consistency, Spec §FR-026, §FR-028b] [**Resolved by design**, spec §FR-012a, §FR-026] — conversation history MUST be **re-authorized under the new turn's context** before any reuse, and the outbound allowlist admits no history field.
- [ ] CHK199 Are requirements defined for redacting or refusing a question whose own text contains content the asker may not read? [Gap, Edge Case]
