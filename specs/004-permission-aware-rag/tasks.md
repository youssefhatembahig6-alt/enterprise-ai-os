---

description: "Task list for feature 004 — Permission-Aware Knowledge Retrieval and Grounded Answers"
---

# Tasks: Permission-Aware Knowledge Retrieval and Grounded Answers

**Input**: Design documents from `specs/004-permission-aware-rag/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Amended 2026-08-11 (seventh, targeted).** Closes **E1** (T044's Qdrant exclusion), **E2**
(a failing-first provisioning test at T020), **E3** (the `benchmark-phase0` entry-point chain)
and **E4** (the BGE runtime kept as a direct `eaios-core` dependency, with a static packaging
test at T007), and hardens PG-E's PostgreSQL isolation rule.

**Regenerated 2026-08-11 (sixth amendment).** Closes every defect in plan.md's *Known
task-list defects* register (D1–D4 and items 1–11) and the ten correction groups that
accompanied it. The specification now carries **115 FRs and 64 SCs**; **96** checklist items
remain open. Phase structure and the three evidence gates are unchanged; every ID and every
narrative reference was rebuilt from the task lines themselves rather than carried forward.

**Tests**: **MANDATORY and written FIRST.** Constitution Principle VIII names authorization
decisions, tenant isolation, and RAG retrieval and grounding as strict-cycle areas. Every
phase writes its security tests, **runs them, and records the failure**, before the
enforcement code exists.

**A test that cannot fail is not a test.** Where a boundary is absent when its test runs, the
test **fails on absence** (T114) and is **re-run against the real component** once it exists
(T123). Where a check could be satisfied by its own harness, it runs in a **scrubbed
subprocess** (T006) or against **fixtures** (T036).

**Falsification is a first-class task type.** **FALSIFY** tasks break a **named file**,
confirm a **named test** fails, and restore that file byte-identical. **Every FALSIFY target
is created by an earlier task.**

**Constitution-driven categories**: tenant scoping and cross-tenant isolation · deterministic
authorization · **pre-retrieval filtering** · audit-record writes · reversible migrations and
deterministic seeds · Docker Compose integration · frontend responsive / accessible / loading
/ empty / error / access-denied states. Not touched: agent tool declarations and approval-gate
wiring — Phase 6 only, and gated.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallel-safe — **different files _and_ different mutable resources** (Qdrant
  service, PostgreSQL database, Redis namespace, MinIO bucket, container, port, evidence file,
  model runtime). A task that mutates a production collection or the shared schema is never
  `[P]`; a test needing a store creates a **uniquely named disposable one** and removes it.
- **[Story]**: US1–US5, mapping to the user stories in [spec.md](spec.md)
- Exact file paths in every description; traceability in parentheses at the end

## Path conventions

uv + pnpm monorepo: `packages/core/src/eaios_core/`, `apps/api/src/eaios_api/`, `apps/web/`,
`packages/ui/src/`, `scripts/seed/src/eaios_seed/`, `services/worker/src/eaios_worker/`,
`tests/` and `benchmarks/` at the repository root.

**Packaging reality.** There is **no `[tool.uv.workspace]`**. The root `pyproject.toml` sets
`package = false`; first-party code resolves through `[tool.pytest.ini_options] pythonpath`
under pytest, and the four sub-manifests are installed by **Docker images**. Third-party
dependencies are therefore **installed**, never path-resolved (T005).

**`specs/004-permission-aware-rag/verification.md` does not exist yet.** T044 creates it from
the feature 003 format; every later task updates that same file.

## Execution order

```
make up && make seed && make credentials     stack, full profile
   ↓
generation-server provisioning (T019, T021)  weights · endpoint · token · verified T4 · runtime · health · protocol
   ↓
Phase 0 measurement (T029, T030)             preview + first-token
   ↓  preview row = PASS
