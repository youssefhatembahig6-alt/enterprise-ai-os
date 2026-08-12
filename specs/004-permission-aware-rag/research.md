# Research: Permission-Aware Knowledge Retrieval and Grounded Answers

**Feature**: 004-permission-aware-rag · **Date**: 2026-08-11 · **Spec**: [spec.md](spec.md)

Phase 0 output. Every decision below is either forced by an existing artefact in this
repository, forced by a clarification recorded in the spec, or an open choice resolved
here with its alternatives.

**Three findings came out of reading the existing code, and two of them are defects.**
They are R3, R4, and R5. They matter more than anything else in this document, because the
plan is built on the assumption that feature 001 left a working filter path behind.

---

## R1 — The retrieval filter already exists, and it is not tested

**Finding**: `packages/core/src/eaios_core/authz/filters.py` defines
`qdrant_filter(subject: AccessContext) -> dict`, written during feature 001 precisely so
that "feature 004 consumes a filter derived from the same context the policy engine reads,
rather than inventing a second, subtly different notion of what a caller may see". Its
docstring states: *"It is unit-tested against a real context, which is the only honest
thing to do with code that cannot yet be exercised end to end."*

**It is not.** A repository-wide search finds exactly two references — its own module and
the `authz/__init__.py` re-export. No test file mentions it.

**Decision**: Adopt `qdrant_filter` as the single source of the retrieval constraint
(FR-013, FR-014), and write its missing unit tests **before** any search code calls it. The
tests must be falsifiable in the way this project already expects: deleting any single key
from the returned mapping must fail a named test.

**Rationale**: The function is the right design and the right home. The claim about it was
the defect, not the code. Re-deriving the filter in the search layer would create the
second notion of access the docstring warns against.

**Alternatives considered**: Building a filter inside the retrieval service — rejected, it
duplicates policy. Trusting the docstring — rejected on the evidence.

---

## R2 — Reuse `cache_key`; it was designed for this feature

**Finding**: `eaios_core.keys.cache_key(company_slug, permission_fingerprint,
normalized_question, data_version)` already exists, with a docstring stating that tenant
and permission fingerprint together "stop an HR-scoped answer from ever being served to an
ordinary employee" and the data version stops "a stale answer surviving a dataset change".
`AccessContext.permission_fingerprint` supplies the middle component, and
`cache_namespace(company_slug)` gives the per-tenant scan pattern.

**Decision**: Use `cache_key` unchanged for every cacheable stage (FR-018). Cache
invalidation on permission change (CHK023) is served by the fingerprint: a changed
permission set produces a different key, so a stale entry becomes unreachable rather than
needing deletion. Ingestion bumps `data_version`, which retires every answer built on the
old index.

**Rationale**: The composition is exactly FR-018's requirement and it is already
fingerprint-tested (`tests/unit/test_permission_fingerprint.py`: distinct sets → distinct
digests, reordering → same digest).

**Alternatives considered**: Keying on the full access context — rejected, it would put
identity in a cache key and defeat sharing between two callers with identical permissions.
Question-only keys — rejected, that is the cross-permission leak FR-018 names.

---

## R3 — DEFECT: the filter uses a payload field the vector store does not index

**Finding**: `qdrant_filter` returns six keys. The provisioned payload indexes in
`infrastructure/qdrant/` are six. **They are not the same six.**

| Field | Indexed | Used by filter |
|-------|:-------:|:--------------:|
| `company_id` | ✅ | ✅ |
| `department_id` | ✅ | ✅ |
| `classification` | ✅ | ✅ |
| `country` | ✅ | ✅ |
| `owner_id` | ✅ | ✅ |
| `document_id` | ✅ | ❌ |
| `allowed_roles` | ❌ | ✅ |

**Decision**: Add an `allowed_roles` keyword payload index to the Qdrant provisioning, as
part of this feature's first migration-equivalent step, **before** any point is written.
Keep `document_id` indexed — it is unused by the filter but required for chunk→document
joins, for FR-005 replacement, and for deletion.

**Rationale**: Feature 001's own note explains why the indexes were created before any
content: "adding it to an already-populated collection is a reindex". That reasoning
applies to `allowed_roles` and was missed. Fixing it now costs nothing; fixing it after
ingestion costs a full reindex.

**Alternatives considered**: Filtering roles after search — rejected outright, that is
FR-013's prohibition. Dropping `allowed_roles` from the filter — rejected, it is the
role-based layer of FR-014.

---

## R4 — DEFECT: equality on nullable attributes makes documents invisible

**Finding**: The filter constrains `department_id` and `country` by equality against the
caller's own values. Measured against the seeded corpus:

- **`country` is null on 18 of 105 documents** (both PUBLIC, all 12 INTERNAL, both
  RESTRICTED, and 4 CONFIDENTIAL). An equality constraint against a caller's country
  excludes every one of them, for every caller.
- **`department_id` is set on all 105**, but a caller belongs to exactly one department.
  Strict equality means an Engineering employee cannot retrieve the HR-owned general leave
  policy — the document the specification's own scenario 1 is about.

**Decision**: The attribute layer must treat a **null attribute on the document as company-wide**, which widens rather than narrows** (canonical term, FR-014a), and must treat department as a scoping
attribute that applies only where classification demands it. Concretely, the constraint
becomes, per attribute: *document attribute is null* **OR** *document attribute equals the
caller's*. Classification remains a ceiling, not a scope.

This changes `qdrant_filter`'s return shape from a flat equality mapping to a mapping the
search layer translates into a should/must structure. The change belongs in
`eaios_core/authz/filters.py`, with the unit tests from R1 written against the new shape.

**Rationale**: Without this, the smoke and full corpora both retrieve almost nothing, and
US1 scenario 1 — an employee asking about the general leave policy — cannot pass. This is
a correctness defect in an untested function, discovered by reading the data rather than
the code.

**Alternatives considered**: Backfilling `country` and `department_id` on every document —
rejected, it changes the fingerprinted dataset (FR-042) to work around a filter bug.
Dropping the attribute layer — rejected, FR-014 requires it.

**Resolved 2026-08-11** (FR-014a): a null *document* attribute means **company-wide**. A
caller *with* a value reaches matching plus company-wide documents; a caller *without* one
reaches company-wide only, unless an independent owner, role, or explicit ACL grant
authorizes the document. Null never disables a filter and never matches everything, and the
company boundary and classification ceiling always apply.

---

