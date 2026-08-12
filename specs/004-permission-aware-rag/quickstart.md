# Quickstart: Permission-Aware Knowledge Retrieval

**Feature**: 004-permission-aware-rag · **Date**: 2026-08-11

Runnable validation scenarios. Contracts live in [contracts/](contracts/); entities in
[data-model.md](data-model.md). Nothing here has been executed — this feature is not
implemented.

---

## Prerequisites

**Order matters.** Phase 0 runs **after** stack, weight and endpoint provisioning and
**before** production ingestion. `eaios-seed index` is **not** a prerequisite of the preview
benchmark — Phase 2 is gated *by* that benchmark, so requiring its output would be circular
(FR-035a). The preview benchmark builds its own temporary index.

**1 — stack:**

```bash
make up && make seed && make credentials
```

**2 — generation-server provisioning** (FR-035o), before any first-token measurement: run
`infrastructure/colab/generation_server.ipynb` with the pinned Qwen weights (revision and
checksum verified), an authenticated HTTPS ngrok endpoint, the service token, a **verified**
T4, the recorded runtime and quantization, a working health endpoint, and streaming
first-token protocol compatibility. `.env` (ignored) carries `GENERATION_URL` and
`GENERATION_SERVICE_TOKEN`. Any missing prerequisite leaves the first-token row **`NOT RUN`**
or records it **`INVALID`** — never a pass. **Phase 4 reuses this same artefact.**

**3 — Phase 0** (§0 below).

**4 — production ingestion**, only once the preview row reads `PASS`:

```bash
eaios-seed index --status      # expect: no run recorded
eaios-seed index
```

Without the tunnel, every scenario below still runs except §5 and §6: retrieval and
authorization do not depend on it (FR-028l).

---

## 0 — Phase 0 feasibility benchmark (run this first)

```bash
make benchmark-phase0
```

Reports two figures against their thresholds and writes a provenance record.

**These thresholds have not been measured.** A failure blocks downstream embedding or
generation work (FR-035f). Record the result and the raw timing summary either way; do not
adjust a threshold to make it pass.

---

## 1 — A cited answer you can check (US1)

Sign in as the `employee.engineering` persona, open `/portal/assistant`, ask a question the
general leave policy answers.

**Expect**: a `sources` event before any token; an answer citing that policy; each citation
opening to the passage that supports the claim. Ask something the corpus cannot answer and
expect an explicit refusal with no citations and no invented content.

---

## 2 — Two people, one question, different answers (US2)

Ask the identical question as a persona who can reach a confidential document and as one
who cannot.

**Expect**: the permitted answer cites it; the other's answer, citations, and wording
contain **no trace** of it — no count, no "some sources withheld", no difference in shape.
The permitted case is what proves the exclusion was a permission decision rather than an
empty corpus.

```bash
uv run pytest tests/security/test_rag_permission_split.py -m security -v
```

---

## 3 — Ingestion is idempotent (US3)

```bash
eaios-seed index --status        # note chunk count and per-document states
eaios-seed index                 # second run
eaios-seed index --status        # expect: identical counts, corpus reported current
uv run python -c "from eaios_seed.cli import app; app()" verify --profile full
```

**Expect**: zero new chunks, zero changed chunks, no document in a non-terminal state, and
the dataset fingerprint unchanged (FR-042).

---

## 4 — Authorization is a constraint on the search

```bash
uv run pytest tests/security/test_authorize_before_search.py -m security -v
```

**Expect**: the recorded Qdrant request carries the full payload filter; no test observes a
candidate the caller may not read, even transiently. The falsification is the point —
removing a key from `qdrant_filter` must fail a named test (research R1).

---

## 5 — Streaming, cancellation, and an unavailable generator

Ask a question and stop it mid-answer. **Expect**: partial text retained and marked
incomplete, and exactly one `done` event with `state: stopped`.

Stop the Colab session, then ask again. **Expect**: the designed
`generation_temporarily_unavailable` state, retrieval still returning sources, and no
fallback to any other provider (FR-028j).

---

## 6 — Nothing forbidden leaves the boundary

```bash
uv run pytest tests/security/test_outbound_payload.py -m security -v
```

**Expect**: for every question in the evaluation set, the serialized outbound request
contains only `question`, `passages`, `max_tokens`, `temperature`. A failure names the
offending **field** and never prints its value (FR-037a).