Phase 2 production ingestion (T056+)         eaios-seed index
```

**No task requires `eaios-seed index` before the preview gate.** Phase 2 is gated by the
benchmark, so the benchmark builds its own temporary index instead (FR-035a).

## Phase gates

| Phase | Entry gate | Exit gate |
|-------|-----------|-----------|
| **0 — feasibility** | none | both figures recorded with raw timings; `benchmarks/phase0/GATE.md` written |
| **1 — authorization** | none — **parallel with Phase 0**, except the Qdrant exclusion below | filter tests pass; every filter field indexed; worker/seed boundary proven; **no point yet written** |
| **2 — ingestion** | Phase 1 exit **AND** Phase 0 **preview** row = `PASS` | corpus indexed; idempotent; manifest agrees |
| **3 — retrieval** | Phase 2 exit | authorization-constrained search; exact citation spans; empty outcomes indistinguishable |
| **4 — generation** | Phase 3 exit **AND** Phase 0 **first-token** row = `PASS` | streaming, cancellation, disconnect, tunnel failure; structural checks already blocking |
| **5 — evaluation** | Phase 4 exit | preflight refuses all five vacuity conditions; per-run directories; three-run gate exercised offline |
| **6 — agents** | **three consecutive `VALID` passing runs recorded** (FR-043, FR-043c) | out of scope beyond the gate |

**No benchmark and no evaluation has been run.** Every gate row starts `NOT RUN`; T036 fails
the build if a user-facing document contradicts that.

---

## Phase 0 — Feasibility gates

**Purpose**: establish whether the two latency thresholds are reachable, before code is
written that assumes they are. Reports; never gates ordinary CI.

**Scope (FR-035p)**: Phase 0 contains **benchmark-support canonical chunker and embedder work
and nothing more**. It implements no ingestion, no production indexing, no retrieval API and
no generation integration — those stay gated behind their own phases.

**Bare-checkout boundary**: §0A–§0D run on a clean checkout with **no stack**. §0E onward need
`make up && make seed && make credentials` (the real targets in `Makefile`; `eaios-seed seed`
defaults to `--profile full`), and §0E additionally needs Colab. T018 enforces the boundary.

### 0A — Licence, model identity, repository hygiene

- [X] T001 Create `docs/models.md` recording, per pinned model: repository id, **exact revision SHA**, weight checksum, licence and its restrictions, runtime/quantization identity — BGE-M3 (MIT) and Qwen2.5-3B-Instruct (Qwen RESEARCH LICENSE, **non-commercial**) — plus a "how weights reach a clean installation" section with the download command, the checksum verification step, and the statement that no hosted inference runtime is introduced (FR-011, FR-011a, FR-011c, FR-011e, FR-011g · CHK073–CHK077)
- [X] T002 [P] Add `models/`, `*.gguf`, `*.safetensors`, `*.bin` to `.gitignore` and write `tests/unit/test_no_weights_committed.py` asserting no tracked file matches a weight pattern (FR-011g · CHK072)
- [X] T003 [P] Record the declared local environment (CPU, cores, RAM, Docker VM limit, absence of CUDA) in `benchmarks/phase0/ENVIRONMENT.md`, copied from spec Assumptions, and the declared Colab class (T4 16 GiB — the **latency reference class**, not a floor) (FR-035a, FR-043a · CHK124, CHK190)

### 0B — Packaging and the clean-checkout import proof

**The Make target is created here, first** — no later task edits a target that does not yet
exist. Third-party dependencies are **installed**, not path-resolved.

- [X] T004 Create the `benchmark-phase0` target in `Makefile`, documented as **not** part of `make test` and **never** run in CI. It **executes `python -m benchmarks.phase0`**, which resolves to `benchmarks/phase0/__main__.py` — the entry point that calls preflight first (T024) — and sets the first-party import paths **explicitly from the checked-in list**: `packages/core/src`, `apps/api/src`, `services/worker/src`, `scripts/seed/src`, repository root. No ambient variable, no cwd assumption (FR-035b, FR-035f · SC-018)
- [X] T005 Add the **exact pinned BGE-M3 runtime dependency** to **both** `pyproject.toml` (root development and benchmark environment) and `packages/core/pyproject.toml`, keeping **one identical version pin** in both, then update `uv.lock`. It is a **direct `eaios-core` dependency by decision**, not an accident of layout: the **API** embeds retrieval queries, the **seed** embeds documents during ingestion, and the **worker** executes tenant-attributed indexing — all three legitimately need it, and all three install `packages/core`. **`uv.lock` covers the root environment; Docker resolves the identical exact pin from `packages/core/pyproject.toml`.** **No `benchmarks/pyproject.toml`** — nothing installs from it (FR-011c, FR-035p · CHK087)
- [X] T006 Write `tests/unit/test_benchmark_imports.py` as a **subprocess** check that pytest's configured `pythonpath` cannot satisfy: strip inherited `PYTHONPATH`, `chdir` to a temporary directory **outside the repository**, invoke the `benchmark-phase0` target by **explicit repository path**, and assert both `eaios_core.chunking` and `eaios_core.embedding.bge_m3` import — failing if the third-party BGE runtime is unavailable. It additionally verifies the **exact entry-point chain**: the target runs `python -m benchmarks.phase0`, that module resolves to `benchmarks/phase0/__main__.py`, and no other entry point is reachable from the target (FR-011c, FR-035f · SC-018)
- [X] T007 Write `tests/unit/test_packaging_layout.py` as a **static** check over the repository: `apps/api/Dockerfile`, `services/worker/Dockerfile` and `scripts/seed/Dockerfile` each install `./packages/core`; `packages/core/pyproject.toml` declares the BGE-M3 runtime; and its pinned version is **character-identical** to the version resolved for that package in the root `uv.lock`. A drift between the two fails the build (FR-011c, FR-035p · CHK087)
- [X] T008 **FALSIFY** — remove the BGE-M3 pin from `packages/core/pyproject.toml` (edited T005), confirm **`tests/unit/test_packaging_layout.py`** fails, then restore `packages/core/pyproject.toml` byte-identical. The named test is the packaging one **by correction**: removing a pin is a *manifest* edit, and only a check that reads the manifest can see it. `tests/unit/test_benchmark_imports.py` tests *importability*, which a manifest edit cannot change without a re-sync — and uninstalling the runtime is far too destructive for a falsification step. The runtime half is falsified separately and non-destructively inside that file, by hiding `torch` and `transformers` from a child process's meta-path so `missing_runtime()` must name them

### 0C — Canonical chunker and embedder (bare checkout, no stack)

- [X] T009 [P] [US5] Write failing tests in `tests/unit/test_chunker_determinism.py`: identical content produces identical boundaries, counts and identifiers across two runs and across a changed locale and process order (FR-007 · SC-007 · CHK053)
- [X] T010 [P] [US5] Write failing tests in `tests/unit/test_chunk_identity.py`: identity is `sha256(document_id ‖ normalized_content_hash ‖ chunk_ordinal ‖ tokenizer_identity ‖ 400 ‖ 50 ‖ chunker_version)` → UUID; two documents with identical text produce different ids; changing the tokenizer identity, either bound, or the chunker version changes every id **even when the text does not** (FR-007b · CHK040, CHK054)
- [X] T011 [P] [US5] Write failing tests in `tests/unit/test_chunk_boundaries.py`: every chunk ≤ **400 BGE-M3 tokens**; overlap ≤ **50 tokens** as complete trailing sentences where possible; document structure respected wherever present; **no sentence split** except where one alone exceeds 400 tokens, then at the nearest preceding clause or whitespace boundary reproducibly; **no empty or whitespace-only chunk** (FR-007a, FR-009 · SC-033 · CHK056, CHK058)
- [X] T012 [US5] Implement `packages/core/src/eaios_core/chunking/config.py` — `ChunkerConfig` with `chunker_version`, structure-first strategy, `max_tokens = 400`, `overlap_tokens = 50`, the BGE-M3 tokenizer identity, and a `chunker_config_hash` covering all of them (FR-007a, FR-007b · contracts IC §2)
- [X] T013 [US5] Implement the sentence-aware chunker in `packages/core/src/eaios_core/chunking/chunker.py` — structure first, then sentence boundaries within the 400-token budget with 50-token overlap, and the clause/whitespace fallback — until the chunking tests **T009 (determinism), T010 (identity) and T011 (boundaries)** pass (FR-007, FR-007a, FR-008, FR-009)
- [X] T014 **FALSIFY** — introduce a dict-ordering dependence into `packages/core/src/eaios_core/chunking/chunker.py` (**created T013**), confirm `tests/unit/test_chunker_determinism.py` fails, then restore that file byte-identical
- [X] T015 [P] [US5] Write failing tests in `tests/unit/test_embedding_identity.py` — **pure and in-memory**: the produced vector dimension is **1024** and the recorded revision and weight checksum match `docs/models.md`. It uses **no Qdrant client and no preview builder**, so §0C stays bare-checkout and no cycle forms with §0G (FR-011, FR-011b · CHK061, CHK077)
- [X] T016 [P] [US5] Write failing tests in `tests/security/test_no_download_at_request_time.py`: with weights absent, `packages/core/src/eaios_core/embedding/bge_m3.py` **raises at construction**, and a query embedding never initiates a download or any outbound connection (FR-011c, FR-011f · CHK071)
- [X] T017 [US5] Implement `packages/core/src/eaios_core/embedding/bge_m3.py` — local-only pinned embedder, no network path, exposing the revision and weight checksum it loaded — until the embedding tests **T015 (identity) and T016 (no download)** pass (FR-011c, FR-011f)

### 0D — The bare-checkout boundary, enforced

- [X] T018 Write `tests/unit/test_phase0_bare_checkout.py`: no module under `packages/core/src/eaios_core/chunking/`, `packages/core/src/eaios_core/embedding/`, or the §0A–§0D benchmark modules imports **PostgreSQL, MinIO, Qdrant, Docker or any application store client**. Model-runtime imports are permitted; **model download and network access are not**. The test fails on the first forbidden import rather than at runtime (FR-011c, FR-035p · SC-057)

### 0E — Generation-server provisioning (before the first-token measure)

**The server is provisioned here, not in Phase 4** (FR-035o). Phase 4 **reuses** this artefact
and contract-tests it; it does not create either again — a gate cannot consume the output of
the phase it gates.

- [X] T019 [US5] Create the generation-server artefact `infrastructure/colab/generation_server.ipynb`: reads `NGROK_AUTHTOKEN` from **Colab Secrets only**, serves the pinned quantized Qwen2.5 3B Instruct, exposes the health endpoint, streams tokens, honours `cancel()`, and mints the service token per session (FR-011a, FR-028e, FR-028h, FR-035o · R11, R34)
- [X] T020 [US5] Write failing tests in `tests/unit/test_server_provisioning.py` — **network-free**, against a fake provisioning probe: **withhold each of the seven FR-035o prerequisites separately** (pinned Qwen revision/checksum · authenticated HTTPS ngrok endpoint · service token · verified T4 · runtime and quantization identity · health endpoint · streaming first-token protocol) and prove that **each single absence prevents measurement and forbids `PASS`**, naming the missing prerequisite; plus **one positive case with all seven present** that permits measurement. Seven negatives and one positive, so neither a blanket refusal nor a blanket acceptance can satisfy the suite (FR-035o · SC-055)
- [X] T021 [US5] Implement provisioning verification in `benchmarks/phase0/server_provisioning.py` covering **all seven** FR-035o prerequisites and recording the result: pinned Qwen **revision and weight checksum verified** · authenticated **HTTPS ngrok endpoint** · **service token** present in ignored environment configuration · **verified T4** (never unidentified or CPU-only) · **runtime and quantization identity** recorded · working **health endpoint** · **streaming first-token protocol compatibility**. Any absent prerequisite is reported by name — until **T020** passes (FR-011a, FR-011b, FR-011f, FR-028e, FR-028g, FR-028k, FR-035c, FR-035o · SC-055)

### 0F — Stack preflight, invoked rather than merely implemented

- [X] T022 [US5] Write failing tests in `tests/unit/test_phase0_preflight.py` for **ordering and failure behaviour**: preflight runs **before** the embedder is imported or constructed, before weights are read, before a Qdrant client is created and before any collection exists; each missing prerequisite exits **nonzero naming it**; and a satisfied preflight permits exactly one subsequent construction (FR-001, FR-001a, FR-011f, FR-035a · SC-018)
- [X] T023 [US5] Implement `benchmarks/phase0/preflight.py`: PostgreSQL, MinIO and Qdrant reachable · active seed profile is **`full`** · **exactly 105 text documents** available · **code corpus excluded** · every required source object **readable** from MinIO · local **BGE weights present with the pinned revision and checksum verified** (FR-001, FR-001a, FR-011f, FR-035a · SC-018)
- [X] T024 [US5] Wire preflight into `benchmarks/phase0/__main__.py` as the **first** call, with **lazy imports after it** — the embedder, the Qdrant client and the preview builder are imported only once preflight has passed — until T022 passes (FR-035a, FR-035f · SC-018)
- [X] T025 **FALSIFY** — move embedder construction above the preflight call in `benchmarks/phase0/__main__.py` (**created T024**), confirm `tests/unit/test_phase0_preflight.py` fails on the ordering assertion, then restore that file byte-identical

### 0G — The corpus-representative preview index

- [X] T026 [US5] Implement the preview-index builder in `benchmarks/phase0/preview_index.py` as a **context manager that always drops its collection, including on failure**: a **uniquely named temporary Qdrant preview collection** populated from **all 105 seeded full-profile text documents** using the pinned **BGE-M3 tokenizer**, the settled **400/50** bounds, the deterministic boundary rules (`packages/core/src/eaios_core/chunking/`), **real 1024-dimension BGE-M3 vectors** (`packages/core/src/eaios_core/embedding/bge_m3.py`), the **production distance metric**, and the **complete production authorization payload with every index**. It reproduces the **expected full-corpus chunk count and payload distribution** — never one point per document — and **never** uses `scripts/seed/src/eaios_seed/indexing/runner.py` or a production collection (FR-007a, FR-010, FR-011, FR-014a, FR-014b, FR-035a · SC-010)
- [X] T027 [US5] Implement pre-measurement validation in `benchmarks/phase0/preview_index.py` and record `benchmarks/phase0/results/preview-index-manifest.json` with the source fingerprint, chunker configuration hash, embedding identity, point count, payload distribution, collection schema and collection name. **All six checks run before any sample**: 105 documents represented · no code or binary content · nonzero chunk count matching the manifest · every point carrying all required authorization attributes · vector dimension and distance metric matching production · every filter field indexed (FR-001a, FR-010, FR-011, FR-014b, FR-035a · SC-025)
- [X] T028 [US5] Add to `benchmarks/phase0/README.md`: the harness is **not a test**, is never invoked by CI, and its preview figure is a **corpus-representative benchmark over an isolated temporary index** — **not** evidence that the Phase 2 production ingestion path has run. **No figure exists yet** (FR-035e, FR-035f · SC-020)

### 0H — The two measures

- [X] T029 [US5] Implement the preview benchmark in `benchmarks/phase0/preview_benchmark.py`: enter the T026 builder, complete **all indexing and all 5 warm-ups before the first measured sample**, then measure **only** the declared source-preview path — pinned BGE-M3 query embedding plus one authorization-filtered search against that stable temporary collection, ending where the `sources` event would be emitted — and drop the collection on the way out. A **missing, empty, incomplete, malformed or production-shape-mismatched** index makes the preview gate **fail**; it may **never** produce a passing latency row (FR-035a, FR-035f · SC-010 · CHK186)
- [X] T030 [US5] Implement the first-token benchmark in `benchmarks/phase0/first_token_benchmark.py`: a five-passage production-size prompt to the **T021-verified** server, clock ending at the first `token` event. It **refuses to record `PASS`** when **any** of the seven FR-035o prerequisites is absent — the row stays `NOT RUN` or is recorded `INVALID` (FR-035o · SC-010a, SC-055 · CHK187)
- [X] T031 [P] Implement `benchmarks/phase0/measure.py` (nearest-rank p95, 5 discarded warm-ups, ≥ 30 measured samples, raw per-request timings retained), `benchmarks/phase0/config.py` (concurrency 1, the 5-passage ≤ 2,000-token prompt budget, both thresholds as named constants) and `benchmarks/phase0/provenance.py` (GPU model, runtime, model revision, quantization, dependency versions, the seven FR-028o tunnel fields plus the keyed `endpoint_hmac`; it **raises rather than emits** a record whose GPU it cannot name) (FR-028n, FR-028o, FR-035a, FR-035c, FR-035f · SC-041 · CHK127, CHK191)
- [X] T032 [P] Write failing unit tests in `tests/unit/test_nearest_rank_p95.py`, including the off-by-one rank case and the ≥ 30-sample minimum (FR-035a · CHK128, CHK189)
- [X] T033 Implement result writing in `benchmarks/phase0/results.py` — one immutable JSON file per run under `benchmarks/phase0/results/`, never overwriting, carrying both figures, the **raw per-request timings**, the provenance record and a verdict of `PASS｜FAIL｜INVALID｜UNSUPPORTED_CONFIGURATION` per measure (FR-035c, FR-035e)

### 0I — Failure path, gate record, and the claim detector

- [X] T034 Implement the failure path in `benchmarks/phase0/__main__.py`: a missed threshold prints the **named** threshold and its measured value and exits nonzero; a CPU-only or unidentified GPU exits `INVALID`; a runtime that cannot enforce deterministic settings exits **`UNSUPPORTED_CONFIGURATION`**; and a **missing, empty, incomplete, malformed or production-shape-mismatched preview index** (T027's checks) **stops before any measured sample**, writes the preview row **`FAIL`, never `PASS`**, records a **content-free validation reason and the validation-artifact path**, leaves **no temporary collection**, and exits nonzero (FR-011j, FR-035c, FR-035f · SC-020, SC-040)
- [X] T035 Create `benchmarks/phase0/GATE.md` with two rows — `preview` and `first_token` — each `NOT RUN`, each naming the phase it gates (Phase 2, Phase 4). This is the machine-readable gate T056 and T112 read (FR-035f)
- [X] T036 Write `tests/unit/test_phase0_gate_not_claimed.py`: fail the build when a **user-facing status or documentation claim** — in `docs/`, `README.md`, or the Feature 004 section of `specs/004-permission-aware-rag/verification.md` — describes either latency threshold as met while its `benchmarks/phase0/GATE.md` row is `NOT RUN`. It **excludes** task instructions and quoted falsification text so it cannot match its own scaffolding. Ship fixtures `tests/fixtures/gate_claims/genuine_claim.md` (a real claim, **must fail**) and `tests/fixtures/gate_claims/quoted_instruction.md` (a quoted task instruction, **must pass**) (FR-035e · SC-020)
- [X] T037 **FALSIFY** — copy `tests/fixtures/gate_claims/genuine_claim.md` (created T036) into `docs/models.md`, confirm `tests/unit/test_phase0_gate_not_claimed.py` fails, then restore `docs/models.md` byte-identical. The quoted-instruction fixture must still pass throughout, proving the detector is neither vacuous nor self-triggering

**Checkpoint / exit criteria**: packaging installed and proven from a scrubbed subprocess ·
bare-checkout boundary enforced · server provisioned and all seven prerequisites verified ·
preflight invoked first · preview index validated against six checks and its manifest recorded
· all indexing and warm-up completed before the first sample · both figures recorded with raw
timings · temporary collection dropped, including on failure · `benchmarks/phase0/GATE.md`
updated with the real verdicts. **Do not edit a threshold to make a row read `PASS`** (FR-035f).

---

## Phase 1 — Authorization foundation ⟨parallel with Phase 0, except the Qdrant exclusion⟩

**Qdrant exclusion.** Phase 0's measured window (T029) uses the shared Qdrant **service**.
Every Phase 1 task touching that service — **T043** (temporary-collection payload-index test),
**T044** (the run that *invokes* T043's test), **T047** (production index provisioning) and
**T049** (index-removal falsification) — is **blocked until T029 has completed and recorded**. No collection creation, deletion, indexing,
schema mutation or destructive test may overlap the measured samples. The rest of Phase 1 —
pure filter unit tests, cache key derivation, migrations, registration — is parallel-safe with
all of Phase 0.

### 1A — Failing tests first (US2)

- [X] T038 [P] [US2] Write failing unit tests in `tests/unit/test_qdrant_filter.py` — one **named** test per filter clause (`company_id`, `classification`, `department_id`, `country`, `allowed_roles`, `owner_id`, `document_id`), each failing when that key is removed from `qdrant_filter`. **Seven** fields: `document_id` carries the resource-grant reach, whose granted ids the retrieval service resolves relationally *before* the search (FR-014b · R1 · R5 · CHK025)
- [X] T039 [P] [US2] Write failing tests in `tests/unit/test_qdrant_filter_null_scope.py`: a null document `country`/`department_id` means **company-wide**; a caller with a value reaches matching **or** company-wide; a caller without a value reaches **only** company-wide (FR-014a · SC-024 · R4)
- [X] T040 [P] [US2] Write failing tests in `tests/security/test_filter_invariants.py`: `company_id` and `classification` are **must**-clauses never widened by any owner, role or ACL branch (FR-013 · Principle I · CHK006)
- [X] T041 [P] [US2] Write failing tests in `tests/unit/test_qdrant_filter_grants.py` exercising **FR-014's five-layer order** — tenant, role, attribute, resource grant, classification — with the owner, role and explicit-ACL branches, the ACL-only document and its negative twin (FR-014, FR-015 · R5)
- [X] T042 [P] [US2] Write `tests/security/test_no_service_verifies_browser_tokens.py`: **the existing API is the only verifier.** Scope here is **`services/worker/` and `scripts/seed/` only** — the boundaries that exist now. Assert statically that neither imports a JWT library, references a signing key or defines a token-decoding path, and behaviourally that each **rejects** a token-bearing request. Extended in Phase 4 (T114) for the generation boundary (FR-028, FR-029 · Principle II)
- [X] T043 [US2] ⟨blocked until T029 completes⟩ Write `tests/integration/test_payload_indexes.py`: fails when **any** field used by `qdrant_filter` lacks a payload index, derived from the filter's own key set rather than a hand-maintained list. It provisions a **uniquely named temporary collection** and drops it in teardown — never the production `documents` collection (FR-014b · SC-025 · CHK006). **Passing**: it imports `ensure_payload_indexes` and `REQUIRED_PAYLOAD_INDEXES` from `packages/core/src/eaios_core/clients/stores.py`, so it was red at collection until T047 supplied them. With T047 implemented it runs against a live Qdrant and passes, provisioning and dropping its own temporary collection and detecting each of the seven indexes independently
- [X] T044 [US2] ⟨blocked until T029 completes and records⟩ Run T038–T043 with `uv run python -m pytest tests/unit/test_qdrant_filter.py tests/unit/test_qdrant_filter_null_scope.py tests/security/test_filter_invariants.py tests/unit/test_qdrant_filter_grants.py tests/security/test_no_service_verifies_browser_tokens.py tests/integration/test_payload_indexes.py -v` — the invocation includes the collection-provisioning test, so it carries the same Qdrant exclusion as T043 — and **create** `specs/004-permission-aware-rag/verification.md` from the feature 003 verification format, recording the failing output under a *Feature 004 · Phase 1 red* heading. Every later task **updates** this same file (Principle VIII)

### 1B — Implementation

- [X] T045 [US2] Rebuild `qdrant_filter` in `packages/core/src/eaios_core/authz/filters.py` to the structured must/should shape of [contracts/retrieval-and-chat.md](contracts/retrieval-and-chat.md) §3, enforcing FR-014's five-layer order with the owner, role and explicit-ACL branches, until T038–T041 pass. It accepts a **keyword-only immutable collection of internally resolved READ-granted document ids**, defaulting to empty, and includes them as the **resource-grant reach** on `document_id`. It performs no query of its own: resolution happens in the retrieval service (T094), and the ids reaching this function are never request-supplied (FR-014, FR-014a, FR-015 · R4 · R5)
- [X] T046 [US2] Remove the docstring claim in `packages/core/src/eaios_core/authz/filters.py` that the function is unit-tested — false until T045; replace it with a reference to `tests/unit/test_qdrant_filter.py` (R1)
- [X] T047 [US2] ⟨blocked until T029 completes⟩ Add `allowed_roles` — and every other filter field — as payload indexes, idempotently, until T043 passes. **Two files, because provisioning happens on two paths**: `packages/core/src/eaios_core/clients/stores.py` gains the canonical `REQUIRED_PAYLOAD_INDEXES` (derived from `FILTER_KEYS`) and the idempotent `ensure_payload_indexes`; `scripts/seed/src/eaios_seed/loaders/stores.py` — the loader/reset path — derives its `PAYLOAD_INDEXES` from that same canonical registry and delegates to `ensure_payload_indexes`, **so all seven indexes survive `reset_all`**. Without the second file the fix is momentary: `reset_all` deletes every collection and `provision_qdrant` rebuilds them, so an index provisioned only in core is silently dropped by the next `seed reset` (R3's defect, one layer up). **Not `[P]`**: it mutates the shared production collection (FR-014b · R3)
- [X] T048 [US2] Implement `scripts/seed/src/eaios_seed/indexing/preflight.py`: refuse to ingest when the collection dimension is not 1024 or any filter field lacks an index, naming the missing item (contracts IC §1 · CHK061)
- [X] T049 **FALSIFY** ⟨blocked until T029 completes⟩ — drop the `allowed_roles` payload index from the temporary collection created by `tests/integration/test_payload_indexes.py` (created T043), confirm that test fails **and** that `scripts/seed/src/eaios_seed/indexing/preflight.py` (created T048) refuses when invoked **directly** — the `eaios-seed index` command does not exist until T074 — then re-provision via `packages/core/src/eaios_core/clients/stores.py`

### 1C — Permission-scoped cache (pure, no Redis)

- [X] T050 [P] [US2] Write failing tests in `tests/security/test_cache_isolation.py` — a **pure unit test over key derivation and an in-memory fake cache**, connecting to no Redis and mutating no shared namespace: two callers whose permissions differ produce **different** cache keys for the same question, and a permission change makes the previous entry unreachable rather than requiring invalidation (FR-018 · R2 · CHK022, CHK023)
- [X] T051 [P] [US2] Write failing tests in `tests/security/test_cache_data_version.py` — likewise pure and in-memory: two different corpus-version checksums produce different cache keys, and an entry keyed on a retired checksum becomes **unreachable without any key being deleted** (FR-018a · R23)
- [X] T052 [US2] Define the `CorpusVersionProvider` protocol in `packages/core/src/eaios_core/corpus_version.py` — `active_checksum(company_id, collection) -> str` — with an in-test stub, so Phase 1 stays independent of Phase 2 (FR-018a · R23)
- [X] T053 [US2] Wire the existing `cache_key` from `packages/core/src/eaios_core/keys.py` into the retrieval path's cache accessor, taking `data_version` from `CorpusVersionProvider` — **reuse `cache_key` unchanged** — until T050 and T051 pass (FR-018, FR-018a · R2)

### 1D — Migration coverage foundation

- [X] T054 Extend `tests/integration/test_migrations.py` to sweep **every** revision under `apps/api/alembic/versions/` for an up/down/up round trip. It runs against a **uniquely named ephemeral PostgreSQL database** created for the sweep and dropped afterwards — **never** the shared development or test database — and is **not `[P]`** (spec 001 FR-007a · Principle I)
- [X] T055 [P] Write `tests/unit/test_table_registration.py`: a **durable registration invariant** over the eight Feature 004 table names, so each one is registered *at the moment its model is created* rather than pre-registered here. The eight, derived from `data-model.md` rather than invented: `ingestion_runs` · `ingestion_document_states` · `corpus_versions` · `conversations` · `conversation_turns` · `turn_citations` · `evaluation_runs` · `evaluation_question_results`. **Corrected from "seven"**: the data model's `### conversations and conversation_turns` heading covers two tables, and the count was taken from the headings. The invariant, in both directions: (a) once a name appears in `Base.metadata.tables` it must **simultaneously** appear in `POST_BASELINE_TABLES` in `packages/core/src/eaios_core/models/__init__.py`; (b) once it is implemented it must **simultaneously** appear in `RUNTIME_TABLES` in `scripts/seed/src/eaios_seed/loaders/stores.py`; (c) neither registry may contain a Feature 004 name that is absent from the metadata or from its migration. **Corrected from a Phase 1 pre-registration**: adding eight names to `RUNTIME_TABLES` before the tables exist makes `reset_all` truncate what is not there and makes the empty-environment pre-flight count a table it cannot query, so the names are added by T057, T078, T138 and T193 and this test fails the moment a model lands without its registry entry (Principle IX · matches the feature 003 pattern)

