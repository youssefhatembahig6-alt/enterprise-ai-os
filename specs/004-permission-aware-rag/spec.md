# Feature Specification: Permission-Aware Knowledge Retrieval and Grounded Answers

**Feature Branch**: `004-permission-aware-rag`

**Created**: 2026-08-11

**Status**: Draft

**Input**: User description: "Build Feature 004: an authorization-aware enterprise knowledge and RAG system. It must ingest approved documents, validate and track ingestion, chunk content deterministically, generate embeddings, index and retrieve through Qdrant, enforce tenant/classification/department/resource permissions before any content reaches retrieval or generation, produce grounded answers with precise source citations, support streaming chat, provide measurable retrieval and answer-quality evaluation, and expose safe observability without logging sensitive content. The existing API remains the only verifier of user session tokens; new workers or services must not independently trust browser JWTs. Agent capabilities are the final phase and must not begin until authorization-aware RAG is stable and verified. Reuse the existing architecture, synthetic datasets, Docker Compose environment, and constitutional security gates."

## Clarifications

### Session 2026-08-11

- ~~Q: Local, hosted, or split embedding and generation providers? → A: **B — local both.**~~ **Superseded** by the deployment decision below. The audit that followed found no discrete GPU on the reference machine, which made local generation of a 3B model too slow to meet any useful latency target.
- Q: Text-document corpus only, or text plus the deferred synthetic code corpus? → A: **A — text documents only.** The existing `documents` collection and the 105 seeded documents. The `code` collection stays empty, the synthetic code repository stays deferred, and binary formats are out of scope.
- Q: What measurable thresholds must be met before the agent phase may begin? → A: **B — pragmatic.** recall@5 ≥ 80%, grounding ≥ 90%, citation precision ≥ 90%, correct abstention ≥ 90%, p95 time to first visible content ≤ 2s, unauthorized leakage exactly zero. Zero leakage and authorization-before-search block every build, as do the deterministic retrieval and citation checks. All must pass **three consecutive** full evaluation runs before the agent phase begins. Latency is measured in a declared controlled environment and gates the agent phase rather than ordinary shared-runner CI. *(The single latency figure was later **superseded** by the two-measure model in the deployment decision below — local preview ≤ 2 s and first generated token ≤ 5 s — once generation moved off the machine. The other five thresholds stand unchanged.)*

### Session 2026-08-11 (deployment decision — supersedes the provider clarification above)

- Q: Where does generation run, given that the reference machine has no discrete GPU? → A: **Split, with a replaceable remote generator.** Embeddings stay local (pinned BGE-M3, 1024 dimensions). Generation runs a pinned quantized Qwen2.5 3B Instruct on a **Google Colab GPU reached over an HTTPS ngrok tunnel**, behind a provider interface so an approved self-hosted GPU endpoint can replace it without touching retrieval or authorization. This is a **development and evaluation profile, not a production enterprise deployment**.
- Q: What may cross the boundary to the remote generator? → A: **Only the minimum authorized passages needed to answer the current question.** Never browser session tokens, signing keys, refresh tokens, access-context objects, ACL records, excluded-source counts, or any chunk the asker may not read. Authorization-constrained search and citation re-authorization happen locally, before and after generation. The remote generator composes prose; it never retrieves and never decides access. The browser never contacts the tunnel.
- Q: How are the tunnel and its credentials handled? → A: `NGROK_AUTHTOKEN` stays only in Colab Secrets. A separate short-lived `GENERATION_SERVICE_TOKEN` authenticates the local API to the generator, lives only in ignored environment configuration, is rotated whenever the Colab session is recreated, and is never committed or logged. Every request is HTTPS with an `Authorization` header. The tunnel URL is masked wherever exposure would grant access. On tunnel failure or authentication failure the system **fails closed** — never a silent fallback to another provider.
- Q: What are the latency targets, given the split? → A: **Two measures.** Local retrieval-ready source preview **p95 ≤ 2 s**; first generated answer token through the tunnel **p95 ≤ 5 s**. Cold-start and model-download time are measured separately and are not warm inference latency.
- Q: What is the declared evaluation baseline? → A: NVIDIA **T4, 16 GiB VRAM**, pinned quantization and runtime, warm weights, the full 105-document corpus, concurrency 1, 5 warm-up requests, ≥ 30 measured requests, nearest-rank p95. A run on CPU-only Colab or an unidentified GPU is **invalid** for the three-run gate. *("Minimum" was **refined** by the gap-closure session below: T4 is the latency **reference class**, not a floor — a faster GPU carries quality evidence but no latency evidence, per FR-043a.)*
- Q: What may this profile process? → A: **This project's synthetic corpus only.** Real enterprise or personal data requires an approved private or self-hosted generation endpoint and MUST NOT be sent through the Colab profile.

- Q: Are the two latency figures demonstrated, or targets? → A: **Acceptance thresholds, not claims.** Neither has been measured. A **Phase 0 feasibility benchmark** must run before implementation proceeds beyond the affected subsystem: pinned BGE-M3 on the declared local CPU environment, pinned quantized Qwen2.5 3B Instruct on a **verified** Colab T4, the expected production prompt size with five retrieved passages, 5 warm-ups, ≥ 30 measured requests, nearest-rank p95. Failure blocks that subsystem, is recorded with the raw timing summary, and may not be silently relaxed — changing the model, prompt budget, hardware baseline, or threshold requires an explicit specification clarification and checklist revalidation.
- Q: How is the outbound generation payload inspected without becoming a leak itself? → A: A **test-only, in-memory transport interceptor** that sees only synthetic fixture passages, inspects the serialized request before transmission, asserts the absence of every forbidden item, persists nothing, writes no passage text to logs, artifacts, snapshots, or failure messages, reports only field names, counts, and pass/fail, and discards the captured request immediately. **Production telemetry never captures prompt or passage bodies.**
- Q: What keeps committed retrieval fixtures consistent with the real embedder? → A: A **fixture manifest** recording embedding model ID and exact revision, weight checksum, vector dimension, quantization/runtime identity, chunker version and configuration hash, source-document IDs and content hashes, fixture-generation command version, generation timestamp, and the resulting fixture checksum. Ordinary CI **fails** if the manifest disagrees with the configured embedder, the Qdrant dimension, the chunker identity, or the source hashes. Regeneration runs only in the controlled environment with the real pinned model, only by explicit command, produces a reviewable diff, and is accepted only after the full retrieval evaluation passes.

- Q: What is the document size limit, and what happens at it? → A: **2 MiB of extracted, normalized UTF-8 text** per document. A document over the limit is **rejected atomically before chunking** — no chunks, no embeddings, no Qdrant points are written — and the **previous successful index for that document is preserved** until a replacement ingestion succeeds.
- Q: What do null `country` and `department_id` mean for retrieval? → A: **Null never disables filtering and never matches everything.** A null document attribute means **company-wide**. A caller *with* a value reaches documents matching that value **or** company-wide documents. A caller *without* a value reaches **only** company-wide documents, unless an independent owner, role, or explicit ACL grant authorizes the document. Company and classification restrictions always apply. Every Qdrant payload index the filter uses — **including `allowed_roles`** — must exist and be tested.
- Q: How much retrieved text may reach generation? → A: **At most 5 passages**, at most **400 tokens per passage** measured by the *pinned generation tokenizer*, at most **2,000 retrieved-passage tokens in total**. Trimming happens **only at the nearest preceding sentence boundary**. The **exact excerpt span sent to generation is preserved and is what the citation resolves to** — a citation may not point at a wider passage than the model was given.

### Session 2026-08-11 (final gap closure)

- Q: Which evaluation figures must reproduce exactly, and which are statistical? → A: **Two classes, declared per measure.** *Deterministic*: retrieval over the committed fixtures, authorization outcomes, citation resolution, and the leakage check — these MUST reproduce **exactly** for a pinned configuration, and a difference between two identical runs is a **failure**, not variance. *Statistical*: grounding, citation precision, correct abstention, and both latency figures — full-model measures that legitimately move between runs. A statistical run uses the **same pinned configuration and the same evaluation manifest**, records **every per-question outcome**, and reports **numerator, denominator and aggregate percentage**. Its threshold is satisfied only by **three consecutive runs each independently meeting it**; variation is permitted only inside that constraint.
- Q: Which corpus does each lane evaluate, and what stops a vacuous run? → A: The **controlled full-model evaluation uses the complete 105-document seeded corpus**. **Ordinary continuous integration uses only the committed deterministic fixture subset and MUST NOT claim or imply a full-corpus quality figure.** The evaluation manifest declares **every question partition with its exact expected count**, and the evaluator **exits nonzero before computing any metric** when the total question count is zero, a required partition is empty, actual counts differ from the manifest, a required metric would have a **zero denominator**, or an expected source document is **absent from the 105-document corpus**. Every evaluation output records the **corpus fingerprint, document count, partition counts and manifest checksum**.
- Q: What exactly is a "document consulted"? → A: A **five-term vocabulary**, used consistently and never interchanged. *Candidate*: an authorized vector-store point eligible before ranking. *Retrieved passage*: a ranked chunk returned by retrieval. *Generation passage*: an authorized, budgeted excerpt actually serialized to the generator. *Cited passage*: a generation passage referenced by the completed answer. ***Documents consulted***: the number of **distinct `document_id` values among generation passages**. User-visible source information may report retrieved, consulted and cited documents; it may **never** report unauthorized candidates or authorization-exclusion counts, which stay operator-only.
- Q: What is the generator health check's deadline and failure taxonomy? → A: **2 seconds**, performed by the **local API** before the answer stream opens. **Timeout, DNS failure, TLS failure, authentication refusal, malformed response, and unhealthy status all mean unavailable** — there is no partially-available state. When unavailable: **no question or passage body is sent**, **no generator stream opens**, **no tunnel detail is exposed**, and the designed generation-temporarily-unavailable state is returned. The check MAY run **concurrently with local retrieval**, but generation MUST NOT begin until **both** the health check and the authorization-constrained retrieval have succeeded.
- Q: Does a faster-than-T4 allocation satisfy the latency baseline? → A: **No.** NVIDIA T4 16 GiB is the **latency reference class**, not a floor. The three-run gate requires the same **GPU class, model revision, quantization, runtime, prompt budget and concurrency**. A faster-GPU run is **valid evidence for quality** — grounding, citation precision, abstention, leakage — but **cannot establish compliance with the T4 latency baseline**; it forms a **separate named series** and MUST NOT be mixed with T4 runs. CPU-only or unidentified-GPU runs remain **invalid** for latency and for the gate.

### Session 2026-08-11 (implementation constants)

- Q: What are the chunk size and overlap? → A: **400 BGE-M3 tokenizer tokens maximum per chunk, 50 tokens target overlap.** Split on document structure and sentence boundaries first; **never split a sentence** unless one sentence alone exceeds 400 tokens, in which case split deterministically at the nearest preceding clause or whitespace boundary. Overlap consists of **complete trailing sentences where possible** and may never exceed 50 tokens. **Empty or whitespace-only chunks are forbidden.** A chunk identifier is derived from document identity, normalized-content hash, ordinal, **tokenizer identity**, the 400-token limit, the 50-token overlap, and the chunker version. Generation **re-counts** passages with the pinned **Qwen** tokenizer and applies its own separate 400-per-passage / 2,000-total budget — the two budgets are independent and both hold.
- Q: What adjudicates grounding and citation precision? → A: The **same pinned quantized Qwen2.5 3B Instruct model, invoked separately as a judge** — never the generation response judging itself. The prompt is a versioned repository artifact at `specs/004-permission-aware-rag/evaluation/grounding-judge-v1.md`, run at **temperature 0** with deterministic settings where supported. Judge input contains **only** the synthetic question, the completed answer, the citation references, and the **exact cited spans** — never unauthorized passages, ACL data, excluded counts, credentials, or tokens. Output conforms to a **strict JSON schema** with per-claim grounded/not-grounded and per-citation supports/does-not-support decisions plus short **enumerated reason codes**. Every evaluation run records the model revision, quantization, runtime, **judge-prompt hash** and **response-schema version**. Before the judge may score the release gate it MUST be validated against a **committed, manually labelled calibration set of at least 20 positive and negative examples**, reaching **≥ 90% agreement**; below that, grounding and citation precision are **INVALID** and cannot be reported as passed. A model MUST NEVER judge its own raw hidden reasoning — only the final answer and its cited evidence. **Deterministic structural checks run alongside the judge**: every substantive claim carries a citation, every citation resolves, and every cited span equals the passage sent to generation.
- Q: What supplies `data_version` for the cache key? → A: A **company-scoped active corpus manifest checksum** — not the dataset fingerprint, not the ingestion run id, not a manually incremented counter. It is derived deterministically from the company id and collection, the active document ids and normalized-content hashes, the chunk ids and chunk-content hashes, the chunker version and configuration hash, the embedding model identity/revision/checksum, the vector dimension, and the **authorization-relevant payload schema version**. The new checksum is published **atomically, only after the complete replacement index succeeds**; a failed or cancelled ingestion leaves the previous checksum active; an idempotent no-op ingestion produces the **same** checksum; any change to content, chunking, embedding identity, or the authorization payload produces a **different** one. Cache entries keyed on an older checksum become **unreachable without destructive deletion**. The active checksum is maintained in a dedicated **company/collection corpus-version record** with migration and rollback coverage.

### Session 2026-08-11 (residual ambiguities closed)