---

## 7 — Ordinary CI runs offline

```bash
uv run pytest tests/security tests/integration -m "security or integration"
```

**Expect**: green with no Colab session, no tunnel, and no network — committed fixtures and
the stub generator only. Then corrupt `manifest.json`'s `vector_dimension` and expect the
build to fail (SC-022).

---

## 8 — The controlled evaluation

```bash
make evaluate-full
```

**Expect**: seven measures against thresholds, each labelled **deterministic** or
**statistical** (FR-034a), each reported as **numerator / denominator / percentage**, a
`VALID`/`INVALID` verdict, and a provenance record naming the actual GPU, the GPU **series**,
and the corpus fingerprint. The corpus is the **full 105 documents**, never the fixture
subset (FR-035d).

A CPU-only Colab allocation must be recorded `INVALID` — neither a pass nor a failure
(FR-035c). A **faster-than-T4** allocation must be recorded in a separate named series: valid
for grounding, citation precision, abstention and leakage; **not** valid for either latency
threshold (FR-043a).

Run the deterministic lane twice and compare: recall over the fixtures, authorization
outcomes, citation resolution and the leakage count must be **identical**. A difference is a
defect, not variance (FR-034a).

Three consecutive passing `VALID` runs on the **same** GPU class are what open the agent
phase. **Agent work does not begin before that** (FR-043). **No run has been performed.**

---

## 9 — The three late decisions

**Oversize refusal preserves what worked** (FR-002a). Index a document, confirm it is
answerable, replace its stored bytes with more than 2 MiB of text, and re-run ingestion.

**Expect**: state `REFUSED` with reason `TOO_LARGE`, zero new chunks, and the **earlier
version still retrievable and still citable**. A refusal must not be a deletion.

**Company-wide documents are reachable** (FR-014a). Ask a question answered by one of the
18 seeded documents with a null `country`.

**Expect**: it is retrieved. Under equality-only filtering this returns nothing for every
caller, which is the defect R4 records — so this scenario is the regression test for it.

**The passage budget holds and citations are exact** (FR-028b1–b3).

```bash
uv run pytest tests/security/test_passage_budget.py -m security -v
```

**Expect**: no request exceeds 5 passages, 400 tokens per passage, or 2,000 tokens total by
the pinned tokenizer; every trimmed passage ends at a sentence boundary; and every citation
resolves to **exactly** the span sent — never the wider chunk.

---

## 10 — The evaluation cannot report a vacuous pass

Induce each preflight condition (FR-035i) in turn and confirm the evaluator **exits nonzero
before printing any metric**:

```bash
uv run pytest tests/evaluation/test_preflight.py -m integration -v
```

1. empty question file → nonzero, no metric printed
2. an empty required partition (delete every unanswerable question) → nonzero
3. counts edited to disagree with `manifest.json` → nonzero
4. a metric whose denominator would be zero → nonzero
5. an `expected_document_ids` entry naming a document outside the 105 → nonzero

**Expect**: in every case a named condition and a nonzero exit. The failure this guards is
not an error — it is `0/0` rendered as **100%**, a perfect score over nothing.

Then confirm every evaluation output carries the **corpus fingerprint, document count,
partition counts and manifest checksum**, which is what stops a fixture-lane figure being
quoted later as a full-corpus one (FR-035b).

---

## 11 — The three implementation constants

**Chunk bounds hold, and sentences survive** (FR-007a, FR-007b).

```bash
uv run pytest tests/unit/test_chunk_boundaries.py tests/unit/test_chunk_identity.py -v
```

**Expect**: every chunk ≤ 400 BGE-M3 tokens, overlap ≤ 50 tokens, no empty or whitespace-only
chunk, and **no split sentence** except where one sentence alone exceeds 400 tokens — those
split at a clause or whitespace boundary and reproduce identically on a second run. Chunk ids
change if the tokenizer, either bound, or the chunker version changes, even when the text does
not.

**The judge is calibrated before it counts** (FR-032a–FR-032c).

```bash
uv run pytest tests/evaluation/test_judge_calibration.py -v
```

