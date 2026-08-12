# Implementation Plan: Permission-Aware Knowledge Retrieval and Grounded Answers

**Branch**: `004-permission-aware-rag` | **Date**: 2026-08-11 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/004-permission-aware-rag/spec.md`

**Reconciled** 2026-08-11 against the final clarified specification, then again after the
gap-closure clarification session (R16–R20). Zero open markers. Every settled decision below
is carried forward. **No evaluation and no benchmark has been run; no figure in this plan is
a result.**

## Summary

Index the 105 seeded text documents into the existing 1024-dimension Qdrant `documents`
collection, retrieve under an authorization constraint applied **inside** the search, and
compose grounded, cited answers with a pinned quantized Qwen2.5 3B Instruct on a Colab T4
behind an authenticated HTTPS tunnel. Embeddings, session verification, access-context
construction, retrieval, citation re-authorization, auditing, and caching all stay local.
The browser reaches only the existing web→API boundary.

**The first execution phase is the FR-035f feasibility benchmark, and it gates the
subsystems it governs.** Neither latency threshold has been measured. This plan asserts
nothing about whether either can be met.

The largest finding of Phase 0 stands: feature 001 already built the retrieval filter, and
it is **untested and currently defective** ([research.md](research.md) R1, R3, R4).

### Settled decisions carried forward

| Decision | Where it lives |
|----------|----------------|
| Local pinned BGE-M3, 1024 dimensions | FR-011 · R1 |
| Colab T4 / ngrok **development-and-evaluation** profile behind a replaceable interface | FR-011a, FR-011d, FR-011e · R8 |
| Authorization-before-search and citation re-authorization, both local | FR-013, FR-022 · contracts §3 |
| **2 MiB** atomic ingestion limit, previous index preserved | FR-002a · R15 |
| Null `country`/`department_id` means **company-wide** | FR-014a · R4 |
| **Every** filter field indexed and tested, `allowed_roles` included | FR-014b · R3 |
| 5 passages · 400 tokens each · 2,000 total, pinned tokenizer | FR-028b1 · R14 |
| Exact citation excerpt spans | FR-028b3 · R14 |
| Ordinary CI on deterministic committed fixtures | FR-035b · R10 |
| Controlled full-model evaluation, separate lane | FR-035d · R10 |
| Phase 0 latency benchmark as the first gate | FR-035f · R12 |
| Three consecutive valid passing runs before agent work | FR-043 |
| Deterministic vs statistical measure classes | FR-034a, FR-034b · R16 |
| Full 105-document corpus for the controlled lane; fixture subset for CI | FR-035d, FR-035b · R17 |
| Evaluation preflight — five conditions, nonzero exit before any metric | FR-031a, FR-035i · R17 |
| Five-term retrieval vocabulary; "documents consulted" = generation passages | FR-036a · R18 |
| Generator health check: local, 2-second deadline, six causes → one state | FR-028k · R19 |
| T4 is the latency **reference class**; faster GPUs are a separate series | FR-043a · R20 |
| Chunks: **400** BGE-M3 tokens, **50** overlap, never split a sentence | FR-007a, FR-007b · R21 |
| Judge: same pinned model, separate invocation, **≥ 90%** calibration gate | FR-032a–FR-032c · R22 |
| `data_version` = **active corpus manifest checksum**, published atomically | FR-018a · R23 |
| Passage/prompt content: request-scoped memory only, released at the terminal event | FR-013a · R24 |
| Indistinguishability: 5 identical properties + ≥ 50 samples, p95 Δ ≤ max(100 ms, 20%) | FR-017a · R25 |
| Readable body: ≥ 20 non-whitespace chars, ≥ 1 letter/digit, valid UTF-8 | FR-002b · R26 |
| Embedding-identity change ⇒ **complete replacement index**, never mixed | FR-011i · R26 |
| Runtime cannot enforce determinism ⇒ **`UNSUPPORTED_CONFIGURATION`** | FR-011j · R26 |
| Tunnel provenance: 7 fields + keyed HMAC, never the address | FR-028o · R26 |
| Generation prompt versioned, distinct from the judge, resets the series | FR-011k · R27 |
| FR-032c structural checks **block ordinary CI** | FR-032c, FR-035b · R27 |
| Colab outbound requires an approved synthetic corpus-manifest match | FR-011l · R28 |
| Stop is **end-to-end**: upstream propagation, 2 s local close, no continuation | FR-025a · R29 |
| "Per request" = **one turn**; the access-context snapshot dies with it | FR-012a · R30 |
| Client disconnect = **implicit cancellation**, recorded `INCOMPLETE｜CLIENT_DISCONNECT` | FR-025b · R31 |
| **Three** manifests with disjoint scopes; the run manifest is evidence, not input | FR-035j–FR-035m · R32 |
| Gate compares manifest **field values**, never the series label | FR-043b · R32 |
| Three runs = **three isolated executions**, not in-process iterations | FR-043c · R33 |
| Generation server is **Phase 0 provisioning**; Phase 4 reuses the artefact | FR-035o · R34 |
| One **run directory** per execution: `results/<run_id>/` | FR-035j · R34 |
| Phase 0 scope bounded; BGE runtime owned by `packages/core` + root env | FR-035p · R34 |
| The gate's own logic is tested offline on fixture records | FR-035n · R33 |

## Technical Context

**Language/Version**: Python 3.12 (API, core, worker, seed); TypeScript 5.6 / Next.js 15.5 (web)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.0, Alembic, Celery, Qdrant client, a BGE-M3 runtime, httpx (tunnel transport), React 19

**Storage**: PostgreSQL (runtime state, RLS-scoped), Qdrant (chunk vectors, 1024-dim cosine), Redis (permission-scoped cache), MinIO (document bytes)

**Testing**: pytest with `unit｜integration｜security｜e2e` markers; Vitest + Playwright for web

**Target Platform**: Docker Compose on Linux/WSL2; Colab T4 for the generation profile only

**Project Type**: Web application — existing monorepo, extended, not restructured

**Performance Goals**: local retrieval-ready preview p95 ≤ 2 s; first generated token p95 ≤ 5 s. **Both are acceptance thresholds and are unmeasured (FR-035e).**

**Constraints**: authorization pre-search, never post-filter; zero unauthorized exposure; ordinary CI fully offline; no browser→tunnel path; dataset fingerprint unchanged; synthetic corpus only

**Scale/Scope**: 105 documents, 2 tenants, ~10 personas, ≥ 40 evaluation questions, 6 new tables, 6 new API routes, 1 new portal surface

## Constitution Check

### Initial gate (pre-design)

| Principle | Result |
|-----------|--------|
| **I. Tenant isolation** | **PASS** — `company_id` unconditional and first; RLS on all six new tables |
| **II. Deterministic authorization** | **PASS** — five layers decide; the generator receives passages only |
| **III. No unauthorized data in context** | **PASS with caveat** — mechanism correct in design, **untested and defective** (R1, R3, R4) |
| **IV. Grounded answers only** | **PASS** — FR-019–FR-021 |
| **V. Facts from systems of record** | **PASS** — FR-023 |
| **VI. Agent tool contracts** | **N/A** — no agent work (FR-043) |
| **VII. Human approval gates** | **N/A** — read-only feature |
| **VIII. Test-first for security** | **PASS** — Phase 1 opens with the missing filter tests |
| **IX. Reproducible synthetic data** | **PASS** — fingerprint untouched (FR-042) |
| **X. Audit by default** | **PASS** — FR-036 with FR-037's content prohibition |

### Post-design re-evaluation

The design added three things that change a gate's standing:

- **Principle III's caveat is now bounded by a dated requirement, not a promise.** FR-014b
  requires every filter field to be indexed *and tested* before ingestion, and the ingestion
  CLI refuses to run when an index is missing (contracts §1). The defect can no longer be
  carried silently past the point where content exists.
- **Principle IV strengthened.** FR-028b3's exact-excerpt-span citation closes a hole the
  first design left: a citation resolving to a wider passage than the model received would
  show a reader context the answer was never grounded in.
- **Principle X unchanged but sharper.** The operator/asker audience split (contracts §8)
  resolves the apparent conflict between FR-038's excluded-count telemetry and FR-017's
  prohibition on revealing withheld counts. FR-036a now fixes the vocabulary that split is
  written in, so "documents consulted" cannot mean one thing in an audit record and another
  in a response.
- **Principle VIII reinforced by the evaluation preflight.** FR-035i makes a vacuous
  evaluation fail rather than score perfectly. Test-first is worth little if the suite can
  report success over zero cases, which is the failure a `0/0` ratio produces silently.
- **Principle III now has a lifetime, not an adjective.** FR-013a bounds FR-013's "even
  transiently" with two endpoints and an enumerated sink list, including the abort path. The
  principle was previously assertable but not checkable.
- **Principle IV's structural half moved into the blocking lane.** FR-032c's three exact
  checks now block ordinary CI (FR-035b) instead of living only in the lane that never blocks
  a build.
- **Principle II's "per request" now has a boundary.** FR-012a fixes it at one turn and makes
  reuse detectable through `conversation_turns.permission_fingerprint`, so a snapshot
  outliving its turn is visible in the data rather than an absence someone must prove.
- **Principle III extended to cancellation, including the unobserved kind.** FR-025a requires
  abort cleanup to release request-scoped content and discard post-cancellation provider
  output. FR-025b extends the same handling to a client disconnect — the case with the longest
  potential content residency, because no browser remains to notice that anything is still
  running.

**No violations require justification.** The Principle III caveat remains a defect to fix
in Phase 1, not a deviation to accept.

## Project Structure

### Documentation (this feature)

```
specs/004-permission-aware-rag/
├── spec.md · plan.md · research.md · data-model.md · quickstart.md
├── contracts/{retrieval-and-chat.md, ingestion-and-fixtures.md}
└── checklists/  # 7 domain checklists + requirements.md, 218 items
```

### Source Code (repository root)

```
packages/core/src/eaios_core/
├── authz/filters.py     # FIX: null→company-wide shape (R4); every field indexed (R3)
├── chunking/            # NEW deterministic chunker + ChunkerConfig
└── keys.py              # REUSE cache_key unchanged (R2)

