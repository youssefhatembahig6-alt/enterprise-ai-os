# Contract: Ingestion, Chunking, Fixtures and Evaluation

**Feature**: 004-permission-aware-rag · **Date**: 2026-08-11

---

## 1. Ingestion CLI

Extends the existing seed CLI, which already owns dataset-shaped operations:

| Command | Behaviour |
|---------|-----------|
| `eaios-seed index` | ingest every eligible document; idempotent (FR-004) |
| `eaios-seed index --status` | per-document terminal states and run counts |
| `eaios-seed index --force` | re-chunk and re-embed regardless of `content_sha256` |
| `eaios-seed fixtures regenerate` | controlled-environment fixture regeneration (FR-035h) |

`index` refuses to run against a Qdrant collection whose vector dimension is not 1024, and
refuses if the `allowed_roles` payload index is absent (research R3) — a missing index
would silently make the role layer a no-op.

### Admission and refusal

Only documents present in `documents` are eligible (FR-001). A file in MinIO with no record
is never indexed. Validation order and refusal vocabulary are fixed
([data-model.md](../data-model.md)): `NOT_TEXT`, `EMPTY_BODY`, `DIGEST_MISMATCH`,
`TOO_LARGE`, `NO_CLASSIFICATION`, `STORAGE_UNREADABLE`, `EMBEDDING_FAILED`,
`INDEX_WRITE_FAILED`.

**Readable body** (FR-002b) — all three required, else `EMPTY_BODY` **atomically before
chunking**: **≥ 20 non-whitespace Unicode characters** · **≥ 1 Unicode letter or digit** ·
**valid UTF-8 after extraction and normalization**.

`TOO_LARGE` is **2 MiB of extracted, normalized UTF-8 text** (FR-002a). The refusal is
**atomic and before chunking** — no chunk, embedding, or point is written — and the
document's **previous successful index is preserved** until a replacement ingestion
succeeds. Truncation is prohibited.

### Idempotency and replacement

- `UNCHANGED` when `content_sha256` **and** `chunker_config_hash` both match the prior run.
- Changed content deletes by `document_id` filter then inserts, as one logical operation, so
  no reader sees two generations (FR-005, CHK039).
- A second run over an unchanged corpus writes zero points and reports the corpus current
  (SC-006).

---

## 2. Chunking contract

| Property | Value |
|----------|-------|
| Max chunk size | **400 BGE-M3 tokenizer tokens** (FR-007a) |
| Target overlap | **50 BGE-M3 tokenizer tokens**, complete trailing sentences where possible, never exceeding 50 |
| Strategy | document structure first, then **sentence boundaries** |
| Sentence splitting | **never**, unless one sentence alone exceeds 400 tokens — then at the nearest **preceding clause or whitespace** boundary, deterministically |
| Empty chunks | **forbidden**; a document that yields none is refused `EMPTY_BODY` |
| Identity | `sha256(document_id ‖ normalized_content_hash ‖ chunk_ordinal ‖ tokenizer_identity ‖ 400 ‖ 50 ‖ chunker_version)` → UUID (FR-007b) |
| Config | `ChunkerConfig` — both bounds included — hashed into `chunker_config_hash` |
| Determinism | identical content ⇒ identical boundaries, count, and ids, on any machine (FR-007) |

**Two tokenizers, two budgets** (FR-028b5). Chunking counts **BGE-M3** tokens; generation
**re-counts** every passage with the pinned **Qwen** tokenizer and applies its own 400-per-
passage / 2,000-total budget. The two segment differently, so a 400-token chunk is not
necessarily a 400-token passage. Reusing the chunker's count at generation time would
silently exceed the prompt budget the first-token measure depends on.

Two documents with identical text produce **different** chunk ids because `document_id`
participates — otherwise one document's permissions would serve the other's content
(CHK040).

---

## 3. Embedding fixture manifest (FR-035g)

**Scope: the committed vectors and the embedder that produced them.** It carries no
generation-prompt, judge, or provider field — those belong to the evaluation-run manifest
(§13). See §13 for the three-manifest split.

`tests/fixtures/retrieval/manifest.json`:

```json
{
  "embedding_model_id": "BAAI/bge-m3",
  "embedding_model_revision": "<exact revision>",
  "weight_checksum": "sha256:…",
  "vector_dimension": 1024,
  "quantization_runtime": "<runtime identity or null>",
  "chunker_version": "…",
  "chunker_config_hash": "sha256:…",
  "source_documents": [{"document_id": "…", "content_sha256": "…"}],
  "generator_command_version": "…",
  "generated_at": "2026-…",
  "fixture_checksum": "sha256:…"
}
```