## R5 — Resource ACL data is thin; the evaluation set must not depend on it alone

**Finding**: `document_acl` holds **4 grants, all `USER`/`READ`**. `principal_type` allows
`USER`, `ROLE`, and `DEPARTMENT`; `permission` allows `READ` and `WRITE`.

**Decision**: Layer 4 (resource ACL) is exercised in retrieval against those 4 grants, and
the evaluation set must include at least one question whose answer is reachable **only**
through an ACL grant, plus its negative twin. `ROLE` and `DEPARTMENT` principals and
`WRITE` are **not** exercised by this feature and that is recorded as a coverage
limitation, not a silent omission (CHK016).

**Rationale**: Four grants is enough to prove the layer fires and not enough to prove it
fires for every principal type. Saying so is better than implying coverage that does not
exist.

---

## R6 — Deterministic chunking and stable identifiers

**Decision**: Chunk on document structure (paragraph boundaries, then a fixed token budget
with fixed overlap), with every parameter pinned in a `ChunkerConfig` whose hash goes in
the fixture manifest. Chunk identity is
`sha256(document_id ‖ chunk_index ‖ chunker_version ‖ chunk_text)`, truncated to a UUID.

**Rationale**: FR-007 requires identical boundaries, counts, and identifiers on any machine
and any run. Deriving the identifier from content *and* position *and* chunker version
means: identical content in two documents yields distinct ids (CHK040, because
`document_id` participates); a chunker change is visible as a wholesale id change rather
than a silent re-boundary; and re-running produces byte-identical ids (SC-007).

**Alternatives considered**: Sequential integers — rejected, they are not stable under
insertion. Content-only hashing — rejected, it collides across documents and would let one
document's permissions serve another's content.

---

## R7 — Ingestion state machine

**Decision**: Per document, per run: `PENDING → VALIDATING → {REFUSED | UNCHANGED |
CHUNKING → EMBEDDING → INDEXING → INGESTED}`. The terminal states are exactly the three
FR-003 names. A document is `UNCHANGED` when its `content_sha256` and the chunker
configuration hash both match the previous run. Replacement (FR-005) deletes by
`document_id` filter and re-inserts within one logical operation so no reader observes both
generations (CHK039).

**Rationale**: FR-003 requires every document to reach a terminal recorded outcome; the
intermediate states are what make "left in an indeterminate state" detectable rather than
inferred.

---

## R8 — Generation provider interface

**Decision**: A narrow interface — `stream_answer(question, passages, config) ->
AsyncIterator[Token]` plus `health() -> Health` — implemented by `ColabTunnelProvider` and
a `StubProvider` used by ordinary CI. Provider selection is explicit configuration
(FR-011d); no fallback chain exists, so a misconfigured provider fails rather than
silently degrading (FR-028j).

**Rationale**: The interface takes *passages*, never a query and never a store handle,
which is what makes FR-028c ("the generator never retrieves") a property of the type
signature rather than a promise about behaviour.

---

## R9 — Streaming transport

**Decision**: **Server-Sent Events** from the local API to the browser, with an explicit
terminal event carrying one of `complete | stopped | incomplete`. Cancellation propagates
by closing the upstream request to the provider.

**Rationale**: The portal already renders server-driven content and needs one-way streaming
only; SSE avoids a second protocol and works through the existing web→API boundary
(FR-028d). The explicit terminal event is what makes FR-028m checkable — an absent event is
itself a failure, whereas a closed socket is ambiguous.

**Alternatives considered**: WebSocket — rejected, bidirectionality is unused and it
complicates the same-origin route handler pattern feature 003 established. Polling —
rejected, it cannot satisfy progressive delivery.

---

## R10 — CI fixtures versus controlled evaluation

**Decision**: Two lanes, as FR-035b and FR-035d require. Ordinary CI loads a committed
fixture set (chunk texts, their vectors, and a manifest) into a throwaway Qdrant collection
and drives a `StubProvider`. The controlled lane runs the real embedder and the real
endpoint. The manifest (FR-035g) is verified at the start of every CI run, and a
disagreement fails the build.

**Rationale**: Every correctness property in FR-035b is a property of authorization,
determinism, or wiring — none needs a model. Keeping models out of CI keeps the build fast,
free, offline, and independent of a Colab session that expires.

---

## R11 — Service authentication and rotation

**Decision**: `GENERATION_SERVICE_TOKEN` is a random secret generated when the Colab
session starts, pasted into ignored local configuration alongside the tunnel URL, and sent
as `Authorization: Bearer`. The provider performs a `health()` probe before each streaming
request (FR-028k). Rotation is implicit: a new session mints a new token, and the old one
stops working, which is the desired failure.

**Rationale**: A short-lived shared secret is proportionate for a research profile reachable
only from the local API. Anything stronger (mTLS, signed requests) buys little when the
tunnel URL itself is unguessable and the corpus is synthetic.

---

## R12 — Benchmark methodology (FR-035f)

**Decision**: The Phase 0 benchmark is a standalone harness, not a test. It measures the
two figures separately, records the raw per-request timings, and writes a provenance record
(FR-028n). It reports; it does not gate CI.

**The thresholds are unmeasured.** Nothing in this document, and nothing the plan produces,
asserts that either is achievable. The local preview figure covers BGE-M3 query embedding
plus a filtered search on a CPU-only machine inside a 7.61 GB VM; the first-token figure
covers a network round trip through a shared tunnel plus prefill of a five-passage prompt
on a T4. Both are plausible and neither is demonstrated.

---

## R13 — Outbound payload inspection

**Decision**: A test-only transport interceptor implementing the same interface as the real
HTTP transport, installed by dependency injection in tests, which serializes the request,
asserts the FR-028a prohibitions against it, and drops it. It reports field names, counts,
and pass/fail only. It cannot be constructed in a running deployment because the production
container never registers it (FR-037b).

**Rationale**: Inspecting the serialized form is the only way to catch a forbidden field
that arrives through nesting or through a future schema change. Asserting on the object
graph would miss exactly that.

---

## R14 — Passage budget, trimming and excerpt spans

**Decision** (FR-028b1–b3): at most 5 passages, at most 400 tokens per passage, at most
2,000 retrieved-passage tokens in total, all counted by the **pinned generation tokenizer**;
trimming only at the nearest preceding sentence boundary; the **exact excerpt span sent to
generation** is recorded on the citation and is what a citation open resolves to.