**Checkpoint**: filter tests pass and are falsifiable; every filter field is indexed and a test
proves it; worker and seed cannot verify a browser token; **zero points written to Qdrant**.

---

## Phase 2 — Deterministic ingestion ⟨requires Phase 1 exit + Phase 0 preview `PASS`⟩

**Qdrant discipline**: every `[P]` test provisions a **uniquely named temporary collection**
and drops it. Production-collection tasks are **never `[P]`** and run one at a time.

- [ ] T056 **GATE** — read `benchmarks/phase0/GATE.md` (created T035); if the `preview` row is not `PASS`, stop. Phase 2 does not start on an unmeasured or failing preview figure (FR-035f)

### 2A — Schema and state machine (US3)

- [ ] T057 [US3] Create `IngestionRun` and `IngestionDocumentState` in `packages/core/src/eaios_core/models/retrieval.py` per [data-model.md](data-model.md), both using `TenantMixin`, with the eight-value refusal enum, the `preserved_prior_index` flag and the unique `(run_id, document_id)` constraint (FR-003, FR-006, FR-002a · CHK041, CHK044) **Register atomically**: add `ingestion_runs` and `ingestion_document_states` to `POST_BASELINE_TABLES` (`packages/core/src/eaios_core/models/__init__.py`) and `RUNTIME_TABLES` (`scripts/seed/src/eaios_seed/loaders/stores.py`) in this same task — `tests/unit/test_table_registration.py` (T055) fails otherwise (T055)
- [ ] T058 [US3] Write reversible migration `apps/api/alembic/versions/0005_ingestion_state.py`: both tables, their enums, `ENABLE ROW LEVEL SECURITY`, the `tenant_isolation` policy as in `0002_row_level_security.py`, grants to `eaios_app`, and a `downgrade()` reversing all four (Principle I)
- [ ] T059 [US3] Run `uv run python -m pytest tests/integration/test_migrations.py -m integration -v` against `apps/api/alembic/versions/0005_ingestion_state.py` on the ephemeral database of T054 and confirm the round trip (CHK042)
- [ ] T060 [P] [US3] Write failing tests in `tests/integration/test_ingestion_states.py` (temporary collection): every document reaches a **terminal** state; a run completing with any non-terminal row is a **run failure**, detectable by query (FR-003 · SC-008 · CHK041, CHK042)

### 2B — Admission, refusal, and the two size boundaries (US3)

- [ ] T061 [P] [US3] Write failing tests in `tests/integration/test_ingestion_refusal.py` covering the closed refusal vocabulary in validation order: `NOT_TEXT`, `EMPTY_BODY`, `DIGEST_MISMATCH`, `TOO_LARGE`, `NO_CLASSIFICATION`, `STORAGE_UNREADABLE` (FR-002 · CHK044)
- [ ] T062 [P] [US3] Write failing tests in `tests/integration/test_readable_body.py`: readable requires **≥ 20 non-whitespace Unicode characters**, **≥ 1 letter or digit** and **valid UTF-8 after normalization** — each induced separately, each producing `EMPTY_BODY` **before chunking** with zero chunks written (FR-002b · SC-038 · CHK049)
- [ ] T063 [US3] Write failing tests in `tests/security/test_oversize_atomic_refusal.py` against a **uniquely named temporary collection seeded with a prior active version**, dropped in teardown: a document over **2 MiB of extracted normalized UTF-8 text** is refused **before chunking** with zero chunks, embeddings or points written, and its **previously indexed version stays retrievable and citable**. **Not `[P]`** (FR-002a · SC-023 · R15)
- [ ] T064 [US3] Implement admission and refusal in `scripts/seed/src/eaios_seed/indexing/admission.py`: only documents present in `documents` are eligible; the readable-body floor and the 2 MiB check both precede chunking; truncation never happens; `preserved_prior_index` is set — until T061, T062 and T063 pass (FR-001, FR-002, FR-002a, FR-002b)
- [ ] T065 [US3] Refuse a document whose structural splitting yields no usable text as `EMPTY_BODY` in `scripts/seed/src/eaios_seed/indexing/admission.py` (FR-002b, FR-007a · CHK058)

### 2C — Embedding replacement (US3)

- [ ] T066 [US3] Write failing tests in `tests/integration/test_embedding_replacement.py` against a **uniquely named temporary collection**, dropped in teardown: a change to the embedding **revision, weight checksum, dimension, tokenizer or runtime identity** forces a **complete replacement index**; **two embedding identities are never active in one collection**; the previous index and corpus checksum keep serving until the replacement is atomically published; a failed replacement leaves the previous generation **byte-identical**. **Not `[P]`** (FR-011i · SC-039 · CHK059, CHK062)

### 2D — Index population, payload and idempotency (US3)

- [ ] T067 [P] [US3] Write failing tests in `tests/integration/test_ingestion_idempotency.py` (temporary collection): `UNCHANGED` requires **both** `content_sha256` and `chunker_config_hash` to match; a second run writes zero points and reports the corpus current (FR-004 · SC-006 · CHK036)
- [ ] T068 [P] [US3] Write failing tests in `tests/integration/test_ingestion_replacement.py` (temporary collection): changed content deletes by `document_id` filter then inserts **as one logical operation**, so no reader observes two generations (FR-005 · CHK039)
- [ ] T069 [P] [US3] Write failing tests in `tests/security/test_chunk_payload_attributes.py` (temporary collection): **every** indexed point carries all six authorization attributes — `company_id`, `department_id`, `classification`, `country`, `owner_id`, `document_id` — matching the source document and **never defaulted, empty-stringed or omitted**; a null `country`/`department_id` is written as the **company-wide** marker (FR-010, FR-014a · CHK006)
- [ ] T070 [US3] Write failing tests in `tests/integration/test_scope_boundary.py` against **uniquely named temporary `documents` and `code` collections**, never the production ones: run the full ingestion entry point against them, assert `code` holds **zero points**, assert a binary or non-text document is refused `NOT_TEXT`, and drop both. **Not `[P]`** (FR-001a, FR-002 · CHK051)
- [ ] T071 [US3] Implement the run orchestrator in `scripts/seed/src/eaios_seed/indexing/runner.py` — **importing and using the canonical Phase 0 modules `eaios_core.chunking` and `eaios_core.embedding.bge_m3`, never a second chunker, tokenizer wrapper, embedding adapter or copied configuration; the runner's chunker and embedding identities and configuration hashes come from those modules** — with state transitions, per-document outcomes, run counts reconcilable against `documents`, idempotent `UNCHANGED` detection, atomic delete-then-insert replacement, payload population carrying all six attributes with a null attribute written as company-wide, and writes only to `documents` so `code` stays empty — until T067–T070 pass. **Not `[P]`** (FR-001a, FR-003, FR-004, FR-005, FR-006, FR-010, FR-014a)
- [ ] T072 [P] [US3] Write `tests/unit/test_runner_uses_canonical_libraries.py`: a **static assertion** over `scripts/seed/src/eaios_seed/indexing/runner.py` that fails when it defines duplicate chunking or embedding logic — no second chunker, tokenizer wrapper, embedding adapter or copied `ChunkerConfig` (FR-007, FR-007a, FR-011, FR-011b · SC-007)
- [ ] T073 [US3] Implement failure recovery in `scripts/seed/src/eaios_seed/indexing/recovery.py`: `INDEX_WRITE_FAILED` and `EMBEDDING_FAILED` leave no partial chunks, the run continues, and non-terminal rows survive an interruption (contracts IC §9 · CHK042, CHK043)
- [ ] T074 [US3] Add the `index`, `index --status` and `index --force` commands to `scripts/seed/src/eaios_seed/cli.py`, wired to the T048 preflight so ingestion cannot start against an unindexed or wrong-dimension collection (contracts IC §1)
- [ ] T075 [P] [US3] Add the tenant-attributed ingestion job in `services/worker/src/eaios_worker/tasks/indexing.py`, following the `tasks/base.py` pattern — it carries the tenant and authorization context of the person it is for and is **refused if that context is absent** — and extend `tests/security/test_job_tenancy.py` (FR-030 · Principle I)