**Ordinary CI fails** when the manifest disagrees with: the configured embedder id or
revision, the live Qdrant vector dimension, the chunker version or config hash, or any
source document's `content_sha256`. Each disagreement is induced in a test, so the check is
proven to fire rather than assumed to (SC-022).

### Regeneration (FR-035h)

Runs only in the controlled environment against the real pinned embedder; is an **explicit
command**, never automatic in CI; produces a reviewable diff; and is accepted only after the
full retrieval evaluation passes on the regenerated set.

---

## 4. Two lanes

| | Ordinary CI | Controlled evaluation |
|---|---|---|
| **Corpus** | the **committed fixture subset** only | the **complete 105-document seeded corpus** (full profile) |
| Embedder | committed fixture vectors | real BGE-M3, local CPU |
| Generator | `StubProvider` | Colab T4 over the tunnel |
| Network | **zero** outbound (SC-018) | tunnel only |
| Blocks the build | ✅ | ✗ |
| Measures | none of FR-032 | all seven |

Ordinary CI **may not report or imply a full-corpus quality figure** (FR-035b). Its recall
is a fixture-subset figure and is labelled as one; the corpus fingerprint on every output
(§10) is what makes the two impossible to confuse after the fact.

**Ordinary CI blocks the build on** (FR-035b): authorization-before-search · zero leakage ·
filter correctness · cache isolation · deterministic ingestion and chunk identifiers ·
citation re-authorization · safe telemetry · streaming and cancellation behaviour · manifest
agreement · **the three deterministic structural checks of FR-032c** (every substantive claim
cited, every citation resolves, every cited span equals the passage sent) · **the
identical-control-flow check of FR-017a** · **the readable-body validation of FR-002b** ·
**the transient-lifetime assertions of FR-013a** · **the synthetic-corpus precondition of
FR-011l** · **the end-to-end cancellation check of FR-025a** (including the falsifying case
where only the display stops) · **the per-turn access-context check of FR-012a** · **the client-disconnect check of FR-025b**
(stub provider, mid-stream disconnect, including the falsifying case where generation
continues) · **the run-manifest schema and mismatch validation of FR-035l** (fixtures only —
no Colab, no ngrok, no model execution, including the falsifying case that changes only the
generation prompt hash while retaining the previous series identity) · **the three-run gate
logic of FR-035n** (fixture manifests and fixture results only — no Colab, no ngrok, no model
load — including all four FR-043c falsifying cases).

The ten additions all have exact answers on committed fixtures. A check with an exact answer
that runs only in the lane which never blocks the build cannot stop a regression, which is why
they moved.

The stub must make streaming and cancellation genuinely exercisable — it emits tokens with
delays and honours cancellation — or those checks pass trivially (CHK214).

---

## 5. Evaluation set

`tests/evaluation/questions.yaml`. Composition constraints, so the set cannot be
accidentally vacuous (CHK099–CHK102):

- **≥ 40 questions** — below that a 90% threshold moves by more than a percentage point per
  question.
- **≥ 8 unanswerable** from any permitted corpus, for abstention.
- **≥ 8 permission-split pairs**: the same question, one persona permitted, one denied.
- **≥ 4 cross-tenant**: answerable only in the other company.
- **≥ 1 ACL-only**: reachable solely through a `document_acl` grant, plus its negative twin
  (research R5).
- **Every persona must be able to answer at least one question** — otherwise a leakage
  figure of zero is achievable by a persona who can reach nothing (CHK101).

Ground truth is authored from the corpus and reviewed, never harvested from system output
(CHK102). The set is version-controlled and versioned alongside the configuration.

### Question manifest (FR-031a)

`tests/evaluation/manifest.json` declares **every partition with its exact expected count** —
`answerable`, `unanswerable`, `permission_split_pairs`, `cross_tenant`, `acl_only`, and
`per_persona{}` — plus the **corpus fingerprint** it was authored against and its own
**checksum**. Counts are declared, never inferred: a partition sized by whatever the loader
found is always "correct" and can never be found empty.

---

## 6. Metrics

