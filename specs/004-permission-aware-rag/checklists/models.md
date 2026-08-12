# Local Model Requirements Quality Checklist: Permission-Aware Knowledge Retrieval

**Purpose**: Validate that requirements for packaging, licensing, pinning, quantization,
offline execution, and weight delivery are complete and unambiguous
**Created**: 2026-08-11
**Feature**: [spec.md](../spec.md)

**Revised 2026-08-11.** The local-generation decision was superseded: embeddings stay
local, generation moved to a pinned quantized Qwen2.5 3B Instruct on a remote GPU behind a
provider interface. Items about local weight delivery for *generation* no longer apply as
written; the *embedder* items still do, and a new section covers the remote boundary.

**Licence questions are now answered from the authoritative model cards** (verified
2026-08-11) — CHK074–CHK076 are resolved with evidence rather than left open.

## Weight Delivery to a Clean Installation

- [x] CHK067 Does the spec state **how model weights reach a clean machine**? [Resolved, Spec §FR-011f] — the Colab session downloads weights during provisioning; nothing ships in this repository. The *embedder* still runs locally and its delivery remains open under CHK069.
- [x] CHK068 Is the distinction stated between *provisioning-time* and *request-time* network access? [Resolved, Spec §FR-011f] — the conflict is closed: provisioning may download; an inference request must not, and must not contact a third-party inference API.
- [ ] CHK069 Is the **local embedder's** weight delivery to a clean machine specified, and is the external host it comes from named and accepted as a provisioning dependency? [Gap, Dependency, Spec §FR-011, §FR-011f]
- [ ] CHK070 Are requirements defined for verifying weight integrity on arrival — a digest or signature — so a substituted model is detectable? [Gap, Security]
- [x] CHK071 Does the spec state what happens when weights are absent at startup: refuse to start, degrade, or fail on first question? [Gap, Exception Flow] [**Resolved by design**, IC §1, RC §6] — the ingestion CLI refuses to start without its payload indexes; the generation provider's `health()` fails closed before streaming.
- [ ] CHK072 Is the one-command startup promise reconciled with weight acquisition — does `make up` on a clean machine still satisfy it, and is that stated? [Consistency, Spec §Assumptions]
- [ ] CHK073 Are requirements defined for the **embedder's** size and memory impact on the local stack, as a stated figure? Generation no longer contributes, but BGE-M3 still runs inside a 7.61 GB Docker VM. [Measurability, Spec §Assumptions]

## Licensing

- [x] CHK074 Does the spec state the licence of each pinned model and whether it permits the intended use, including redistribution inside an image? [Resolved 2026-08-11, Spec §FR-011g] — BGE-M3 = **MIT**; Qwen2.5-3B-Instruct = **Qwen RESEARCH LICENSE AGREEMENT**, recorded with clause citations.
- [x] CHK075 Are requirements defined for recording model licence and attribution alongside the revision record? [Resolved, Spec §FR-011g, §FR-011b]
- [x] CHK076 Is there a requirement that a model whose licence forbids redistribution must be acquired rather than embedded, with the consequences for CHK067 stated? [Resolved, Spec §FR-011g] — weights download during Colab provisioning (FR-011f); nothing is redistributed from this repository.
- [ ] CHK177 Does the spec state that the **Qwen research-only restriction bounds the whole feature's permitted use**, not merely its licence metadata — that a commercial deployment needs a different model or a vendor licence? [Compliance, Spec §FR-011g, §FR-011h]
- [ ] CHK178 Is the alignment between the research-only licence and the synthetic-corpus limitation stated as a *reason*, so removing one does not silently invalidate the other? [Consistency, Spec §FR-011g, §FR-011h]
- [ ] CHK179 Are requirements defined for what happens if the pinned Qwen revision is withdrawn or its licence changes? [Gap, Dependency]

## Revision Pinning and Quantization

