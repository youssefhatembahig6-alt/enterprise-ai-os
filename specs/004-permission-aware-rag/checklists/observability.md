# Observability Requirements Quality Checklist: Permission-Aware Knowledge Retrieval

**Purpose**: Validate that audit and telemetry requirements are complete and unambiguous,
and that the prohibition on sensitive content is stated precisely enough to enforce
**Created**: 2026-08-11
**Feature**: [spec.md](../spec.md)

## The Prohibition

- [ ] CHK157 Is the prohibited-content list in FR-037 exhaustive, or are there categories — retrieved passages, prompt text, chunk identifiers that reveal titles — left unaddressed? [Completeness, Spec §FR-037]
- [x] CHK158 Is "document content" defined to include derived forms such as summaries, snippets, and highlighted fragments? [Ambiguity, Spec §FR-037] [**Resolved by design**, spec §FR-013a] — the prohibition names **derived forms explicitly** — summaries, snippets and highlighted fragments are passage content for this purpose, and are barred from the same enumerated sinks.
- [ ] CHK159 Does the prohibition extend to *exception messages and stack traces* raised by the model runtime, which routinely echo prompt fragments? [Gap, Spec §FR-037]
- [ ] CHK160 Are embeddings prohibited on stated grounds — is the spec's position that a vector is recoverable content, and is that position written down? [Clarity, Spec §FR-037]
- [x] CHK161 Is "question text" prohibited consistently, given that FR-036 requires auditing "the question's identity" — is identity defined as a digest or a reference rather than the text? [Consistency, Spec §FR-036, §FR-037] [**Resolved by design**, IC §8, data-model] — `question_digest` is what is audited and stored; question text is in the never-recorded list.
- [ ] CHK162 Is SC-011's "verified by automated search" specified with a stated corpus of search terms, so a clean result is meaningful rather than lucky? [Measurability, Anti-vacuity, Spec §SC-011]
- [ ] CHK163 Is there a requirement that the leak-detection search itself be proven capable of finding a planted secret? [Anti-vacuity, Gap, Spec §SC-011]

## Audit Completeness

- [ ] CHK164 Are the required audit fields in FR-036 sufficient to reconstruct an authorization decision without reading content? [Completeness, Spec §FR-036]
- [x] CHK165 Is it stated whether *refused* retrievals produce an audit record, or only served ones? [Ambiguity, Spec §FR-036, §FR-039] [**Resolved by design**, spec §FR-039, IC §8] — refusals of ingestion, retrieval and generation are all audited, and the audit record carries the decision and outcome.
- [ ] CHK166 Does the spec state which tenant a cross-tenant attempt is recorded under, consistently with the existing rule? [Consistency, Traceability]
- [ ] CHK167 Are audit obligations stated for ingestion refusals as well as retrieval and generation refusals? [Consistency, Spec §FR-039, §FR-003]
- [x] CHK168 Is "the documents consulted" defined — every candidate, only those cited, or everything retrieved? [Ambiguity, Spec §FR-036] [**Resolved by design**, spec §FR-036a, IC §8, research R18] — five fixed terms — candidate, retrieved passage, generation passage, cited passage — with **documents consulted** defined as distinct `document_id` values among **generation passages**, which names what actually informed the answer.
- [ ] CHK169 Are retention requirements for audit and conversation records stated, or inherited silently? [Gap, Dependency]

## Diagnosability Without Content

- [ ] CHK170 Are the four questions FR-038 requires telemetry to answer each mapped to a stated signal? [Completeness, Spec §FR-038]
- [x] CHK171 Is "how many were excluded by authorization" reconcilable with FR-017's prohibition on revealing withheld counts *to the asker* — is the audience distinction stated? [Conflict, Spec §FR-017, §FR-038] [**Resolved by design**, IC §8] — the excluded count is operator-facing telemetry only and never reaches a response — the audience distinction FR-017 and FR-038 need in order not to conflict.
- [x] CHK172 Are requirements defined for distinguishing a slow retrieval from a slow generation in telemetry? [Gap, Spec §FR-038] [**Resolved by design**, IC §8] — retrieval duration and generation duration are separate telemetry signals.
- [ ] CHK173 Is the requirement that operators can distinguish permission decisions from failures stated with the mechanism by which they differ in the record? [Clarity, Spec §FR-039]
- [ ] CHK174 Are requirements defined for observing the *evaluation* runs themselves, so a degraded figure can be investigated? [Gap, Coverage]

## Consistency

- [x] CHK175 Do the observability requirements conflict anywhere with the leakage requirements — could a compliant audit record itself constitute exposure to a reader of the logs? [Conflict, Spec §FR-036, §FR-015] [**Resolved by design**, spec §FR-013a, IC §8] — no — audit records carry identifiers, digests, counts and decisions only, and FR-013a bars passage and prompt content from audit-adjacent sinks by name, so a compliant record cannot itself be an exposure.
- [ ] CHK176 Is access to audit records themselves subject to authorization, and is that stated? [Gap, Security]

## Tunnel, Credentials and Run Provenance (added 2026-08-11)

- [x] CHK206 Is the masking requirement stated for every surface where exposure would grant access, with the tunnel URL named explicitly alongside credentials? [Completeness, Spec §FR-028i] [**Resolved by design**, RC §6] — the tunnel URL and token are masked wherever they appear; the URL is never sent to the browser and never written to an audit record.
- [ ] CHK207 Are requirements defined to keep the service token and tunnel URL out of committed files, not only out of logs? [Coverage, Spec §FR-028g]
- [x] CHK208 Is there a requirement that outbound generation payloads be capturable for audit without that capture itself storing passage content? [**Requirement resolved**, Spec §FR-037a, §FR-037b, §SC-021] — a test-only in-memory interceptor over synthetic fixtures that persists nothing, writes no passage text anywhere including failure messages, reports only field names/counts/pass-fail, and discards the request immediately; production telemetry never captures prompt or passage bodies.
- [x] CHK209 Does the run-provenance record in FR-028n include everything needed to declare a run valid or invalid for the gate? [Completeness, Spec §FR-028n, §FR-035c] [**Resolved by design**, data-model `evaluation_runs`] — the provenance columns — GPU model, runtime, revision, quantization, dependency versions, tunnel conditions — are exactly what the `validity` verdict is decided from.
- [x] CHK210 Are requirements defined for recording tunnel conditions without recording the tunnel address? [Ambiguity, Spec §FR-028i, §FR-028n] [**Resolved by design**, spec §FR-028o, RC §6, research R26] — seven named fields — provider profile, GPU series, ngrok region, protocol/TLS version, RTT p50/p95, health outcome — plus a **keyed HMAC endpoint fingerprint** for correlation; the hostname, full URL, ngrok token and service credential are never stored or displayed.
- [ ] CHK211 Is a failed or rotated service token required to be auditable as an event, distinct from an authorization denial? [Gap, Spec §FR-039]