| Measure | Definition | Threshold | Class (FR-034a) |
|---------|-----------|-----------|-----------------|
| recall@5 | expected document appears among the top 5 retrieved **chunks'** documents | ≥ 80% | **deterministic** on the fixture lane |
| Grounding | answers where every substantive claim traces to a cited passage | ≥ 90% | statistical |
| Citation precision | citations that support the claim they are attached to | ≥ 90% | statistical |
| Abstention | unanswerable questions correctly refused | ≥ 90% | statistical |
| Preview p95 | local `sources` event, nearest-rank | ≤ 2 s | statistical |
| First-token p95 | first `token` event, nearest-rank | ≤ 5 s | statistical |
| Leakage | permitted-set violations | **exactly 0** | **deterministic** |

**Deterministic** measures must reproduce **exactly** for a pinned configuration; a
difference between two identical runs fails the run rather than counting as variance.
Authorization outcomes and citation resolution are deterministic on the same terms.
**Statistical** measures are met by three consecutive independently passing runs, never by
an average. Every run records **per-question outcomes** and reports **numerator /
denominator / percentage** — a percentage alone cannot be told apart from a run that
evaluated almost nothing (FR-034b).

### The judge (FR-032a–FR-032c)

Grounding and citation precision are adjudicated by the **same pinned quantized Qwen2.5 3B
Instruct, invoked separately as a judge** — never the generation response judging itself, and
never over any model's raw hidden reasoning.

| Aspect | Value |
|--------|-------|
| Prompt | `specs/004-permission-aware-rag/evaluation/grounding-judge-v1.md`, versioned; its hash recorded per run |
| Settings | temperature 0, deterministic where supported |
| Input allowlist | `question`, `answer`, `citations[]`, `cited_spans[]` — **nothing else** |
| Forbidden in input | unauthorized passages, ACL data, excluded counts, credentials, tokens |
| Output | `tests/evaluation/schemas/judge_response_v1.json` — per-claim `grounded｜not_grounded`, per-citation `supports｜does_not_support`, each with an enumerated `reason_code` |
| Recorded per run | judge model revision, quantization, runtime, **judge** prompt hash, schema version — recorded separately from `generation_prompt_version`/`generation_prompt_hash` (FR-011k) |

**Calibration gate.** Before scoring a release-gate run the judge MUST reach **≥ 90%
agreement** with `tests/evaluation/calibration/grounding_calibration.yaml` — at least 20
manually labelled positive and negative examples. Below 90%, grounding and citation precision
are recorded **`INVALID`**, are neither a pass nor a failure, and MUST NOT be reported as
having met their thresholds.

**Deterministic checks run alongside, not instead** (FR-032c): every substantive claim carries
a citation · every citation resolves · every cited span equals the passage sent to generation.
These belong to the **deterministic** class of FR-034a even though the judged measures beside
them are statistical — folding them into a judged score would hide an exact failure inside an
approximate one.

Abstention counts only refusals for the right reason (CHK097).

---

## 7. Three-run gate (FR-043)

Three consecutive `VALID` runs, all seven measures passing, same declared GPU class and
pinned configuration. A change of GPU class, quantization, runtime, or prompt version starts
a new sequence. `INVALID` runs (CPU-only or unidentified GPU) are neither pass nor fail and
do not continue the sequence (FR-035c, CHK216). Results are recorded in `evaluation_runs`
and are citable evidence, not a claim (CHK112).

**Configuration identity.** The sequence is fixed on GPU class, model revision, quantization,
runtime, **generation prompt version (FR-011k)**, prompt budget, and concurrency. A generation
prompt edit starts a new series exactly as a quantization change does — the prompt is part of
the configuration a figure is attributed to.

**Manifest identity (FR-043b).** The gate compares **every evaluation-run manifest field
except `time.run_timestamp` and the run identifier**. A change to the generation prompt
version or hash — or to any other field — **starts a new series and resets the count**. The
comparison is over **field values**, never over the series label: a run that keeps an old
series identity while changing a field **fails validation**.

**GPU series (FR-043a).** T4 16 GiB is the **latency reference class, not a floor**. A run on
a faster GPU is valid evidence for grounding, citation precision, abstention and leakage, but
**cannot** establish either latency threshold; it is recorded under a **separate series name**
and never mixed into a T4 sequence. The gate fixes GPU class, model revision, quantization,
runtime, **prompt budget** and **concurrency** across all three runs.

| Allocation | Quality evidence | Latency evidence | Counts toward the gate |
|---|---|---|---|
| Declared T4 16 GiB | ✅ | ✅ | ✅ |
| Faster GPU (e.g. L4, A100) | ✅ | ✗ | ✗ — separate named series |
| CPU-only | ✗ | ✗ | ✗ — `INVALID_NO_GPU` |
| Unidentified GPU | ✗ | ✗ | ✗ — `INVALID_UNKNOWN_GPU` |