### 2E — Corpus version and `data_version`

- [ ] T076 [P] [US3] Write failing tests in `tests/integration/test_corpus_version.py` (temporary collection): the checksum derives from the **eight** inputs in fixed order (company, collection, document ids and normalized-content hashes, chunk ids and content hashes, chunker version and config hash, embedding identity/revision/checksum, vector dimension, **authorization payload schema version**); an idempotent no-op run yields the **same** checksum; a change to any one input yields a **different** one (FR-018a · SC-035 · R23)
- [ ] T077 [P] [US3] Write failing tests in `tests/integration/test_corpus_version_atomicity.py` (temporary collection): a **failed or cancelled** run publishes nothing and leaves the previous checksum active; publication deactivates the previous row and inserts the new one in **one transaction**; exactly one active row exists per `(company_id, collection)` (FR-018a · SC-035)
- [ ] T078 [US3] Create the `CorpusVersion` model in `packages/core/src/eaios_core/models/retrieval.py` with `checksum`, `is_active`, `published_at`, `run_id` and `inputs_digest`, plus the **partial unique index** on `(company_id, collection) WHERE is_active`, and add it to `apps/api/alembic/versions/0005_ingestion_state.py` with its `downgrade()` (FR-018a · data-model) **Register atomically**: add `corpus_versions` to `POST_BASELINE_TABLES` (`packages/core/src/eaios_core/models/__init__.py`) and `RUNTIME_TABLES` (`scripts/seed/src/eaios_seed/loaders/stores.py`) in this same task — `tests/unit/test_table_registration.py` (T055) fails otherwise (T055)
- [ ] T079 [US3] Implement checksum derivation in `packages/core/src/eaios_core/corpus_manifest.py` over the eight inputs in fixed order, recording `inputs_digest` so a checksum can be **explained** rather than only compared (FR-018a · R23)
- [ ] T080 [US3] Implement the real `CorpusVersionProvider` against `corpus_versions` in `packages/core/src/eaios_core/corpus_version.py`, replacing the Phase 1 stub, and publish atomically from `scripts/seed/src/eaios_seed/indexing/runner.py` **only after** the complete replacement index succeeds — until T066, T076 and T077 pass. **Not `[P]`** (FR-011i, FR-018a · SC-035)
- [ ] T081 **FALSIFY** — publish the checksum before the index write completes in `scripts/seed/src/eaios_seed/indexing/runner.py` (created T071), confirm `tests/integration/test_corpus_version_atomicity.py` fails, then restore that file byte-identical
- [ ] T082 [US3] ⟨serialized with T054, T059, T139, T194 — same file, same ephemeral database⟩ Extend `tests/integration/test_migrations.py` to cover the `corpus_versions` up/down/up round trip on the ephemeral database, confirming the partial unique index is dropped and recreated correctly (FR-018a · Principle I)

### 2F — Fixtures and the embedding fixture manifest

- [ ] T083 [US3] Write failing tests in `tests/integration/test_fixture_manifest.py`: the build **fails** when the **embedding fixture manifest** disagrees with the configured embedder, the live Qdrant dimension, the chunker identity or the source hashes — one induced disagreement per field. **Not `[P]`** (FR-035g · SC-022)
- [ ] T084 [US3] Implement fixture generation in `scripts/seed/src/eaios_seed/fixtures/generate.py` and the eleven-field **embedding fixture manifest** writer in `scripts/seed/src/eaios_seed/fixtures/manifest.py`, emitting `tests/fixtures/retrieval/manifest.json` — scoped to vectors and the embedder, carrying **no** generation-prompt, judge or provider field (FR-035g, FR-035m · contracts IC §3)
- [ ] T085 [US3] Add `eaios-seed fixtures regenerate` to `scripts/seed/src/eaios_seed/cli.py`: explicit command only, never automatic, producing a reviewable diff, accepted only after the full retrieval evaluation passes (FR-035h · CHK212)
- [ ] T086 **FALSIFY** — edit `vector_dimension` in `tests/fixtures/retrieval/manifest.json` (created T084) to 768, confirm `tests/integration/test_fixture_manifest.py` fails, then restore that file byte-identical
- [ ] T087 Add `make index` and `make fixtures` targets to `Makefile` and document the ingestion command in `docs/running.md` (FR-006)
- [ ] T088 [P] Extend `docs/dataset.md` with the ingestion state machine and the refusal vocabulary, and confirm `make fingerprint` is unchanged before and after indexing (FR-042 · SC-014)

**Checkpoint**: the corpus is indexed; a second run is a no-op; the fingerprint is unchanged;
every point carries all six authorization attributes; the fixture manifest agrees with the
embedder that produced it.

---

## Phase 3 — Retrieval and citations ⟨requires Phase 2⟩

### 3A — Authorization-constrained search (US1, US2)

- [ ] T089 [P] [US2] Write failing tests in `tests/security/test_authorize_before_search.py`: the **recorded Qdrant request** carries the full payload filter, and no candidate outside the permitted set is ever materialized — asserted on the request, not the response (FR-013 · SC-003 · R1)
- [ ] T090 [P] [US2] Write failing tests in `tests/security/test_rag_permission_split.py`: the same question asked by a permitted and a denied persona yields answers, citations and wording containing **no trace** of the restricted document (FR-016, FR-017 · SC-004)
- [ ] T091 [P] [US2] Write failing tests in `tests/security/test_rag_cross_tenant.py`: zero chunks from one company reach a member of the other, across every evaluation persona pairing; a single instance fails the run and blocks the build (FR-033 · SC-005 · Principle I)
- [ ] T092 [P] [US2] Write failing tests in `tests/security/test_indistinguishable_empty.py`: a permission-narrowed empty result and a genuinely empty authorized result take **identical control flow** on deterministic fixtures — identical HTTP status, SSE event types and ordering, user-visible wording, retry behaviour and externally visible metadata, with **no** withheld-source signal. **Ordinary CI, build-blocking**; the timing half is T208 (FR-017, FR-017a · SC-037 · R25)
- [ ] T093 [P] [US2] Write failing tests in `tests/security/test_passage_lifetime.py`: passage and prompt content — and derived forms such as summaries, snippets and highlighted fragments — appear in **no** persistent store, cache, log, trace, metric, snapshot, test artifact, exception message or retry queue, and are released at the terminal event **and on the abort path** (FR-013a · SC-036 · R24)
- [ ] T094 [US1] Implement the search service in `apps/api/src/eaios_api/retrieval/service.py`, consuming `qdrant_filter` with the API-built immutable `AccessContext` and **never** accepting a company, department, classification or role from the request body, query string or header. It also **resolves the resource-grant reach relationally before the search**: query `document_acl` for `READ` grants matching the caller's **user id**, **role ids**, and **department id when present**, scoped to the caller's company, and pass **only the resulting document ids** into `qdrant_filter`. Granted ids and ACL rows are **never** accepted from the request — they are derived server-side from the verified context, and a request-supplied id is a privilege escalation wearing the shape of a parameter (FR-012, FR-013, FR-015, FR-029 · contracts RC §3 · R5)
- [ ] T095 [US2] Implement the indistinguishable-empty path in `apps/api/src/eaios_api/retrieval/empty_result.py`: one code path produces the empty outcome regardless of **why** it is empty — until T092 passes (FR-017, FR-017a · SC-037)
- [ ] T096 **FALSIFY** — branch on the exclusion count in `apps/api/src/eaios_api/retrieval/empty_result.py` (created T095) so the permission-narrowed case takes a different path, confirm `tests/security/test_indistinguishable_empty.py` fails, then restore that file byte-identical
- [ ] T097 **FALSIFY** — delete the `company_id` clause from `qdrant_filter` in `packages/core/src/eaios_core/authz/filters.py` (rebuilt T045), confirm `tests/security/test_rag_cross_tenant.py` fails, then restore that file byte-identical

### 3B — Passage budget and excerpt spans (US1)

- [ ] T098 [P] [US1] Write failing tests in `tests/security/test_passage_budget.py`: no request exceeds **5 passages**, **400 tokens per passage** or **2,000 retrieved-passage tokens total** by the **pinned generation tokenizer**; every trimmed passage ends at a sentence boundary; the selection is the top-ranked authorized results (FR-028b, FR-028b1, FR-028b2 · SC-026 · R14)
- [ ] T099 [P] [US1] Write failing tests in `tests/security/test_excerpt_spans.py`: every citation resolves to **exactly** the span sent to generation — never the wider chunk, never a different span (FR-028b3 · SC-027)
- [ ] T100 [P] [US1] Write failing tests in `tests/unit/test_two_tokenizer_budgets.py`: generation **re-counts** every passage with the pinned **Qwen** tokenizer and never inherits the chunker's **BGE-M3** count; a chunk at exactly 400 BGE-M3 tokens exceeding 400 Qwen tokens is trimmed, and the 2,000-token total still holds (FR-028b5 · R21)
- [ ] T101 [US1] Implement `apps/api/src/eaios_api/retrieval/budget.py` — the three simultaneous bounds and sentence-boundary trimming, counted with the pinned **Qwen** tokenizer, independent of the chunker's bound — until T098 and T100 pass (FR-028b, FR-028b1, FR-028b2, FR-028b5 · R14, R21)
- [ ] T102 [US1] Implement excerpt-span capture in `apps/api/src/eaios_api/retrieval/citations.py`, recording `excerpt_start`/`excerpt_end` at the moment the passage is serialized, until T099 passes (FR-028b3)

### 3C — Citation re-authorization (US1)

- [ ] T103 [P] [US1] Write failing tests in `tests/security/test_citation_reauthorization.py`: opening a citation re-runs the full authorization decision **independently of any turn's snapshot**; a document deleted, restricted or made unreadable between answer and open **fails closed as not-found** (FR-022 · edge case)
- [ ] T104 [US1] Implement citation resolution and re-authorization in `apps/api/src/eaios_api/retrieval/citations.py`, dropping any citation whose **source document no longer exists or is no longer readable** — the deleted-document case, distinct from the unsent-passage case implemented at **T155** — until T103 passes; every answer to an answerable question carries at least one resolvable citation (FR-022 · SC-001)

### 3D — Vocabulary and telemetry naming

- [ ] T105 [P] Implement the five-term vocabulary as named types in `apps/api/src/eaios_api/retrieval/vocabulary.py` — `Candidate`, `RetrievedPassage`, `GenerationPassage`, `CitedPassage`, and `documents_consulted` as **distinct `document_id` values among generation passages** (FR-036a · R18)
- [ ] T106 [P] Write `tests/security/test_exclusion_counts_never_surface.py`: zero occurrences of an unauthorized-candidate count or an authorization-exclusion count in any response body, SSE event or user-visible source list; operator telemetry may retain aggregates (FR-017, FR-038 · SC-030 · CHK171)

### 3E — Cache, contracts and the CI lane

- [ ] T107 [US2] Wire the permission-scoped cache into `apps/api/src/eaios_api/retrieval/service.py` using the T053 accessor, and extend `tests/security/test_cache_isolation.py` to cover retrieval results and citation resolution as well as query embedding — the cache holds references and derived results, **never passage bodies** (FR-018, FR-013a · CHK022)
- [ ] T108 [US1] Add the retrieval-preview route in `apps/api/src/eaios_api/chat/router.py` emitting the `sources` milestone, and register it in `apps/api/src/eaios_api/main.py` (contracts RC §1 · SC-010 · CHK186)
- [ ] T109 [P] Regenerate `packages/contracts/src/generated/api.ts` from the OpenAPI schema and run `make contracts-check` (contracts RC §9)
- [ ] T110 Add the deterministic retrieval lane to `.github/workflows/ci.yml` under the existing `stack` job: committed fixtures only, **zero outbound network**, no Colab or ngrok host reachable, **no model download and no model load**, running the `tests/security` and `tests/integration` retrieval suites including T092 and T093 (FR-035b · SC-018)
- [ ] T111 **FALSIFY** — point the CI lane in `.github/workflows/ci.yml` (edited T110) at a live embedder instead of `tests/fixtures/retrieval/`, confirm the no-network assertion fails, then restore that file byte-identical

**Checkpoint**: retrieval is authorization-constrained and cache-isolated; empty outcomes are
indistinguishable by construction; citations resolve to exact spans; passage content leaves no
residue; the offline CI lane is green with no tunnel and no credential.

---

## Phase 4 — Generation and streaming ⟨requires Phase 3 + Phase 0 first-token `PASS`⟩

**The generation server already exists.** T019 created `generation_server.ipynb` and T021
verified its seven prerequisites in Phase 0. Phase 4 **reuses and contract-tests** that
artefact; it does not recreate it (FR-035o).

- [ ] T112 **GATE** — read `benchmarks/phase0/GATE.md` (created T035); if the `first_token` row is not `PASS`, stop. Phase 4 does not start on an unmeasured or failing first-token figure (FR-035f)

### 4A — Provider interface and the generation trust boundary (tests first)