**Rationale**: three bounds rather than one because they fail differently — passage count
governs diversity of sources, per-passage tokens governs whether any single passage can
crowd out the rest, and the total governs prefill time, which is the dominant term in the
first-token figure. Counting with the *generation* tokenizer rather than the embedder's or a
character approximation is what makes the budget mean the same thing to the model that
consumes it.

Sentence-boundary trimming exists because a fragment cut mid-clause can invert the meaning
of its source, and the citation would then attest to something the document does not say —
a grounding failure that reads as a success.

Excerpt spans exist because a citation resolving to the whole chunk would show a reader
context the model never received. That is a subtler breach of FR-019 than an uncited claim,
and harder to notice.

**Alternatives considered**: a single total-token budget — rejected, one long passage could
consume it entirely and reduce the answer to a single source. Character budgets — rejected,
they do not correspond to what the model consumes. Citing whole chunks — rejected above.

**Consequence for the data model**: `turn_citations` carries `excerpt_start`/`excerpt_end`.

---

## R15 — Oversize documents: atomic refusal, prior index preserved

**Decision** (FR-002a): 2 MiB of extracted, normalized UTF-8 text. Over that, refuse
**atomically before chunking** — no chunk, no embedding, no point — and **preserve the
document's previous successful index** until a replacement ingestion succeeds. Truncation is
prohibited.

**Rationale**: the ordering matters more than the number. Refusing *before* chunking means
there is no partial state to clean up, so the failure mode is "nothing happened" rather than
"something half-happened", which is the only version that is safe to retry.

Preserving the prior index is the less obvious half. Without it, editing a good document
into an oversize one would silently delete the answerable version — a content change would
become a availability regression with no signal. With it, the corpus degrades only when a
replacement genuinely succeeds.

Truncation is prohibited because a citation into a silently shortened document points at an
offset that no longer means what it said, and FR-028b3's span guarantee would be false.

**Alternatives considered**: splitting oversize documents across multiple records —
rejected, it invents corpus structure the dataset does not have and changes what a citation
identifies. Truncating with a marker — rejected above. Deleting the prior index on refusal —
rejected, it converts an ingestion refusal into data loss.

---

## R16 — Deterministic and statistical measures are different kinds of claim

**Decision** (FR-034a, FR-034b): classify every measure. Retrieval over committed fixtures,
authorization outcomes, citation resolution, and the leakage count are **deterministic** and
must reproduce exactly for a pinned configuration. Grounding, citation precision, abstention,
and both latency figures are **statistical**. Statistical thresholds are met by three
consecutive independently passing runs, never by an average; every run records per-question
outcomes and reports numerator, denominator and percentage.

**Rationale**: the two classes fail differently and so must be judged differently. A
deterministic measure that moves between identical runs has a **defect** — nondeterministic
ordering, an unpinned dependency, a leaked clock — and treating that drift as ordinary
variance is how such defects survive. A statistical measure that never moves is equally
suspicious, usually meaning the sample is too small to move.

Reporting the denominator matters more than it looks: `abstention 100%` is indistinguishable
between a run over forty unanswerable questions and a run over one. FR-035i stops the
degenerate case; the denominator makes the healthy case auditable.

Three passing runs rather than an average, because an average lets one failing run be carried
by two good ones — exactly the situation the gate exists to catch.

**Alternatives considered**: a single reproducibility rule for everything — rejected, it
either forbids legitimate generative variance or excuses genuine nondeterminism.
Averaging three runs — rejected above. Confidence intervals — rejected as heavier machinery
than a 40-question set supports.

---

## R17 — The evaluation preflight, and why a vacuous run is worse than a failed one

**Decision** (FR-031a, FR-035i): the evaluation manifest declares every partition with its
exact expected count, plus corpus fingerprint and checksum. The evaluator exits nonzero
**before computing any metric** on: zero questions, an empty required partition, counts
disagreeing with the manifest, a zero denominator, or an expected document missing from the
105-document corpus. Every output records corpus fingerprint, document count, partition
counts and manifest checksum.

**Rationale**: every quality figure here is a ratio, and every ratio has a denominator that
can quietly become zero — a mis-typed partition name, a filter that matches nothing, a
corpus loaded from the wrong profile. The failure mode is not an error; it is a **perfect
score**. `0/0` rendered as `100%` passes a gate that exists to stop exactly this.

Declared counts rather than inferred ones, because a partition whose size is whatever the
loader found cannot be checked for emptiness — it is always "correct" by construction.

Recording the corpus fingerprint on the output closes the other half: it makes a
fixture-lane figure impossible to mistake for a full-corpus one after the fact.

**Alternatives considered**: warning instead of exiting — rejected, a warning in a passing
run is not read. Checking after computing metrics — rejected, by then the misleading number
exists and can be quoted. A minimum-count assertion inside each metric — rejected as five
places to forget instead of one.

---

## R18 — One vocabulary for what retrieval produced

**Decision** (FR-036a): five terms, never interchanged — **candidate** (authorized point
before ranking), **retrieved passage** (ranked chunk returned), **generation passage**
(authorized, budgeted excerpt actually serialized), **cited passage** (generation passage the
answer references), and **documents consulted** = distinct `document_id` values among
**generation passages**. User-visible source information may report retrieved, consulted and
cited; never unauthorized candidates or exclusion counts.

**Rationale**: FR-036 audits "documents consulted" and FR-017 forbids revealing what was
withheld. Without fixed definitions those two requirements can be satisfied by
implementations that disagree — one auditing every candidate, another only what was cited —
and the audit trail stops being comparable between runs, which is the one property an audit
trail must have.

Anchoring "consulted" to **generation passages** rather than retrieved ones is the deliberate
choice: it names what actually informed the answer. A chunk retrieved and then dropped by the
passage budget did not inform anything, and counting it would overstate what the model saw —
in the direction that flatters the system.

**Alternatives considered**: "consulted" = retrieved — rejected above. "consulted" = cited —
rejected, it would hide passages the model read and did not cite, which is precisely what a
grounding investigation needs. Leaving the term to implementation — rejected; it is the term
two requirements are written against.

---

## R19 — The health check needs a deadline, or it is the stall it prevents

**Decision** (FR-028k): the local API checks generator health before opening the stream, with
a **2-second deadline**. Timeout, DNS failure, TLS failure, authentication refusal, malformed
response and unhealthy status are one outcome: **unavailable**. Unavailable sends no question
or passage body, opens no stream, exposes no tunnel detail. The check may run concurrently
with local retrieval; generation starts only when **both** it and authorization-constrained
retrieval have succeeded.