apps/api/src/eaios_api/
├── retrieval/           # NEW search service — consumes qdrant_filter
├── generation/          # NEW provider interface, ColabTunnelProvider, StubProvider
└── chat/                # NEW routers, SSE, citation re-authorization

scripts/seed/src/eaios_seed/{indexing,fixtures}/   # NEW
services/worker/src/eaios_worker/tasks/            # ingestion as a tenant-attributed job
apps/web/app/portal/(authed)/assistant/            # NEW surface in the existing shell
tests/{unit,integration,security,e2e}/ · tests/fixtures/retrieval/ · tests/evaluation/
```

**Structure Decision**: extend, do not add an application. Retrieval and generation live in
`apps/api` because they must hold the access context, which only the API builds. The chunker
lives in `packages/core` because the API and the seed CLI need identical chunk identity, and
`scripts/seed` may not import from `apps/api` (spec 001 FR-001a).

## Execution phases and dependency gates

Each phase states what must be true before it starts. A gate is a precondition, not a
suggestion.

### Phase 0 — feasibility benchmark ⟨no predecessor⟩

**Harness plus the canonical benchmark-support libraries** — the chunker and embedder the
measurement needs, and nothing else (FR-035p). Phase 0 also **provisions the generation
server** it measures (FR-035o): the `infrastructure/colab/generation_server.ipynb` artefact,
pinned weights with revision and checksum verified, the authenticated HTTPS endpoint, the
service token, a **verified** T4, the runtime and quantization identity, a health endpoint,
and streaming first-token protocol compatibility. **Phase 4 reuses that artefact and contract
rather than creating either again.** Pinned BGE-M3 on the declared local CPU environment; pinned quantized Qwen2.5
3B Instruct on a **verified** T4; the production prompt budget (5 passages, ≤ 2,000 tokens);
5 warm-ups; ≥ 30 measured; nearest-rank p95. Records both figures, the raw timing summary,
and a provenance record (FR-028n).

**Outcome gate**: if the **preview** figure fails, Phase 2 (embedding/ingestion) does not
start. If the **first-token** figure fails, Phase 4 (generation/streaming) does not start.
Either failure is recorded; no threshold is relaxed without a specification clarification
and checklist revalidation. **This plan makes no claim about the outcome.**

### Phase 1 — authorization foundation ⟨no predecessor; runs in parallel with Phase 0⟩

Test-first, and deliberately independent of the benchmark so the known defects are fixed
regardless of its result.

1. Write the missing `qdrant_filter` unit tests (R1), falsifiable by key deletion.
2. Rebuild the filter for null→company-wide semantics (FR-014a, R4).
3. Add **every** missing payload index, `allowed_roles` included, with a test that fails
   when an index is absent (FR-014b).
4. Wire `cache_key` with the cross-permission test written first (R2).

**Exit gate**: filter tests pass; every filter field is indexed; no point has yet been
written.

### Phase 2 — ingestion ⟨requires Phase 1 exit + Phase 0 preview pass⟩

State machine, deterministic sentence-aware chunker (**400 / 50**, FR-007a), 2 MiB atomic
refusal with prior-index preservation, embedding, indexing, idempotency, replacement,
**corpus-version checksum computed and published atomically** (FR-018a), manifest generation;
migrations 1 and 4.

### Phase 3 — retrieval and citations ⟨requires Phase 2⟩

Authorization-constrained search, the `sources` preview event, excerpt-span capture,
citation resolution and re-authorization, audit records.

### Phase 4 — generation and streaming ⟨requires Phase 3 + Phase 0 first-token pass⟩

Provider interface, stub, Colab provider, passage budgeting and sentence-boundary trimming,
SSE, **end-to-end cancellation with the 2-second close deadline and the `provider_cancel_*`
outcomes** (FR-025a), **client-disconnect handling** (FR-025b), **per-turn access-context
snapshots** (FR-012a), unavailability states, the test-only interceptor; migration 2.

### Phase 5 — evaluation ⟨requires Phase 4⟩

Question set and its partition manifest (FR-031a), the **evaluation-run manifest with its
eleven field groups and `INVALID_CONFIGURATION` validation** (FR-035j–FR-035l), the **judge
prompt, response schema and calibration set with its ≥ 90% agreement gate**
(FR-032a–FR-032c), **preflight guard first** (FR-035i) so
the harness cannot produce a figure before it can refuse to, deterministic/statistical
classification (FR-034a), per-question outcome recording with numerator and denominator
(FR-034b), seven measures, provenance and GPU series (FR-043a), the two CI lanes;
migration 3.

**Exit gate**: the preflight fails on all five conditions; the deterministic lane reproduces
exactly across two runs; every output carries corpus fingerprint, document count, partition
counts and manifest checksum. **No evaluation has been run, and this plan records no
result.**

### Phase 6 — agent capabilities ⟨requires three consecutive valid passing runs⟩

**Deferred. Not started, and not task-generated, until FR-043's gate passes** — three
**isolated executions** (FR-043c), not three rows.

## Rollout, recovery and failure modes

Absent from the first plan; added in reconciliation.

### Rollout

Additive only. Every new route, table, and surface is new; no existing behaviour changes,
which is why SC-014 requires every feature 001–003 check to pass unchanged. Ingestion is
run by an operator command, not automatically on deploy, so a stack can start with an empty
index and serve the existing portal exactly as today.

### Failure modes and responses

| Failure | Response | Requirement |
|---------|----------|-------------|
| Missing payload index at ingestion | CLI refuses to run | FR-014b |
| Document > 2 MiB | atomic refusal before chunking; **previous index preserved** | FR-002a |
| Embedding fails mid-document | `EMBEDDING_FAILED`; no partial chunks written | FR-002, FR-003 |
| Vector-store write rejected mid-run | `INDEX_WRITE_FAILED`; run continues; document non-terminal state is a run failure | FR-003 |
| Run interrupted | non-terminal rows survive and are detectable by query; the next run re-processes them | FR-003 |
| Manifest disagrees with embedder/dimension/chunker/sources | ordinary CI **fails** | FR-035g |
| Tunnel unavailable / auth fails | **fail closed**; designed unavailable state; retrieval still serves sources | FR-028j, FR-028k, FR-028l |
| Tunnel drops mid-stream | explicit incomplete terminal event; partial never presented as complete | FR-028m |
| Colab allocates CPU-only or an unknown GPU | evaluation run recorded **INVALID** — neither pass nor fail | FR-035c |
| Colab allocates a **faster** GPU | valid for quality, invalid for latency; recorded in a **separate named series** | FR-043a |
| Health check hangs rather than refusing | 2-second deadline expires → *unavailable*, same as an explicit refusal | FR-028k |
| Evaluation set loads with an empty partition | preflight **exits nonzero before any metric** | FR-035i |
| Question counts disagree with the manifest | preflight **exits nonzero**; the set loaded is not the set reviewed | FR-031a, FR-035i |
| A deterministic measure differs between identical runs | **run fails** — that is a defect, not variance | FR-034a |
| A single sentence exceeds the 400-token chunk budget | split at the nearest preceding clause or whitespace boundary, deterministically | FR-007a |
| Structural splitting yields no usable text | refused `EMPTY_BODY`; an empty chunk is never written | FR-007a, FR-002 |
| Judge agreement with the calibration set < 90% | grounding and citation precision recorded **INVALID** — neither pass nor fail | FR-032b |
| Ingestion cancelled after some chunks are written | **no checksum published**; the previous corpus version stays active | FR-018a |
| Embedding identity changes | **complete replacement index**; previous index and checksum serve until it is published; failure leaves them untouched | FR-011i |
| Document body below the readable floor | refused `EMPTY_BODY` before chunking | FR-002b |
| Request aborted mid-stream | abort cleanup releases passage and prompt content exactly as the terminal event would | FR-013a |
| Runtime cannot enforce deterministic settings | Phase 0 verdict **`UNSUPPORTED_CONFIGURATION`** — no fallback, no relaxed tolerance | FR-011j |
| Corpus manifest does not match the approved synthetic fingerprint | **fail closed before the outbound request is constructed** | FR-011l |
| Generation prompt edited mid-sequence | new series; the three-run gate resets | FR-011k |
| Stop request received | emission halts, cancellation propagates upstream, stream closed and cleaned up **within 2 s** | FR-025a |
| Upstream cancellation unconfirmed at 2 s | connection **severed**; content-free `provider_cancel_unconfirmed` recorded; later output discarded | FR-025a |
| Follow-up, regeneration, or resumed conversation | a **new** access context is built; history re-authorized under it | FR-012a |
| Client disconnects mid-stream | upstream cancelled and content released exactly as an explicit stop; turn persisted `INCOMPLETE｜CLIENT_DISCONNECT`, **never** `STOPPED`; no terminal event required | FR-025b |
| Run-manifest field missing or disagreeing with the runtime | run recorded **`INVALID_CONFIGURATION`** — neither pass nor fail; advances no gate | FR-035k |
| A first-token prerequisite is absent at Phase 0 | row stays **`NOT RUN`** or is recorded **`INVALID`** — never a pass | FR-035o |
| Two runs would write the same results path | rejected — each run owns `results/<run_id>/` | FR-035j, FR-043c |
| Only the generation prompt hash changes, series identity retained | **validation fails** — the gate compares field values, not the label | FR-043b |
| Three result rows share one `process_fingerprint` | rejected — three iterations are not three runs | FR-043c |
| A run reuses another's samples or artifacts | rejected — matching `raw_results_checksum` | FR-043c |
| A failed or invalid run lands between two passing runs | sequence **breaks**; the next valid execution is run one | FR-043c |
| Preflight skipped on run two or three | sequence invalid — `preflight_completed_at` is null | FR-035i, FR-043c |
| Generator cites a passage it was never sent | citation dropped by the API before the browser sees it | FR-028c |

### Recovery and rollback

- **Index rollback**: re-run ingestion from the previous dataset state; chunk identity is
  deterministic (FR-007), so a rebuild is byte-identical rather than merely equivalent.
- **Migration rollback**: every migration has a `down`, exercised by the existing
  `tests/integration/test_migrations.py`.
- **Credential rotation**: a new Colab session mints a new service token; the previous one
  stops working, which is the intended outcome (FR-028h).
- **Fixture rollback**: fixtures are committed, so reverting the commit reverts the CI
  baseline; regeneration is an explicit reviewable command (FR-035h).
- **Nothing to roll back in the dataset**: indexing never writes to it, and the fingerprint
  is asserted unchanged (FR-042, SC-014).

## Complexity Tracking

| Deviation | Why necessary | Simpler alternative rejected because |
|-----------|---------------|--------------------------------------|
| Generation leaves the machine | reference hardware has no discrete GPU | measured: Intel UHD integrated, no CUDA, 7.61 GB Docker VM |
| A second network dependency (tunnel) | the only route to a GPU in this profile | a hosted inference API — a third-party data path for a corpus restricted to synthetic data |
| Two evaluation lanes | correctness must block every build; quality cannot run on 4 vCPU | one lane — either CI carries a GPU-bound model, or correctness stops gating |
| Filter returns a structured shape, not a flat mapping | null must mean company-wide, which equality cannot express | flat equality — measured to make 18 of 105 documents unreachable by anyone |
| Two evaluation-run series, T4 and faster-GPU | a faster GPU proves quality but not the T4 latency baseline | one series — the gate's latency figure would then describe no particular machine |

## Open items blocking task generation

**None.** The three items that once stood here are requirements: FR-002a (2 MiB), FR-014a/b
(null semantics, index completeness), FR-028b1–b3 (passage budget, excerpt spans).

Two things remain outstanding; **neither blocks task generation**:

- **The Phase 0 benchmark has not been run** (FR-035e). Its tasks can be written; Phases 2
  and 4 must not begin until it reports.
- **CHK130 and CHK192** stay *requirement resolved, implementation evidence pending*.

**Checklist status after the Phase 0 provisioning session**: 122 / 218 resolved (120, 119, 118,
117, 106, 97, 90, 82, and 26 at the start of reconciliation). **Every `[Ambiguity]` and `[Conflict]`
item is closed, and no open item is a specification gap.** The 96 that stay open are
implementation-quality questions the design cannot answer on paper — they are answered by
tests, migrations and measurements, not by this plan.

---

## Task-list reconciliation

The task graph was regenerated after the Phase 0 provisioning, run-directory, packaging,
import-boundary, resource-exclusion and dependency decisions recorded above. The ordering,
reference, coverage, parallel-safety, packaging, preflight and per-run-directory defects
identified during review were reconciled in the current `tasks.md`.

**`tasks.md` is the authoritative execution graph.** No historical task numbers are retained
in this section: the task list has been renumbered, so task numbers are unsafe as durable
references from another document. Read the requirement or the decision here, and find the
tasks that carry it in `tasks.md`.

**No benchmark and no evaluation has been run.** The gates remain evidence-driven and begin
as `NOT RUN`.