- [ ] T113 [P] [US4] Write failing tests in `tests/unit/test_generation_provider.py`: the provider in use is **named in configuration**, never inferred, and a second provider is **not reachable as a fallback** (FR-011d, FR-028d · CHK180–CHK185)
- [ ] T114 [US4] Extend `tests/security/test_no_service_verifies_browser_tokens.py` with the **generation boundary**, written to **fail on absence**: it declares `apps/api/src/eaios_api/generation/` and its `provider.py`, `stub.py` and `colab_tunnel.py` as required and **fails if any is missing**, so it cannot pass vacuously. It asserts statically that none imports a JWT library, references a signing key or defines a decode path, and behaviourally that each **rejects** a token-bearing request (FR-028, FR-029 · Principle II)
- [ ] T115 [P] [US4] Write failing tests in `tests/security/test_no_download_at_request_time.py` for the provider path: an inference request through `apps/api/src/eaios_api/generation/colab_tunnel.py` **never** triggers a model download; weight acquisition is provisioning-time only (FR-011f · CHK071)
- [ ] T116 [P] [US4] Write failing tests in `tests/unit/test_tunnel_transport_drop.py` using a **fake streaming HTTP transport** that emits partial content then drops, **network-free**: `colab_tunnel.py` detects EOF, reset or timeout, **stops decoding**, **discards later output**, raises the **typed tunnel-failure signal** the API layer consumes, and exposes **no passage or prompt content** (FR-028m, FR-013a · R31)
- [ ] T117 [US4] Run T113–T116 with `uv run python -m pytest tests/unit/test_generation_provider.py tests/security/test_no_service_verifies_browser_tokens.py tests/security/test_no_download_at_request_time.py tests/unit/test_tunnel_transport_drop.py -v`, confirm T114 **fails on the absent generation modules**, and update the Feature 004 section of `specs/004-permission-aware-rag/verification.md` (created T044) under a *Phase 4 red* heading — Principle VIII evidence that the boundary test is non-vacuous (FR-028)
- [ ] T118 [US4] Define the provider interface in `apps/api/src/eaios_api/generation/provider.py` — `health()`, `stream()`, `cancel()`, and nothing that could retrieve or decide access; the provider is resolved from named configuration with **no fallback path** — until T113 passes (FR-011d, FR-028d · R8)
- [ ] T119 [P] [US4] Implement `apps/api/src/eaios_api/generation/stub.py`: emits tokens **with delays**, **honours `cancel()`**, and can be configured to **withhold cancellation acknowledgement** and to **drop mid-stream**, so cancellation, disconnect and tunnel-failure checks are genuinely exercised (FR-035b · CHK214)
- [ ] T120 [US4] Implement `apps/api/src/eaios_api/generation/colab_tunnel.py` against the **Phase 0 server contract** (contracts RC §6): HTTPS only, `Authorization: Bearer ${GENERATION_SERVICE_TOKEN}` on every request, no retry without authentication, **mid-stream drop detection** raising the typed tunnel-failure signal, and a full `cancel()` — propagate upstream, stop decoding, **sever at the 2-second deadline**, discard later output, report **`provider_cancel_unconfirmed`** content-free when confirmation does not arrive. The serialized body carries only the four permitted fields. One path serves stop and disconnect — until T115 and T116 pass (FR-025a, FR-025b, FR-028a, FR-028e, FR-028j, FR-028m · SC-044 · R29, R31)
- [ ] T121 [US4] Assert against the **existing** `infrastructure/colab/generation_server.ipynb` (created T019) in a new `tests/integration/test_generation_server_contract.py` that it satisfies the contract the transport depends on — health response shape, streaming first-token protocol, cancellation acknowledgement. **Reuse, not recreation**; the test fails if a second server artefact appears (FR-035o · SC-055)
- [ ] T122 [P] [US4] Add `GENERATION_PROVIDER`, `GENERATION_URL` and `GENERATION_SERVICE_TOKEN` (as `SecretStr`) to `packages/core/src/eaios_core/settings.py` and `infrastructure/.env.example` **with empty defaults**; the token and tunnel URL live only in ignored environment configuration and are never committed or logged (FR-028g, FR-028i · SC-018c)
- [ ] T123 [US4] Re-run `tests/security/test_no_service_verifies_browser_tokens.py` against the **real** provider interface, stub and transport now that they exist, confirm the generation-boundary assertions pass non-vacuously, and add the module to the ordinary-CI security suite in `.github/workflows/ci.yml` (FR-028, FR-029 · Principle II)

### 4B — The outbound boundary (tests first)

- [ ] T124 [P] [US4] Write failing tests in `tests/security/test_outbound_payload.py`: the **serialized** request contains only `question`, `passages`, `max_tokens`, `temperature` — asserting the absence of session tokens, signing keys, refresh tokens, access-context objects, ACL records, excluded-source counts, unauthorized chunks and unapproved metadata, and carrying only the **minimum authorized passages** (FR-028a, FR-028b, FR-037a · SC-018a)
- [ ] T125 [P] [US4] Write failing tests in `tests/security/test_synthetic_corpus_precondition.py`: an outbound request is **constructed only when** the active corpus manifest identifies the approved synthetic seed corpus and matches its fingerprint; an unknown, modified, user-supplied or non-synthetic corpus **fails closed before construction**, with zero passages serialized (FR-011h, FR-011l · SC-042 · R28)
- [ ] T126 [US4] Implement the test-only interceptor in `apps/api/src/eaios_api/generation/interceptor.py`: installed by dependency injection in tests only, reports **field names, counts and pass/fail** and never a value, persists nothing, discards the captured request immediately (FR-037a, FR-037b · R13)
- [ ] T127 [US4] Implement the synthetic-corpus precondition in `apps/api/src/eaios_api/generation/precondition.py`, evaluated **before** the request object is built, until T125 passes (FR-011h, FR-011l · SC-042)
- [ ] T128 [US4] Write `tests/security/test_interceptor_never_leaks.py`: a **deliberately failing** payload assertion emits zero passage text into logs, artifacts, snapshots or the failure message (FR-037b · SC-021)
- [ ] T129 [US4] Assert in `tests/security/test_interceptor_unreachable_in_production.py` that the interceptor cannot be constructed from the production container wiring in `apps/api/src/eaios_api/main.py` (FR-037b)

### 4C — Health, unavailability and mid-stream failure (US4)

- [ ] T130 [P] [US4] Write failing tests in `tests/security/test_generation_health.py` for all six unavailability conditions — **2-second deadline exceeded**, DNS failure, TLS failure, authentication refusal, malformed response, unhealthy status — each producing the designed state with **zero** questions or passage bodies sent and **zero** generator streams opened, each **failing closed** (FR-028k · SC-018b, SC-031 · R19)
- [ ] T131 [US4] Implement `apps/api/src/eaios_api/generation/health.py` with the 2-second deadline, collapsing all six causes to one user-visible outcome while recording the cause in operator telemetry only; ingestion, authorization and retrieval keep working while generation is unavailable (FR-028k, FR-028l · contracts RC §6)
- [ ] T132 [US4] Implement the concurrency rule in `apps/api/src/eaios_api/chat/router.py`: `health()` **may** run alongside local retrieval, but generation starts only when **both** it and the authorization-constrained retrieval have succeeded (FR-028k)
- [ ] T133 [P] [US4] Write failing tests in `tests/integration/test_stream_interruption.py` against the drop-capable stub: a mid-stream tunnel failure stops generation, rejects later provider output, releases request-scoped content, persists `INCOMPLETE` with `incomplete_reason = TUNNEL_FAILED`, and — **because the client is still connected** — emits the terminal `done` event with `state: incomplete` (FR-028m, FR-025 · SC-010b · CHK147, CHK203)
- [ ] T134 [US4] Implement the API-layer mid-stream tunnel-failure path in `apps/api/src/eaios_api/chat/stream_failure.py`, consuming the typed signal T120 raises: stop generation, reject later output, clean request-scoped content, persist `INCOMPLETE｜TUNNEL_FAILED`, emit the terminal event while the client remains connected — until T133 passes (FR-025, FR-028m, FR-013a · SC-010b)

### 4D — Per-turn access context and conversation state (tests first) (US4)

- [ ] T135 [P] [US4] Write failing tests in `tests/security/test_per_turn_access_context.py`: **every** chat turn receives a freshly built access-context snapshot, reusable only by operations of that turn; a retry preserves it only while the original turn is active; follow-up turns, regenerated answers and resumed conversations each build a **new** one; no worker or provider can create, validate, widen or reuse a context across turns. The test **fails** when a snapshot is reused (FR-012a · SC-045 · R30)
- [ ] T136 [P] [US4] Write failing tests in `tests/security/test_history_reauthorization.py`: with a permission **withdrawn between two turns**, prior assistant content whose cited sources are no longer authorized is **removed before the outbound payload is constructed**, the removed history is **never sent to the generator**, and the follow-up answer contains no trace of it (FR-016, FR-026 · edge case)
- [ ] T137 [US4] Run T135 and T136 with `uv run python -m pytest tests/security/test_per_turn_access_context.py tests/security/test_history_reauthorization.py -m security -v` and update the *Phase 4 red* heading of `specs/004-permission-aware-rag/verification.md` — Principle III evidence, before any conversation code exists
- [ ] T138 [US4] Create `Conversation`, `ConversationTurn` and `TurnCitation` in `packages/core/src/eaios_core/models/retrieval.py` per [data-model.md](data-model.md), storing `question_digest` and **never** the question text, plus `answer_state`, `incomplete_reason`, `provider_cancel_status` and the turn's own `permission_fingerprint` (FR-037 · CHK161) **Register atomically**: add `conversations`, `conversation_turns` and `turn_citations` to `POST_BASELINE_TABLES` (`packages/core/src/eaios_core/models/__init__.py`) and `RUNTIME_TABLES` (`scripts/seed/src/eaios_seed/loaders/stores.py`) in this same task — `tests/unit/test_table_registration.py` (T055) fails otherwise (T055)
- [ ] T139 [US4] Write reversible migration `apps/api/alembic/versions/0006_conversations.py` with RLS, the tenant policy, grants, the three new enums and a full `downgrade()`, then re-run `tests/integration/test_migrations.py` on the ephemeral database (Principle I)
- [ ] T140 [US4] Implement per-turn snapshot construction in `apps/api/src/eaios_api/chat/context.py`: one freshly built `AccessContext` per turn, recorded as `permission_fingerprint`, never shared — until T135 passes (FR-012a, FR-016 · SC-045)
- [ ] T141 [US4] Implement conversation-history rebuilding in `apps/api/src/eaios_api/chat/history.py` — **separate from T140**: before the outbound payload is constructed, re-authorize every prior turn's cited sources under the **new** turn's context, **remove** assistant content whose sources are no longer authorized, and pass only the surviving history forward — until T136 passes (FR-016, FR-026 · edge case)

### 4E — SSE, cancellation and disconnect (tests first) (US4)

- [ ] T142 [P] [US4] Write failing tests in `tests/integration/test_sse_contract.py`: `sources` precedes every `token`; `citation` events carry a `claim_ordinal` and arrive **with** the claim; exactly **one** terminal `done` event carries the state; a stream closing without it **while the client is connected** is a defect (FR-025, FR-020 · contracts RC §2 · CHK137, CHK139, CHK146)
- [ ] T143 [P] [US4] Write failing tests in `tests/integration/test_end_to_end_cancellation.py`: a stop halts emission **and stops token generation at the provider**; the stream closes terminal `stopped` and the answer is marked incomplete; request-scoped content is released; **no** retry, queued continuation or background generation follows; cleanup completes **within 2 seconds**; when the provider withholds acknowledgement the connection is **severed**, `provider_cancel_status = UNCONFIRMED` is recorded content-free, and later output discarded (FR-025a · SC-043, SC-044 · R29)
- [ ] T144 [P] [US4] Write failing tests in `tests/integration/test_client_disconnect.py`: an unexpected disconnect cancels upstream, releases request-scoped content, completes cleanup **within 2 seconds**, persists `INCOMPLETE｜CLIENT_DISCONNECT` and **never** `STOPPED`, requires **no** terminal SSE event, permits no continuation, and writes an audit record carrying only turn id, timestamps, status, duration and cancellation-confirmation status (FR-025b · SC-046, SC-047 · R31)
- [ ] T145 [US4] Implement SSE emission in `apps/api/src/eaios_api/chat/sse.py` and the schemas in `apps/api/src/eaios_api/chat/schemas.py` until T142 passes (contracts RC §2)
- [ ] T146 [US4] Implement end-to-end cancellation in `apps/api/src/eaios_api/chat/cancellation.py` — upstream propagation through `provider.cancel()` (T120), the 2-second close deadline, abort-cleanup release, and the `CONFIRMED`/`UNCONFIRMED` outcomes — until T143 passes (FR-025, FR-025a, FR-013a · SC-010b, SC-043, SC-044)
- [ ] T147 [US4] Implement disconnect detection and handling in `apps/api/src/eaios_api/chat/cancellation.py`, sharing the cancellation path but recording `INCOMPLETE｜CLIENT_DISCONNECT` and emitting no terminal event, until T144 passes (FR-025b · SC-046, SC-047)
- [ ] T148 **FALSIFY** — change `apps/api/src/eaios_api/chat/cancellation.py` (created T146) so a stop closes the stream but leaves `provider.cancel()` uncalled, confirm `tests/integration/test_end_to_end_cancellation.py` fails, then restore that file byte-identical. A display-only stop passes every browser-side check there is
- [ ] T149 **FALSIFY** — change `apps/api/src/eaios_api/chat/cancellation.py` (**created T146**, **extended T147** with the disconnect path this task attacks) so a disconnect releases the local request but leaves the provider generating, confirm `tests/integration/test_client_disconnect.py` fails, then restore that file byte-identical