**Rationale**: an ephemeral Colab tunnel does not usually refuse — it **hangs**. A check
without a deadline converts an unavailable generator into an indefinite wait, which is the
failure FR-028k was written to prevent, reintroduced by its own implementation. 2 seconds is
chosen against the 5-second first-token budget: long enough to survive tunnel jitter, short
enough that the designed unavailable state arrives well inside the budget a person is
already waiting through.

Collapsing six causes into one outcome is deliberate. Distinguishing "TLS failed" from
"authentication refused" in a user-facing state would describe the endpoint, which FR-028i
forbids; operators get the cause from telemetry, askers get one state.

Concurrency with retrieval is a latency optimization only. Retrieval is authorization-
constrained and its result gates generation regardless of what the health check returns, so
running them in parallel cannot reorder the authorization decision.

**Alternatives considered**: no deadline — rejected above. A longer deadline — rejected, it
consumes the budget it is protecting. Skipping the check and letting the first token time out
— rejected, that is an empty stream, which FR-028k exists to forbid.

---

## R20 — A faster GPU proves quality, not latency

**Decision** (FR-043a): T4 16 GiB is the **latency reference class**, not a floor. A
faster-GPU run is valid for grounding, citation precision, abstention and leakage, but cannot
establish either latency threshold, and is recorded as a **separate named series** never
mixed with T4 runs. CPU-only and unidentified-GPU runs stay invalid for latency and for the
gate. The three-run gate fixes GPU class, model revision, quantization, runtime, prompt
budget and concurrency.

**Rationale**: Colab allocates whatever it has. Without this rule the three-run gate is
satisfiable by drift — a T4 run, an L4 run, another T4 — and the latency evidence would then
describe no particular machine. The asymmetry is the point: a faster GPU cannot make an
answer more grounded, so quality evidence transfers; it can obviously make first-token
latency shorter, so latency evidence does not.

The alternative failure is worse than a missing measurement. A latency figure attributed to
the declared baseline but actually produced on better hardware is a claim that cannot be
reproduced on the hardware it names, and nothing in the record would reveal it.

**Alternatives considered**: T4 as a floor with faster allowed — rejected, it makes the
sequence's latency figure depend on allocation luck. Normalizing by relative GPU throughput —
rejected, it would be an estimate presented as a measurement. Discarding faster-GPU runs
entirely — rejected, their quality evidence is genuinely valid and costs nothing to keep.

---

## R21 — Chunk bounds: 400 tokens, 50 overlap, and never a split sentence

**Decision** (FR-007a, FR-007b): 400 BGE-M3 tokenizer tokens maximum, 50 tokens target
overlap, structure and sentence boundaries first, a sentence split only when one sentence
alone exceeds 400 tokens and then at the nearest preceding clause or whitespace boundary.
Empty and whitespace-only chunks are forbidden. Chunk identity includes the tokenizer
identity and both bounds.

**Rationale**: 400 is chosen against the generation budget rather than against retrieval
alone — FR-028b2 allows 400 tokens per passage, so a chunk that fits the chunker's bound
also fits a passage slot without trimming in the common case, and trimming becomes the
exception rather than the rule. Five such passages sit inside the 2,000-token total with
room for the question and the instruction.

50 tokens of overlap — one to three sentences in ordinary prose — exists because the
sentence that answers a question is often the one immediately after a heading, and a
boundary placed just before it would leave that sentence without its context in either
neighbour.

Never splitting a sentence is the rule that protects grounding. A fragment cut mid-clause
can invert its source's meaning, and a citation would then attest to something the document
does not say — a failure that reads as a success. The single exception is a sentence longer
than the whole budget, where refusing to split would mean refusing to index; splitting at a
clause or whitespace boundary is the least destructive option, and *deterministically* so,
because the same document must produce the same chunks on every machine (FR-007).

Putting the tokenizer identity and both bounds into the chunk identifier means "identical
chunk identifiers" in SC-007 asserts *produced by the same procedure*, not merely *same
text*. Two runs that agree on text but disagree on tokenizer would otherwise look identical.

**Alternatives considered**: character-based chunking — rejected, characters do not
correspond to what either model consumes. A larger 1,024-token chunk — rejected, it would
force trimming on nearly every passage and make the excerpt span differ from the chunk in
the common case rather than the rare one. Zero overlap — rejected above. Splitting long
sentences by token count — rejected, it produces mid-word breaks that a citation cannot
honestly quote.

**Consequence**: both numbers enter `chunker_config_hash`, so changing either re-ingests the
corpus rather than mixing chunk generations — which is the intended cost.

---

## R22 — The judge is the same model, invoked separately, and calibrated before it counts

**Decision** (FR-032a–FR-032c): grounding and citation precision are adjudicated by the same
pinned quantized Qwen2.5 3B Instruct, invoked **separately** as a judge with a versioned
prompt artifact, temperature 0, a strict JSON output schema, and an input restricted to the
question, the answer, the citation references and the exact cited spans. It must reach
**≥ 90% agreement** with a committed manually labelled calibration set before scoring a
release-gate run. Deterministic structural checks run alongside it.

**Rationale**: reusing the generation model avoids introducing a second model, a second
licence and a second download into a profile that already carries one non-commercial
licence. The cost is the obvious objection — a model marking its own homework — and the
separation is what answers it: the judge sees the finished answer and its cited spans, not
the generation context, not the model's reasoning, and not which model produced the answer.
It is scoring a text against evidence, a task that does not require it to be a different
model, only a different invocation.

Temperature 0 and a strict schema exist because a judged figure that varies between two
identical runs cannot be compared across a three-run gate. The enumerated reason codes make
disagreements analysable in aggregate instead of read one by one.

The calibration gate is the part that makes the judge admissible at all. Without it, a
90%-grounding figure is a claim about a model nobody checked, and the release gate would
rest on it. Requiring agreement with human labels first converts the judge from an authority
into an instrument with a stated error bound. Failing calibration produces **INVALID**
rather than a failure, for the same reason a CPU-only Colab run does: the measurement did not
happen, which is not the same as the system being wrong.

Structural checks stay because they are exact where the judge is approximate. "Every citation
resolves" and "every cited span equals the passage sent" have correct answers that no model
needs to opine on, and folding them into a judged score would hide a deterministic failure
inside a statistical one.