### What counts as a run (FR-043c)

**Three isolated executions**, never three iterations inside one evaluation process.

| # | Every execution must | Detected by |
|---|----------------------|-------------|
| 1 | start after the previous reaches a **terminal result** | `started_at` vs the previous `completed_at` |
| 2 | run the **complete preflight** again | `preflight_completed_at` non-null for **this** run |
| 3 | receive a **unique run id and timestamp** | `id`, `time.run_timestamp` |
| 4 | produce its **own** manifest, raw results and results record | distinct `run_manifest_checksum`, `raw_results_checksum` |
| 5 | compute every metric from **its own samples** | `raw_results_checksum` differing between runs |
| 6 | start a **fresh process with empty caches** | distinct `process_fingerprint` |
| 7 | write into **its own run directory** `tests/evaluation/results/<run_id>/` | distinct `run_directory` (FR-035j) |

**Permitted**: same day, same verified T4 allocation, same tunnel session — provided every
required manifest field stays identical (FR-043b). **One orchestration command may launch the
sequence**, provided it spawns **three isolated child executions**. A loop inside one process
does **not** count, however many rows it writes.

**Breaking the sequence**: any **failed, invalid, cancelled or configuration-mismatched**
execution breaks it. The next valid execution is **run one of a new sequence** — "consecutive"
means consecutive, not "three passes among some attempts".

**Four falsifying cases**, each of which MUST fail:

| | Case |
|---|---|
| a | three result rows produced by **one** evaluation process |
| b | **reused** samples or result artifacts between runs |
| c | a failed or invalid run **between** two passing runs |
| d | preflight **skipped** on run two or three |

---

## 8. Telemetry and audit boundaries

**Vocabulary (FR-036a)** — five terms, never interchanged:

| Term | Definition |
|------|------------|
| candidate | an authorized point eligible **before** ranking |
| retrieved passage | a ranked chunk returned by retrieval |
| generation passage | an authorized, budgeted excerpt **actually serialized** to the generator |
| cited passage | a generation passage the completed answer references |
| **documents consulted** | distinct `document_id` values among **generation passages** |

User-visible source information may report retrieved, consulted and cited documents. It may
**never** report unauthorized candidates or exclusion counts.

Audited (FR-036): asker, tenant, `question_digest`, documents consulted, decision, outcome.
**Never** recorded (FR-037): document content, question text, answer text, embeddings,
credentials, the tunnel URL.

Telemetry answers, without content (FR-038): retrieval duration, generation duration,
candidates considered, candidates excluded by authorization, and whether the answer was
refused for lack of support. The excluded-count is **operator-facing only** and never
reaches a response — the audience distinction FR-017 and FR-038 need in order not to
conflict (CHK171).

---

## 9. Failure recovery

| Failure | Recorded as | Recovery |
|---------|-------------|----------|
| Run interrupted | rows left non-terminal | detectable by query; the next run re-processes them. A run whose rows are non-terminal at completion is a **run failure** (FR-003), not a silent partial |
| Vector write rejected mid-run | `INDEX_WRITE_FAILED` | the run continues to the next document; the failed one retries next run |
| Embedding fails | `EMBEDDING_FAILED` | no partial chunks written for that document |
| Oversize document | `TOO_LARGE` | atomic, pre-chunking; the **previous index survives** (FR-002a) |
| Repeated failure across runs | reason recorded each run | no automatic escalation; the per-document history is the signal (CHK047 remains open by design) |

**Index rollback** is a re-run: chunk identity is deterministic (FR-007), so rebuilding from
an unchanged corpus reproduces byte-identical ids and vectors, which is what makes rollback
a recovery rather than a fresh guess.

---

## 10. Evaluation preflight (FR-035i)

Before **any** metric is computed, the evaluator exits **nonzero** on:

| # | Condition | Why it is fatal rather than a warning |
|---|-----------|---------------------------------------|
| 1 | total question count is zero | every metric becomes `0/0`, which renders as a perfect score |
| 2 | a required partition is empty | e.g. abstention 100% over zero unanswerable questions |
| 3 | actual counts differ from the manifest (§5) | the set loaded is not the set that was reviewed |
| 4 | a required metric would divide by zero | same as 1, reached one partition at a time |
| 5 | an expected source document is absent from the 105-document corpus | ground truth points outside the corpus under test |

Every evaluation output records **corpus fingerprint, document count, partition counts, and
manifest checksum**. That record is what makes a fixture-lane figure impossible to quote
later as a full-corpus one.

