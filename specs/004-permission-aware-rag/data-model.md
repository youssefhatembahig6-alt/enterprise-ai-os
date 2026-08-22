# Data Model: Permission-Aware Knowledge Retrieval

**Feature**: 004-permission-aware-rag · **Date**: 2026-08-11 · **Spec**: [spec.md](spec.md)

Existing entities are listed only where this feature reads or extends them. Nothing here
changes the generated dataset: every new table is runtime state, so the fingerprint is
untouched (FR-042, SC-014).

---

## Existing, read-only to this feature

| Entity | Used for |
|--------|----------|
| `documents` | the corpus. `id`, `company_id`, `department_id`, `owner_id`, `classification`, `country`, `content_sha256`, `storage_key`, `byte_size` all become chunk payload or ingestion inputs |
| `document_acl` | layer 4. 4 grants, all `USER`/`READ` (research R5) |
| `users`, `departments`, `companies`, `roles`, `user_roles` | the access context, already built by feature 003 |
| `audit_logs` | extended with new action values; the table is unchanged |
| MinIO objects | document bytes, read during ingestion by `storage_key` |

---

## New: PostgreSQL

### `ingestion_runs`

One row per pass over the corpus (FR-006).

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid PK | |
| `company_id` | uuid FK → companies | tenant-scoped like every table (Principle I) |
| `started_at` / `completed_at` | timestamptz | `completed_at` null while running |
| `embedding_model_revision` | text | FR-011b |
| `chunker_version` | text | |
| `chunker_config_hash` | text | |
| `data_version` | text | consumed by `cache_key` (research R2) |
| `documents_seen` / `_ingested` / `_unchanged` / `_refused` | int | reconcilable against `documents` (FR-006) |
| `status` | enum `RUNNING｜COMPLETED｜FAILED` | |

### `ingestion_document_states`

One row per document per run — the state machine of research R7 (FR-003).

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid PK | |
| `run_id` | uuid FK → ingestion_runs ON DELETE CASCADE | |
| `company_id` | uuid FK | |
| `document_id` | uuid FK → documents | |
| `state` | enum `PENDING｜VALIDATING｜CHUNKING｜EMBEDDING｜INDEXING｜INGESTED｜UNCHANGED｜REFUSED` | |
| `refusal_reason` | enum, nullable | closed vocabulary (CHK044): `NOT_TEXT｜EMPTY_BODY｜DIGEST_MISMATCH｜TOO_LARGE｜NO_CLASSIFICATION｜STORAGE_UNREADABLE｜EMBEDDING_FAILED｜INDEX_WRITE_FAILED`. `EMPTY_BODY` covers all three readable-body conditions of FR-002b |
| `chunk_count` | int, nullable | |
| `preserved_prior_index` | bool | true when a `TOO_LARGE` (or other pre-chunking) refusal left an earlier successful index in place (FR-002a) |
| `content_sha256` | text | what `UNCHANGED` is decided against |
| `updated_at` | timestamptz | |

Unique on `(run_id, document_id)`. A row still in a non-terminal state when its run
completes is the FR-003 failure condition, and is detectable by query rather than by
inference.

### `corpus_versions`

The active-index checksum consumed as `data_version` (FR-018a). One active row per
`(company_id, collection)`.

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid PK | |
| `company_id` | uuid FK → companies | scoping — the checksum is company-scoped, never global |
| `collection` | text | `documents`; the `code` collection stays empty this feature |
| `checksum` | text | the corpus manifest checksum — the value `cache_key` consumes |
| `is_active` | bool | exactly one true row per `(company_id, collection)` |
| `published_at` | timestamptz | set at publication, never at computation |
| `run_id` | uuid FK → ingestion_runs, nullable | the run that produced it |
| `inputs_digest` | jsonb | the eight derivation inputs, recorded so a checksum can be explained rather than only compared |

Partial unique index on `(company_id, collection) WHERE is_active`. Publication is a single
transaction: deactivate the previous row and insert the new active one **after** the complete
replacement index succeeds. A failed or cancelled run publishes nothing, so the previous row
stays active and every cache entry keyed on it stays valid.