- Q: What does "even transiently" in FR-013 permit and forbid? → A: Passage and prompt content — **and any derived form of it**: summaries, snippets, highlighted fragments — may exist **only in request-scoped memory**, from authorized retrieval until the terminal SSE event or abort cleanup completes, and MUST be released then. It may **never** enter persistent storage, caches, logs, traces, metrics, snapshots, test artifacts, exception messages, or retry queues. The **index itself is exempt** — it is the authorized source the content is retrieved *from*; the prohibition governs everything downstream of retrieval. FR-018's permission-scoped cache therefore holds **references and derived results, never passage or prompt bodies**.
- Q: How is "no difference in latency-shaped behaviour" made measurable? → A: A permission-narrowed empty result and a genuinely empty authorized result MUST have **identical HTTP status, identical SSE event types and ordering, identical user-visible wording, identical retry behaviour, and no excluded-count or withheld-source signal**. **Ordinary CI** verifies identical **control flow** against deterministic fixtures. A **controlled security evaluation** uses **≥ 50 warm samples per case** and requires the **p95 time-to-terminal difference not to exceed the greater of 100 ms or 20%**. The timing measure gates **stabilization**, not shared-runner CI.
- Q: What makes a document body "readable"? → A: A normalized text document is readable only when it has **≥ 20 non-whitespace Unicode characters**, **≥ 1 Unicode letter or digit**, and is **valid UTF-8 after extraction and normalization**. Anything else fails **atomically as `EMPTY_BODY` before chunking**.
- Q: What does "invalidate the index" mean as an outcome? → A: A change to the embedding **model revision, weight checksum, vector dimension, tokenizer, or runtime identity** requires a **complete replacement index**. **Mixed embedding identities MUST NEVER be active.** The previous index and its corpus checksum stay active until the replacement is **fully built and atomically published**; a failure leaves the previous version **untouched**.
- Q: What if the pinned runtime cannot enforce deterministic settings? → A: **Phase 0 fails as `UNSUPPORTED_CONFIGURATION`.** There is **no** silent fallback, **no** relaxed comparison, **no** alternate model, and **no** claim of deterministic success.
- Q: How are tunnel conditions recorded without recording the tunnel address? → A: Record the **provider profile, Colab GPU series, ngrok region, protocol and TLS version, measured network RTT p50/p95, health-check outcome**, and a **keyed HMAC fingerprint of the endpoint** for run correlation. **Never** store or display the tunnel hostname, the full URL, the ngrok token, or the service credential.
- Q: Is the generation prompt a versioned artefact? → A: **Yes, and distinct from the grounding-judge prompt.** Every evaluation run records `generation_prompt_version` and `generation_prompt_hash`. **Any prompt change starts a new GPU/configuration series and resets the three-run gate**, exactly as a quantization or runtime change does.
- Q: Which lane do the deterministic structural checks gate? → A: **Both, and ordinary CI first.** Every substantive claim cited, every citation resolvable, and every cited span equal to the passage sent MUST **block ordinary CI** using deterministic fixtures. The controlled full-model evaluation repeats them, but is **not** their only gate.
- Q: What stops the Colab profile receiving non-synthetic data? → A: The outbound path MAY send passages **only when the active corpus manifest identifies the approved synthetic seed corpus and its recorded fingerprint**. Any **unknown, modified, user-supplied, or non-synthetic** corpus **fails closed before the outbound request is built**. Real data requires an approved private or self-hosted provider.

### Session 2026-08-11 (final two ambiguities closed)

- Q: What does "stoppable" stop — the display, the generation, or the underlying work? → A: **End-to-end cancellation, never merely hiding output.** Content emission stops immediately; cancellation **propagates through the local API to the Colab generation request** and stops token generation; the SSE stream closes with the existing terminal `stopped` state and the answer is marked incomplete; **all** request-scoped question, prompt, passage and partial-generation content is released during abort cleanup (FR-013a); and **no** retry, queued continuation, or background generation may follow. The local API MUST close the stream and complete local cleanup **within 2 seconds** of receiving the stop request. If **upstream** cancellation cannot be confirmed within that deadline, the provider connection is **severed**, a content-free **`provider_cancel_unconfirmed`** status is recorded, and **all later provider output is discarded**. A test MUST prove that stopping only the display while generation continues is a **failure**.
- Q: What is the boundary of "per request" in FR-016? → A: **One logical user question — one turn.** Every incoming authenticated chat turn receives a **newly built access-context snapshot** from the local API. The snapshot may be reused **only** by internal retrieval and generation operations belonging to **that same turn**; a retry may preserve it **only while the original turn is still active**. Follow-up turns, regenerated answers, and resumed conversations MUST build a **new** access context, and conversation history MUST be **re-authorized under the new turn's context** before any reuse. **No worker or provider may create, validate, widen, or reuse an access context across turns.** Citation authorization immediately before emission or persistence remains independently required (FR-022), and cache access stays scoped to the current permission fingerprint and data version (FR-018, FR-018a).

### Session 2026-08-11 (client disconnect)

- Q: Is navigating away mid-stream the same as pressing stop? → A: **An implicit cancellation, but not an explicit user stop.** An unexpected client disconnect — navigation, tab close, browser crash, network loss — MUST cause the local API to detect the disconnected stream, **cancel the upstream provider request, stop generation, reject all later provider output, and release all request-scoped content**, under the **same 2-second local cleanup deadline and the same `provider_cancel_unconfirmed` handling** as FR-025a. The turn is persisted as **`INCOMPLETE` with reason `CLIENT_DISCONNECT`** — **never** `stopped`, because the person did not ask to stop. **No retry, continuation, resumable stream, or background work** is permitted. Because the connection is gone, **no terminal SSE event is required**; the **server-side state and the content-free audit record are authoritative**. The audit record may carry turn id, timestamps, status, duration and cancellation-confirmation status, and **no** question, prompt, passage, partial answer, token, URL, or credential content. Ordinary CI MUST include a stub-provider test that disconnects the client mid-stream and proves upstream cancellation, cleanup within 2 seconds, the incomplete state, the absence of any continuation, and content-free logs — **and a falsifying case in which the UI disconnects but generation continues, which MUST fail**.

### Session 2026-08-11 (evaluation-run manifest)

- Q: Where is a run's full configuration recorded, given that neither existing manifest carries it? → A: **A third, distinct manifest.** The **embedding fixture manifest** (FR-035g) and the **question partition manifest** (FR-031a) keep their existing scopes and gain nothing. Every controlled evaluation run MUST additionally produce **`tests/evaluation/results/run-manifest.json`** *(path superseded by the run-directory decision below: `tests/evaluation/results/<run_id>/run-manifest.json`)*, carrying at minimum: the **generation prompt version and SHA-256 hash**; the **generation model identifier and pinned revision**; the **generation quantization and runtime identity**; the **judge prompt version/hash and judge model identity**; the **embedding model identifier/revision/checksum**; the **corpus fingerprint and active `data_version`**; the **chunker configuration hash**; the **question-manifest checksum**; the **provider profile and GPU series**; and the **evaluation command version and timestamp**. It is **immutable evidence for that run** and MUST be referenced by the run's results record. A run is **`INVALID_CONFIGURATION`** when any required field is missing or disagrees with the configured runtime. The **three-consecutive-run gate requires identical manifest fields across all three runs, except timestamp and run identifier**, and a change to the **generation prompt version or hash starts a new evaluation series and resets the count**. **Ordinary CI validates the manifest schema and the mismatch behaviour against fixtures**, contacting neither Colab nor ngrok and running neither model.

### Session 2026-08-11 (three-run execution semantics)

- Q: Must the three runs be on distinct occasions, or may they be three repetitions in one job? → A: **Three isolated controlled-evaluation executions — never three iterations inside one evaluation process.** Each execution MUST: start only **after the preceding execution reaches a terminal result**; run the **complete preflight again**; receive a **unique run identifier and timestamp**; produce **its own immutable `run-manifest.json`, raw results, and results record**; compute **every metric from its own samples**, reusing no measurement or outcome from another run; and start a **fresh evaluation process with empty request and result caches**. The three MAY occur **on the same day** and MAY use the **same verified Colab T4 allocation and tunnel session**, provided the required configuration-manifest fields remain identical (FR-043b). **One orchestration command MAY launch the sequence**, but it MUST create **three isolated child executions** satisfying every rule above — **a loop inside one process does not count**. Any **failed, invalid, cancelled, or configuration-mismatched** execution **breaks** the consecutive sequence, and the next valid execution becomes **run one of a new sequence**. Ordinary CI MUST test this gate using **fixture manifests and results only**, contacting neither Colab nor ngrok and loading no model.

### Session 2026-08-11 (Phase 0 provisioning, run directories, phase scope)

- Q: The first-token benchmark measures a generation server that the phase it gates would create — where does that server come from? → A: **Phase 0 provisioning, not Phase 4 creation.** The generation-server artefact `infrastructure/colab/generation_server.ipynb` belongs to **Phase 0**. Before any first-token sample is taken, Phase 0 MUST provision or verify: the **pinned Qwen model weights** (with revision and checksum verification, as provisioning-time work); an **authenticated HTTPS ngrok endpoint**; the **service token**; a **verified T4**; the **runtime and quantization identity**; a working **health endpoint**; and **streaming first-token protocol compatibility**. **Phase 4 reuses this artefact and its server contract** rather than creating either again. If weights, endpoint, credentials, a verified T4, or protocol compatibility are missing, the first-token row stays **`NOT RUN`** or is recorded **`INVALID`** — it can **never** pass.
- Q: Where does an evaluation run's manifest live, now that three runs must be isolated? → A: **One directory per run.** Each controlled execution owns **`tests/evaluation/results/<run_id>/`**, containing its own immutable **`run-manifest.json`**, its own **raw-results file**, and its own **results record**. The single fixed path is replaced. Three consecutive runs therefore reference **three distinct manifest paths and three distinct checksums**. Ordinary-CI fixtures live in a **separate committed fixtures directory**, never under `results/`.
- Q: How much may Phase 0 implement? → A: **Only the canonical chunker and embedder libraries the feasibility measurement needs.** Phase 0 does **not** permit ingestion, production indexing, retrieval APIs, or generation integration before their own gates. The local **BGE runtime dependency belongs to the package that imports it — `packages/core` — and to the root development environment**, never to an inert standalone benchmark manifest. **Duplicate benchmark-only implementations of chunking or embedding are prohibited**; the benchmark imports the canonical modules.
- Q: Where does Phase 0 sit in the execution order? → A: **After stack, weight and endpoint provisioning; before production ingestion.** **`eaios-seed index` is NOT a prerequisite of the preview benchmark** — Phase 2 is gated *by* that benchmark, so requiring its output would be circular. The preview benchmark builds its own temporary index instead (FR-035a).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ask a question and get an answer you can check (Priority: P1)

A signed-in employee opens the portal, types a question about company policy in their own
words, and receives an answer assembled from the company's own documents. Every claim in
the answer carries a citation naming the document it came from, and each citation opens
the passage it was drawn from. If the corpus cannot answer the question, the assistant
says so rather than composing something plausible.

**Why this priority**: This is the feature. Everything else exists to make this answer
trustworthy. It is also the smallest slice that delivers standalone value — a person with
a question gets an answer they can verify, which is more than the portal does today.

**Independent Test**: Sign in as a seeded employee, ask a question whose answer exists in
a document that employee may read, and confirm the answer names that document, that the
cited passage contains the claim, and that a question with no supporting document produces
an explicit "not found in your documents" rather than an invented answer.

**Acceptance Scenarios**:

1. **Given** a signed-in employee and an indexed corpus, **When** they ask a question
   answerable from a policy document they are permitted to read, **Then** the answer
   states the policy, cites that document by title, and the cited passage contains the
   statement the answer makes.
2. **Given** the same employee, **When** they ask a question that no document in their
   permitted set can answer, **Then** the assistant says the answer is not present in the
   documents available to them, cites nothing, and invents nothing.
3. **Given** an answer with citations, **When** the employee opens a citation, **Then**
   they see the passage that supports the claim and the document it belongs to.

---

### User Story 2 - Two people, one question, different answers (Priority: P1)

Two employees of the same company ask the identical question. One holds a permission and a
department attribute that reach a confidential document; the other does not. The first
receives an answer drawn from that document. The second receives an answer drawn only from
what they may read — and nothing in their answer, its citations, or its wording reveals
that a document they cannot read exists.

**Why this priority**: Equal to US1, because an answer that is not permission-aware is
worse than no answer at all. This is the scenario the whole system is built to
demonstrate, and it is the one a defence panel will ask about.

**Independent Test**: Ask the same question as two seeded personas with different
permissions and compare the two responses; assert the restricted content appears in one
and appears nowhere — not in text, not in citations, not in counts or "some results were
withheld" hints — in the other.

**Acceptance Scenarios**:

1. **Given** a document readable only by the HR role, **When** an employee without that
   role asks a question whose best answer is in that document, **Then** their answer is
   built only from documents they may read and makes no reference to the excluded one.
2. **Given** the same question asked by a permitted colleague, **When** the answer is
   produced, **Then** it does cite the restricted document — proving the exclusion above
   was a permission decision and not an empty corpus.
3. **Given** an employee of the other company, **When** they ask a question whose answer
   exists only in the first company's documents, **Then** they receive the same
   "not present" response as for a question nobody can answer.

---

### User Story 3 - Bring the corpus in, and know what happened to it (Priority: P2)

