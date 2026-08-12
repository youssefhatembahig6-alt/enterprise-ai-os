# Contract: Retrieval, Chat and Citations

**Feature**: 004-permission-aware-rag · **Date**: 2026-08-11

The browser reaches only the Next.js origin, which reaches only the local API (FR-028d).
No browser route, and no route handler, may hold the generation service credential.

---

## 1. API endpoints (added to the existing FastAPI surface)

All require an authenticated session; all build the access context through the existing
feature 003 dependency; none accepts a tenant, role, or permission from the request.

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/chat/conversations` | start a conversation |
| `GET` | `/chat/conversations` | list the caller's own conversations |
| `POST` | `/chat/conversations/{id}/ask` | ask; responds `text/event-stream` |
| `POST` | `/chat/conversations/{id}/stop` | cancel a response in progress — **end-to-end** (§2a), not display-only |
| `GET` | `/chat/citations/{turn_id}/{citation_id}` | open a citation — **re-authorized** (FR-022) |
| `GET` | `/chat/health` | generation-service availability (FR-028k) |

`GET /chat/citations/...` answers **404** for a citation the caller may no longer read,
byte-identical to one that never existed — the same rule feature 003 applies to
cross-tenant identifiers (FR-021, FR-030).

### Retrieval preview

`/ask` emits a `sources` event **before** any generated token. This is the milestone
SC-010 measures (CHK186, CHK205): it proves retrieval and authorization completed, and it
is entirely local, so it stays meaningful if the generator changes.

---

## 2. SSE event contract

```
event: sources        data: {"chunks":[{"citation_id","document_id","title","chunk_index"}]}
event: token          data: {"text":"…"}
event: citation       data: {"citation_id","claim_ordinal"}
event: done           data: {"state":"complete|stopped|incomplete|refused_unsupported|generation_unavailable"}
```

**`done` is mandatory — while the client is connected.** Every stream ends with exactly one,
including on failure. A stream that closes without it is a **defect**, not an incomplete
answer, which is what makes FR-028m checkable rather than inferred from a dropped socket.

**The one exception** is an unexpected client disconnect (FR-025b): the connection is gone, so
no event can be delivered and none is required. The exception is conditioned on **the client
having disconnected**, never on the event merely being absent — otherwise it would excuse the
defect it is carved out of.

`chunk_text` is **not** sent in `sources`; the passage is fetched by citation open, so an
unopened citation never ships its passage to the browser.

---

## 2a. Cancellation contract (FR-025a)

`/stop` is **end-to-end cancellation**, never hiding output.

| Step | Requirement |
|------|-------------|
| 1 | stop emitting content **immediately** |
| 2 | **propagate** cancellation to the Colab generation request and **stop token generation** |
| 3 | close the SSE stream with the terminal `done` state **`stopped`**; the answer is marked incomplete |
| 4 | release **all** request-scoped question, prompt, passage and partial-generation content in abort cleanup (FR-013a) |
| 5 | **no** retry, **no** queued continuation, **no** background generation afterwards |

**Deadline**: the local API closes the stream and completes local cleanup **within 2 seconds**
of receiving the stop request — the same budget as the health check (§6), and for the same
reason: an unbounded wait is the failure the mechanism exists to prevent.

| Upstream outcome by 2 s | Result |
|---|---|
| cancellation confirmed | `answer_state = STOPPED`, `provider_cancel_status = CONFIRMED` |
| not confirmed | **sever the provider connection**, record content-free **`provider_cancel_unconfirmed`**, **discard all later provider output**; `answer_state = STOPPED`, `provider_cancel_status = UNCONFIRMED` |

A stopped turn **is recorded** with partial text retained and marked incomplete, **is audited**
like any other generation (FR-036), and **is not resumable** — a resumed answer is a new turn
under a new access context (FR-012a).

**Required failing test**: a test MUST prove that stopping **only the display** while
generation continues is a **failure**. That is the cheapest wrong implementation, and it
satisfies every other criterion in this contract.

### Client disconnect (FR-025b)

An unexpected disconnect — navigation, tab close, browser crash, network loss — is an
**implicit cancellation**, not an explicit stop.

| | Explicit stop (FR-025a) | Client disconnect (FR-025b) |
|---|---|---|
| Upstream cancellation | ✅ | ✅ — identical |
| 2-second local cleanup deadline | ✅ | ✅ — identical |
| `provider_cancel_unconfirmed` handling | ✅ | ✅ — identical |
| Request-scoped content released | ✅ | ✅ — identical |
| Retry · continuation · resumable stream · background work | **none** | **none** |
| Terminal `done` event | **required**, `state: stopped` | **not required** — the connection is gone |
| Persisted state | `STOPPED` | `INCOMPLETE`, `incomplete_reason = CLIENT_DISCONNECT` |
| Authoritative record | the stream **and** the turn | the **server-side state and audit record** |

The turn is **never** recorded `STOPPED`. The person did not ask to stop, and a record that
says they did is a record of an intent they never expressed.

**Audit content** (FR-037, FR-013a): turn id · timestamps · status · duration ·
cancellation-confirmation status. **Never**: question, prompt, passage, partial answer, token,
URL, or credential content.

**Required tests, in ordinary CI against the stub provider**: disconnect the client mid-stream
and prove upstream cancellation, cleanup within 2 seconds, the incomplete state with its
reason, the absence of any continuation, and content-free logs. **Plus a falsifying case** in
which the UI disconnects while generation continues — it **must fail**. A disconnect that
leaves a GPU generating is invisible from the browser, which is exactly why it needs a test
rather than a convention.

---

## 3. Authorization contract

Order is fixed and is the existing engine's (FR-014). Retrieval calls
`eaios_core.authz.filters.qdrant_filter(context)` and passes the result to the vector
search as a **pre-filter**. There is no post-filter step; adding one would satisfy FR-013's
letter and break its intent.

**Prohibited by construction**: the search layer never receives a company, department,
classification, or role from the request body, query string, or header. It receives an
`AccessContext` and nothing else.

### Snapshot lifetime (FR-012a)

"Per request" is **one logical user question — one turn**.

| | Rule |
|---|---|
| Built | freshly by the **local API**, once per authenticated chat turn |
| Reusable by | internal retrieval and generation operations of **that turn only** |
| Retries | may preserve it **only while the original turn is still active** |
| New context required for | follow-up turns · regenerated answers · resumed conversations |
| Conversation history | **re-authorized** under the new turn's context before any reuse (FR-026) |
| Workers and providers | MUST NOT create, validate, widen, or reuse a context **across turns** |
| Still independently required | citation authorization immediately before emission or persistence (FR-022) |
| Cache | scoped to the current permission fingerprint and `data_version` (FR-018, FR-018a) |

`conversation_turns.permission_fingerprint` records the fingerprint of the turn's **own**
snapshot, so reuse across turns is **detectable** rather than assumed absent.

### Filter shape (FR-014a, FR-014b)

`qdrant_filter` returns a **structured** constraint, not a flat equality mapping, because
null must mean *company-wide* and equality cannot express that:

| Clause | Semantics |
|--------|-----------|
| `company_id` | **must** equal the caller's — unconditional, never widened |
| `classification` | **must** be within the caller's ceiling — never widened |
| `department_id` | **should**: equals the caller's **or** is null (company-wide) |
| `country` | **should**: equals the caller's **or** is null (company-wide) |
| `allowed_roles` | **should**: intersects the caller's role ids |
| `owner_id` | **should**: equals the caller — ownership reaches its own documents |

A caller with a null attribute matches only the null (company-wide) branch of that clause,
unless owner, role, or an ACL grant reaches the document independently.

**Every clause field must have a payload index** and a test that fails when the index is
absent (FR-014b). `allowed_roles` is the one currently missing.

**Response narrowing is invisible** (FR-017): the `sources` event carries no total, no
"withheld" count, and no indication that the permitted set is smaller than the corpus.

---

## 4. Grounded-answer contract

- Every substantive claim carries ≥ 1 `citation` event bound to a `claim_ordinal`
  (FR-019, FR-020).
- A claim with no citation is a **grounding failure**, counted by the evaluation, not
  silently rendered.
- When the permitted corpus cannot support an answer, the stream emits **no** `token`
  events carrying claims and terminates `refused_unsupported` (FR-021).
- A citation naming a `citation_id` that was not in the `sources` event is **dropped** by
  the API before the browser sees it (CHK196) — the generator has no authority to
  introduce a source.

---

## 5. Generation provider interface (FR-011d)

```python
class GenerationProvider(Protocol):
    async def health(self) -> Health: ...
    def stream_answer(self, *, question: str, passages: Sequence[Passage],
                      config: GenerationConfig) -> AsyncIterator[Token]: ...