**Derivation inputs** (FR-018a), in fixed order: company id · collection · active document
ids and normalized-content hashes · chunk ids and chunk-content hashes · chunker version and
`chunker_config_hash` · embedding model identity, revision and weight checksum · vector
dimension · authorization-relevant payload schema version.

### `conversations` and `conversation_turns`

| `conversations` | Type | Notes |
|-----------------|------|-------|
| `id` | uuid PK | |
| `company_id`, `user_id` | uuid FK | scoping for FR-026 |
| `created_at`, `last_turn_at` | timestamptz | |

| `conversation_turns` | Type | Notes |
|----------------------|------|-------|
| `id` | uuid PK | |
| `conversation_id` | uuid FK ON DELETE CASCADE | |
| `company_id` | uuid FK | |
| `question_digest` | text | **not the question text** — FR-037 |
| `answer_state` | enum `COMPLETE｜STOPPED｜INCOMPLETE｜REFUSED_UNSUPPORTED｜GENERATION_UNAVAILABLE` | FR-025, FR-025a, FR-028l, FR-028m |
| `incomplete_reason` | enum `CLIENT_DISCONNECT｜TUNNEL_FAILED`, nullable | set only on an `INCOMPLETE` turn. `INCOMPLETE` now has two causes — a mid-stream tunnel failure (FR-028m) and an implicit cancellation by client disconnect (FR-025b) — and telemetry and FR-039 both need them distinguishable |
| `provider_cancel_status` | enum `CONFIRMED｜UNCONFIRMED`, nullable | set on a `STOPPED` turn **and on an `INCOMPLETE｜CLIENT_DISCONNECT` turn** — both cancel upstream under the same deadline (FR-025a, FR-025b). `UNCONFIRMED` is the content-free `provider_cancel_unconfirmed` record of FR-025a — the connection was severed at the 2-second deadline and later provider output was discarded |
| `permission_fingerprint` | text | the fingerprint of the **turn's own** access-context snapshot (FR-012a). Recorded per turn so a snapshot reused across turns is detectable rather than assumed absent |
| `answer_text` | text, nullable | the answer is shown to its owner, so it is stored; it is never logged (FR-037) |
| `created_at` | timestamptz | |

### `turn_citations`

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid PK | |
| `turn_id` | uuid FK ON DELETE CASCADE | |
| `company_id` | uuid FK | |
| `document_id` | uuid FK → documents | re-authorized on open (FR-022) |
| `chunk_id` | uuid | the passage, resolved against the index |
| `excerpt_start` / `excerpt_end` | int | character offsets of the **exact span sent to generation** (FR-028b3); a citation resolves to this span, never to the wider chunk |
| `claim_ordinal` | int | which claim it supports (FR-020) |