An operator runs ingestion over the seeded document corpus. Each document is validated,
chunked, embedded, and indexed, and the operator can see, per document, whether it was
ingested, skipped, or refused and why. Running ingestion a second time changes nothing:
the same corpus produces the same chunks, the same identifiers, and no duplicates.

**Why this priority**: US1 and US2 cannot be demonstrated without a corpus, but ingestion
delivers no user-facing value on its own — its value is that the answers above can be
trusted and reproduced.

**Independent Test**: Run ingestion from an empty index, record the per-document outcomes
and the resulting chunk count, run it again, and confirm the index is byte-for-byte
equivalent and no document was processed twice.

**Acceptance Scenarios**:

1. **Given** an empty vector index and a seeded corpus, **When** ingestion runs, **Then**
   every eligible document reaches a terminal state of ingested or refused-with-a-reason,
   and no document is left in an indeterminate state.
2. **Given** a completed ingestion, **When** ingestion runs again unchanged, **Then** no
   new chunks are created, no existing chunk changes, and the run reports the corpus as
   already current.
3. **Given** a document that cannot be processed, **When** ingestion reaches it, **Then**
   that document is recorded as refused with a stated reason and the run continues.

---

### User Story 4 - The answer arrives as it is written (Priority: P3)

An employee asks a question and sees the answer appear progressively rather than waiting
for a blank screen. They can stop a response in progress. Citations are attached to the
answer they belong to, and a response that is stopped part-way is clearly marked as
incomplete rather than presented as a finished answer.

**Why this priority**: A correct answer delivered after a long silence reads as a broken
system. Valuable, but the answer being right and permitted matters more than how it
arrives.

**Independent Test**: Ask a question and observe partial content rendering before
completion, stop a response mid-stream, and confirm the interface marks it stopped and
does not present the fragment as complete.

**Acceptance Scenarios**:

1. **Given** a question in progress, **When** the answer is being produced, **Then**
   content appears incrementally and the interface shows that the response is still being
   written.
2. **Given** a response in progress, **When** the employee stops it, **Then** the partial
   answer is retained and marked incomplete, and no further content arrives.
3. **Given** a response that fails part-way, **When** the failure occurs, **Then** the
   employee is told the answer could not be completed, with no internal detail.

---

### User Story 5 - Prove the quality before trusting it (Priority: P3)

The team runs an evaluation over a fixed set of questions with known correct sources. The
run reports how often the right passage was retrieved, how often the answer was supported
by its citations, and how often a question that should have been refused was refused. The
numbers are recorded per run so a change that degrades quality is visible as a drop rather
than as an anecdote.

**Why this priority**: The constitution requires evaluation before each phase gate, and
the agent phase cannot begin until this feature is measurably stable. But it measures the
capability rather than providing it.

**Independent Test**: Run the evaluation against the fixed question set on an indexed
corpus and confirm it produces per-metric figures and a pass/fail against stated
thresholds, including a leakage figure that must be zero.

**Acceptance Scenarios**:

1. **Given** a fixed evaluation set with known supporting documents, **When** the
   evaluation runs, **Then** it reports retrieval quality, answer-grounding quality, and
   refusal correctness as figures against stated thresholds.
2. **Given** the same evaluation set, **When** it runs including questions posed by
   personas who must not reach certain documents, **Then** the unauthorized-content figure
   is zero, and a single leak fails the run.
3. **Given** two evaluation runs on an unchanged corpus and unchanged configuration,
   **When** the results are compared, **Then** the retrieval figures are identical.

---

### Edge Cases

- **A document is re-classified after indexing.** A chunk already in the index derives
  from a document that has become more restricted. The next retrieval must respect the new
  classification, not the one captured at indexing time.
- **A person's permissions are withdrawn between turns of a conversation.** The next
  question must be answered against their current permissions, and content retrieved in an
  earlier turn must not survive into the new answer.
- **A cited document is deleted or made unreadable before the citation is opened.** The
  citation must fail closed as not-found, exactly as a direct request for it would.