**Alternatives considered**: a larger third-party judge model — rejected, a second remote
data path for a corpus already restricted to synthetic data. Human adjudication of every run
— rejected as unrepeatable across a three-run gate. The generation response scoring itself
in the same call — rejected, it cannot be separated from the context that produced it.
Skipping calibration — rejected above.

---

## R23 — `data_version` is the active corpus manifest checksum

**Decision** (FR-018a): `data_version` is a company-scoped, per-collection checksum over the
active index — company and collection, active document ids and normalized-content hashes,
chunk ids and chunk-content hashes, chunker version and config hash, embedding identity,
revision and checksum, vector dimension, and the authorization-relevant payload schema
version. Published atomically only after a complete replacement index succeeds, and held in a
dedicated corpus-version record.

**Rationale**: the three obvious candidates each fail in a different direction. The **dataset
fingerprint** does not change when the index changes — re-chunking or re-embedding the same
documents leaves it identical, so stale answers would stay reachable. An **ingestion run id**
changes when the index does *not* — a no-op run would invalidate every cache entry for no
reason, which is a correctness-neutral but expensive mistake, and worse, it would hide a real
change behind an expected one. A **manual counter** depends on someone remembering.

A checksum over what the index actually contains has the property the cache needs in both
directions: identical index ⇒ identical key ⇒ warm cache after a no-op run; any change to
what is retrievable *or to who may retrieve it* ⇒ different key ⇒ old entries unreachable.
Including the **authorization payload schema version** is the part that is easy to omit and
matters most: a change in how permissions are encoded in the payload changes who can retrieve
what, without changing a single document.

Atomic publication after success is what makes a cancelled ingestion safe. Publishing early
would point the cache at an index that does not exist yet; publishing late but non-atomically
would leave a window where two checksums are active. Keeping the previous checksum active on
failure means a failed ingestion degrades nothing — the last complete index keeps serving.

Unreachability rather than deletion is deliberate: entries under the old key expire on their
own TTL, and no code path has to enumerate and delete keys, which is the operation most likely
to fail halfway and leave exactly the inconsistency it was meant to prevent.

**Alternatives considered**: dataset fingerprint, run id, manual counter — each rejected
above. A per-document version — rejected, the cache key covers a whole answer that may draw
on several documents, so it needs one value describing the corpus the answer was built from.
Explicit cache deletion on re-index — rejected above.

---

## R24 — "Transiently" is a lifetime, not an adjective

**Decision** (FR-013a): passage and prompt content, and any derived form of it, lives only in
request-scoped memory from authorized retrieval until the terminal SSE event or abort cleanup,
then is released. Never persistent storage, caches, logs, traces, metrics, snapshots, test
artifacts, exception messages, or retry queues. The index is exempt — it is the source, not a
downstream copy. FR-018's cache holds references and derived results, never bodies.

**Rationale**: FR-013 forbade forbidden content from being returned "even transiently", which
is a strong claim with no boundary — and an unbounded claim cannot be tested. Naming a
lifetime with two endpoints makes it checkable: content appears at authorized retrieval and
must be gone at the terminal event.

The sink list is deliberately long and specific because each entry has failed in real systems.
Retry queues serialize a request body and hold it past the request. Exception messages
interpolate the object that failed. Snapshots capture whatever the assertion touched. None of
these look like storage to the person writing them, which is exactly why they need naming.

The **abort path** is called out because it is the branch least likely to be exercised: the
happy path releases content by falling out of scope, and the aborted path is where a reference
survives in a background task or an unawaited coroutine.

The index exemption is the necessary carve-out — without it the requirement would forbid the
feature. The distinction that makes it safe is direction: the index is what authorization is
applied *to*; everything after retrieval is a copy that authorization has already been decided
for and cannot be re-decided on.

**The cache tension is real and resolved rather than ignored.** FR-018 permits a
permission-scoped cache; a cache of passage bodies would violate FR-013a. The resolution is to
cache references and derived results, re-resolving bodies per request under the current
permissions — which also strengthens FR-016, since a cached body could outlive the permission
that fetched it.

**Alternatives considered**: leaving "transiently" to judgement — rejected, it is the word an
implementer would resolve in their own favour. Permitting a short-TTL body cache — rejected,
it reintroduces exactly the outliving-permission problem. Exempting test artifacts — rejected;
SC-021 already establishes that failure output is where content most plausibly escapes.

---

## R25 — Indistinguishability needs two lanes, because timing does

**Decision** (FR-017a): five identical observable properties — status, SSE event types and
ordering, wording, retry behaviour, and the absence of any withheld-source signal. Ordinary CI
verifies **identical control flow** on fixtures and blocks the build. A controlled security
evaluation adds **≥ 50 warm samples per case** with a **p95 time-to-terminal difference ≤
max(100 ms, 20%)**, gating stabilization rather than shared-runner CI.

**Rationale**: FR-017 named "no difference in latency-shaped behaviour", which is the right
threat — a permission-narrowed response that returns faster than a genuinely empty one
discloses that something was withheld — but it is unmeasurable as written.

Splitting it is what makes both halves real. Control-flow identity is a **structural**
property: the same branches, the same event sequence, the same wording, deterministically
checkable on fixtures with no timing at all. That is the part that can block every build.

Timing is a **statistical** property whose signal is smaller than a shared runner's variance;
asserting it there would produce a flaky gate that gets disabled, which is worse than not
asserting it. Fifty warm samples per case is the smallest count at which a p95 comparison
means anything for a two-case test.

`max(100 ms, 20%)` rather than a flat bound because the absolute floor covers the fast case
where 20% is a few milliseconds of noise, and the relative bound covers the slow case where
100 ms would be an implausibly tight demand on a tunnel round trip.

**Alternatives considered**: a flat millisecond bound — rejected, wrong at one end of the
range or the other. Timing in ordinary CI — rejected above. Constant-time padding of every
response — rejected; it would degrade every response to protect a case that structural
identity already covers, and padding that is itself measurable is a false comfort.

---

## R26 — Readable body, invalidation, unsupported runtime, and endpoint provenance

Four boundary definitions that were each a single unresolved word.

**Readable body** (FR-002b): ≥ 20 non-whitespace Unicode characters, ≥ 1 letter or digit,
valid UTF-8 after normalization; otherwise `EMPTY_BODY` atomically before chunking. Twenty
characters is a floor, not an estimate of usefulness — a body below it cannot answer a
question and cannot fail informatively later, so refusing it early keeps every corpus count
describing something retrievable. The letter-or-digit condition catches the punctuation-only
document that passes a length check.