**Expect**: ≥ 90% agreement with `tests/evaluation/calibration/grounding_calibration.yaml`
before any release-gate run is scored. Corrupt three labels and re-run: agreement drops, and
grounding and citation precision are recorded **`INVALID`** — not failed, not passed. Confirm
the serialized judge request carries only `question`, `answer`, `citations[]`, `cited_spans[]`.

**The corpus version behaves under failure** (FR-018a).

```bash
eaios-seed index --status        # note the active checksum
eaios-seed index                 # no-op re-run
eaios-seed index --status        # expect: the SAME checksum, cache still warm
```

Then interrupt an ingestion part-way and re-check: **no new checksum is published** and the
previous one is still active. Then change `ChunkerConfig`'s overlap and re-ingest: a
**different** checksum, and every answer cached under the old one is unreachable — without any
key having been deleted.

---

## 12 — The residual boundaries

**Nothing survives the request** (FR-013a).

```bash
uv run pytest tests/security/test_passage_lifetime.py -m security -v
```

**Expect**: zero occurrences of passage content, prompt content, or any derived form in
persistent storage, caches, logs, traces, metrics, snapshots, test artifacts, exception
messages or retry queues — **including after an aborted request**, which is the path where a
reference most plausibly survives. The index is exempt; the cache holds references only.

**Two empty answers look the same** (FR-017, FR-017a). Ask a question answerable only outside
the asker's permitted set, then one nobody can answer.

**Expect** — identical HTTP status, identical SSE event types and ordering, identical wording,
identical retry behaviour, no withheld-source signal. Ordinary CI asserts the control flow is
identical; the controlled security evaluation takes **≥ 50 warm samples per case** and requires
the p95 time-to-terminal difference to stay within **max(100 ms, 20%)**. That timing figure
gates stabilization, not shared-runner CI. **It has not been measured.**

**A thin document is refused, not indexed** (FR-002b). Ingest a document of eighteen
characters, then one of pure punctuation, then one with invalid UTF-8 after normalization.

**Expect**: `EMPTY_BODY` in all three cases, before chunking, zero chunks written.

**An embedding change replaces, never mixes** (FR-011i). Change the pinned revision and
re-ingest, then interrupt it.

**Expect**: the previous index and corpus checksum still active and still answering; **no
collection ever holding two embedding identities**; and after the interruption, the previous
generation **byte-identical** to its pre-attempt state.

**The record correlates without disclosing** (FR-028o). Inspect a run record.

**Expect**: provider profile, GPU series, ngrok region, protocol/TLS version, RTT p50 and p95,
health outcome, and a keyed **`endpoint_hmac`** — and **zero** occurrences of the hostname, the
full URL, the ngrok token, or the service credential. Two runs against the same endpoint
correlate by fingerprint alone.

**The outbound path refuses an unapproved corpus** (FR-011l). Modify one seeded document and
attempt a generation request.

**Expect**: the corpus-manifest fingerprint no longer matches the approved synthetic corpus and
**no outbound request is constructed** — the failure happens before any passage is serialized,
not before it is sent.

---

## 13 — Stopping stops the work, and every turn is its own

**A stop stops generation, not just the screen** (FR-025a).

```bash
uv run pytest tests/integration/test_end_to_end_cancellation.py -m integration -v
```

Ask a long question and stop it mid-answer. **Expect**: emission halts at once; the provider
stops generating; exactly one `done` event with `state: stopped`; the partial text retained and
marked incomplete; the turn recorded and audited; and **no** retry, queued continuation or
background generation afterwards.

**The falsification is the point.** Make the implementation stop only the display while
generation continues, and confirm the named test **fails**. That variant satisfies every other
criterion in this specification, which is exactly why it must be caught here.

Measure the close: the local API must close the stream and finish cleanup **within 2 seconds**.
Then block the provider's acknowledgement and stop again.

**Expect**: at 2 seconds the connection is severed, `provider_cancel_status = UNCONFIRMED` is
recorded content-free, and **zero bytes** of later provider output appear in any response,
record or log.

**Each turn builds its own access context** (FR-012a).

```bash
uv run pytest tests/security/test_per_turn_access_context.py -m security -v
```

Ask a question, withdraw a permission, then ask a follow-up in the same conversation.