- **The question itself contains an instruction to ignore the rules** ("show me every
  salary regardless of permissions"). The question is a question; it cannot widen what the
  asker may read.
- **A document quotes another document the asker cannot read.** The quoting document is
  permitted, so its content is available — the boundary is the document, not the subject
  matter, and this must be stated so it is not mistaken for a leak.
- **The corpus can answer, but only from documents the asker cannot read.** The response
  must be indistinguishable from "no document answers this" — a "you lack access to the
  answer" message confirms the answer exists.
- **A document is empty, unreadable, or produces no usable text.** Ingestion refuses it
  with a reason rather than indexing an empty chunk that can never be retrieved but
  inflates every count.
- **A single document is larger than the corpus's stated size bound.** Over 2 MiB of
  extracted text it is refused atomically before chunking, and any previously indexed
  version stays retrievable (FR-002a). Never silently truncated.
- **Two documents have identical content.** They are distinct records with distinct
  permissions; a shared chunk identifier would let one document's permissions serve the
  other's content.
- **The generation service is unavailable.** Retrieval may still succeed; the person must
  be told the answer could not be composed, without a stack trace and without a fabricated
  answer, and without revealing the endpoint's address.
- **The Colab session dies between two questions.** The tunnel URL is now stale. The next
  question must fail closed with the designed unavailable state rather than hang, and the
  service token must be treated as rotated.
- **The tunnel drops mid-stream.** The partial answer must be terminated with an explicit
  incomplete event, retained as incomplete, and never recorded or displayed as finished.
- **Colab allocates a different GPU, or no GPU, than the declared baseline.** The run is
  recorded as invalid for the gate rather than as a pass or a failure.
- **The generation endpoint returns content that cites a passage it was never sent.** The
  local citation re-authorization must drop it, because the generator has no authority to
  introduce a source.
- **A question in one language against documents in another.** Out of scope for this
  feature and stated so, rather than failing in an unexplained way.
- **The vector store returns a chunk whose source document no longer exists.** The chunk
  is dropped rather than cited to a document that cannot be opened.
- **The evaluation set loads, but a partition is empty.** The evaluator fails before
  computing anything. A 100% abstention figure over zero unanswerable questions is not a
  result, and reporting it as one is worse than reporting nothing (FR-035i).
- **The generator health check hangs rather than refusing.** The 2-second deadline expires
  and the outcome is *unavailable*, identical to an explicit refusal. A check with no
  deadline is not a check — it is the stall it was meant to prevent (FR-028k).
- **Colab allocates a GPU faster than the declared T4.** The run is valid for the quality
  measures and invalid for the latency ones, recorded in a separate named series rather
  than blended into the T4 sequence (FR-043a).
- **A single sentence is longer than the whole chunk budget.** It is split at the nearest
  preceding clause or whitespace boundary, deterministically, rather than mid-word or by
  character count (FR-007a). This is the only case in which a sentence is ever split.
- **Structural splitting yields nothing.** An empty or whitespace-only chunk is forbidden;
  the document is refused as `EMPTY_BODY` rather than indexed as a chunk that can never be
  retrieved but inflates every count (FR-007a, FR-002).
- **The judge disagrees with its calibration set.** Below 90% agreement, grounding and
  citation precision are recorded **INVALID** — neither a pass nor a failure — and the
  release gate cannot be satisfied on that run (FR-032b).
- **Ingestion is cancelled after some chunks are written.** No new corpus-version checksum
  is published, so the **previous** checksum stays active and every cache entry keyed on it
  stays valid. A partially built index is never the active one (FR-018a).
- **An embedding revision changes but the corpus does not.** The checksum changes because
  embedding identity is one of its inputs, so no cache entry survives across vector spaces
  and no index can be partially re-embedded while active (FR-018a, FR-011, FR-011i).
- **A document contains only punctuation, or eighteen characters.** It fails the readable-body
  floor and is refused `EMPTY_BODY` before chunking — a body that is technically non-empty
  but carries no retrievable meaning inflates counts without ever answering anything
  (FR-002b).
- **A request is aborted mid-stream.** Abort cleanup releases the passage and prompt content
  exactly as the terminal event would. An aborted request is the path most likely to leave
  content resident, which is why it is named rather than left to the happy path (FR-013a).
- **The runtime silently ignores a deterministic setting.** Phase 0 fails as
  `UNSUPPORTED_CONFIGURATION` rather than proceeding with a comparison that cannot mean what
  it claims (FR-011j).
- **The seeded corpus is edited before a Colab run.** The active corpus manifest no longer
  matches the approved synthetic fingerprint, and the outbound request **is never built**
  (FR-011l). Failing closed here is the difference between a policy and a control.
- **The generation prompt is edited between two passing runs.** The three-run sequence resets
  and a new series begins, because the runs would otherwise be attributed to a configuration
  that no longer exists (FR-011k).
- **A stop arrives after the last token but before the terminal event.** The turn still
  terminates as `stopped`, because the person's intent was to stop and the record must reflect
  what they did, not how close the answer happened to be (FR-025a).
- **The provider never confirms cancellation.** After 2 seconds the connection is severed, a
  content-free `provider_cancel_unconfirmed` status is recorded, and every later byte from the
  provider is discarded unread. An unconfirmed cancellation is a known state, not a hang
  (FR-025a).
- **A conversation is resumed days later.** A **new** access context is built for the new turn,
  and every earlier turn's content is re-authorized under it before any reuse. A snapshot that
  outlives its turn is the leak FR-012a exists to prevent (FR-012a, FR-026).
- **A person asks a follow-up after losing a permission.** The follow-up builds its own
  context, so the withdrawal takes effect on that turn — and the earlier turn's content cannot
  be reused to answer it (FR-012a, FR-016).
- **A person navigates away, closes the tab, or loses the network mid-stream.** The local API
  detects the dead stream and cancels upstream exactly as an explicit stop does, but the turn
  is recorded **`INCOMPLETE` with reason `CLIENT_DISCONNECT`** rather than `stopped` — the
  record must not claim an intent the person never expressed (FR-025b).
- **A stream ends without a terminal `done` event.** That is a **defect** for a live
  connection and the **expected** outcome for a disconnected one. The two are distinguished by
  whether the client was still connected, not by the absence of the event (FR-025b).
- **The Colab server is not provisioned when the benchmark runs.** The first-token row stays
  `NOT RUN`, or the attempt is recorded `INVALID` — never a pass. Phase 0 provisions the server
  it measures; it does not borrow one from the phase it gates (FR-035o).
- **Two runs write to the same results path.** Rejected. Each run owns
  `tests/evaluation/results/<run_id>/`, and a shared path would make three isolated executions
  indistinguishable from one execution writing three times (FR-035j, FR-043c).
- **A run manifest is missing one field.** The run is `INVALID_CONFIGURATION` — neither a pass
  nor a failure. A figure whose configuration cannot be fully stated is not attributable, and
  an unattributable figure cannot advance a gate (FR-035k).
- **Only the generation prompt hash changes, and the series identity is kept.** Validation
  **fails**: the manifest comparison is over field values, not over the series label, so a
  relabelled series cannot smuggle a changed prompt into an existing sequence (FR-043b).
- **Two runs disagree on quantization but agree on everything else.** The sequence resets. The
  gate compares every manifest field except timestamp and run identifier, so no configuration
  difference is invisible to it (FR-043b).
- **Three result rows are produced by one evaluation process.** The gate **rejects** them.
  Three rows are not three runs; a loop inside one process shares caches, warmed weights and
  loaded state, which is exactly the variance the three-run gate exists to sample across
  (FR-043c).
- **A run reuses another run's samples or result artifacts.** Rejected. Every metric must be
  computed from that execution's own samples, or the second run is a copy of the first with a
  new identifier (FR-043c).
- **A failed or invalid run occurs between two passing runs.** The sequence **breaks**; the
  next valid execution is run one of a new sequence. "Consecutive" means consecutive, not
  "three passes among some attempts" (FR-043c).
- **Preflight is skipped on run two or three.** The sequence is invalid. The preflight is what
  proves the question set and corpus have not moved under the sequence, so skipping it makes
  the later runs unattributable (FR-035i, FR-043c).

## Requirements *(mandatory)*

### Functional Requirements

**Ingestion and provenance**

- **FR-001**: The system MUST ingest documents from the existing seeded corpus — the 105
  seeded text documents across both companies — and MUST ingest only documents that are
  recorded in the system of record. A file present in storage but absent from the document
  records MUST NOT be indexed.
- **FR-001a**: Scope is **text documents only**. Ingestion MUST target the existing
  `documents` collection. The `code` collection MUST remain empty, the synthetic code
  repository (feature 001 decision D4) remains deferred, and binary document formats
  (decision D3) are out of scope. A document whose stored bytes are not text MUST be
  refused with that reason under FR-002 rather than partially parsed.
- **FR-002**: Every ingested document MUST be validated before processing: it MUST have a
  readable body, a non-zero size, an owning company, a classification, and a content
  digest that matches the stored bytes. A document failing any check MUST be refused with
  a stated reason and MUST NOT be partially indexed.
- **FR-002a**: A document whose **extracted, normalized UTF-8 text exceeds 2 MiB** MUST be
  refused with `TOO_LARGE`. The refusal MUST be **atomic and occur before chunking**: no
  chunk, no embedding, and no vector-store point may be written for that document. The
  document's **previous successful index MUST be preserved** until a replacement ingestion
  succeeds — an oversize revision must not destroy the answerable version that preceded it.
  Truncation is prohibited; a silently shortened document is a document whose citations no
  longer mean what they say.
- **FR-002b**: A normalized text document has a **readable body** only when **all three**
  hold: **≥ 20 non-whitespace Unicode characters**; **≥ 1 Unicode letter or digit**; and
  **valid UTF-8 after extraction and normalization**. A document failing any of the three
  MUST be refused **atomically as `EMPTY_BODY`, before chunking** — no chunk, embedding, or
  point is written. The floor exists because a body of punctuation or whitespace is
  technically non-empty and permanently unanswerable, and counting it as ingested makes
  every corpus figure describe something that cannot be retrieved.
- **FR-003**: Every ingestion attempt MUST reach a terminal, recorded outcome per document
  — ingested, unchanged, or refused-with-reason. A document left in an in-progress state
  after a run MUST be reported as a failure of the run, because a silent partial index is
  indistinguishable from a complete one at query time.
- **FR-004**: Ingestion MUST be idempotent. Re-running it against an unchanged corpus MUST
  produce no new chunks, no changed chunks, and no duplicates, and MUST report the corpus
  as already current.
- **FR-005**: When a document's content changes, its previously indexed chunks MUST be
  replaced rather than supplemented, so no answer can cite a passage that no longer exists
  in the document.
- **FR-006**: Ingestion MUST record, per run, the number of documents seen, ingested,
  unchanged, and refused, and the reasons for refusals. These counts MUST be reconcilable
  against the document records.

**Chunking and embedding**

- **FR-007**: Chunking MUST be deterministic: the same document content MUST always
  produce the same chunk boundaries, the same chunk count, and the same chunk identifiers,
  on any machine and on any run. This follows the existing determinism guarantee and is
  what makes an evaluation figure comparable between runs.
- **FR-007a**: Chunking MUST use **400 BGE-M3 tokenizer tokens** as the maximum chunk size
  and **50 BGE-M3 tokenizer tokens** as the target overlap, with these rules:

  1. Split on **document structure first**, then **sentence boundaries**.
  2. **Never split a sentence**, unless one sentence alone exceeds 400 tokens.
  3. For such an oversized sentence, split **deterministically at the nearest preceding
     clause or whitespace boundary** — never mid-word, never by character count.
  4. Overlap consists of **complete trailing sentences where possible** and MUST NOT exceed
     50 tokens.
  5. **Empty or whitespace-only chunks are forbidden.**

  Both parameters are part of `ChunkerConfig` and therefore of `chunker_config_hash`, so
  changing either re-ingests the corpus rather than silently mixing chunk generations.
- **FR-007b**: A chunk identifier MUST be derived from: the **document identity**, the
  **normalized-content hash**, the **chunk ordinal**, the **tokenizer identity**, the
  **400-token limit**, the **50-token overlap**, and the **chunker version**. Including the
  tokenizer and the two bounds is what makes "same identifiers" in SC-007 mean *produced by
  the same procedure*, not merely *same text*.
- **FR-008**: Each chunk MUST carry enough of its source to be quotable: the text of the
  passage, its position within the document, and the identity of the document it came
  from. A citation that cannot show the supporting passage does not satisfy FR-018.
- **FR-009**: Chunk boundaries MUST respect document structure where the document has any,
  so a cited passage is a coherent unit rather than a fragment cut mid-sentence.
- **FR-010**: Each chunk MUST carry the authorization attributes of its source document —
  company, department, classification, country, owner, and document identity — as
  retrievable properties of the indexed record. These are what make FR-013 enforceable
  inside the search rather than after it.
- **FR-011**: Embeddings MUST be generated by a single pinned model — **BGE-M3, producing
  1024-dimension vectors**, matching the vector store's existing configuration — whose
  exact revision is recorded with the index. A change of model or revision MUST invalidate
  the index rather than silently mixing vector spaces, because similarity between two
  embedding models is meaningless.
- **FR-011a**: Answers MUST be generated by a single pinned model — **a quantized Qwen2.5
  3B Instruct** — served by a **remote GPU generation endpoint**. In the development and
  evaluation profile this is a Google Colab session exposed over an HTTPS tunnel.
  Generation MUST use deterministic settings wherever the runtime supports them.
- **FR-011d**: Generation MUST sit behind a **provider interface**. Replacing the Colab
  endpoint with an approved self-hosted GPU endpoint MUST require no change to ingestion,
  retrieval, authorization, or citation logic. The provider in use MUST be named in
  configuration, never inferred, and a second provider MUST NOT be reachable as a fallback
  (FR-028d).
- **FR-011e**: The Colab-over-tunnel arrangement is a **development and evaluation
  deployment profile, not a production enterprise deployment**, and the specification MUST
  say so wherever the profile is described. Production deployment requires an approved
  private or self-hosted endpoint.
- **FR-011b**: The system MUST record, alongside the index and every evaluation run: the
  embedding model revision, the generation model revision, the quantization used, the
  vector dimension, the prompt version, and the runtime configuration. A quality figure
  that cannot be attributed to the exact configuration that produced it is not a
  measurement, and this is what makes FR-034's repeatability checkable across time.
- **FR-011c**: **Embedding MUST run locally**; no retrieval path may depend on a network
  call. **Generation reaches a remote endpoint**, and that is the only outbound call this
  feature makes. The reference machine has no discrete GPU, so local generation of a 3B
  model could not meet any useful latency target — this is the trade the profile buys, and
  it is bought at the cost of the previously stated zero-network property, which no longer
  holds at generation time. It still holds for **ordinary continuous integration**
  (FR-035b), which is where it was doing the most work.
- **FR-011f**: Weight acquisition is a **provisioning-time** activity, distinct from
  request time. The Colab session MAY download model weights while it is being provisioned.
  An inference request MUST NOT trigger a model download and MUST NOT contact any
  third-party inference API. Acquisition MUST verify the **exact revision and the weight
  checksum** at provisioning time (FR-011, FR-011g); an unverified download is not
  provisioning, it is a guess about what will run.
- **FR-011g**: Model licences MUST be verified against authoritative model cards and
  recorded. Weights MUST NOT be redistributed in this repository or in a public project
  image unless the verified licence explicitly permits it. **Verified 2026-08-11**: BGE-M3
  is **MIT** (commercial use and redistribution permitted with notice). Qwen2.5-3B-Instruct
  is the **Qwen RESEARCH LICENSE AGREEMENT** — §2(a) restricts use to *"NON-COMMERCIAL
  PURPOSES ONLY"*, defined in §1(i) as *"research or evaluation purposes only"*; §2(b)
  requires a separate licence for commercial use; §3 permits redistribution only with the
  agreement attached, an attribution notice, and modified files marked. The research-only
  restriction is **consistent with** this feature's synthetic-corpus-and-evaluation scope
  (FR-011h) and is a further reason the provider must be replaceable (FR-011d): any
  commercial deployment requires a different model or a licence from the vendor.
- **FR-011h**: The remote-generation profile MAY process **this project's synthetic corpus
  only**. Real enterprise data and personal data MUST NOT be sent through it, and require
  an approved private or self-hosted generation endpoint. This limitation MUST be stated in
  the operator-facing documentation, not only here.

**Authorization — the core requirement**

- **FR-011i**: A change to the embedding **model revision, weight checksum, vector
  dimension, tokenizer identity, or runtime identity** MUST require a **complete replacement
  index**. **Mixed embedding identities MUST NEVER be active in the same collection.** The
  previous index and its corpus-version checksum (FR-018a) MUST remain active until the
  replacement is **fully built and atomically published**; a failed or cancelled replacement
  MUST leave the previous version **untouched**. This is what "invalidate the index" in
  FR-011 means as an outcome: replace-then-publish, never mark-and-serve.
- **FR-011j**: If the pinned runtime **cannot enforce** the deterministic settings FR-011a
  requires, the Phase 0 benchmark MUST fail as **`UNSUPPORTED_CONFIGURATION`**. There MUST
  be **no** silent fallback, **no** relaxed comparison tolerance, **no** substitution of an
  alternate model, and **no** claim of deterministic success. A determinism claim the runtime
  cannot support is worse than no claim, because every figure downstream inherits it.
- **FR-011k**: The **generation prompt MUST be a versioned repository artefact**, distinct
  from the grounding-judge prompt of FR-032a. Every evaluation run MUST record
  **`generation_prompt_version`** and **`generation_prompt_hash`**. **Any change to the
  generation prompt starts a new GPU/configuration series and resets the three-run gate**
  (FR-043, FR-043a), exactly as a quantization or runtime change does — the prompt is part of
  the configuration a quality figure is attributed to, not an implementation detail beneath
  it. Its version and hash are recorded in the **evaluation-run manifest** (FR-035j) and on
  the run record, never in the embedding fixture manifest or the question partition manifest.
- **FR-011l**: The remote-generation path MAY build an outbound request **only when the
  active corpus manifest (FR-018a) identifies the approved synthetic seed corpus and matches
  its recorded fingerprint**. An **unknown, modified, user-supplied, or non-synthetic**
  corpus MUST **fail closed before the outbound request is constructed** — not at review
  time, and not by convention. Real enterprise or personal data requires an approved private
  or self-hosted provider (FR-011h). This is the control that makes FR-011h enforceable
  rather than aspirational.
- **FR-012**: The immutable access context built by the existing API (spec 003 FR-008 to
  FR-011) MUST be the only source of the asker's identity, tenant, attributes,
  permissions, and roles for every retrieval and every generation. No component may derive
  them from the question, the conversation, or any client-supplied value.
- **FR-012a**: **"Per request" means one logical user question — one turn.** Every incoming
  authenticated chat turn MUST receive a **newly built access-context snapshot** from the
  local API.

  | Rule | Requirement |
  |------|-------------|
  | Scope of reuse | **only** internal retrieval and generation operations belonging to the **same turn** |
  | Retries | MAY preserve the snapshot **only while the original turn is still active** |
  | Follow-up turns, regenerated answers, resumed conversations | MUST build a **new** access context |
  | Conversation history | MUST be **re-authorized under the new turn's context** before any reuse (FR-026) |
  | Workers and providers | MUST NOT create, validate, widen, or reuse an access context **across turns** |
  | Citations | FR-022's authorization immediately before emission or persistence remains **independently** required |
  | Cache | stays scoped to the current permission fingerprint and `data_version` (FR-018, FR-018a) |

  A snapshot that outlives its turn is indistinguishable from a cached permission, which is
  precisely what FR-016 forbids.
- **FR-013**: Authorization MUST be applied **as a constraint on the search itself**, not
  as a filter over its results. The vector store MUST NOT return a chunk the asker may not
  read, even transiently and even if it would be discarded afterwards. A ranked list
  computed over forbidden content and then trimmed has already let that content influence
  what the asker sees.
- **FR-013a**: Passage and prompt content — **and any derived form of it**, including
  summaries, snippets, and highlighted fragments — MAY exist **only in request-scoped
  memory**, from the moment of authorized retrieval until the terminal SSE event or abort
  cleanup completes, and MUST be **released** at that point. It MUST **never** enter
  persistent storage, caches, logs, traces, metrics, snapshots, test artifacts, exception
  messages, or retry queues.

  | | Status |
  |---|---|
  | The index itself | **Exempt** — it is the authorized source content is retrieved *from*; FR-013a governs everything **downstream** of retrieval |
  | The permission-scoped cache (FR-018) | Holds **references and derived results, never passage or prompt bodies** |
  | The composed answer (`answer_text`) | **Not** passage content; it is shown to its owner and stored, and is never logged (FR-037) |
  | The cited excerpt span (FR-028b3) | Stored as **offsets**, resolved against the index on open — never as a copy of the text |

  This bounds FR-013's "even transiently" so compliance is checkable rather than argued: an
  abort path that leaves passages resident is the failure this requirement names, because it
  is the path least likely to be exercised.
- **FR-014**: The retrieval constraint MUST enforce, in the existing deterministic order:
  tenant boundary, then role-based permission, then attribute rules (department, country,
  employment relationship), then resource-level grants, then classification. A denial at
  any layer MUST prevent the chunk from being retrieved at all.
- **FR-014a**: **Null scope attributes mean company-wide, never "unfiltered".** A null
  `country` or `department_id` on a document places it in scope for the whole company; it
  MUST NOT disable a filter and MUST NOT match every caller unconditionally. Resolution,
  per attribute:

  | Caller attribute | Reaches |
  |------------------|---------|
  | has a value | documents with the **same value**, plus **company-wide** documents |
  | has no value | **company-wide** documents only, unless an independent owner, role, or explicit ACL grant authorizes the document |

  **Company boundary and classification ceiling always apply** and are never widened by this
  rule. Without it the measured corpus is unreachable: `country` is null on 18 of the 105
  seeded documents, and an equality-only constraint excludes every one of them from every
  caller.
- **FR-014b**: **Every payload attribute the retrieval filter uses MUST have a payload index
  in the vector store, and each MUST be tested.** `allowed_roles` is currently used by the
  filter and is not indexed; the index MUST be added before any point is written, since
  adding it to a populated collection is a reindex. A filter attribute with no index is a
  layer that may silently fail to constrain.
- **FR-015**: No content the asker may not read may enter the generation step's input
  under any circumstance — not as context, not as a summary, not as a count, and not as an
  instruction. This is Constitution Principle III and it is absolute.
- **FR-016**: Authorization MUST be evaluated **per request** — as FR-012a defines that
  boundary — against current records, not
  cached from an earlier turn of the same conversation. A permission withdrawn between two
  questions MUST take effect on the second.
- **FR-017**: A response that was narrowed by authorization MUST be indistinguishable from
  a response narrowed by an empty corpus. No count of withheld results, no "some sources
  were not shown", and no difference in latency-shaped behaviour that reveals the
  existence of unreadable content.
- **FR-017a**: FR-017's indistinguishability MUST be measurable on **five observable
  properties**. A permission-narrowed empty result and a genuinely empty authorized result
  MUST have:

  1. identical **HTTP status**;
  2. identical **SSE event types and ordering**;
  3. identical **user-visible wording**;
  4. identical **retry behaviour**;
  5. **no** excluded-count or withheld-source signal of any kind.

  **Ordinary continuous integration** MUST verify **identical control flow** against
  deterministic fixtures — this blocks the build. A **controlled security evaluation** MUST
  additionally use **≥ 50 warm samples per case** and require the **p95 time-to-terminal
  difference** between the two cases to be **no greater than 100 ms or 20%, whichever is
  larger**. The timing measure gates **stabilization**, not shared-runner continuous
  integration, because a shared runner's variance exceeds the signal being measured.
- **FR-018**: Any cached retrieval or generation result MUST be scoped such that it can
  never be served to a caller whose permissions differ from the caller it was computed
  for. A cache keyed on the question alone is a cross-permission leak.

**Grounded answers and citations**

- **FR-018a**: `data_version` in the cache key MUST be a **company-scoped active corpus
  manifest checksum**, derived deterministically from: the company id and collection; the
  active document ids and their normalized-content hashes; the chunk ids and chunk-content
  hashes; the chunker version and configuration hash; the embedding model identity, revision
  and checksum; the vector dimension; and the **authorization-relevant payload schema
  version**. It MUST NOT be the dataset fingerprint, an ingestion run id, or a manually
  incremented counter — the first does not change when the index does, and the last two
  change when the index does not.

  | Rule | Requirement |
  |------|-------------|
  | Publication | **Atomic**, and only **after** the complete replacement index succeeds |
  | Failed or cancelled ingestion | the **previous** checksum stays active |
  | Idempotent no-op ingestion | produces the **same** checksum |
  | Content, chunking, embedding identity, or authorization-payload change | produces a **different** checksum |
  | Older-checksum cache entries | become **unreachable** without destructive deletion |
  | Storage | a dedicated **company/collection corpus-version record**, with migration and rollback coverage |

- **FR-019**: Every substantive claim in an answer MUST be attributable to a retrieved
  passage. The system MUST NOT present unsupported statements as fact — Constitution
  Principle IV.
- **FR-020**: Every answer MUST carry citations identifying the source documents, and each
  citation MUST resolve to the specific passage that supports the claim, not merely to the
  document as a whole.
- **FR-021**: When the permitted corpus does not support an answer, the system MUST say so
  explicitly. A plausible answer with no supporting passage is the failure mode this
  requirement exists to prevent.
- **FR-022**: A citation MUST be re-authorized when it is opened. A person who could see a
  passage when the answer was produced, and cannot now, MUST be refused as though the
  passage did not exist.
- **FR-023**: Business facts that live in the systems of record — figures, dates, holdings,
  balances — MUST be presented from those records rather than from prose recollection,
  per Constitution Principle V.

**Conversation and delivery**

- **FR-024**: The assistant MUST be reachable from the authenticated portal, as an
  additional surface, and MUST NOT weaken or bypass any existing portal behaviour.
- **FR-025**: Answers MUST be delivered progressively so the person sees the response
  forming, and MUST be stoppable in progress. A stopped or failed response MUST be marked
  incomplete and MUST NOT be presented as a finished answer.
- **FR-025a**: "Stoppable" in FR-025 means **end-to-end cancellation**, never merely hiding
  output. On receiving a stop request the system MUST:

  1. **stop emitting content immediately**;
  2. **propagate cancellation** through the local API to the Colab generation request and
     **stop token generation** — the display and the work stop together;
  3. **close the SSE stream** with the existing terminal `stopped` state and mark the answer
     **incomplete**;
  4. **release all** request-scoped question, prompt, passage, and partial-generation content
     during abort cleanup (FR-013a);
  5. permit **no** retry, **no** queued continuation, and **no** background generation
     afterwards.

  The local API MUST **close the stream and complete local cleanup within 2 seconds** of
  receiving the stop request. If **upstream** cancellation cannot be confirmed within that
  deadline, the system MUST **sever the provider connection**, record only a **content-free
  `provider_cancel_unconfirmed`** status, and **discard all later provider output**.

  A stopped turn **is recorded** in conversation history with its partial text retained and
  marked incomplete, **is audited** exactly as any other generation is (FR-036), and **is not
  resumable** — a resumed answer would be a new turn under a new access context (FR-012a).

  **Testing obligation**: a test MUST prove that stopping **only the display** while
  generation continues is a **failure**. Without it, the cheapest wrong implementation passes
  every other criterion in this specification.
- **FR-025b**: An **unexpected client disconnect** — navigation, tab close, browser crash, or
  network loss — is an **implicit cancellation**, and MUST NOT be reported as an explicit user
  stop. On detecting a disconnected stream the local API MUST:

  1. **cancel the upstream provider request and stop generation**;
  2. **reject all later provider output**;
  3. **release all** request-scoped content (FR-013a);
  4. apply the **same 2-second local cleanup deadline** and the same
     **`provider_cancel_unconfirmed`** handling as FR-025a;
  5. persist the turn as **`INCOMPLETE` with reason `CLIENT_DISCONNECT`** — **never**
     `STOPPED`;
  6. permit **no** retry, continuation, resumable stream, or background work.

  Because the client connection is gone, **no terminal SSE event is required**; the
  **server-side state and the content-free audit record are authoritative**. This is the only
  exception to the mandatory-terminal-event rule, and it is conditioned on the connection
  being gone rather than on the event being absent.

  The audit record MAY contain the **turn id, timestamps, status, duration, and
  cancellation-confirmation status**, and MUST contain **no** question, prompt, passage,
  partial answer, token, URL, or credential content (FR-037, FR-013a).

  **Testing obligation**: ordinary continuous integration MUST include a **stub-provider**
  test that disconnects the client mid-stream and proves upstream cancellation, cleanup within
  2 seconds, the incomplete state, the absence of any continuation, and content-free logs —
  **and a falsifying case in which the UI disconnects while generation continues, which MUST
  fail**. A disconnect that leaves a GPU generating is the failure this requirement exists to
  catch, and it is invisible from the browser.
- **FR-026**: Conversation history MUST be scoped to its owner and tenant, and a prior
  turn MUST NOT reintroduce content the asker may no longer read.
- **FR-027**: The assistant surface MUST implement the same designed states the portal
  already requires — loading, empty, error, unauthenticated, expired, and access-denied —
  under the rule stated in the portal routes contract.

**Session-token trust boundary**

- **FR-028**: The existing API MUST remain the **only** verifier of user session
  credentials. Workers, retrieval components, generation components, and any new service
  MUST NOT accept, parse, or validate a browser-issued session token, and MUST NOT be
  given the signing key.
- **FR-029**: Any component acting on a person's behalf MUST receive the already-built,
  immutable access context from the API rather than an identity assertion it verifies
  itself. This preserves the single verification point spec 003's key arrangement depends
  on.
- **FR-030**: Background work performed on a person's behalf MUST carry the tenant and the
  authorization context of the person it is for, and MUST be refused if that context is
  absent. A job with no owner is a job with no boundary.

**The generation boundary**

- **FR-028a**: The following MUST NEVER leave the local API: browser session tokens, the
  token signing key, refresh tokens, access-context objects, ACL records, excluded-source
  counts, and any chunk the asker is not authorized to read. This is an enumerated
  prohibition rather than a principle, so a reviewer can check a request payload against a
  list.
- **FR-028b**: The request to the generation endpoint MUST carry **only the minimum
  authorized passages required to answer the current question**, plus the question and the
  instructions needed to compose an answer. "Minimum" MUST be defined by a stated selection
  rule, not left to judgement.
- **FR-028b1**: The passage budget sent to generation is bounded on three axes
  simultaneously: **at most 5 passages**, **at most 400 tokens per passage**, and **at most
  2,000 retrieved-passage tokens in total**, where a token is counted by the **pinned
  generation tokenizer** rather than by any approximation. All three bounds apply; the
  tightest one governs.
- **FR-028b2**: When a passage must be shortened to fit, it MUST be trimmed **only at the
  nearest preceding sentence boundary**. Mid-sentence truncation is prohibited: a fragment
  cut mid-clause can invert the meaning of the sentence it came from, and the citation would
  then attest to something the source does not say.
- **FR-028b3**: The **exact excerpt span sent to generation MUST be preserved and MUST be
  what a citation resolves to.** A citation may not present a wider span than the model
  received. Otherwise a reader checking a citation would be shown context the answer was
  never grounded in, which is a subtler failure of FR-019 than an uncited claim.
- **FR-028b5**: The chunking budget (FR-007a, BGE-M3 tokens) and the generation passage
  budget (FR-028b1, pinned **Qwen** tokenizer) are **independent and both hold**.
  Generation MUST **re-count** every passage with the Qwen tokenizer rather than reusing the
  chunker's count; the two tokenizers segment differently, so a 400-token chunk is not
  necessarily a 400-token passage, and assuming otherwise would silently exceed the prompt
  budget the first-token measure depends on.
- **FR-028c**: The remote generator MUST NOT perform retrieval and MUST NOT make any
  authorization decision. Authorization-constrained search happens locally **before** the
  request; citation re-authorization happens locally **after** the response and before
  anything is shown. A generator that could widen its own context would make FR-013
  unenforceable.
- **FR-028d**: The browser MUST NEVER contact the generation endpoint or the tunnel
  directly. All generation traffic MUST pass through the local API, which is the only
  component holding the service credential.
- **FR-028e**: Requests to the generation endpoint MUST use HTTPS and MUST carry an
  `Authorization` header. A request that cannot be authenticated MUST fail rather than
  proceed unauthenticated.

**Tunnel and service credentials**

- **FR-028f**: `NGROK_AUTHTOKEN` MUST exist only in Colab Secrets. It MUST NOT appear in
  this repository, in environment files, in images, or in logs.
- **FR-028g**: A **separate, short-lived `GENERATION_SERVICE_TOKEN`** MUST authenticate the
  local API to the generation endpoint. It and the current tunnel URL MUST live only in
  ignored environment configuration, MUST NOT be committed, and MUST NOT be logged.
- **FR-028h**: The service token MUST be rotated whenever the Colab session is recreated,
  and a stale token MUST be refused rather than tolerated.
- **FR-028i**: The tunnel URL and every credential MUST be masked wherever their exposure
  would grant access — logs, traces, error messages, audit records, and any operator-facing
  surface.
- **FR-028j**: If the tunnel is unavailable or authentication fails, the system MUST **fail
  closed**. It MUST NOT silently fall back to another hosted provider, to an unauthenticated
  request, or to an ungrounded answer.

**Generation-service availability**

- **FR-028k**: Generation-service availability MUST be determined **before** streaming
  begins, so an unavailable service produces a designed state rather than an empty stream.
  The check is performed by the **local API** with a **2-second deadline**. **Timeout, DNS
  failure, TLS failure, authentication refusal, malformed response, and any unhealthy
  status all mean unavailable** — there is no partially-available state. When unavailable,
  the system MUST send **no question and no passage body**, MUST open **no generator
  stream**, MUST expose **no tunnel detail**, and MUST return the designed state of
  FR-028l. The check MAY run **concurrently with local retrieval**, but generation MUST NOT
  begin until **both** the health check and the authorization-constrained retrieval have
  succeeded — the concurrency is a latency optimization, never a reordering of the
  authorization decision.
- **FR-028l**: While generation is unavailable, ingestion, authorization, and retrieval MUST
  remain operational, and the assistant MUST show a designed **"generation temporarily
  unavailable"** state that is distinct from an empty result, an access denial, and an
  expired session.
- **FR-028m**: If the tunnel fails **during** streaming, the response MUST terminate with an
  explicit incomplete-answer event. Partial output MUST NOT be presented as a complete
  answer, and MUST NOT be recorded as one.
- **FR-028n**: Every evaluation run MUST record the **actual** GPU model, the runtime, the
  model revision, the quantization, the dependency versions, and the tunnel/network
  conditions observed. A run that cannot state its GPU is not a measurement (FR-035c).

- **FR-028o**: Recorded tunnel conditions (FR-028n) MUST consist of exactly: the **provider
  profile**; the **Colab GPU series**; the **ngrok region**; the **protocol and TLS
  version**; the **measured network RTT p50 and p95**; the **health-check outcome**; and a
  **keyed HMAC fingerprint of the endpoint** for run correlation. The system MUST **never**
  store or display the tunnel **hostname**, the **full URL**, the **ngrok token**, or the
  **service credential**. The HMAC fingerprint exists so two runs can be correlated to the
  same endpoint without the record naming it — correlation and disclosure are different
  needs, and only the first is required here.

**Evaluation**

- **FR-031**: A fixed evaluation set MUST exist, pairing questions with the documents that
  should answer them and with the personas who should and should not be able to reach
  those documents.
- **FR-031a**: The evaluation set MUST carry a **question partition manifest** — one of the
  three distinct manifests this feature defines (FR-035m), scoped **only** to the question set
  and carrying no model, prompt, or runtime field — declaring **every question
  partition with its exact expected count** — answerable, unanswerable, permission-split
  pairs, cross-tenant, ACL-only, and per-persona — together with the **corpus fingerprint**
  it was authored against and its own **checksum**. A partition whose size is implied
  rather than declared cannot be checked for emptiness, which is the failure FR-035i
  exists to catch.
- **FR-032**: Evaluation MUST report these figures **separately**, against these
  thresholds. A single aggregate score would let a leak be averaged away by good retrieval.

  | Measure | Definition | Threshold |
  |---------|-----------|-----------|
  | Retrieval — recall@5 | the expected supporting document appears in the top 5 retrieved chunks | **≥ 80%** |
  | Grounding | answers in which every substantive claim traces to a cited passage | **≥ 90%** |
  | Citation precision | citations that actually support the claim they are attached to | **≥ 90%** |
  | Correct abstention | questions unanswerable from the asker's permitted corpus that are correctly refused | **≥ 90%** |
  | Local retrieval-ready source preview | p95, declared environment (FR-035a) | **≤ 2 seconds** |
  | First generated answer token, through the tunnel | p95, declared environment (FR-035a) | **≤ 5 seconds** |
  | Unauthorized content exposure | permitted-set violations of any kind | **exactly 0** |

- **FR-032a**: Grounding and citation precision MUST be adjudicated by the **same pinned
  quantized Qwen2.5 3B Instruct model invoked separately as a judge** — never by the
  generation response judging itself, and **never** over a model's own raw hidden reasoning.
  Only the **final answer and its cited evidence** are evaluated.

  | Aspect | Requirement |
  |--------|-------------|
  | Prompt | versioned repository artifact `specs/004-permission-aware-rag/evaluation/grounding-judge-v1.md` |
  | Settings | **temperature 0**, deterministic where the runtime supports it |
  | Input | **only** the synthetic question, the completed answer, the citation references, and the **exact cited spans** |
  | Never in the input | unauthorized passages, ACL data, excluded-source counts, credentials, tokens |
  | Output | **strict JSON schema** — per-claim grounded / not-grounded, per-citation supports / does-not-support, each with a short **enumerated reason code** |
  | Recorded per run | model revision, quantization, runtime, **judge-prompt hash**, **response-schema version** |

- **FR-032b**: Before the judge may score the release gate it MUST be validated against a
  **committed, manually labelled calibration set of at least 20 positive and negative
  examples**, reaching **≥ 90% agreement** with those labels. Below 90%, grounding and
  citation precision are recorded **INVALID** — neither a pass nor a failure — and MUST NOT
  be reported as having met their thresholds. A judge nobody calibrated is an opinion, and
  an opinion cannot gate a release.
- **FR-032c**: **Deterministic structural checks MUST run alongside the judge** and are not
  replaced by it: every substantive claim carries a citation; every citation **resolves**;
  and every **cited span equals the passage sent to generation** (FR-028b3). These are
  correctness properties with exact answers, so they belong to the deterministic class of
  FR-034a even though the judged measures beside them are statistical. **All three MUST
  block ordinary continuous integration** against deterministic fixtures (FR-035b). The
  controlled full-model evaluation repeats them, but MUST NOT be their only gate — a check
  with an exact answer that runs only in the lane which never blocks the build is a check
  that cannot stop a regression.
- **FR-033**: Unauthorized content exposure MUST measure **zero**. A single instance MUST
  fail the evaluation run and MUST block the build, per Constitution Principle VIII. The
  grounding, citation, and abstention thresholds are below 100% because they measure a
  generative model's behaviour, which is imperfect; the leakage threshold is not, because
  it measures an authorization decision, which is not.
- **FR-034**: Evaluation MUST be repeatable: the same corpus, configuration, question set,
  and recorded model revisions (FR-011b) MUST produce the same retrieval figures on every
  run.
- **FR-034a**: Every measure MUST be classified **deterministic** or **statistical**, and
  the classification MUST be recorded with the run:

  | Class | Measures | Reproducibility requirement |
  |-------|----------|-----------------------------|
  | **Deterministic** | retrieval over the committed fixtures, authorization outcomes, citation resolution, unauthorized-exposure count | **Exact** for a pinned configuration. A difference between two identical runs is a **failure**, not variance, and MUST fail the run. |
  | **Statistical** | grounding, citation precision, correct abstention, preview p95, first-token p95 | Legitimately vary. Satisfied only when **each of three consecutive runs independently meets** the threshold (FR-043). |

  Averaging across runs MUST NOT be used to reach a statistical threshold; three
  independently passing runs is the standard, precisely because an average lets one bad run
  be carried by two good ones.
- **FR-034b**: A statistical run MUST use the **same pinned configuration and the same
  evaluation manifest** as the runs it is compared with, MUST record **every per-question
  outcome**, and MUST report **numerator, denominator, and aggregate percentage** rather
  than a percentage alone. A percentage without its denominator cannot be distinguished
  from a run that evaluated almost nothing.
- **FR-035**: Evaluation MUST run in continuous integration and MUST block the change on
  failure. **Blocking every build**: zero unauthorized exposure (FR-033), authorization
  applied before the search rather than after it (FR-013), deterministic retrieval
  (FR-034), and the citation checks. These are correctness properties, not quality scores,
  and none of them depends on a fast machine.
- **FR-035a**: Both latency thresholds MUST be measured in this **declared controlled
  environment**, and they gate the agent phase rather than ordinary shared-runner
  continuous integration:

  | Attribute | Declared value |
  |-----------|----------------|
  | GPU | NVIDIA **T4**, **16 GiB VRAM** — the **latency reference class**, not a floor (FR-043a) |
  | Model | pinned Qwen2.5 3B Instruct, pinned quantization, pinned runtime |
  | Model state | **warm** — weights resident |
  | Corpus | **full profile, 105 documents** |
  | Concurrency | **1** |
  | Warm-up | **5** requests, discarded |
  | Sample size | **≥ 30** measured requests |
  | Percentile method | **nearest-rank p95** |

- **FR-035c**: **Cold-start and model-download time MUST be measured and reported
  separately** and MUST NOT be counted as warm inference latency. An evaluation run
  executed on **CPU-only Colab or an unidentified GPU is invalid** for the three-run gate
  and MUST be recorded as invalid rather than as a failure or a pass.
- **FR-035b**: **Ordinary continuous integration MUST make zero Colab, tunnel, or other
  network calls.** It MUST use deterministic committed fixtures — committed embeddings,
  committed chunks, and a stubbed streaming generator — so that every correctness property
  is checkable without a GPU, a tunnel, or a credential. The build MUST be blocked by:
  authorization-before-search, zero leakage, filter correctness, cache isolation,
  deterministic ingestion and chunk identifiers, citation re-authorization, safe telemetry,
  streaming/cancellation behaviour, **the three deterministic structural checks of FR-032c**,
  **the identical-control-flow check of FR-017a**, **the readable-body validation of
  FR-002b**, **the transient-lifetime assertions of FR-013a**, and **the synthetic-corpus
  precondition of FR-011l**. **Ordinary continuous integration evaluates only
  the committed deterministic fixture subset and MUST NOT report, or allow a reader to
  infer, a full-corpus quality figure.**
- **FR-035d**: The **controlled full-model evaluation** MUST use the real local BGE-M3
  embedder, the real generation endpoint, and the **complete 105-document seeded corpus
  (full profile)**, and MUST measure every figure in FR-032. It is
  a separate activity from ordinary continuous integration and MUST NOT be a precondition
  for an ordinary build.
- **FR-035e**: Both latency figures in FR-032 are **acceptance thresholds, not demonstrated
  results**. Neither has been measured. No document, report, or interface may describe
  either as achieved until the benchmark in FR-035f has produced a passing figure, and the
  specification MUST NOT be read as claiming otherwise.
- **FR-035f**: A **Phase 0 feasibility benchmark** MUST be the first activity of the
  implementation plan, before work proceeds beyond the subsystem each threshold governs. It
  MUST use:

  | Parameter | Value |
  |-----------|-------|
  | Embedding | pinned BGE-M3 on the declared local CPU environment |
  | Generation | pinned quantized Qwen2.5 3B Instruct on a **verified** Colab T4 |
  | Prompt | the expected production prompt size, with **five** retrieved passages |
  | Warm-up | **5** requests, discarded |
  | Sample | **≥ 30** measured requests |
  | Percentile | **nearest-rank p95** |

  If either threshold fails: implementation beyond the relevant subsystem is **blocked**;
  the result and the **raw timing summary** are recorded; and the threshold MUST NOT be
  silently relaxed. Changing the model, the prompt budget, the hardware baseline, or a
  threshold requires an **explicit specification clarification and checklist
  revalidation** — the same route any other requirement change takes.
- **FR-035g**: Every committed retrieval fixture set MUST carry an **embedding fixture
  manifest** — one of the three distinct manifests this feature defines (FR-035m), scoped
  **only** to the committed vectors and the embedder that produced them, and carrying **no**
  generation-prompt, judge, or provider field — recording:
  the embedding model ID and exact revision; the model-weight checksum; the vector
  dimension; the quantization and runtime identity where applicable; the chunker version
  and configuration hash; the source-document identifiers and content hashes; the
  fixture-generation command version; the generation timestamp; and the resulting fixture
  checksum. **Ordinary continuous integration MUST fail** when the manifest disagrees with
  the configured embedder, the vector store's dimension, the chunker identity, or the
  source hashes — otherwise CI could pass against vectors that no longer describe the
  corpus or the model.
- **FR-035h**: Fixture **regeneration** MUST run in the controlled environment against the
  real pinned embedder, MUST be an explicit command rather than anything ordinary CI
  performs automatically, MUST produce a reviewable diff, and MUST NOT be accepted until
  the full retrieval evaluation passes on the regenerated set. A fixture that regenerates
  itself during a build is a fixture that can silently absorb a regression.
- **FR-035j**: Every **controlled evaluation run** MUST own a **run directory**
  `tests/evaluation/results/<run_id>/` containing its own immutable **`run-manifest.json`**,
  its own **raw-results file**, and its own **results record**. No two runs share a path.
  Ordinary-CI fixtures live in a **separate committed fixtures directory** and never under
  `results/`. The manifest records at minimum:

  | # | Field group | Contents |
  |---|-------------|----------|
  | 1 | Generation prompt | version and **SHA-256 hash** |
  | 2 | Generation model | identifier and **pinned revision** |
  | 3 | Generation runtime | quantization and runtime identity |
  | 4 | Judge | prompt version/hash and judge model identity |
  | 5 | Embedding model | identifier, revision, weight checksum |
  | 6 | Corpus | fingerprint and active `data_version` (FR-018a) |
  | 7 | Chunker | configuration hash |
  | 8 | Question set | question-manifest checksum (FR-031a) |
  | 9 | Provider | provider profile and GPU series (FR-043a) |
  | 10 | Command | evaluation command version |
  | 11 | Time | run timestamp |

  The manifest is **immutable evidence for that run** and MUST be **referenced by the run's
  results record** by its **full run-directory path and checksum**. A figure and the
  configuration that produced it must travel together, in one directory, or the figure is not
  attributable. Three consecutive runs therefore reference **three distinct manifest paths and
  three distinct checksums** — a shared path would make the isolation of FR-043c
  unverifiable.
- **FR-035k**: A run MUST be recorded **`INVALID_CONFIGURATION`** — neither a pass nor a
  failure — when **any required manifest field is missing** or **disagrees with the configured
  runtime**. Disagreement is checked against the live configuration, not against the previous
  run, so a manifest cannot be correct merely by being consistent with itself.
- **FR-035l**: **Ordinary continuous integration MUST validate the run-manifest schema and the
  mismatch behaviour** using committed fixtures — every required field present, every absent
  field rejected, every disagreement producing `INVALID_CONFIGURATION`. It MUST do so
  **without contacting Colab or ngrok and without running either model**, so the validation
  that guards the controlled lane is itself checkable in the offline one.
- **FR-035n**: **Ordinary continuous integration MUST test the three-run gate** using
  **fixture manifests and fixture results only** — synthesized run records and manifests
  committed to the repository — contacting **neither Colab nor ngrok** and **loading no
  model**. The gate's logic is decidable from records alone; making it checkable offline is
  what keeps the expensive lane's gate from being discovered broken at the moment it matters.
- **FR-035o**: The **generation-server artefact** `infrastructure/colab/generation_server.ipynb`
  is **Phase 0 provisioning**, not Phase 4 creation. Before any first-token sample is taken,
  the following MUST be provisioned or verified:

  | # | Prerequisite |
  |---|--------------|
  | 1 | **pinned Qwen model weights**, with revision and checksum verified (FR-011a, FR-011f) |
  | 2 | **authenticated HTTPS ngrok endpoint** (FR-028e) |
  | 3 | **service token** present in ignored environment configuration (FR-028g) |
  | 4 | **verified T4** — never an unidentified or CPU-only allocation (FR-035c) |
  | 5 | **runtime and quantization identity** recorded (FR-011b) |
  | 6 | a working **health endpoint** (FR-028k) |
  | 7 | **streaming first-token protocol compatibility** (contracts RC §2) |

  **Phase 4 MUST reuse this artefact and its server contract** rather than creating either
  again — one server definition, provisioned once and consumed twice. If any prerequisite is
  absent, the first-token row stays **`NOT RUN`** or is recorded **`INVALID`**; it may
  **never** pass. A measurement against a server that does not yet exist is not a
  measurement.
- **FR-035p**: Phase 0 MAY implement **only the canonical chunker and embedder libraries the
  feasibility measurement requires**. It MUST NOT implement ingestion, production indexing,
  retrieval APIs, or generation integration before those subsystems' own gates. The local
  **BGE runtime dependency is owned by `packages/core`** — the package whose modules import
  it — **and by the root development environment**; it MUST NOT be declared in a standalone
  benchmark manifest that nothing installs. **Duplicate benchmark-only implementations of
  chunking or embedding are prohibited**: the benchmark imports the canonical modules, so one
  determinism guarantee covers both paths (FR-007, FR-011).
- **FR-035m**: This feature defines **exactly three manifests**, with **disjoint scopes**;
  none may absorb another's fields:

  | Manifest | Path | Scope | Requirement |
  |----------|------|-------|-------------|
  | **Embedding fixture manifest** | `tests/fixtures/retrieval/manifest.json` | the committed vectors and the embedder that produced them | FR-035g |
  | **Question partition manifest** | `tests/evaluation/manifest.json` | the evaluation question set and its partition counts | FR-031a |
  | **Evaluation-run manifest** | `tests/evaluation/results/<run_id>/run-manifest.json` | the full configuration of **one** controlled run, in that run's own directory | FR-035j |

  The first two are **inputs**, committed and reviewed. The third is **evidence**, produced by
  a run and never edited afterwards.
- **FR-035i**: The evaluator MUST run a **preflight** and MUST **exit nonzero before
  computing any metric** when any of the following holds:

  1. the total question count is **zero**;
  2. any **required partition is empty**;
  3. **actual partition counts differ** from the manifest of FR-031a;
  4. any required metric would be computed over a **zero denominator**;
  5. any **expected source document is absent** from the 105-document corpus.

  A run that cannot be performed MUST fail loudly; it MUST NOT report zero questions, or an
  undefined ratio, as a pass. Every evaluation output MUST record the **corpus fingerprint,
  document count, partition counts, and manifest checksum**, so a run's scope is legible
  from its own record rather than assumed from the command that started it.


**Observability**

- **FR-036**: Every retrieval and every generation MUST be audited with the asker, the
  tenant, the question's identity, the **documents consulted** as FR-036a defines that
  term, and the decision — allowed or refused — per Constitution Principle X.
- **FR-036a**: These five terms MUST be used consistently and MUST NOT be interchanged in
  requirements, telemetry, audit records, or interfaces:

  | Term | Definition |
  |------|------------|
  | **Candidate** | an authorized vector-store point eligible **before** ranking |
  | **Retrieved passage** | a ranked chunk returned by retrieval |
  | **Generation passage** | an authorized, budgeted excerpt **actually serialized** to the generator (FR-028b1–FR-028b3) |
  | **Cited passage** | a generation passage referenced by the completed answer |
  | **Documents consulted** | the count of **distinct `document_id` values among generation passages** |

  User-visible source information MAY report retrieved, consulted, and cited documents. It
  MUST NEVER report unauthorized candidates or authorization-exclusion counts; those are
  operator-only telemetry under FR-038, and FR-017's prohibition is unchanged by this
  definition.
- **FR-037**: Logs, traces, metrics, and audit records MUST NOT contain document content,
  question text, answer text, embeddings, or session credentials. Diagnosis MUST be
  possible from identifiers, counts, timings, and decision outcomes alone.
- **FR-037a**: Outbound generation payloads MUST be inspectable **without the inspection
  becoming a disclosure**. The mechanism is a **test-only, in-memory transport
  interceptor** that: receives only synthetic fixture passages; inspects the **serialized**
  request immediately before transmission; asserts the request contains no session token,
  signing key, refresh token, access-context object, ACL record, excluded-source count,
  unauthorized chunk, raw credential, or unapproved metadata field; **persists nothing**;
  writes **no passage text** to logs, artifacts, snapshots, or failure messages; reports
  only **field names, counts, and pass/fail**; and **discards the captured request
  immediately** after the assertion.
- **FR-037b**: **Production telemetry MUST NEVER capture prompt or passage bodies.** The
  interceptor of FR-037a exists only in the test path and MUST NOT be reachable in a
  running deployment. FR-037's prohibition is unconditional; FR-037a does not create an
  exception to it, it describes the only way to check compliance without breaking it.
- **FR-038**: Operational telemetry MUST be sufficient to answer, without reading content:
  how long retrieval and generation took, how many chunks were considered, how many were
  excluded by authorization, and whether the answer was refused for lack of support.
  Candidate counts and authorization-exclusion counts under this requirement are
  **operator-only** and MUST NOT reach any response (FR-017, FR-036a).
- **FR-039**: Refusals — of ingestion, of retrieval, and of generation — MUST be
  distinguishable in the record so an operator can tell a permission decision from a
  failure, even though the asker cannot.

**Preserving what already works**

- **FR-040**: The public website, health endpoints, and dataset manifest MUST remain
  anonymously reachable and unchanged, with every existing check passing.
- **FR-041**: The existing authentication, authorization, portal, and HR behaviours MUST
  continue to pass unchanged. This feature adds surfaces; it changes none.
- **FR-042**: The dataset fingerprint MUST remain stable. Indexing derives from the
  dataset and MUST NOT alter it, exactly as credential provisioning does not.

**Phase boundary**

- **FR-043**: Agent capabilities — tool execution, planning, multi-step orchestration, and
  any write action with its human approval gate — are **out of scope** and MUST NOT be
  started until **all six of FR-032's measures pass three consecutive full evaluation
  runs**, each on **the same declared GPU class and the same pinned configuration**. Three
  consecutive runs rather than one, because a single passing run on a generative system is
  as likely to be a favourable sample as a stable capability; three is the smallest number
  that distinguishes them. A run that changed GPU class, quantization, runtime, or prompt
  version does not continue the sequence — it starts a new one. This is the constitution's phase gate,
  stated with a number so it is enforceable rather than remembered.
- **FR-043a**: The T4 class of FR-035a is a **latency reference class, not a minimum**. A
  run on a **faster GPU** is valid evidence for the quality measures — grounding, citation
  precision, correct abstention, and unauthorized exposure — but MUST NOT establish
  compliance with either latency threshold, and MUST be recorded as a **separate named
  series** that is never mixed with T4 runs in a three-run sequence. Runs on **CPU-only or
  an unidentified GPU** remain invalid for latency and for the gate (FR-035c). The gate
  requires the same **GPU class, model revision, quantization, runtime, generation prompt
  version (FR-011k), prompt budget, and concurrency** across all three runs; a faster machine proves the answers are good, not
  that the declared hardware is fast enough.
- **FR-043b**: The three-consecutive-run gate MUST require **identical evaluation-run manifest
  fields across all three runs, except the timestamp and the run identifier**. A change to the
  **generation prompt version or hash starts a new evaluation series and resets the count**,
  as does a change to any other manifest field. The comparison is over **field values**, not
  over the series label — a run that keeps an old series identity while changing a field MUST
  fail validation, which is the case a falsifying test MUST cover. The three manifests
  compared MUST come from **three distinct run directories** (FR-035j); comparing a manifest
  with itself is not a comparison.
- **FR-043c**: "Three consecutive valid runs" means **three isolated controlled-evaluation
  executions**, never three iterations inside one evaluation process. Each execution MUST
  satisfy **all six** of:

  | # | Rule |
  |---|------|
  | 1 | start only **after the preceding execution reaches a terminal result** |
  | 2 | run the **complete preflight again** (FR-035i) |
  | 3 | receive a **unique run identifier and timestamp** |
  | 4 | produce **its own immutable `run-manifest.json`, raw results, and results record** (FR-035j) |
  | 5 | compute **every metric from its own samples**, reusing **no** measurement or outcome from another run |
  | 6 | start a **fresh evaluation process with empty request and result caches** |

  **Permitted**: the three executions MAY occur on the same day and MAY use the same verified
  Colab T4 allocation and tunnel session, provided every required manifest field stays
  identical (FR-043b). **One orchestration command MAY launch the sequence**, provided it
  creates **three isolated child executions** meeting all six rules — **an in-process loop does
  not count**, however many result rows it writes.

  **Sequence breaking**: any **failed, invalid, cancelled, or configuration-mismatched**
  execution **breaks** the consecutive sequence. The next valid execution becomes **run one of
  a new sequence**. Four falsifying cases MUST be covered: (a) three result rows from one
  evaluation process; (b) reused samples or result artifacts; (c) a failed or invalid run
  between two passing runs; (d) preflight skipped on run two or three.

### Key Entities

- **Document** *(existing)*: A stored file with exactly one owning company, an owner, an
  optional department, a classification, an optional country, and a content digest. This
  feature indexes documents; it does not create or modify them.
- **Chunk** *(new)*: A retrievable passage derived deterministically from one document —
  at most 400 BGE-M3 tokens with 50 tokens of overlap (FR-007a) — carrying its text, its
  position in that document, its source document's identity, and the authorization
  attributes that decide who may retrieve it.
- **Corpus version** *(new)*: The company-scoped, per-collection checksum of the **active**
  index, published atomically after a successful complete ingestion and consumed as
  `data_version` by the cache key (FR-018a).
- **Access-context snapshot** *(new)*: The immutable description of who is asking, built
  fresh by the local API for **each turn** and valid only within it (FR-012a).
- **Evaluation execution** *(new)*: One isolated controlled-evaluation process with its own
  preflight, run identifier, manifest, raw results, samples and empty caches — the unit the
  three-run gate counts (FR-043c).
- **Run directory** *(new)*: `tests/evaluation/results/<run_id>/` — the single place one
  controlled execution's manifest, raw results and results record live together, and the unit
  the three-run gate counts distinct paths of (FR-035j, FR-043c).
- **Generation-server artefact** *(new)*: `infrastructure/colab/generation_server.ipynb`,
  provisioned and verified in Phase 0 and **reused** by Phase 4 — never created twice
  (FR-035o).
- **Evaluation-run manifest** *(new)*: The immutable per-run record of the full
  configuration a figure was produced under, referenced by that run's results record and
  compared field-by-field across the three-run gate (FR-035j, FR-043b).
- **Generation prompt** *(new)*: A versioned repository artefact, distinct from the judge
  prompt, whose version and hash are recorded per evaluation run and whose change resets the
  three-run gate (FR-011k).
- **Grounding judge** *(new)*: A separate, pinned, temperature-0 invocation of the
  generation model that scores grounding and citation precision from the answer and its
  cited spans alone, and that may not score the release gate until it agrees with a
  committed labelled calibration set (FR-032a, FR-032b).
- **Embedding** *(new)*: The vector representation of one chunk, produced by a single
  pinned model recorded alongside the index.
- **Ingestion run** *(new)*: One pass over the corpus, with per-document outcomes, counts,
  and refusal reasons — the record that makes FR-003 checkable.
- **Conversation** *(new)*: An ordered series of questions and answers belonging to one
  person in one tenant, each answer carrying its citations.
- **Citation** *(new)*: The link from a claim in an answer to the passage supporting it,
  re-authorized whenever it is opened.
- **Evaluation set** *(new)*: Fixed questions paired with expected supporting documents
  and with the personas who should and should not reach them.
- **Access context** *(existing)*: The immutable, server-built description of who is
  asking. This feature consumes it and never rebuilds it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A signed-in employee can ask a question and receive an answer carrying at
  least one resolvable citation, for 100% of evaluation questions their permitted corpus
  can answer. Timing is governed by SC-010.
- **SC-002**: **Grounding ≥ 90%** — the share of answers in which every substantive claim
  traces to a cited passage, over the fixed evaluation set. FR-019 forbids unsupported
  claims absolutely; this criterion measures how often a generative model honours that, and
  the gap between them is why the citation check exists.
- **SC-002a**: **Citation precision ≥ 90%** — the share of citations that actually support
  the claim they are attached to. A plausible citation pointing at the wrong passage is
  worse than no citation, because it survives a glance.
- **SC-003**: Unauthorized content exposure measures **zero** across the entire evaluation
  set, including every persona pairing designed to provoke a leak.
- **SC-004**: For questions whose answers exist only outside the asker's permitted set,
  100% of responses are indistinguishable from responses to questions nobody can answer.
- **SC-005**: Zero cross-tenant retrieval: no chunk belonging to one company is ever
  returned to a member of the other, across every question in the evaluation set.
- **SC-006**: Re-running ingestion over an unchanged corpus produces zero new chunks, zero
  changed chunks, and zero duplicates.
- **SC-007**: Two ingestion runs from empty, on the same corpus, produce identical chunk
  counts and identical chunk identifiers.
- **SC-008**: Every document in the seeded corpus reaches a terminal ingestion outcome,
  with zero documents left in an indeterminate state.
- **SC-009**: **Correct abstention ≥ 90%** — for questions the asker's permitted corpus
  cannot answer, the assistant declines explicitly rather than composing an answer.
- **SC-010**: **p95 local retrieval-ready source preview ≤ 2 seconds**, measured in the
  declared controlled environment of FR-035a. This is entirely local work — no tunnel is
  involved — so it is the measure that stays true if the generator changes.
- **SC-010a**: **p95 first generated answer token ≤ 5 seconds**, through the tunnel, in the
  same declared environment. Cold-start and weight-download time are excluded and reported
  separately (FR-035c).
- **SC-010b**: A stopped or failed response is marked incomplete in 100% of cases,
  including when the tunnel fails mid-stream. Both criteria above gate the agent phase; they
  do not gate ordinary shared-runner continuous integration.
- **SC-011**: Zero occurrences of document content, question text, answer text, embeddings,
  or credentials in logs, traces, metrics, or audit records, verified by automated search.
- **SC-012**: 100% of retrievals and generations produce an audit record naming the asker,
  the tenant, the **documents consulted** in the sense of FR-036a, and the decision.
- **SC-013**: The evaluation suite runs in continuous integration and blocks the change on
  failure, demonstrated by a run in which an induced leak fails the build.
- **SC-014**: Every feature 001, 002, and 003 check continues to pass unchanged, and the
  dataset fingerprint is identical before and after indexing.
- **SC-015**: The assistant surface renders every state it can reach — loading, empty,
  error, unauthenticated, expired, and access-denied — verified by automated test.
- **SC-016**: **Retrieval recall@5 ≥ 80%** — the expected supporting document appears in
  the top 5 retrieved chunks, over the fixed evaluation set.
- **SC-017**: All seven measures in FR-032 pass **three consecutive** full evaluation runs,
  on the same declared GPU class and pinned configuration, before any agent work begins.
- **SC-018**: **Ordinary continuous integration makes zero network calls** to Colab, the
  tunnel, or any external service, demonstrated by a full CI run in an environment with no
  outbound access. Retrieval and authorization are fully exercised there using committed
  fixtures and a stubbed generator.
- **SC-018a**: **Zero occurrences** of the enumerated forbidden items in FR-028a in any
  outbound generation request, verified by inspecting captured request payloads across the
  whole evaluation set.
- **SC-018b**: **100% of tunnel-unavailable and authentication-failure cases fail closed** —
  no silent fallback, no unauthenticated retry, no ungrounded answer — and produce the
  designed unavailable state while ingestion, authorization, and retrieval keep working.
- **SC-018c**: **Zero occurrences** of the tunnel URL, the service token, or the ngrok
  authtoken in logs, traces, metrics, audit records, or committed files.
- **SC-018d**: **100% of evaluation runs record** the actual GPU model, runtime, model
  revision, quantization, dependency versions, and tunnel conditions; runs on CPU-only Colab
  or an unidentified GPU are recorded as **invalid** and are excluded from the three-run
  sequence.
- **SC-020**: The Phase 0 feasibility benchmark exists and has produced a recorded result,
  with its raw timing summary, before implementation proceeds beyond the subsystem each
  threshold governs. Until then both latency thresholds are **pending evidence**, and zero
  documents describe them as met.
- **SC-021**: **Zero occurrences** of prompt text or passage text in continuous-integration
  logs, artifacts, snapshots, or failure messages, verified by automated search over the
  produced output — including the output of a **deliberately failing** payload-inspection
  assertion, which is where such text would most plausibly escape.
- **SC-022**: 100% of committed fixture sets carry a complete manifest, and a build with a
  manifest that disagrees with the configured embedder, the vector dimension, the chunker
  identity, or the source hashes **fails**, demonstrated by inducing each disagreement.
- **SC-023**: 100% of documents exceeding 2 MiB of extracted text are refused before
  chunking, with zero chunks, embeddings, or points written, and with any previously indexed
  version of that document still retrievable.
- **SC-024**: Company-wide documents (null `country` or `department_id`) are retrievable by
  every permitted caller, and 100% of the 18 null-`country` seeded documents are reachable
  by at least one persona — a figure that is zero under equality-only filtering.
- **SC-025**: Every payload attribute used by the retrieval filter has a payload index,
  verified by a check that fails when an index is missing.
- **SC-026**: 100% of generation requests respect all three passage bounds simultaneously,
  and 100% of trimmed passages end at a sentence boundary.
- **SC-027**: 100% of citations resolve to exactly the excerpt span sent to generation —
  never wider, never a different span.
- **SC-019**: Every index and every evaluation run records the embedding model revision,
  the generation model revision, the quantization, the vector dimension, the prompt
  version, and the runtime configuration; 100% of recorded quality figures are attributable
  to a specific configuration.
- **SC-028**: Every deterministic measure (FR-034a) produces **byte-identical** results
  across two runs of the same pinned configuration, demonstrated by running the
  deterministic lane twice and comparing; any difference fails the run.
- **SC-029**: The evaluator **exits nonzero before computing any metric** in 100% of the
  five preflight conditions of FR-035i, demonstrated by inducing each one; and 100% of
  evaluation outputs record the corpus fingerprint, document count, partition counts, and
  manifest checksum.
- **SC-030**: Zero occurrences of an unauthorized-candidate count or an
  authorization-exclusion count in any response, interface, or user-visible source list,
  verified by automated search; and the five terms of FR-036a appear with exactly one
  meaning each across requirements, contracts, telemetry, and audit records.
- **SC-031**: 100% of the six unavailability conditions in FR-028k — timeout at 2 seconds,
  DNS failure, TLS failure, authentication refusal, malformed response, unhealthy status —
  produce the designed unavailable state with **zero** questions or passage bodies sent and
  **zero** generator streams opened, demonstrated by inducing each condition.
- **SC-033**: 100% of chunks are within 400 BGE-M3 tokens, carry at most 50 tokens of
  overlap, and are non-empty; **zero** sentences are split except where a single sentence
  exceeds 400 tokens, and those splits fall on a clause or whitespace boundary and reproduce
  identically across runs.
- **SC-034**: The grounding judge reaches **≥ 90% agreement** with the committed calibration
  set before scoring any release-gate run; a run whose judge falls below 90% records
  grounding and citation precision as **INVALID**, demonstrated by inducing disagreement.
- **SC-035**: A cancelled or failed ingestion leaves the previous corpus-version checksum
  active in 100% of cases; an idempotent no-op ingestion produces an **identical** checksum;
  and a change to content, chunking, embedding identity, or the authorization payload
  produces a **different** one — each demonstrated separately.
- **SC-055**: 100% of first-token measurements are preceded by verification of **all seven**
  FR-035o prerequisites; a run missing any one records **`NOT RUN`** or **`INVALID`** and
  **zero** such runs produce a passing first-token row — demonstrated by withholding each
  prerequisite in turn.
- **SC-056**: Three counted runs reference **three distinct run-directory paths and three
  distinct manifest checksums**; **zero** counted sequences contain two runs sharing a results
  path, demonstrated by inducing a shared path and confirming the sequence is rejected.
- **SC-057**: Phase 0 introduces **zero** ingestion, production-indexing, retrieval-API or
  generation-integration code, and **zero** benchmark-only implementations of chunking or
  embedding — verified by a check that the benchmark imports the canonical modules and defines
  neither.
- **SC-052**: 100% of counted sequences consist of **three isolated executions**, each with a
  distinct process fingerprint, its own completed preflight, its own manifest and raw results,
  and no reused sample — demonstrated by **four falsifying cases** that each **fail**: three
  rows from one process; reused samples or artifacts; a failed or invalid run between two
  passing runs; preflight skipped on run two or three.
- **SC-053**: A failed, invalid, cancelled, or configuration-mismatched execution breaks the
  sequence in 100% of cases, and the next valid execution is counted as **run one**, never as
  run two or three — demonstrated by inducing each of the four break causes.
- **SC-054**: The three-run gate is exercised in ordinary continuous integration against
  **fixture manifests and fixture results only**, with **zero** Colab calls, **zero** ngrok
  calls and **zero** model loads.
- **SC-048**: 100% of controlled evaluation runs produce `run-manifest.json` with **all
  eleven field groups populated**, and 100% of results records reference the manifest of the
  run that produced them.
- **SC-049**: A run with any missing or runtime-disagreeing manifest field is recorded
  **`INVALID_CONFIGURATION`** in 100% of cases — demonstrated by omitting each required field
  in turn and by inducing one disagreement — and **zero** such runs advance the three-run gate.
- **SC-050**: The three-run gate accepts only runs whose manifest fields are **identical
  except timestamp and run identifier**; a run that changes **only the generation prompt hash
  while retaining the previous series identity fails validation**, demonstrated by inducing
  exactly that case.
- **SC-051**: Ordinary continuous integration validates the run-manifest schema and the
  mismatch behaviour against fixtures with **zero** Colab calls, **zero** ngrok calls and
  **zero** model executions.
- **SC-046**: 100% of client disconnects cancel the upstream provider request and complete
  local cleanup **within 2 seconds**, with **zero** continuations, retries, resumable streams,
  or background work afterwards — demonstrated by a stub-provider test that disconnects
  mid-stream, and by a falsifying case in which generation continues, which **fails**.
- **SC-047**: 100% of disconnected turns are persisted **`INCOMPLETE` with reason
  `CLIENT_DISCONNECT`** and **zero** are persisted `STOPPED`; their audit records carry turn
  id, timestamps, status, duration and cancellation-confirmation status, and **zero**
  occurrences of question, prompt, passage, partial-answer, token, URL, or credential content.
- **SC-043**: 100% of stop requests halt **token generation at the provider**, not only the
  display — demonstrated by a test that fails when generation continues after the stream
  closes; and **zero** retries, queued continuations, or background generations occur after a
  cancellation.
- **SC-044**: The local API closes the stream and completes local cleanup **within 2 seconds**
  of a stop request in 100% of cases; when upstream cancellation is unconfirmed by that
  deadline, the connection is severed, a content-free `provider_cancel_unconfirmed` status is
  recorded, and **zero bytes** of later provider output reach a response, a record, or a log.
- **SC-045**: 100% of chat turns carry a **newly built** access-context snapshot; **zero**
  snapshots are observed in use by a later turn, a regenerated answer, or a resumed
  conversation — demonstrated by a test that fails when a snapshot is reused across turns.
- **SC-036**: **Zero** occurrences of passage content, prompt content, or any derived form
  of either in persistent storage, caches, logs, traces, metrics, snapshots, test artifacts,
  exception messages, or retry queues — verified by automated search, **including on the
  abort path**, where an interrupted request leaves nothing resident after cleanup.
- **SC-037**: Permission-narrowed and genuinely empty results are identical on all five
  observable properties of FR-017a in 100% of evaluation pairs; and in the controlled
  security evaluation, over **≥ 50 warm samples per case**, the p95 time-to-terminal
  difference is **≤ max(100 ms, 20%)**.
- **SC-038**: 100% of documents failing any of FR-002b's three readable-body conditions are
  refused `EMPTY_BODY` before chunking, with zero chunks written — demonstrated by inducing
  each condition separately.
- **SC-039**: **Zero** collections ever hold two embedding identities simultaneously; a
  failed replacement index leaves the previous index and corpus checksum **byte-identical**
  to their pre-attempt state.
- **SC-040**: A runtime that cannot enforce the required deterministic settings produces a
  Phase 0 verdict of **`UNSUPPORTED_CONFIGURATION`** in 100% of cases, and **zero** documents
  describe that run as a deterministic success.
- **SC-041**: 100% of run records carry the seven FR-028o tunnel-condition fields, and
  **zero** occurrences of the tunnel hostname, full URL, ngrok token, or service credential
  appear in any record or display; two runs against the same endpoint correlate by HMAC
  fingerprint alone.
- **SC-042**: 100% of outbound generation requests are preceded by a corpus-manifest match
  against the approved synthetic fingerprint; an unknown, modified, or non-synthetic corpus
  produces **zero** outbound requests, demonstrated by mutating the corpus and confirming no
  request is constructed.
- **SC-032**: 100% of evaluation runs record their GPU series, and a run on a non-T4 GPU is
  **never** counted toward the T4 latency baseline or mixed into a T4 three-run sequence,
  demonstrated by a recorded faster-GPU run that advances no latency evidence.

## Assumptions

- **The corpus is the existing synthetic dataset.** No new document generation is in
  scope; the 105 seeded documents across both companies, with their existing
  classifications, departments, owners, and resource grants, are the corpus. This keeps
  the dataset fingerprint stable and the permission scenarios already expressible.
- **The vector store is already prepared for this.** Collections exist with tenant-scoped
  payload indexes on company, department, classification, country, owner, and document,
  and hold zero points. Feature 001 created them empty on purpose so ingestion adds content
  to a store that already filters correctly.
- **Authorization logic is reused, not rebuilt.** The five-layer decision order, the
  access context, and the audit trail exist and are verified. This feature applies them to
  a new subject — chunks — rather than introducing a second policy engine.
- **Answers are read-only.** No action this feature exposes changes a record, so
  Constitution Principle VII's approval gate remains out of scope, as it was for feature
  003. The first write action changes what this feature must satisfy.
- **Conversation history does not widen access.** Each turn is authorized independently
  against current permissions, and no content from an earlier turn is reused in a later
  answer without being re-retrieved under the current context.
- **One language.** The corpus and the questions are in English; multilingual retrieval is
  out of scope and stated in the edge cases rather than left to fail unexplained.
- **The local environment is the existing Docker Compose stack**, on the smoke profile in
  continuous integration and the full profile for demonstration. Ingestion, embedding,
  retrieval, and every authorization decision run inside it. Only generation is remote.
- **The reference machine has no discrete GPU.** Measured 2026-08-11: Intel Core i5-13420H,
  8 cores / 12 threads, 15.7 GB RAM with the Docker VM limited to 7.61 GB, and Intel UHD
  integrated graphics with no CUDA stack. This is why generation moved off the machine, and
  why the local half of the latency budget is the half that is safe to promise.
- **Colab sessions are ephemeral by nature.** Session lifetime, tunnel URL, GPU model, and
  availability all change without notice. The requirements treat that as normal operation
  rather than as an incident, which is why FR-028k–FR-028m exist.
- **The synthetic corpus is the only permitted data for this profile.** Nothing in this
  feature's remote path may carry real enterprise or personal data (FR-011h).
- **Prompt content is not user-supplied policy.** A question is data. Instructions inside
  a question do not alter what the asker may read, and this is enforced by the retrieval
  constraint rather than by asking the model to behave.