### `evaluation_runs`

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid PK | |
| `started_at`, `completed_at` | timestamptz | |
| `validity` | enum `VALID｜INVALID_NO_GPU｜INVALID_UNKNOWN_GPU｜INVALID_ABORTED｜INVALID_UNSUPPORTED_CONFIGURATION｜INVALID_CONFIGURATION` | FR-035c — invalid is neither pass nor fail. The last value mirrors the Phase 0 `UNSUPPORTED_CONFIGURATION` verdict (FR-011j) for a run whose runtime cannot enforce deterministic settings |
| `generation_prompt_version`, `generation_prompt_hash` | text | the versioned generation prompt (FR-011k) — **distinct from the judge prompt**; a change starts a new series and resets the three-run gate |
| `run_manifest_path`, `run_manifest_checksum` | text | the **evaluation-run manifest** this figure was produced under (FR-035j). A results record without a resolvable manifest reference is not attributable evidence |
| `process_fingerprint` | text | established at process start, unique per execution. Three rows sharing one fingerprint are **three iterations, not three runs** (FR-043c) — this is what makes falsifying case (a) detectable rather than assumed absent |
| `preflight_completed_at` | timestamptz | null means the preflight did not complete for **this** execution; the gate rejects the sequence (FR-035i, FR-043c) |
| `run_directory` | text | `tests/evaluation/results/<run_id>/` — the one place this run's manifest, raw results and record live. Two rows sharing it are **one execution writing twice**, not two runs (FR-035j, FR-043c) |
| `raw_results_path`, `raw_results_checksum` | text | this execution's own samples, inside its run directory. Two rows sharing a checksum are **reused artifacts** (FR-043c), falsifying case (b) |
| `gpu_model`, `runtime`, `model_revision`, `quantization`, `dependency_versions` | text/jsonb | FR-028n |
| `tunnel_conditions` | jsonb | exactly the seven FR-028o fields: `provider_profile`, `gpu_series`, `ngrok_region`, `protocol_tls_version`, `rtt_p50_ms`, `rtt_p95_ms`, `health_outcome`, plus `endpoint_hmac` — a **keyed HMAC fingerprint** for run correlation. **Never** the hostname, full URL, ngrok token, or service credential |
| `judge_model_revision`, `judge_quantization`, `judge_runtime` | text | the judge is the same model, invoked separately (FR-032a) |
| `judge_prompt_hash`, `judge_schema_version` | text | which prompt and which response schema produced the judged figures |
| `judge_calibration_agreement` | numeric | agreement with the committed labelled set; **< 0.90 ⇒ grounding and citation precision are `INVALID`** (FR-032b) |
| `judge_calibration_set_checksum` | text | which calibration set that agreement was measured against |
| `gpu_series` | text | the named series this run belongs to. Only the declared **T4** series carries latency evidence; a faster GPU is a separate series, valid for quality only (FR-043a) |
| `corpus_fingerprint`, `document_count` | text, int | which corpus produced the figures — the fixture subset and the full 105 can never be confused afterwards (FR-035i) |
| `partition_counts`, `manifest_checksum` | jsonb, text | the evaluation set actually loaded, against the manifest it was reviewed as (FR-031a) |
| `recall_at_5`, `grounding`, `citation_precision`, `abstention`, `preview_p95_ms`, `first_token_p95_ms`, `leakage_count` | numeric | the seven measures (FR-032) |
| `*_numerator`, `*_denominator` | int | every ratio carries both; a percentage alone cannot be told from a run over almost nothing (FR-034b) |
| `passed` | bool | all seven within threshold |

Consecutive `VALID` runs with `passed = true`, the **same `gpu_series`**, and an unchanged
configuration are what FR-043's three-run gate counts — and only when they are **three
isolated executions** (FR-043c): distinct `process_fingerprint`, each with its own
`preflight_completed_at`, its own `run_manifest_checksum`, and its own
`raw_results_checksum`. Any `validity != VALID`, `passed = false`, or configuration mismatch
between two counted runs **breaks** the sequence; the next valid execution is run one of a new
one.

### `evaluation_question_results`

One row per question per run — the per-question outcomes FR-034b requires, without which an
aggregate cannot be audited.

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid PK | |
| `run_id` | uuid FK → evaluation_runs ON DELETE CASCADE | |
| `question_id` | text | from `questions.yaml` |
| `partition` | text | the declared partition it counted toward (FR-031a) |
| `measure_outcomes` | jsonb | per-measure pass/fail for this question |
| `measure_class` | enum `DETERMINISTIC｜STATISTICAL` | FR-034a |

A **deterministic** measure differing between two runs of the same pinned configuration is a
**failure**, detectable by comparing these rows — not variance to be tolerated.

---

## New: Qdrant payload (`documents` collection)

Vectors: 1024, cosine — already provisioned. One point per chunk.

| Payload field | Source | Indexed today | Purpose |
|---------------|--------|:-------------:|---------|
| `company_id` | document | ✅ | Principle I, unconditional |
| `department_id` | document | ✅ | attribute layer |
| `country` | document, nullable | ✅ | attribute layer |
| `classification` | document | ✅ | ceiling |
| `owner_id` | document | ✅ | ownership |
| `document_id` | document | ✅ | joins, replacement, deletion |
| **`allowed_roles`** | roles granted by policy + ACL | ❌ **must be added** | role layer — **research R3** |
| `chunk_index` | chunker | — | citation position |
| `chunk_text` | chunker | — | the quotable passage (FR-008), ≤ 400 BGE-M3 tokens (FR-007a) |

**Two payload changes are required before the first point is written**: add the
`allowed_roles` keyword index — and every other index the filter uses (FR-014b) — and
populate the payload so a **null document attribute means company-wide**, never
*matching nobody* and never *matching everything* (FR-014a). Every index must be tested;
an unindexed filter attribute is a layer that may silently fail to constrain.