```

`passages` are already-authorized texts. The provider receives **no** store handle, **no**
access context, and **no** identity — which makes FR-028c a property of the signature.

Implementations: `ColabTunnelProvider` (dev/eval profile), `StubProvider` (ordinary CI).
Selection is explicit configuration; there is no fallback chain (FR-028j).

### Passage lifetime (FR-013a)

Passage and prompt content — and derived forms such as summaries, snippets and highlighted
fragments — exist **only in request-scoped memory**, from authorized retrieval until the
terminal `done` event or abort cleanup, and are released there.

| Sink | Permitted |
|------|:---------:|
| request-scoped memory, until the terminal event | ✅ |
| the index (the source content is retrieved *from*) | ✅ — exempt |
| the permission-scoped cache | **references and derived results only**, never bodies (FR-018) |
| `answer_text` (the composed answer, shown to its owner) | ✅ — not passage content |
| citation excerpts | **offsets only**, resolved against the index on open |
| persistent storage · caches · logs · traces · metrics · snapshots · test artifacts · exception messages · retry queues | ❌ |

The **abort path** is asserted explicitly: it is the branch least likely to be exercised, and
the one where a reference most plausibly survives in an unawaited task.

### Passage budget (FR-028b1–FR-028b5)

Counted with the **pinned Qwen tokenizer**, re-counted at generation time and never inherited
from the chunker's BGE-M3 count (FR-028b5). Chunking's 400-token bound and this 400-token
bound are independent constraints that both hold.


At most **5 passages**; at most **400 tokens per passage**; at most **2,000
retrieved-passage tokens in total**, counted by the **pinned generation tokenizer**. All
three bounds apply simultaneously and the tightest governs. Trimming occurs **only at the
nearest preceding sentence boundary**.

The **exact excerpt span sent to generation is recorded on the citation** and is what a
citation open resolves to — never a wider span. `turn_citations` therefore carries the span
offsets, not only the chunk id.

### Outbound request schema — the whole of it

```json
{"question": "…", "passages": [{"ref":"c1","text":"…"}], "max_tokens": 512, "temperature": 0.0}
```

**Nothing else may appear.** Forbidden by FR-028a and asserted by the interceptor
(§7): session tokens, signing keys, refresh tokens, access-context objects, ACL records,
excluded-source counts, unauthorized chunks, raw credentials, unapproved metadata.

`ref` is an opaque per-request label, not a chunk or document identifier — so a captured
payload cannot be correlated back to the corpus.

---

## 6. Tunnel authentication and health

**Provisioned in Phase 0, reused in Phase 4 (FR-035o).** The generation-server artefact
`infrastructure/colab/generation_server.ipynb` and the server contract below are **created
once, in Phase 0**, because the first-token benchmark measures them and Phase 4 is gated on
that measurement. Phase 4 **consumes** this contract; it does not restate or re-create it.

| Provisioned before the first measurement | Requirement |
|---|---|
| pinned Qwen weights, revision + checksum verified | FR-011a, FR-011f |
| authenticated HTTPS ngrok endpoint | FR-028e |
| service token in ignored environment configuration | FR-028g |
| **verified** T4 — never unidentified or CPU-only | FR-035c |
| runtime and quantization identity recorded | FR-011b |
| working health endpoint | FR-028k |
| streaming first-token protocol compatibility | §2 |

Any absent prerequisite leaves the first-token row **`NOT RUN`** or records it **`INVALID`**;
it can never pass.

- HTTPS only; `Authorization: Bearer ${GENERATION_SERVICE_TOKEN}` on every request
  (FR-028e).
- `health()` runs before each `/ask` (FR-028k), from the **local API**, with a **2-second
  deadline**. Failure → `generation_unavailable`, and retrieval still runs so the person
  sees their sources (FR-028l).

  | Condition | Outcome |
  |-----------|---------|
  | deadline exceeded (2 s) | unavailable |
  | DNS failure | unavailable |
  | TLS failure | unavailable |
  | authentication refused (401/403) | unavailable |
  | malformed response | unavailable |
  | unhealthy status | unavailable |

  There is no partially-available state. When unavailable the API sends **no question and no
  passage body**, opens **no generator stream**, and exposes **no tunnel detail** — the six
  causes collapse to one user-visible state because distinguishing them would describe the
  endpoint (FR-028i). Operators get the cause from telemetry.

  `health()` **may** run concurrently with local retrieval, but generation starts only when
  **both** it and the authorization-constrained retrieval have succeeded. The concurrency is
  a latency optimization and never a reordering of the authorization decision.
- Failure of the tunnel or of authentication **fails closed** (FR-028j).
- The tunnel URL and token are masked wherever they appear (FR-028i); the URL is never sent
  to the browser and never written to an audit record.
- **Recorded tunnel conditions** (FR-028o) are exactly these, and nothing else:

  | Field | Note |
  |-------|------|
  | `provider_profile` | which profile served the run |
  | `gpu_series` | the Colab GPU series (FR-043a) |
  | `ngrok_region` | region only, never the hostname |
  | `protocol_tls_version` | e.g. HTTP/2, TLS 1.3 |
  | `rtt_p50_ms`, `rtt_p95_ms` | measured network round trip |
  | `health_outcome` | the FR-028k result |
  | `endpoint_hmac` | **keyed HMAC fingerprint** of the endpoint, for run correlation only |

  **Never recorded or displayed**: the tunnel hostname, the full URL, the ngrok token, the
  service credential. The HMAC answers "was this the same endpoint?" without answering "which
  endpoint?" — correlation and disclosure are different needs, and only the first is required.

- **Synthetic-corpus precondition** (FR-011l). Before an outbound request is **constructed**,
  the active corpus manifest (FR-018a) must identify the approved synthetic seed corpus and
  match its recorded fingerprint. An unknown, modified, user-supplied, or non-synthetic corpus
  **fails closed** — no request is built, no passage is serialized. Checking the manifest
  fingerprint rather than a configuration flag is what makes this a control: an edited corpus
  fails it without anyone having to declare the edit.
- Rotation: a new Colab session mints a new token; the previous one stops working, which is
  the intended outcome rather than an incident (FR-028h).

---

## 7. Test-only payload interceptor (FR-037a)

A transport implementing the same interface as the real HTTP transport, installed by
injection in tests only. It:

1. receives requests built from **synthetic fixture passages** only;
2. serializes the request as it would be transmitted;
3. asserts the FR-028a prohibitions against the serialized form;
4. **persists nothing**;
5. writes **no passage text** to logs, artifacts, snapshots, or failure messages —
   a failure reports the offending **field name** and nothing of its value;
6. reports field names, counts, pass/fail;
7. **discards** the captured request immediately after the assertion.

It is never registered in the production container (FR-037b).

---

## 7a. Indistinguishability (FR-017, FR-017a)

A permission-narrowed empty result and a genuinely empty authorized result must be identical
on five observable properties:

| Property | Requirement |
|----------|-------------|
| HTTP status | identical |
| SSE event types and ordering | identical |
| User-visible wording | identical |
| Retry behaviour | identical |
| Withheld-source signal | **none**, in either case |

**Ordinary CI** asserts **identical control flow** on deterministic fixtures and **blocks the
build** — a structural property, no timing involved.

**Controlled security evaluation** additionally requires **≥ 50 warm samples per case** with a
**p95 time-to-terminal difference ≤ max(100 ms, 20%)**. This gates **stabilization**, not
shared-runner CI, because a shared runner's variance exceeds the signal. A flaky timing gate
gets disabled, which is worse than not asserting it there.

---

## 8. Web contract

New portal surface `/portal/assistant`, inside the existing `(authed)` group, so it
inherits the shell, the loading boundary, and the error boundary feature 003 built. Its
route/state classification is added to `apps/web/tests/portal-states.test.tsx`, whose
matrix fails on any unclassified cell — including `generation_unavailable`, which is a new
state and must be classified rather than folded into `error`.

Client fetches go to same-origin route handlers, matching the sign-in pattern; the
`EXPECTED_CLIENT_FETCHERS` allowlist in `state-coverage.test.tsx` gains exactly one entry.

---

## 9. OpenAPI and generated types

The new routes appear in `/openapi.json`; `packages/contracts` is regenerated and
committed, and the existing `Committed API types match the running API` CI step covers them
with no change (spec 003 T114).