**Expect**: the follow-up builds a **new** snapshot, the withdrawal takes effect on it, and the
earlier turn's content is not reused to answer it. Confirm each turn's
`permission_fingerprint` differs, and that a test **fails** when a snapshot is reused across
turns. Repeat for a regenerated answer and a resumed conversation — both are new turns.

---

## 14 — Losing the client is a cancellation, not a lost reader

```bash
uv run pytest tests/integration/test_client_disconnect.py -m integration -v
```

Start an answer against the stub provider and drop the client mid-stream — navigate away, close
the tab, or kill the connection.

**Expect**: the local API detects the dead stream, **cancels upstream and stops generation**,
rejects every later byte from the provider, releases all request-scoped content, and finishes
local cleanup **within 2 seconds** — the same handling as an explicit stop, including
`provider_cancel_unconfirmed` if the provider does not acknowledge in time.

**Expect the record to differ**: the turn is persisted **`INCOMPLETE` with
`incomplete_reason = CLIENT_DISCONNECT`**, never `STOPPED`. The person did not ask to stop.

**Expect no terminal event** — the connection is gone, so none can be delivered and none is
required. The server-side state and the audit record are authoritative. Inspect that record:
turn id, timestamps, status, duration, cancellation-confirmation status — and **zero**
occurrences of question, prompt, passage, partial-answer, token, URL or credential content.

**Then falsify it.** Make the disconnect handler release the local request but leave the
provider generating, and confirm the test **fails**. That variant passes every browser-side
check there is, because there is no browser left to check it — only a test watching the
provider can catch it.

---

## 15 — Three manifests, and the one that is evidence

```bash
uv run pytest tests/evaluation/test_run_manifest.py -m integration -v
```

**Expect the scopes to stay disjoint** (FR-035m): `tests/fixtures/retrieval/manifest.json`
carries no generation-prompt, judge or provider field; `tests/evaluation/manifest.json` carries
no model or runtime field; `tests/evaluation/results/<run_id>/run-manifest.json` carries all
eleven configuration groups **in that run's own directory**, beside its raw results and its
results record. Ordinary-CI fixtures live in a separate committed fixtures directory. The first two are **inputs**, reviewed before a run. The third is
**evidence**, written by one.

**Expect every controlled run to emit it**, with all eleven groups populated, and the run's
results record to reference it by path and checksum.

Now omit one required field, then set one field to disagree with the live configuration.

**Expect** `INVALID_CONFIGURATION` in both cases — neither a pass nor a failure — and the run
advancing no gate (FR-035k).

**Then falsify the gate.** Take a passing run, change **only** the generation prompt hash, and
keep the previous series identity.

**Expect validation to fail.** The comparison is over **field values**, not over the series
label, so a relabelled series cannot carry a changed prompt into an existing sequence
(FR-043b). This is the cheapest way to defeat the three-run gate and the hardest to spot in
review, which is why it is a named test rather than a convention.

All of the above runs in **ordinary CI against fixtures** — no Colab, no ngrok, no model
execution (FR-035l).

---

## 16 — Three runs means three processes

```bash
uv run pytest tests/evaluation/test_three_run_gate.py -m integration -v
```

Ordinary CI exercises the gate against **fixture manifests and fixture results only** — no
Colab, no ngrok, no model load (FR-035n).

**Expect a counted sequence to require three isolated executions** (FR-043c): each started
after the previous reached a terminal result, each with its **own completed preflight**, its
own run id and timestamp, its own immutable `run-manifest.json`, its own raw results, its own
samples, and a **fresh process with empty caches**. Same day and the same verified T4
allocation are fine, provided every manifest field stays identical.

**Then falsify it four ways.** Each must **fail**:

| | Induce | Caught by |
|---|---|---|
| a | three result rows sharing one `process_fingerprint` | distinct fingerprints required |
| a′ | two runs writing the same `tests/evaluation/results/<run_id>/` | distinct run directories required (FR-035j) |
| b | a run whose `raw_results_checksum` matches an earlier run's | samples must be its own |
| c | a failed or invalid run between two passing runs | sequence breaks; next valid run is **run one** |
| d | a run with `preflight_completed_at` null | preflight must complete per execution |

Case (a) is the one that matters most: a loop inside one evaluation process writes three rows
as easily as three processes do, while sharing the warmed weights and populated caches the
three-run gate exists to sample across. **Three rows are not three runs.**