---

## New: file artefacts

### The three manifests, and why they are three (FR-035m)

| Manifest | Path | Scope | Kind |
|----------|------|-------|------|
| **Embedding fixture manifest** | `tests/fixtures/retrieval/manifest.json` | the committed vectors and the embedder that produced them | **input** — committed and reviewed |
| **Question partition manifest** | `tests/evaluation/manifest.json` | the question set and its declared partition counts | **input** — committed and reviewed |
| **Evaluation-run manifest** | `tests/evaluation/results/<run_id>/run-manifest.json` | the full configuration of **one** controlled run, in its own directory | **evidence** — produced by a run, never edited |

The scopes are **disjoint by requirement**: no generation-prompt, judge, or provider field
appears in the first; no model or runtime field appears in the second. Merging them was
rejected because an input is reviewed before a run and evidence is written by it — a file that
is both cannot be trusted as either.

### Embedding fixture manifest — `tests/fixtures/retrieval/manifest.json`

Nine fields, exactly as FR-035g enumerates: `embedding_model_id`,
`embedding_model_revision`, `weight_checksum`, `vector_dimension`, `quantization_runtime`,
`chunker_version`, `chunker_config_hash`, `source_documents[] {document_id, content_sha256}`,
`generator_command_version`, `generated_at`, `fixture_checksum`.

CI compares it against the configured embedder, the live Qdrant dimension, the chunker
identity, and the source hashes; disagreement fails the build (FR-035g, SC-022).

### Evaluation set — `tests/evaluation/questions.yaml`

Per question: `id`, `text`, `expected_document_ids[]`, `personas_permitted[]`,
`personas_denied[]`, `answerable` (bool), `partition`. Composition constraints are stated in
the contract, not left to whoever writes it (CHK100, CHK101).

### Prompt artefacts

| Artefact | Contents |
|----------|----------|
| `specs/004-permission-aware-rag/evaluation/generation-prompt-v1.md` | the versioned **generation** prompt (FR-011k); its version and hash are recorded per run, and a change resets the three-run gate |
| `specs/004-permission-aware-rag/evaluation/grounding-judge-v1.md` | the versioned **judge** prompt (FR-032a) — a separate artefact with an independent change discipline |

### Judge artefacts (FR-032a, FR-032b)

| Artefact | Contents |
|----------|----------|
| `specs/004-permission-aware-rag/evaluation/grounding-judge-v1.md` | the versioned judge prompt; its hash is recorded on every run |
| `tests/evaluation/schemas/judge_response_v1.json` | the strict output schema — per-claim `grounded｜not_grounded`, per-citation `supports｜does_not_support`, each with an enumerated `reason_code` |
| `tests/evaluation/calibration/grounding_calibration.yaml` | ≥ 20 manually labelled positive and negative examples, with the label author and date |

The judge receives **only** `question`, `answer`, `citations[]`, and `cited_spans[]`. A test
asserts the serialized judge request against that allowlist, exactly as FR-037a does for the
generation request.

### Evaluation-run manifest — `tests/evaluation/results/<run_id>/run-manifest.json`

**One directory per run** (FR-035j). Each controlled execution owns
`tests/evaluation/results/<run_id>/`, holding its own immutable `run-manifest.json`, its own
raw-results file and its own results record. Ordinary-CI fixtures live in a **separate
committed fixtures directory** and never under `results/`. Referenced by `evaluation_runs`
(`run_manifest_path`, `run_manifest_checksum`); three counted runs carry **three distinct
paths and three distinct checksums**. Eleven required field groups (FR-035j):

| # | Field group | Contents |
|---|-------------|----------|
| 1 | `generation_prompt` | `version`, `sha256` |
| 2 | `generation_model` | `identifier`, `revision` |
| 3 | `generation_runtime` | `quantization`, `runtime_identity` |
| 4 | `judge` | `prompt_version`, `prompt_hash`, `model_identity` |
| 5 | `embedding_model` | `identifier`, `revision`, `weight_checksum` |
| 6 | `corpus` | `fingerprint`, `data_version` |
| 7 | `chunker` | `config_hash` |
| 8 | `question_set` | `manifest_checksum` |
| 9 | `provider` | `profile`, `gpu_series` |
| 10 | `command` | `evaluation_command_version` |
| 11 | `time` | `run_timestamp` |