- [x] CHK077 Is "pinned" defined as an exact, immutable identifier rather than a tag that can move? [Clarity, Spec §FR-011, §FR-011a] [**Resolved by design**, IC §3] — the manifest records `embedding_model_revision` and `weight_checksum` — an exact identifier plus a content check, not a movable tag.
- [ ] CHK078 Does the spec state the quantization scheme as a pinned property, or only that quantization exists? [Clarity, Spec §FR-011a, §FR-011b]
- [x] CHK079 Are requirements defined for what a change of quantization means for the recorded evaluation figures — does it invalidate them as a model change would? [Gap, Consistency, Spec §FR-011b, §FR-034] [**Resolved by design**, spec §FR-035j, §FR-043b, IC §13, research R32] — a change of quantization is a change of an **evaluation-run manifest field**, so it starts a new series and resets the three-run count; earlier figures stay attributable to their own manifest rather than being silently carried forward.
- [x] CHK080 Is the recorded configuration set in FR-011b complete enough to reproduce a figure — does it include the runtime engine and its version, not only the model? [Completeness, Spec §FR-011b] [**Resolved by design**, IC §3] — the nine manifest fields include `quantization_runtime` alongside the model revision, so the runtime engine is part of the recorded configuration.
- [x] CHK081 Is "prompt version" defined as a versioned artefact with a stated change discipline, so a prompt edit is visible as a configuration change? [Ambiguity, Spec §FR-011b] [**Resolved by design**, spec §FR-011k, research R27] — the generation prompt is a **versioned repository artefact** distinct from the judge prompt, recorded per run as `generation_prompt_version` and `generation_prompt_hash`, and **any change resets the three-run gate** — so a prompt edit is visible as a configuration change.

## Determinism of Generation

- [x] CHK082 Is "deterministic settings wherever the runtime supports them" specified with a stated fallback when the runtime does *not* support them? [Ambiguity, Spec §FR-011a] [**Resolved by design**, spec §FR-011j, research R26] — a runtime that cannot enforce the required deterministic settings makes Phase 0 fail as **`UNSUPPORTED_CONFIGURATION`** — no silent fallback, no relaxed tolerance, no alternate model, no claim of deterministic success.
- [x] CHK083 Does the spec state which figures are expected to be exactly reproducible and which are statistical, so FR-034's repeatability claim is bounded to retrieval? [Consistency, Spec §FR-034, §FR-011a] [**Resolved by design**, spec §FR-034a, research R16] — every measure is classified deterministic or statistical and the class is recorded with the run; deterministic figures must reproduce **exactly** and a difference fails the run, while statistical ones are met only by three independently passing runs.
- [ ] CHK084 Are requirements defined for detecting non-determinism that *should not* be there — e.g. two identical evaluation runs disagreeing on retrieval? [Gap, Measurability]

## Offline Execution

- [ ] CHK085 Is the **CI** zero-network property specified as enforceable with a stated verification method, now that the global no-network claim has been narrowed to CI only? [Measurability, Spec §FR-035b, §SC-018]
- [ ] CHK086 Does SC-018 specify how the no-outbound-access CI environment is established, so the criterion is reproducible? [Measurability, Spec §SC-018]
- [x] CHK087 Are requirements defined for the resource floor a machine must meet to run **the embedder** locally alongside the existing stack? [Gap, Spec §FR-011c] [**Resolved by design**, spec §FR-035p, research R34] — the local BGE runtime is owned by **`packages/core`** — the package whose modules import it — and by the root development environment; the benchmark imports the canonical modules rather than declaring a duplicate dependency or a second implementation.
- [x] CHK088 Is the interaction between model execution and the shared CI runner stated? [Resolved, Spec §FR-035b] — CI runs neither model; it uses committed fixtures and a stubbed generator, so the runner's limits no longer bind.

## Consistency With the Rest of the Spec

- [ ] CHK089 Do the model requirements conflict with the existing determinism guarantees of the dataset, or is the boundary between "dataset determinism" and "generation determinism" stated? [Consistency, Spec §FR-042]
- [x] CHK090 Is the generation model's context limit stated as a constraint on retrieval breadth? [**Requirement resolved**, Spec §FR-028b1, §SC-026] — three simultaneous bounds measured by the pinned generation tokenizer: ≤ 5 passages, ≤ 400 tokens per passage, ≤ 2,000 tokens total.

## Remote Generation Profile (added 2026-08-11)

- [ ] CHK180 Is the provider interface specified by the operations it must support, so a replacement endpoint can be judged conformant? [Clarity, Spec §FR-011d]
- [ ] CHK181 Does the spec state that retrieval, authorization, and citation logic are unchanged by a provider swap, as a checkable property rather than an aspiration? [Measurability, Spec §FR-011d]
- [ ] CHK182 Is "development and evaluation profile, not production" stated everywhere the profile appears, including operator-facing documentation? [Consistency, Spec §FR-011e, §FR-011h]
- [ ] CHK183 Is the provisioning-time versus request-time distinction defined precisely enough that "an inference request must not trigger a download" is checkable? [Clarity, Spec §FR-011f]
- [ ] CHK184 Are requirements defined for pinning the *runtime* on the remote side, not only the model and quantization? [Completeness, Spec §FR-011a, §FR-028n]
- [ ] CHK185 Is the embedder's local-only requirement stated distinctly from the generator's remote arrangement, so the two cannot drift into one rule? [Consistency, Spec §FR-011c]