**Invalidation as an outcome** (FR-011i): a change of embedding revision, checksum, dimension,
tokenizer, or runtime identity requires a **complete replacement index**, atomically published
(FR-018a), with the previous index and checksum active until it succeeds. "Invalidate" had
three plausible readings — refuse to serve, rebuild, mark stale — and only replace-then-publish
avoids a window in which the collection holds two vector spaces. Mixed embedding identities are
not a degraded state; similarity between two embedding models is meaningless, so a mixed index
returns confidently wrong neighbours.

**Unsupported determinism** (FR-011j): `UNSUPPORTED_CONFIGURATION` — not a fallback, not a
loosened tolerance, not another model. Every figure downstream inherits a determinism claim,
so a claim the runtime cannot honour contaminates the whole evaluation rather than one run. A
named verdict also distinguishes "we could not measure this" from "this failed", which is the
same distinction `INVALID` draws for a CPU-only allocation.

**Endpoint provenance** (FR-028o): provider profile, GPU series, ngrok region, protocol and TLS
version, RTT p50/p95, health outcome, and a **keyed HMAC fingerprint** of the endpoint — never
the hostname, URL, token, or credential. The operational need is *correlation*: did these three
runs hit the same endpoint? A keyed HMAC answers exactly that and nothing else, where storing
the hostname would answer it by disclosing the address FR-028i exists to mask.

**Alternatives considered**: a byte-size floor instead of a character floor — rejected, it
varies with encoding. Marking a stale index and serving it — rejected above. A truncated
hostname — rejected, still an address. An unkeyed hash of the URL — rejected, an ngrok
hostname's keyspace is small enough to reverse.

---

## R27 — The generation prompt is configuration, and the structural checks belong in CI

**Decision** (FR-011k, FR-032c): the generation prompt is a versioned repository artefact,
distinct from the judge prompt, recorded per run as `generation_prompt_version` and
`generation_prompt_hash`, and **any change resets the three-run gate**. The three deterministic
structural checks **block ordinary CI** on fixtures; the full-model evaluation repeats them but
is not their only gate.

**Rationale**: FR-011b already required recording "the prompt version" and FR-043 already reset
the sequence on a prompt-version change — but nothing defined the prompt as an artefact, so
there was no version to record and no change to detect. The judge prompt received this
treatment in R22; the generation prompt, which has more effect on every measured figure, did
not. A prompt edit between two passing runs would otherwise attribute both to a configuration
that no longer exists.

The structural checks moved because of where they sit, not what they measure. "Every claim
cited", "every citation resolves", "every cited span equals the passage sent" all have exact
answers and all run against committed fixtures with a stub generator. Leaving them only in the
controlled lane — which by design never blocks the build — meant three exact correctness
properties could regress into main and be discovered later by a GPU run nobody had scheduled.

**Alternatives considered**: an inline prompt constant — rejected, a change would not appear in
review as a configuration change. Sharing one prompt artefact between generation and judging —
rejected, it couples two independent change disciplines and would reset the gate on a judge
edit. Structural checks in the controlled lane only — rejected above.

---

## R28 — Synthetic-only is a precondition, not a policy

**Decision** (FR-011l): the outbound path may build a request **only when the active corpus
manifest identifies the approved synthetic seed corpus and matches its recorded fingerprint**.
An unknown, modified, user-supplied, or non-synthetic corpus **fails closed before the request
is constructed**.

**Rationale**: FR-011h stated the limitation and nothing enforced it. A data-handling limit
that lives only in prose is satisfied by whoever remembers it, and the moment this feature is
useful is exactly the moment someone points it at a real document to see what happens.

Checking the **corpus manifest fingerprint** rather than a configuration flag is what makes it
a control: FR-018a's checksum already changes when any document content changes, so an edited
corpus fails the check without anyone having to declare that it was edited. A flag would have
to be set correctly by the person the control exists to protect against.

Failing **before the request is constructed** rather than before it is sent matters because a
constructed request has already serialized passages into memory that FR-013a governs, and
because a send-time check is one refactor away from being bypassed by a second call site.

**Alternatives considered**: a configuration flag — rejected above. A review-time checklist —
rejected, not a control. Blocking at send time — rejected above. Allowing an override for
"approved" real data — rejected; that decision belongs to choosing a private provider
(FR-011h), not to a flag on this path.

---

## R29 — Stopping means the work stops, not the screen

**Decision** (FR-025a): `/stop` is end-to-end. Emission halts immediately; cancellation
propagates to the Colab request and stops token generation; the stream closes with the
terminal `stopped` state; request-scoped content is released in abort cleanup; no retry,
queued continuation or background generation follows. The local API closes and cleans up
**within 2 seconds**. If upstream cancellation is unconfirmed by then, the connection is
severed, a content-free `provider_cancel_unconfirmed` status is recorded, and later provider
output is discarded.

**Rationale**: "stoppable" had three readings and the cheapest one is wrong in a way nothing
else in this specification would catch. Stopping the display alone satisfies FR-025's visible
behaviour, produces the right terminal event, and marks the answer incomplete — while the
provider keeps generating, the tunnel keeps consuming, and passages stay resident in memory
that FR-013a requires released. Every criterion passes and the requirement is defeated. That is
why the **falsifying test is written into the requirement**: a display-only stop must fail a
named test.

The 2-second deadline mirrors the health check deliberately. Both bound a wait on a remote
component that usually hangs rather than refuses, and a cancellation with no deadline
reintroduces the stall it was meant to end.

**Severing beats waiting** when confirmation does not arrive. The alternative — holding the
connection open hoping for acknowledgement — keeps the request alive past the point the person
ended it, which is both a resource leak and an FR-013a violation. Recording
`provider_cancel_unconfirmed` **content-free** turns an unknown into a known state: operators
can see how often upstream cancellation fails without the record carrying anything about the
question.

Discarding later output rather than merely ignoring it is the precise part. Bytes that arrive
after cancellation belong to a turn that no longer exists; letting them reach a buffer, a log,
or a retry queue would re-create exactly the residency FR-013a forbids.

**Alternatives considered**: display-only stop — rejected above, and now explicitly falsified.
No deadline — rejected, an unconfirmable cancellation would hang. Waiting indefinitely for
confirmation — rejected above. Resumable stopped turns — rejected; a resumed answer must be a
new turn under a new access context, or the stop becomes a pause that outlives its permissions.

---

## R30 — "Per request" is per turn, and the snapshot dies with it