A missing field, or a field disagreeing with the live configuration, makes the run
`INVALID_CONFIGURATION` (FR-035k). The three-run gate compares **every field except
`time.run_timestamp` and the run identifier** (FR-043b).

### Question partition manifest — `tests/evaluation/manifest.json`

Declares **every partition with its exact expected count** (`answerable`, `unanswerable`,
`permission_split_pairs`, `cross_tenant`, `acl_only`, `per_persona{}`), the **corpus
fingerprint** it was authored against, and its own **checksum** (FR-031a). The evaluator's
preflight compares actual counts against it and **exits nonzero before computing any
metric** on disagreement, emptiness, a zero total, a zero denominator, or an expected
document absent from the 105-document corpus (FR-035i).

---

## State transitions

**Ingestion** (FR-003, R7):

```
PENDING → VALIDATING ─┬→ REFUSED(reason)                      [terminal]
                      ├→ UNCHANGED                            [terminal]
                      └→ CHUNKING → EMBEDDING → INDEXING → INGESTED  [terminal]
```

**Corpus version** (FR-018a):

```
run starts → checksum computed over the replacement index
           ├→ run fails or is cancelled → nothing published; previous row stays active
           └→ complete replacement index succeeds → publish atomically
                                                    (deactivate previous, insert active)
```

A no-op run recomputes the same checksum and publishes nothing new, because the value is
unchanged — which is why the cache stays warm across an idempotent re-run.

An **embedding-identity change** (revision, weight checksum, dimension, tokenizer, or runtime
identity) takes the same path but always produces a **complete replacement index**: the
previous index and checksum stay active until the replacement is fully built and published, and
**two embedding identities are never active in one collection** (FR-011i).

**Answer** (FR-025, FR-028l, FR-028m):

```
                    ┌→ COMPLETE
RETRIEVING → GENERATING ─┼→ STOPPED                 (person cancelled — FR-025a)
        │           └→ INCOMPLETE              (tunnel failed mid-stream)
        ├→ REFUSED_UNSUPPORTED                 (permitted corpus cannot answer)
        └→ GENERATION_UNAVAILABLE              (health check failed before streaming)
```

`GENERATION_UNAVAILABLE` is reached **before** streaming begins (FR-028k), which is what
keeps it distinct from `INCOMPLETE`.

**Disconnect** (FR-025b) — an implicit cancellation, recorded as its own reason:

```
client stream detected dead
  → cancel upstream · reject later output · release request-scoped content
  → INCOMPLETE, incomplete_reason = CLIENT_DISCONNECT
     (provider_cancel_status set exactly as in the STOPPED path below)
```

**No terminal SSE event is emitted** — the connection is gone. The server-side state and the
content-free audit record are authoritative. The turn is **never** `STOPPED`: the person did
not ask to stop, and the record must not claim an intent they never expressed.

**Cancellation** (FR-025a) — `STOPPED` is reached through one path with two outcomes:

```
stop received → stop emitting · propagate upstream · release request-scoped content
              ├→ provider confirms within 2 s  → STOPPED, provider_cancel_status = CONFIRMED
              └→ no confirmation by 2 s        → sever connection, discard later output
                                               → STOPPED, provider_cancel_status = UNCONFIRMED
```

Both outcomes close the stream within the same 2-second deadline; they differ only in what is
known about the provider. A `STOPPED` turn is recorded, audited, and **not resumable** — a
resumed answer is a new turn under a new access context (FR-012a).

---

## Migrations

Reversible, one per concern, in `apps/api/alembic/versions/`:

1. `ingestion_runs`, `ingestion_document_states`, `corpus_versions` + enums, including the
   partial unique index enforcing one active corpus version per `(company_id, collection)`
2. `conversations`, `conversation_turns`, `turn_citations`
3. `evaluation_runs`, `evaluation_question_results` + the measure-class enum
4. RLS policies and tenant-scope grants on all eight tables, matching the existing pattern

Every `down` path drops what its `up` created, and the existing
`tests/integration/test_migrations.py` exercises reversibility (spec 001 FR-007a). Qdrant
payload-index creation is idempotent provisioning, not a migration, and runs before any
point exists.