### 4F — Grounding, abstention, systems of record, structure (US1)

- [ ] T150 [P] [US1] Write failing tests in `tests/security/test_grounding_enforcement.py`: a generated citation naming a passage the model was **never sent** is dropped by the API before the browser sees it, and no substantive claim is presented without a citation (FR-019, FR-028c · edge case)
- [ ] T151 [P] [US1] Write failing tests in `tests/integration/test_abstention.py` against the deterministic **stub provider**: for a question the permitted corpus cannot answer the assistant refuses **explicitly**, emits terminal `done` with `refused_unsupported`, produces **zero** citations and invents no content (FR-021 · SC-009)
- [ ] T152 [P] [US1] Write failing tests in `tests/security/test_systems_of_record.py`: a generated **figure, date, holding or balance** that cannot be matched to an authorized cited source span **or** an approved structured system-of-record value is **rejected or abstained on** rather than displayed (FR-023 · Principle V)
- [ ] T153 [P] [US1] Write failing tests in `tests/integration/test_structural_citation_checks.py` against the stub: **every substantive claim carries a citation**, **every citation resolves**, and **every cited span equals the passage sent to generation** (FR-032c, FR-035b · SC-027)
- [ ] T154 [US1] Implement the shared structural-check module `apps/api/src/eaios_api/retrieval/structural.py` — the three deterministic checks, consumed by the ordinary-CI suite and later repeated by the Phase 5 harness — until T153 passes (FR-019, FR-032c · SC-027)
- [ ] T155 [US1] Implement unsent-passage citation rejection in `apps/api/src/eaios_api/retrieval/citations.py`: drop or reject **every citation whose exact passage was not serialized into the generation request**, compared against the recorded generation-passage set. **Not** the deleted-source-document case of T104 — until T150 passes (FR-028c · edge case)
- [ ] T156 [US1] Implement the **systems-of-record validator** in `apps/api/src/eaios_api/retrieval/records_validator.py`: extract figures, dates, holdings and balances from the draft answer and match each against an authorized cited source span or an approved structured value; **reject or abstain** on any unmatched value. Integrated **before answer emission and before persistence** — until T152 passes (FR-023 · Principle V)
- [ ] T157 [US4] Implement the refusal path in `apps/api/src/eaios_api/chat/router.py` producing terminal `done` with `refused_unsupported` when the permitted corpus does not support an answer, until T151 passes (FR-021 · SC-009)
- [ ] T158 Wire T150–T153 into the ordinary-CI lane in `.github/workflows/ci.yml` **now, in this phase** — the three structural checks, grounding enforcement, abstention and the systems-of-record validator are **build-blocking from here on**, not from Phase 5 (FR-032c, FR-035b · SC-027)
- [ ] T159 **FALSIFY** — remove the span-equality assertion from `apps/api/src/eaios_api/retrieval/structural.py` (created T154), confirm `tests/integration/test_structural_citation_checks.py` fails **in the ordinary CI lane**, then restore that file byte-identical

### 4G — The versioned generation prompt (US4)

- [ ] T160 [US4] Author the versioned generation prompt at `specs/004-permission-aware-rag/evaluation/generation-prompt-v1.md` — **distinct from the grounding-judge prompt** — with a stated change discipline: any edit is a configuration change that starts a new series (FR-011k · CHK081)
- [ ] T161 [US4] Load and hash the prompt in `apps/api/src/eaios_api/generation/prompt.py`, exposing `generation_prompt_version` and `generation_prompt_hash` for the Phase 5 recorders (FR-011b, FR-011k)

### 4H — Portal surface (US4)

- [ ] T162 [US4] Create `apps/web/app/portal/(authed)/assistant/page.tsx` inside the existing `(authed)` group so it inherits the feature 003 shell, loading boundary and error boundary, adding a surface without weakening any existing portal behaviour (FR-024, FR-027 · contracts RC §8 · CHK150)
- [ ] T163 [US4] Add the same-origin route handler `apps/web/app/portal/api/assistant/route.ts`, proxying to the API — **the browser never contacts the tunnel** (FR-028f)
- [ ] T164 [P] [US4] Add exactly one entry to `EXPECTED_CLIENT_FETCHERS` in `apps/web/tests/state-coverage.test.tsx` and assert no other origin appears (FR-028f · SC-018c)
- [ ] T165 [US4] Add the assistant route and its reachable states to the matrix in `apps/web/tests/portal-states.test.tsx`, classifying `generation_unavailable` as its own cell rather than folding it into `error` (FR-027, FR-028l · SC-015 · CHK151, CHK200)
- [ ] T166 [P] [US4] Add `packages/ui/src/AssistantStream.tsx` (progressive token rendering), `packages/ui/src/AssistantCitation.tsx` (inline citation bound to its claim ordinal) and `packages/ui/src/AssistantIncompleteNotice.tsx` (the visible incomplete marker), exporting all three from `packages/ui/src/index.ts` (FR-020, FR-025 · CHK137, CHK146)
- [ ] T167 [P] [US4] Extend `apps/web/e2e/portal-accessibility.spec.ts` and `apps/web/e2e/responsive.spec.ts` to cover the assistant surface at 360, 768 and 1280 px, with no horizontal overflow and keyboard-reachable controls (SC-015)
- [ ] T168 [P] [US4] Extend `apps/web/e2e/portal.spec.ts` with the streaming, cancellation, disconnect, mid-stream-failure and `generation_unavailable` journeys against the stub provider — no tunnel in the browser test path (FR-035b)

**Checkpoint**: answers stream with citations; stop, disconnect and tunnel failure all stop the
work; unsupported figures are rejected; unsent-passage citations are dropped; the structural
checks are **already blocking**; the browser reaches only same-origin routes.

---

## Phase 5 — Evaluation and stabilization ⟨requires Phase 4⟩

**Per-run directories (FR-035j).** Every controlled execution owns
`tests/evaluation/results/<run_id>/`, holding its own immutable `run-manifest.json`, its own
raw-results file and its own results record. **Ordinary-CI manifest tests use committed
fixtures under `tests/evaluation/fixtures/runs/`**, never `results/`.

### 5A — The question set and its partition manifest (US5)

- [ ] T169 [US5] Author `tests/evaluation/questions.yaml` against the **full 105-document corpus**: ≥ 40 questions, ≥ 8 unanswerable, ≥ 8 permission-split pairs, ≥ 4 cross-tenant, ≥ 1 ACL-only with its negative twin, and **every persona able to answer at least one**, pairing each question with its expected documents and permitted/denied personas (FR-031 · contracts IC §5 · CHK099–CHK102)
- [ ] T170 [US5] Write the **question partition manifest** `tests/evaluation/manifest.json` declaring **every partition with its exact expected count**, the corpus fingerprint it was authored against and its own checksum — scoped to the question set, carrying **no** model, prompt or runtime field (FR-031a, FR-035m · R17)
- [ ] T171 [P] [US5] Add `tests/evaluation/README.md` stating that ground truth is authored from the corpus and reviewed, **never harvested from system output**, and version-controlled alongside the configuration (CHK102, CHK103)

### 5B — Preflight before any metric (tests first) (US5)

- [ ] T172 [US5] Write failing tests in `tests/evaluation/test_preflight.py`, one per condition: zero total questions; an empty required partition; counts disagreeing with the manifest; a metric with a **zero denominator**; an expected document **absent from the 105** — each asserting a **nonzero exit with no metric printed** (FR-035i · SC-029 · contracts IC §10)
- [ ] T173 [US5] Implement `tests/evaluation/harness/preflight.py` until T172 passes, ordered so the guard runs **before** any metric computation (FR-035i · R17)
- [ ] T174 [US5] Create the harness entry point `tests/evaluation/harness/__main__.py`, calling preflight **first** and only then the metric pipeline (FR-035i)
- [ ] T175 **FALSIFY** — move the preflight call in `tests/evaluation/harness/__main__.py` (created T174) to after the first metric computation, confirm `tests/evaluation/test_preflight.py` fails, then restore that file byte-identical. The defect this guards is not an error; it is `0/0` rendered as **100%**

### 5C — The evaluation-run manifest, one directory per run (US5)

- [ ] T176 [US5] Author the run-manifest JSON schema at `tests/evaluation/schemas/run_manifest_v1.json` with the **eleven required field groups** — `generation_prompt` (version, sha256) · `generation_model` (identifier, revision) · `generation_runtime` (quantization, runtime_identity) · `judge` (prompt_version, prompt_hash, model_identity) · `embedding_model` (identifier, revision, weight_checksum) · `corpus` (fingerprint, data_version) · `chunker` (config_hash) · `question_set` (manifest_checksum) · `provider` (profile, gpu_series) · `command` (evaluation_command_version) · `time` (run_timestamp) — and state its scope as **distinct from** the embedding fixture manifest and the question partition manifest (FR-035j, FR-035m · R32)
- [ ] T177 [P] [US5] Write failing tests in `tests/evaluation/test_run_manifest.py` using **committed fixtures under `tests/evaluation/fixtures/runs/`** — no model, no network: every required field present validates; **each** field omitted in turn produces `INVALID_CONFIGURATION`; a field disagreeing with the configured runtime produces `INVALID_CONFIGURATION`; the three manifest scopes stay disjoint; and **three fixture runs reference three distinct run directories with three distinct manifest checksums** (FR-035k, FR-035l, FR-035m · SC-048, SC-049, SC-051, SC-056)
- [ ] T178 [US5] Implement the manifest writer in `tests/evaluation/harness/run_manifest.py`: populate all eleven groups from the live configuration and emit **`tests/evaluation/results/<run_id>/run-manifest.json`**, **immutable once written**, alongside that run's raw-results file and results record in the **same run directory** — until the positive case of T177 passes (FR-035j · SC-048, SC-056)
- [ ] T179 [US5] Implement validation in `tests/evaluation/harness/run_manifest.py`: a **missing** field or one **disagreeing with the live configuration** records the run `INVALID_CONFIGURATION` — checked against the runtime, not the previous run — until T177 passes fully (FR-035k · SC-049)
- [ ] T180 [US5] Implement series continuity in `tests/evaluation/harness/series.py` by **comparing manifest field values**, never the series label: every field except `time.run_timestamp` and the run identifier must match, the three manifests compared come from **three distinct run directories**, and a change to the generation prompt version or hash starts a new series (FR-011k, FR-043b · SC-050, SC-056)
- [ ] T181 **FALSIFY** — in a **disposable run directory** under `tests/evaluation/fixtures/runs/` (created T177) change **only** `generation_prompt.sha256` while retaining the previous series identity, confirm `tests/evaluation/test_run_manifest.py` reports a failed validation rather than continuing the series, then restore that fixture byte-identical. The live `results/` tree is never edited

### 5D — The grounding judge (US5)

- [ ] T182 [US5] Author the versioned judge prompt at `specs/004-permission-aware-rag/evaluation/grounding-judge-v1.md`: per-claim grounded/not-grounded and per-citation supports/does-not-support, each with an enumerated **reason code**, scoring **only** the final answer against its cited spans (FR-032a · R22)
- [ ] T183 [P] [US5] Define the strict output schema at `tests/evaluation/schemas/judge_response_v1.json` and reject any judge response that does not validate against it (FR-032a · CHK095)
- [ ] T184 [US5] Author `tests/evaluation/calibration/grounding_calibration.yaml` — at least **20 manually labelled positive and negative examples**, each with label author and date, authored from the corpus (FR-032b · CHK102)
- [ ] T185 [P] [US5] Write failing tests in `tests/security/test_judge_input_boundary.py`: the **serialized** judge request contains only `question`, `answer`, `citations[]`, `cited_spans[]` — asserting the absence of unauthorized passages, ACL data, excluded-source counts, credentials and tokens (FR-032a, FR-037a · SC-018a)
- [ ] T186 [US5] Implement the judge invocation in `tests/evaluation/harness/judge.py`: the **same pinned model, a separate call**, temperature 0, deterministic settings where supported, recording judge model revision, quantization, runtime, **prompt hash** and **schema version** (FR-032a · R22)
- [ ] T187 [US5] Write failing tests in `tests/evaluation/test_judge_calibration.py`: agreement below **90%** records grounding and citation precision as **`INVALID`** and blocks them from being reported as met (FR-032b · SC-034)
- [ ] T188 [US5] Implement the calibration gate in `tests/evaluation/harness/calibration.py`, running **before** the judge scores any release-gate run and refusing to proceed on failure (FR-032b · R22)
- [ ] T189 **FALSIFY** — corrupt three labels in `tests/evaluation/calibration/grounding_calibration.yaml` (created T184), confirm `tests/evaluation/test_judge_calibration.py` records the run `INVALID` rather than failed, then restore that file byte-identical
- [ ] T190 [P] [US5] Import the shared structural checks from `apps/api/src/eaios_api/retrieval/structural.py` into `tests/evaluation/harness/structural.py` so the controlled lane **repeats** the three deterministic checks; ordinary CI (T153, T158) remains their first gate (FR-032c, FR-034a · SC-027)

### 5E — Metrics, records and provenance (US5)