**Decision** (FR-012a): one logical user question is one turn. Each authenticated chat turn
receives a newly built access-context snapshot from the local API, reusable only within that
turn; retries may preserve it only while the turn is active; follow-ups, regenerations and
resumed conversations build a new one; history is re-authorized under the new turn's context;
no worker or provider may create, validate, widen or reuse a context across turns. FR-022's
citation authorization and the permission-scoped cache remain independently required.

**Rationale**: FR-016 required authorization "per request" and FR-026 required that a prior
turn not reintroduce unreadable content — but "request" was undefined, so the two requirements
could be satisfied by implementations that disagree about when a permission change takes
effect. A snapshot reused across turns is functionally a cached permission, which FR-016
forbids in the same sentence that "per request" appears in.

Choosing the **turn** rather than the HTTP request is what makes it implementable without
weakening it. One turn legitimately spans several internal operations — query embedding,
search, budgeting, generation, citation resolution — and rebuilding the context between them
would be pure cost with no safety gain, since no permission can change inside a single
question's execution in any way the person could exploit. Rebuilding **between** turns is where
the safety lives.

**Regenerated answers** are called out because they look like a continuation and are not: the
person is asking again, possibly minutes later, and reusing the original snapshot would answer
a new question under old permissions.

The **detectability** clause matters more than it reads.
`conversation_turns.permission_fingerprint` records the fingerprint of the turn's own snapshot,
so a reused context is visible in the data rather than being an absence someone has to prove.
A rule with no observable trace is a rule that degrades silently.

FR-022 stays independently required because citation opens happen **outside** any turn — later,
from a different page, possibly after the permission changed — so they cannot inherit a turn's
snapshot at all.

**Alternatives considered**: per HTTP request — rejected, it fragments one question into
several contexts for no gain. Per conversation — rejected, it is the cached permission FR-016
forbids. Per retrieval operation — rejected, same fragmentation with an added risk that two
operations in one answer disagree about what the asker may read.

---

## R31 — A disconnect is a cancellation the person did not ask for

**Decision** (FR-025b): an unexpected client disconnect — navigation, tab close, browser crash,
network loss — cancels upstream exactly as an explicit stop does, under the same 2-second
cleanup deadline and the same `provider_cancel_unconfirmed` handling, but is persisted as
`INCOMPLETE` with reason `CLIENT_DISCONNECT` rather than `STOPPED`. No terminal SSE event is
required; the server-side state and a content-free audit record are authoritative. Ordinary CI
tests it against the stub provider, including a falsifying case where generation continues.

**Rationale**: the two halves of this pull in opposite directions, and both matter.

**Mechanically it must be identical to a stop.** The resource consequences of a disconnect are
the same as a cancellation — a GPU still generating, a tunnel still consuming, passages still
resident in memory FR-013a requires released — and the browser is gone, so nothing on the
client side will notice or clean up. If a disconnect were treated as merely a lost reader, the
work would continue to completion with nobody waiting for it, which is the most expensive
possible outcome and the one with the longest content residency.

**Semantically it must not be a stop.** `STOPPED` records an intent. A person whose train went
into a tunnel did not decide to stop their answer, and a record saying they did is wrong in a
way that matters later: telemetry counting user-initiated cancellations would be inflated by
network conditions, and the two have entirely different responses. Splitting them costs one
enum value and buys a record that means what it says.

**`INCOMPLETE` needed a reason field** as a consequence. It previously had exactly one cause —
a mid-stream tunnel failure (FR-028m) — so the state alone identified it. With two causes,
`incomplete_reason` is what keeps FR-039's "refusals distinguishable from failures" and the
FR-038 telemetry split meaningful.

**The terminal-event exception is narrow on purpose.** RC §2 makes a missing `done` event a
defect, and that rule earns its strength by having no ordinary escape. Conditioning the
exception on *the client having disconnected* rather than on *the event being absent* is what
stops it becoming a general excuse — a dropped socket with a live client is still a defect.

**The falsifying test is the requirement.** A disconnect handler that releases the local
request but leaves the provider generating passes every observable browser-side check, because
there is no browser left to observe. Only a test that watches the *provider* can catch it, and
only a deliberately broken variant proves that test works.

**Alternatives considered**: treating a disconnect as `STOPPED` — rejected above, it fabricates
intent. Letting generation run to completion and caching the answer — rejected; it maximizes
both cost and content residency, and the answer would be served later under permissions that
were never re-checked. Requiring a terminal event anyway — rejected, it cannot be delivered and
would make every disconnect look like a defect. A grace period before cancelling — rejected; it
is a fixed window of exactly the residency FR-013a forbids, bought for a reconnect this feature
does not support.

---

## R32 — Three manifests, because an input and a piece of evidence are different things

**Decision** (FR-035j–FR-035m, FR-043b): keep the **embedding fixture manifest** and the
**question partition manifest** at their existing scopes, and add a third — the
**evaluation-run manifest** at `tests/evaluation/results/<run_id>/run-manifest.json` — one
directory per run, holding that run's manifest, raw results and results record together (R34) — carrying eleven
field groups that describe the full configuration of one controlled run. Immutable, referenced
by the run's results record. A missing or runtime-disagreeing field makes the run
`INVALID_CONFIGURATION`. The three-run gate compares every field except timestamp and run
identifier; a generation prompt change starts a new series. Ordinary CI validates the schema
and the mismatch behaviour on fixtures, touching neither model.

**Rationale**: the obvious move was to extend one of the two manifests already in the design,
and both readings fail for the same structural reason. The fixture manifest and the question
manifest are **inputs**: committed, reviewed before a run, changed deliberately by a person.
The run manifest is **evidence**: written by a run, never edited afterwards. A file that is
both is trustworthy as neither — reviewing an input that a run may rewrite is theatre, and
treating a reviewable file as evidence invites exactly the edit that makes a figure look
attributable when it is not.

The eleven groups are chosen to close the attribution question completely. FR-011b already
required recording "the prompt version" and FR-043 already reset the sequence on a prompt
change, but nothing said *where* — so the requirement was satisfiable by a variable in
someone's head. A named artefact with a named path turns it into something a reviewer can open.

**`INVALID_CONFIGURATION` rather than failure** follows the pattern already established by
`INVALID_NO_GPU` and `INVALID_UNSUPPORTED_CONFIGURATION`: a run whose configuration cannot be
fully stated did not measure anything, which is not the same as measuring something bad.
Recording it as a failure would put a false negative into the gate's history.