A warning would not do: a warning inside a passing run is not read, and by the time a metric
has been computed the misleading number exists and can be cited.

---

## 11. Corpus version and `data_version` (FR-018a)

The cache key's `data_version` is the **active corpus manifest checksum**, company-scoped and
per-collection, held in `corpus_versions` ([data-model.md](../data-model.md)).

**Derivation**, in fixed order — company id · collection · active document ids and
normalized-content hashes · chunk ids and chunk-content hashes · chunker version and
`chunker_config_hash` · embedding model identity, revision and weight checksum · vector
dimension · **authorization-relevant payload schema version**.

| Rule | Behaviour |
|------|-----------|
| Publication | atomic, **only after** the complete replacement index succeeds |
| Failed / cancelled run | nothing published; the **previous** checksum stays active |
| Idempotent no-op run | the **same** checksum — the cache stays warm |
| Content, chunking, embedding identity, or authorization-payload change | a **different** checksum |
| Old-key cache entries | become **unreachable**; they are never enumerated and deleted |

The last row is the deliberate one: destructive deletion is the operation most likely to fail
halfway and leave the inconsistency it was meant to prevent. Entries under a retired checksum
expire on their own TTL and are never read again.

Including the **authorization payload schema version** is the input that is easiest to omit
and matters most — a change to how permissions are encoded changes *who can retrieve what*
without changing a single document, and a checksum blind to it would serve pre-change answers
to post-change permissions.

---

## 12. Embedding-identity replacement (FR-011i)

A change to the embedding **model revision, weight checksum, vector dimension, tokenizer
identity, or runtime identity** requires a **complete replacement index**.

| Rule | Behaviour |
|------|-----------|
| Mixed identities | **Never active.** Similarity between two embedding models is meaningless, so a mixed collection returns confidently wrong neighbours |
| During the rebuild | the **previous** index and its corpus-version checksum stay active and keep serving |
| On success | the replacement is published atomically (§11) and the previous generation is retired |
| On failure or cancellation | the previous index and checksum are left **untouched** |

This is what "invalidate the index" means as an outcome (FR-011): **replace-then-publish**,
never mark-and-serve. A stale-marked index that still answers is the state this rule exists to
make unreachable.

---

## 13. The three manifests (FR-035m)

This feature defines **exactly three**, with **disjoint scopes**. None may absorb another's
fields.

| Manifest | Path | Scope | Kind | Requirement |
|----------|------|-------|------|-------------|
| Embedding fixture | `tests/fixtures/retrieval/manifest.json` | committed vectors + the embedder that produced them | **input** | FR-035g · §3 |
| Question partition | `tests/evaluation/manifest.json` | the question set + declared partition counts | **input** | FR-031a · §5 |
| **Evaluation run** | `tests/evaluation/results/<run_id>/run-manifest.json` | the full configuration of **one** controlled run, in that run's own directory | **evidence** | FR-035j |

### Evaluation-run manifest (FR-035j)

Eleven required field groups: generation prompt (version + SHA-256) · generation model
(identifier + pinned revision) · generation runtime (quantization + runtime identity) · judge
(prompt version/hash + model identity) · embedding model (identifier + revision + checksum) ·
corpus (fingerprint + active `data_version`) · chunker (config hash) · question set (manifest
checksum) · provider (profile + GPU series) · command (evaluation command version) · time (run
timestamp).

**One directory per run**: `tests/evaluation/results/<run_id>/` holds this run's manifest, raw
results and results record together. **Immutable** once written, and **referenced by the run's
results record** by full path and checksum — a figure and the configuration that produced it
travel together, or the figure is not attributable. Three counted runs reference **three
distinct paths and three distinct checksums**; ordinary-CI fixtures live in a **separate
committed fixtures directory**, never under `results/`.

### Validation (FR-035k, FR-035l)

| Condition | Outcome |
|-----------|---------|
| a required field is **missing** | `INVALID_CONFIGURATION` — neither pass nor fail |
| a field **disagrees with the configured runtime** | `INVALID_CONFIGURATION` |
| manifest complete and agreeing | the run proceeds to its measures |

Disagreement is checked against the **live configuration**, not against the previous run: a
manifest cannot be correct merely by being consistent with itself.

**Ordinary CI validates the schema and the mismatch behaviour against fixtures** — every
required field present, every absent field rejected, every disagreement producing
`INVALID_CONFIGURATION` — **without contacting Colab or ngrok and without running either
model**. The validation that guards the controlled lane is itself checkable in the offline one.