- [ ] T191 [P] [US5] Implement the seven measures in `tests/evaluation/harness/metrics.py`, each labelled **deterministic** or **statistical** per FR-034a and each reporting **numerator, denominator and percentage**; grounding and citation precision consume the calibrated judge; recall@5 is the expected document among the top 5 retrieved chunks' documents; the same corpus, configuration, question set and recorded revisions produce the same retrieval figures on every run (FR-032, FR-032a, FR-033, FR-034, FR-034a, FR-034b · SC-002, SC-002a, SC-016 · R16)
- [ ] T192 [P] [US5] Write `tests/evaluation/test_deterministic_lane_reproduces.py`: running the deterministic lane twice on the same pinned configuration produces **identical** results; any difference **fails the run** rather than counting as variance (FR-034a · SC-028)
- [ ] T193 [US5] Create `EvaluationRun` and `EvaluationQuestionResult` in `packages/core/src/eaios_core/models/evaluation.py` with `gpu_series`, `corpus_fingerprint`, `document_count`, `partition_counts`, `manifest_checksum`, `generation_prompt_version`, `generation_prompt_hash`, the eight `judge_*` columns, **`run_directory`**, `run_manifest_path`, `run_manifest_checksum`, `process_fingerprint`, `preflight_completed_at`, `raw_results_path`, `raw_results_checksum`, the per-measure numerators and denominators, and the measure-class and validity enums including `INVALID_CONFIGURATION` (FR-011b, FR-011k, FR-032a, FR-032b, FR-034b, FR-035j, FR-035k, FR-043a, FR-043c · SC-019 · data-model) **Register atomically**: add `evaluation_runs` and `evaluation_question_results` to `POST_BASELINE_TABLES` (`packages/core/src/eaios_core/models/__init__.py`) and `RUNTIME_TABLES` (`scripts/seed/src/eaios_seed/loaders/stores.py`) in this same task — `tests/unit/test_table_registration.py` (T055) fails otherwise (T055)
- [ ] T194 [US5] Write reversible migration `apps/api/alembic/versions/0007_evaluation_runs.py` with RLS-consistent grants and a full `downgrade()`, then re-run `tests/integration/test_migrations.py` on the ephemeral database (Principle I · data-model migrations)
- [ ] T195 [US5] Store the run-directory reference on the record: `tests/evaluation/harness/run_manifest.py` writes `run_directory`, `run_manifest_path` and `run_manifest_checksum` onto the `EvaluationRun` row, and a results record without a resolvable manifest reference is rejected as unattributable (FR-035j · SC-048)
- [ ] T196 [US5] Implement provenance and validity in `tests/evaluation/harness/provenance.py`: CPU-only or unidentified GPU → `INVALID_NO_GPU` / `INVALID_UNKNOWN_GPU`; a runtime that cannot enforce deterministic settings → `INVALID_UNSUPPORTED_CONFIGURATION`; **none a pass or a failure** — and record the seven FR-028o tunnel fields plus the keyed `endpoint_hmac` without the hostname, URL, token or credential (FR-011j, FR-028n, FR-028o, FR-035c · SC-018d, SC-041 · CHK191)
- [ ] T197 [US5] Implement GPU-series separation in `tests/evaluation/harness/series.py`: a faster-than-T4 run is valid for grounding, citation precision, abstention and leakage, **invalid for either latency threshold**, recorded under a separate series name (FR-043a · SC-032 · R20)
- [ ] T198 [US5] Create the series record `tests/evaluation/results/series.json` with an empty T4 series and the schema the recorder appends to (FR-043a)
- [ ] T199 **FALSIFY** — append a synthetic L4 run to `tests/evaluation/results/series.json` (created T198), confirm `tests/evaluation/harness/series.py` advances **no** latency evidence and does not extend the T4 sequence, then restore that file byte-identical

### 5F — Three isolated executions and the release gate (US5)

- [ ] T200 [P] [US5] Write failing tests in `tests/evaluation/test_three_run_gate.py` using **fixture manifests and fixture result rows** under `tests/evaluation/fixtures/runs/` — no Colab, no ngrok, no model load: a counted sequence requires **three isolated executions**, each started after the previous reached a terminal result, each with its own completed preflight, unique run id and timestamp, **its own run directory**, own manifest, own raw results and empty caches (FR-035n, FR-043c · SC-052, SC-054, SC-056)
- [ ] T201 [US5] Extend `tests/evaluation/test_three_run_gate.py` with the **five falsifying cases**, each of which must **fail**: (a) three result rows sharing one `process_fingerprint`; (a′) two runs sharing a `run_directory`; (b) a run whose `raw_results_checksum` matches an earlier run's; (c) a failed or invalid run **between** two passing runs; (d) a run with `preflight_completed_at` null (FR-043c · SC-052, SC-053, SC-056)
- [ ] T202 [US5] Implement per-execution isolation in `tests/evaluation/harness/execution.py`: establish `process_fingerprint` at process start, set `preflight_completed_at` only when **this** execution's preflight completed, allocate **this run's directory**, and write `raw_results_path`/`raw_results_checksum` from its own samples — until T200 passes (FR-043c · SC-052)
- [ ] T203 [US5] Implement the sequence recorder in `tests/evaluation/harness/gate.py`: three consecutive `VALID` runs, all seven measures passing, **identical manifest fields except timestamp and run identifier** (T180), **three distinct `process_fingerprint` values**, three completed preflights, three distinct `raw_results_checksum` values and **three distinct run directories**; any failed, invalid, cancelled or mismatched execution **breaks** the sequence and the next valid execution becomes **run one** — until T201 passes (FR-043, FR-043a, FR-043b, FR-043c · SC-017, SC-053)
- [ ] T204 [US5] Implement the orchestrator `tests/evaluation/harness/orchestrate.py`: one command launching **three isolated child processes** sequentially, each starting only after the previous reaches a terminal result, each with empty request and result caches and its own run directory; an in-process loop is not implemented and is rejected by T201(a) (FR-043c · SC-052)
- [ ] T205 **FALSIFY** — change `tests/evaluation/harness/orchestrate.py` (created T204) to loop in-process and write three rows into one run directory, confirm `tests/evaluation/test_three_run_gate.py` cases (a) and (a′) fail the sequence, then restore that file byte-identical
- [ ] T206 [US5] Update the Feature 004 section of `specs/004-permission-aware-rag/verification.md` (created T044): consolidate the Phase 1 and Phase 4 red records and add the evaluation-run release table — three run rows, each `NOT RUN`, each with its run id, **run directory**, `process_fingerprint`, `run_manifest_checksum` and validity — plus the schema those rows follow and a statement that **no evaluation has been performed** (FR-043c · SC-017, SC-020)
- [ ] T207 [US5] Add `make evaluate-full` to `Makefile`, documented as the **controlled** lane: real embedder, real endpoint, full 105-document corpus, invoked through the T204 orchestrator, never by ordinary CI (FR-035d · CHK116, CHK218)
- [ ] T208 [P] [US5] Implement the controlled timing experiment in `tests/evaluation/harness/timing_indistinguishability.py`: **≥ 50 warm samples per case**, p95 time-to-terminal difference between a permission-narrowed empty result and a genuinely empty one **≤ max(100 ms, 20%)** — **controlled lane only** (FR-017a · SC-037 · R25)

### 5G — Observability and audit evidence

- [ ] T209 [P] Implement audit writing in `apps/api/src/eaios_api/chat/audit.py`: asker, tenant, `question_digest`, **documents consulted** in the FR-036a sense, decision and outcome, with refusals of ingestion, retrieval and generation distinguishable from failures, and a cancelled or disconnected generation audited exactly as any other (FR-036, FR-039 · SC-012 · CHK165)
- [ ] T210 [P] Extend `tests/security/test_log_safety.py` to sweep for document content, question text, answer text, embeddings, credentials, **the tunnel URL and hostname**, and any derived passage form across logs, traces, metrics, audit records and committed files (FR-013a, FR-037 · SC-011, SC-018c · CHK206)
- [ ] T211 [P] Implement split retrieval/generation duration telemetry in `apps/api/src/eaios_api/chat/telemetry.py`, keeping candidate and exclusion counts **operator-only** (FR-038 · CHK172, CHK171)
- [ ] T212 **FALSIFY** — log a passage body from `apps/api/src/eaios_api/retrieval/service.py` (created T094), confirm `tests/security/test_log_safety.py` fails, then restore that file byte-identical

### 5H — CI separation and documentation

- [ ] T213 Wire both lanes in `.github/workflows/ci.yml`: the **ordinary** lane runs fixtures and the stub with zero outbound network, **no model download and no model load**, and **blocks the build** on the FR-035b set — already including the structural checks (T158) and now the run-manifest validation (T177) and the three-run gate (T200, T201); the **controlled** lane is never triggered by CI, demonstrated by a run in which an induced leak fails the build (FR-035, FR-035b, FR-035d, FR-035l, FR-035n · SC-013, SC-018 · CHK215)
- [ ] T214 [P] Add `docs/rag.md` describing the two lanes, the **three manifests and their disjoint scopes**, the per-run directory layout, the vocabulary of FR-036a, and the ingestion and evaluation commands; link it from `docs/README.md` (FR-035m, FR-036a, FR-035b, FR-035d · CHK215)
- [ ] T215 [P] Update the root `README.md` feature table with feature 004 as **in progress**, explicitly not claiming any threshold met, and run `make docs-check` (FR-035e · SC-020)
- [ ] T216 Run `make test` and `make lint`, record the run id and result in the Feature 004 section of `specs/004-permission-aware-rag/verification.md`, confirm the public website, health endpoints and dataset manifest remain anonymously reachable and every feature 001–003 check passes unchanged, and confirm `make fingerprint` matches the value recorded in `docs/dataset.md` before indexing (FR-040, FR-041, FR-042 · SC-014)

**Checkpoint**: the evaluator refuses a vacuous figure; each run owns an immutable directory;
the three-run gate rejects all five falsifying cases; the two lanes cannot be confused.

---

## Phase 6 — Agents ⟨requires three consecutive `VALID` passing runs⟩

- [ ] T217 **GATE** — read the Feature 004 section of `specs/004-permission-aware-rag/verification.md` (created T044); confirm **three consecutive rows** recording `VALID` runs with all seven measures passing, the **same `gpu_series`**, **three distinct `process_fingerprint` values**, **three distinct run directories**, three completed preflights and identical manifest fields except timestamp and run id. If any row is `NOT RUN`, `INVALID`, a different series, or shares a fingerprint or directory, **stop here** (FR-043, FR-043a, FR-043b, FR-043c · SC-017)
- [ ] T218 ⟨blocked by T217⟩ Draft the agent tool-declaration contract in `specs/005-agent-capabilities/contracts/tools.md` — typed I/O, permissions, tenant scope, audit class, approval class — per Constitution Principle VI. **Design only; no execution path** (FR-043)
- [ ] T219 ⟨blocked by T217⟩ Draft the human-approval-gate design in `specs/005-agent-capabilities/contracts/approvals.md` for irreversible actions per Constitution Principle VII (spec Assumptions)
- [ ] T220 ⟨blocked by T217⟩ Write `tests/security/test_agent_phase_gate.py`: fails if any agent tool, planner or orchestration entry point exists while `specs/004-permission-aware-rag/verification.md` lacks three passing rows (SC-017)

---

## Dependencies

```
Phase 0 ─────────────────┐            (T001–T037)
                         ├─→ Phase 2 (T056 gate: preview PASS)
Phase 1 ─────────────────┘            (T038–T055)   [T043, T047, T049 blocked until T029]
   │
   └─→ Phase 2 (T056–T088) ─→ Phase 3 (T089–T111) ─→ Phase 4 (T112 gate: first-token PASS)
                                                          │
                                                     (T112–T168) ─→ Phase 5 (T169–T216)
                                                                          │
                                                                     Phase 6 (T217 gate)
```

**Hard gates**: T056 (preview `PASS`), T112 (first-token `PASS`), T217 (three isolated passing
executions). Each reads a file an earlier task creates — `benchmarks/phase0/GATE.md` by T035,
`verification.md` by T044.

**Ordering, verified against each target's description:**

| Test | Precedes | Guards |
|------|----------|--------|
| T006 subprocess import proof | T026 builder | packaging installed, not path-faked |
| T009–T011 chunking | T013 chunker | FR-007a |
| T015, T016 embedding | T017 embedder | FR-011c, FR-011f |
| T018 bare-checkout guard | §0E onward | FR-035p |
| T021 server provisioning | T030 first-token | FR-035o |
| T022 preflight ordering | T023, T024 | FR-035a |
| T027 index validation | T029 measurement | FR-035a |
| T038–T043 filter + index | T045, T047 | FR-014, FR-014b |
| T020 provisioning prerequisites | T021 server verifier | FR-035o · SC-055 |
| T029 preview measurement **completes** | T043, T044, T047, T049 | Qdrant service exclusion |
| T061–T063 admission | T064 | FR-002, FR-002a, FR-002b |
| T067–T070 payload + scope | T071 runner | FR-004, FR-005, FR-010, FR-001a |
| T076, T077 corpus version | T078–T080 | FR-018a |
| T089–T093 | T094, T095 | FR-013, FR-017a, FR-013a |
| T098, T100 budget | T101 | FR-028b1, FR-028b5 |
| T113–T116 provider + transport | T118–T120 | FR-011d, FR-028m |
| T125 synthetic corpus | T127 | FR-011l |
| T130 health | T131 | FR-028k |
| T133 stream interruption | T134 | FR-028m |
| T135, T136 per-turn + history | T138–T141 | FR-012a, FR-026 |
| T142–T144 SSE / stop / disconnect | T145–T147 | FR-025, FR-025a, FR-025b |
| T150–T153 grounding, abstention, records, structure | T154–T157 | FR-019, FR-021, FR-023, FR-028c, FR-032c |
| T172 preflight | T173, T174 | FR-035i |
| T177 run manifest | T178–T180 | FR-035j, FR-035k, FR-043b |
| T200, T201 three-run gate | T202–T204 | FR-043c |