**Comparing field values rather than the series label** is the part that matters most. A series
identifier is a label a person assigns; if the gate trusted it, relabelling would be enough to
continue a sequence across a changed prompt. The falsifying case — change only the prompt hash,
keep the old series identity, and confirm validation fails — exists precisely because that is
the cheapest way to defeat the gate and the hardest to notice in review.

**Validating in ordinary CI** keeps the guard honest. The manifest protects the controlled
lane, which runs rarely and expensively; a guard exercised only there would be discovered
broken at the worst moment. Schema and mismatch behaviour are both checkable against fixtures
with no model and no network, so the offline lane can prove the expensive lane's guard works.

**Alternatives considered**: extending the fixture manifest — rejected, it would put run
evidence into a reviewed input and couple fixture regeneration to prompt edits. Extending the
question manifest — rejected for the same reason, plus it would make a question-set change look
like a configuration change. Recording configuration only in the `evaluation_runs` row —
rejected, a database row is not portable evidence and cannot be diffed in review; the row now
*references* the manifest instead. Trusting the series label — rejected above.

---

## R33 — Three runs means three processes

**Decision** (FR-043c, FR-035n): three **isolated controlled-evaluation executions**, each
starting after the previous reaches a terminal result, each re-running the complete preflight,
each with its own run identifier, timestamp, manifest, raw results, results record, samples and
empty caches. Same day and same T4/tunnel session are permitted while manifest fields stay
identical. An orchestration command may spawn three isolated children; an in-process loop may
not. Any failed, invalid, cancelled or mismatched execution breaks the sequence. Ordinary CI
tests the gate on fixture manifests and results.

**Rationale**: FR-043 asked for three consecutive runs to distinguish a stable capability from
a favourable sample. A loop inside one process cannot do that. It shares the warmed weights,
the loaded tokenizer, the populated caches, the same tunnel handshake and the same allocation —
so the second and third iterations are not independent samples of the system, they are cheaper
repetitions of the first with most of the variance already spent. Three rows would appear in
the record and the gate would count them, which is the failure this rule exists to make
impossible.

**Re-running the preflight** on every execution is the part that looks redundant and is not.
The preflight is what proves the question set, its partition counts and the corpus have not
moved (FR-035i). Skipping it on runs two and three means the later figures could describe a
different corpus than the first, and the sequence would be comparing runs that are not
comparable.

**Empty caches** matter for the same reason: a cached retrieval result or a cached answer
carried between executions makes the later run partly a replay of the earlier one.

**Same day and same session are permitted** deliberately. The gate samples *process* variance,
not calendar variance — requiring three separate days would add cost and delay without adding
evidence, and would tempt whoever is waiting to relax something else instead. A new allocation
between runs is *permitted* but not required; what is required is that the manifest fields
agree (FR-043b).

**The orchestration carve-out** is what keeps the rule practical. Insisting a human type the
command three times would be enforced by nobody. Allowing one command that spawns three
isolated children keeps the ergonomics while preserving the property, and the property stays
checkable: three distinct `process_fingerprint` values, three completed preflights, three
distinct raw-result checksums.

**Detectability is the whole design.** Each rule is paired with a recorded field —
`process_fingerprint`, `preflight_completed_at`, `raw_results_checksum`,
`run_manifest_checksum` — so a violation is visible in the data rather than being an absence
someone must prove. A rule with no observable trace is a rule that degrades silently.

**Alternatives considered**: allowing in-process repetitions — rejected above, it defeats the
gate's only purpose. Requiring three distinct days — rejected, cost without evidence.
Requiring a fresh Colab allocation per run — rejected, it would make the manifest fields
*harder* to keep identical and so weaken FR-043b. Trusting the row count — rejected; three rows
are the thing an in-process loop produces most easily.

---

## R34 — Phase 0 provisions the server it measures, and every run owns a directory

Three decisions that all follow from one question: *what may a phase depend on, given it gates
the phase that would otherwise supply it?*

**The generation server is Phase 0 provisioning** (FR-035o). The first-token benchmark measures
a Colab-hosted Qwen behind an authenticated tunnel. That server was previously created in
Phase 4 — the phase the benchmark gates. Same shape as B1 and rejected for the same reason: a
gate cannot consume its own output. So `infrastructure/colab/generation_server.ipynb`, the
weights, the endpoint, the token, the verified T4, the runtime identity, the health endpoint
and the streaming protocol all move to Phase 0, and **Phase 4 reuses the artefact rather than
authoring a second one**.

The seven prerequisites are enumerated rather than summarised because each fails differently
and each is individually silent. Missing weights look like a slow first token. An unverified
T4 looks like a fast one. A protocol mismatch looks like a hang. Naming them turns "the
benchmark did not run" into a specific, recordable reason — and `NOT RUN` or `INVALID` rather
than a pass is what stops a missing prerequisite from being read later as evidence.

**Every run owns a directory** (FR-035j). A single fixed `run-manifest.json` path silently
contradicted FR-043c: three isolated executions writing to one file leave one manifest, and
the third overwrites evidence the gate is supposed to compare. `results/<run_id>/` makes the
isolation observable — three runs means three paths and three checksums, and a shared path is
detectable rather than assumed absent. Ordinary-CI fixtures move to their own committed
directory so a fixture can never be mistaken for a produced result.

**Phase 0's scope is bounded to what the measurement needs** (FR-035p). Lifting the chunker and
embedder into Phase 0 (B1) created an obvious temptation to lift more. The rule is that Phase 0
may implement the canonical libraries the measurement requires and nothing else — no ingestion,
no production indexing, no retrieval API, no generation integration before their gates.

The dependency-ownership clause is the part that looks like packaging trivia and is not. The
BGE runtime belongs to **`packages/core`**, the package whose modules import it, and to the
root development environment. Declaring it in a standalone benchmark manifest would put a
runtime dependency somewhere nothing installs from — an inert declaration that reads as
satisfied. And **prohibiting a benchmark-only chunker or embedder** is what keeps FR-007's
determinism guarantee covering both the measured path and the production one; two
implementations would mean the benchmark measures a workload the system never runs.

**Alternatives considered**: leaving the server in Phase 4 — rejected, it is the circularity
B1 removed, reappearing on the generation side. Timestamped filenames in one directory —
rejected, it keeps fixtures and results in the same tree and leaves the run id implicit.
Allowing a benchmark-local embedder for speed — rejected above.