**FALSIFY map** — rebuilt from the FALSIFY task lines; every target created earlier:

| FALSIFY | Breaks | Created by |
|---|---|---|
| T008 | `packages/core/pyproject.toml` | T005 |
| T014 | `chunking/chunker.py` | T013 |
| T025 | `benchmarks/phase0/__main__.py` | T024 |
| T037 | `docs/models.md` (fixture from T036) | T001, T036 |
| T049 | temporary collection of `test_payload_indexes.py` | T043 |
| T081 | `indexing/runner.py` | T071 |
| T086 | `tests/fixtures/retrieval/manifest.json` | T084 |
| T096 | `retrieval/empty_result.py` | T095 |
| T097 | `authz/filters.py` | T045 |
| T111 | `.github/workflows/ci.yml` | T110 |
| T148, T149 | `chat/cancellation.py` | T146 |
| T159 | `retrieval/structural.py` | T154 |
| T175 | `harness/__main__.py` | T174 |
| T181 | fixture run directory | T177 |
| T189 | `grounding_calibration.yaml` | T184 |
| T199 | `results/series.json` | T198 |
| T205 | `harness/orchestrate.py` | T204 |
| T212 | `retrieval/service.py` | T094 |

## Parallel groups

`[P]` requires different files **and** different mutable resources.

| Group | Tasks | Why safe |
|-------|-------|----------|
| **PG-A** | T002, T003 | `.gitignore` + a new test module; a new benchmark doc. T001 owns `docs/models.md` alone |
| **PG-B** | T009, T010, T011, T015, T016 | five distinct pure test modules, no stack, no store |
| **PG-C** | T038, T039, T040, T041, T042 | five distinct filter/boundary test modules. **T043 is not `[P]`** — it provisions a collection and is blocked until T029 |
| **PG-D** | Phase 0 ∥ Phase 1 **except** T043, T044, T047, T049 | those four touch the Qdrant service T029 measures — T044 because it runs T043's test; everything else is disjoint |
| **PG-E** | T060, T061, T062, T067, T068, T069, T076, T077 | eight distinct Phase 2 test modules, each with its **own temporary collection** *and* **PostgreSQL isolation**: unique identifiers per test, rows either rolled back or confined to identifiers no sibling reads, and **no truncation, no migration, and no shared active corpus-version key**. T063, T066, T070 are **not** `[P]` — they own a collection's lifecycle |
| **PG-F** | T089, T090, T091, T092, T093, T098, T099, T100, T103, T105, T106 | distinct Phase 3 test and vocabulary modules |
| **PG-G** | T113, T115, T116, T119, T122, T124, T125, T130, T133 | provider tests, stub, settings and boundary suites. **T114 is not `[P]`** — it edits the shared boundary module |
| **PG-H** | T135, T136 ∥ T142, T143, T144 | per-turn and history suites are independent of SSE, stop and disconnect |
| **PG-I** | T150, T151, T152, T153 | four distinct grounding/abstention/record/structure modules |
| **PG-J** | T164, T166, T167, T168 | web tests and three new UI components |
| **PG-K** | T177 ∥ T183, T185 ∥ T200 | run-manifest fixtures, judge schema and boundary test, three-run fixtures. **T201 is not `[P]`** — same file as T200 |
| **PG-L** | T191, T192, T208 ∥ T209, T210, T211 | evaluation harness and observability, different trees |

**Never `[P]` — Qdrant service**: T026, T027, T029, T037 (Phase 0 measured window) · T043,
T044, T047, T049 (blocked until T029) · T063, T066, T070, T071, T080, T083, T084 (production
collection).
**Never `[P]` — PostgreSQL**: T054, T059, T082, T139, T194 (ephemeral database, one at a time).
Any `[P]` task that writes to the shared development database MUST use **unique identifiers**
and **roll back or confine its rows**; **truncation, migration and writing a shared active
`corpus_versions` key are forbidden in parallel** — those are the operations that make two
otherwise independent tests collide.
**Never `[P]` — same file**: `authz/filters.py` (T045, T046, T097) · `seed/cli.py` (T074, T085)
· `indexing/admission.py` (T064, T065) · `indexing/runner.py` (T071, T080, T081) ·
`corpus_version.py` (T052, T080) · `models/retrieval.py` (T057, T078, T138) ·
`retrieval/citations.py` (T102, T104, T155) · `chat/router.py` (T108, T132, T157) ·
`chat/cancellation.py` (T146–T149) · `retrieval/structural.py` (T154, T159) ·
`tests/integration/test_migrations.py` (T054, T059, T082, T139, T194) ·
`harness/run_manifest.py` (T178, T179, T195) · `harness/series.py` (T180, T197) ·
`verification.md` (T044, T117, T137, T206, T216) ·
`.github/workflows/ci.yml` (T110, T111, T123, T158, T213) · `Makefile` (T004, T087, T207).

**`tests/integration/test_migrations.py` is serialized end to end.** T054, T059, T082, T139
and T194 all extend or re-run that one module against the **same uniquely named ephemeral
PostgreSQL database**, and each performs a migration. **None of them is `[P]`**, and they run
in ascending order. A migration is precisely the operation the PG-E rule forbids running
beside anything else, so the file rule and the PostgreSQL rule agree rather than contradict.

**`Makefile` is serialized, but only against itself.** T004, T087 and T207 each add a target
to the one file; **none is `[P]`**. They sit in Phases 0, 2 and 5, so the phase gates already
separate them — the tag is removed so the scheduling contract says what the gates enforce.

**`tests/evaluation/test_three_run_gate.py` — read the rule precisely.** **T200 is `[P]`**: it
may run beside any unrelated task, and PG-K schedules it beside T177, T183 and T185. What the
rule forbids is the *pair*: **T201 must follow T200** — it extends the module T200 creates,
with the five falsifying cases — and **T201 is not `[P]`**. The file appears here as a
same-file ordering constraint between two specific tasks, not as a parallel-safety exclusion
on T200.

**Cross-phase shared file — a different class, and not an exclusion.**
`tests/security/test_no_download_at_request_time.py` is written by **T016** (Phase 0: weights
absent, the embedder raises at construction) and extended by **T115** (Phase 4: the provider
path never triggers a download). **Both keep `[P]`, and both are correct to keep it.** They
cannot overlap, because **T016 belongs to Phase 0 and T115 to Phase 4**, and the gates
**T056** and **T112** stand between them — Phase 4 cannot begin until the `first_token` row
reads `PASS`, by which time every Phase 0 task has finished.

This is the general rule, stated once: **`[P]` authorizes parallelism only among tasks inside
the phase currently executing. It never authorizes crossing a phase gate.** Two `[P]` tasks in
different phases are separated by the gate, not by their tags, so a shared file between them
is not a conflict and neither task loses `[P]`. Only same-phase sharing needs the
serialization rules above.

## Ordinary CI versus controlled evaluation

Classified task by task — **not** all of Phase 5 is controlled.

| | Ordinary CI (blocks the build) | Controlled evaluation (never blocks) |
|---|---|---|
| Phase 0–4 | T002, T006, T007, T008, T018, T020, T032, T036, T037, T062, T069, T070, T072, T083, T092, T093, T110, T115, T116, T123, T124, T125, T130, T133, T135, T136, T142–T144, T150–T153, T158, T164, T168 | T021, T029, T030 |
| Phase 5 | T172, T177, T181, T185, T187, T189, T192, T200, T201, T205, T210, T212, T213, T216 | T169, T170, T178–T180, T182–T184, T186, T188, T190, T191, T193–T199, T202–T204, T206–T208 |
| Corpus | committed fixture subset | full 105 documents |
| Generator | `StubProvider` (T119) | the Phase 0-provisioned Colab T4 |
| Network | **zero** outbound — no Colab, no ngrok, no model download, no model load | tunnel only |

**T007 and T020 are ordinary CI.** T007 is a **static** read of three Dockerfiles,
`packages/core/pyproject.toml` and `uv.lock` — no network, no model, no service. T020 runs
**against a fake provisioning probe** — it proves the seven-prerequisite refusal without
reaching Colab, ngrok or any weight file. Both **block the build**; neither belongs to the
controlled lane, where T021 (which contacts the real endpoint) sits.

T213 keeps them separate; T111 is the falsification that proves it.

## Task totals

| Phase | Tasks | Range | Test-authoring | Written failing first | FALSIFY |
|-------|------:|-------|---------------:|----------------------:|--------:|
| 0 — feasibility gates | 37 | T001–T037 | 12 | 8 | 4 |
| 1 — authorization foundation | 18 | T038–T055 | 9 | 6 | 1 |
| 2 — deterministic ingestion | 33 | T056–T088 | 14 | 12 | 2 |
| 3 — retrieval and citations | 23 | T089–T111 | 10 | 9 | 3 |
| 4 — generation and streaming | 57 | T112–T168 | 23 | 16 | 3 |
| 5 — evaluation and stabilization | 48 | T169–T216 | 16 | 5 | 6 |
| 6 — agents | 4 | T217–T220 | 1 | 0 | 0 |
| **Total** | **220** | T001–T220 | **85** | **56** | **19** |

## Story coverage

| Story | Priority | Phases | Independently testable when |
|-------|----------|--------|------------------------------|
| **US1** — an answer you can check | P1 | 3, 4 | T104, T150 and T152 pass — citations resolve, invented sources drop, unsupported figures are rejected |
| **US2** — two people, one question | P1 | 1, 3 | T090 and T092 pass — no trace, and no distinguishable empty |
| **US3** — bring the corpus in | P2 | 2 | T067 passes — a second run is a no-op |
| **US4** — the answer as it is written | P3 | 4 | T142, T143, T144 and T133 pass — SSE, stop, disconnect, tunnel failure |
| **US5** — prove the quality | P3 | 0, 5 | T172 and T200 pass — no vacuous figure, no vacuous sequence |

**MVP scope**: Phase 1 + Phase 2 + Phase 3 (T038–T111, 74 tasks) delivers **US2 and US3** end
to end — authorization-constrained retrieval over a deterministically ingested corpus, with
citations and indistinguishable empty outcomes, entirely offline and with no GPU.

## Checklist evidence map

All 96 open checklist items map to a task or a named future evidence artifact.

| Checklist | Open items | Answered by |
|-----------|-----------|-------------|
| `authorization.md` | CHK001–CHK004, CHK007–CHK009, CHK011, CHK012, CHK015–CHK020, CHK026, CHK029, CHK031–CHK035 | T038–T049, T089–T097, T105–T107 |
| `authorization.md` | CHK024, CHK027, CHK028 | T042 + T114/T123, T050–T053, T075 |
| `authorization.md` | CHK193, CHK196, CHK197, CHK199 | T124, T125, T150, T155 |
| `ingestion.md` | CHK038, CHK046–CHK048, CHK052, CHK057, CHK060, CHK063–CHK066 | T060–T065, T067–T074 |
| `ingestion.md` | CHK051 | T070 |
| `models.md` | CHK069, CHK070, CHK072, CHK073, CHK078, CHK084–CHK086, CHK087, CHK089 | T001, T002, T005, T006, T007, T015–T017, T193, T196 |
| `models.md` | CHK177–CHK179, CHK180–CHK185 | T113–T123 |
| `evaluation.md` | CHK093, CHK097, CHK098, CHK104, CHK106–CHK108, CHK113, CHK117 | T169–T208 |
| `experience.md` | CHK140, CHK148, CHK149, CHK152–CHK156, CHK201, CHK204 | T142–T149, T162–T168 |
| `observability.md` | CHK157, CHK159, CHK160, CHK162–CHK164, CHK166, CHK167, CHK169, CHK170, CHK173, CHK174, CHK176, CHK207, CHK211 | T209–T212 |
| `performance.md` | CHK132, CHK135, CHK188 | `benchmarks/phase0/GATE.md` (T035), `benchmarks/phase0/results/` (T033) and `preview-index-manifest.json` (T027) — **evidence artifacts, not tasks**; no figure exists until Phase 0 runs |

**Chunk-bounds evidence**: the 400/50 bounds, sentence rules and chunk-id composition are
answered by the **Phase 0** chunker tasks **T009–T014**, not by any Phase 2 task.

**Mapped to a future evidence artifact rather than a task**: CHK132, CHK135, CHK188. **No open
item is unmappable.**

## Ambiguities that block a task from being fully executable

**None.** Every clarified decision is a requirement with executable tasks behind it:

| Decision | Requirement | Tasks |
|----------|-------------|-------|
| Chunk bounds 400 / 50 | FR-007a, FR-007b · R21 | T009–T014 |
| Grounding judge + calibration | FR-032a–FR-032c · R22 | T182–T190 |
| `data_version` = corpus checksum | FR-018a · R23 | T050–T053, T076–T082 |
| End-to-end stop | FR-025a · R29 | T143, T146, T148 |
| Per-turn access context | FR-012a · R30 | T135, T140 |
| Client disconnect | FR-025b · R31 | T144, T147, T149 |
| Three manifests, run manifest is evidence | FR-035j–FR-035n, FR-043b · R32 | T176–T181, T195 |
| Three isolated executions | FR-043c · R33 | T200–T206, T217 |
| Phase 0 provisions the server; one run directory each; bounded scope | FR-035o, FR-035j, FR-035p · R34 | T018–T021, T178, T193, T202 |

**No benchmark and no evaluation has been run, and no task above records one as passed.**
