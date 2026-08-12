# Ingestion Requirements Quality Checklist: Permission-Aware Knowledge Retrieval

**Purpose**: Validate that ingestion, chunking, and embedding-identity requirements are
complete, unambiguous, and measurable
**Created**: 2026-08-11
**Feature**: [spec.md](../spec.md)

## Idempotency

- [x] CHK036 Is "unchanged corpus" defined by a stated comparison (content digest? record version? both?) so idempotency is checkable? [Clarity, Spec §FR-004] [**Resolved by design**, IC §1 Idempotency] — `UNCHANGED` requires `content_sha256` **and** `chunker_config_hash` to both match the prior run.
- [x] CHK037 Does the spec define what "no new chunks, no changed chunks, no duplicates" is measured against — chunk identifiers, chunk content, or the stored vectors? [Measurability, Spec §FR-004, §SC-006] [**Resolved by design**, spec §FR-007b, IC §2] — "no new, no changed, no duplicate chunks" is measured against **chunk identifiers**, whose derivation is fully specified — document identity, normalized-content hash, ordinal, tokenizer identity, both bounds, chunker version.
- [ ] CHK038 Are requirements defined for a document whose *metadata* changed but whose content did not — is that a re-ingest, a no-op, or an update? [Gap, Edge Case]
- [x] CHK039 Is the replacement requirement for changed content specified as atomic, so a reader can never observe old and new chunks of the same document together? [Gap, Spec §FR-005] [**Resolved by design**, IC §1 Idempotency] — replacement deletes by `document_id` filter then inserts as one logical operation, so no reader observes two generations.
- [x] CHK040 Does the spec state whether two documents with identical content must produce distinct chunk identities, and why? [Consistency, Spec §Edge Cases] [**Resolved by design**, IC §2] — `document_id` participates in chunk identity, stated with the reason — otherwise one document's permissions would serve another's content.

## Failure and Recovery

- [x] CHK041 Is "terminal, recorded outcome" enumerated exhaustively — are ingested, unchanged, and refused the complete set? [Completeness, Spec §FR-003] [**Resolved by design**, data-model.md] — the terminal set is exactly `INGESTED｜UNCHANGED｜REFUSED`; the five intermediate states exist so a non-terminal row is detectable by query.
- [x] CHK042 Are requirements defined for resuming an ingestion run interrupted part-way, or only for detecting that one was? [Gap, Recovery Flow] [**Resolved by design**, IC §9] — non-terminal rows survive an interruption and the next run re-processes them; a run completing with non-terminal rows is a run failure, not a silent partial.
- [x] CHK043 Does the spec define the outcome when the vector store is reachable but rejects a write mid-run? [Gap, Exception Flow] [**Resolved by design**, IC §9] — `INDEX_WRITE_FAILED`; the run continues to the next document and the failed one retries next run.
- [x] CHK044 Are refusal reasons required to come from a stated, closed vocabulary, or may they be free text? [Clarity, Spec §FR-002, §FR-006] [**Resolved by design**, IC §1, data-model.md] — a closed eight-value refusal vocabulary, not free text.
- [x] CHK045 Is there a requirement that a partially indexed document leaves *no* chunks behind? [**Requirement resolved**, Spec §FR-002a] — the oversize path is explicitly atomic and pre-chunking; the same atomicity is required of FR-005 replacement.
- [ ] CHK046 Are the reconciliation requirements in FR-006 specified precisely enough to state what "reconcilable against the document records" means arithmetically? [Measurability, Spec §FR-006]
- [ ] CHK047 Are requirements defined for a document that repeatedly fails across runs — is there any escalation, or is silent repetition acceptable? [Gap, Coverage]

## Validation and Eligibility

- [ ] CHK048 Are all validation conditions in FR-002 individually checkable, and is each paired with a distinct refusal reason? [Clarity, Spec §FR-002]
- [x] CHK049 Is "readable body" defined for a text-only corpus — what makes bytes unreadable? [Ambiguity, Spec §FR-002, §FR-001a] [**Resolved by design**, spec §FR-002b, IC §1] — **≥ 20 non-whitespace Unicode characters**, **≥ 1 Unicode letter or digit**, and **valid UTF-8 after extraction and normalization** — anything else is `EMPTY_BODY` atomically before chunking.
- [x] CHK050 Does the spec state a maximum document size and the rule at the boundary? [**Requirement resolved**, Spec §FR-002a, §SC-023] — 2 MiB of extracted normalized UTF-8 text, atomic refusal before chunking, no chunks/embeddings/points written, previous index preserved until replacement succeeds, truncation prohibited.
- [ ] CHK051 Is the eligibility boundary — recorded in the system of record — specified as the *only* admission criterion? [Clarity, Spec §FR-001]
- [ ] CHK052 Are requirements defined for a document present in the records but absent from storage, the inverse of the case FR-001 covers? [Gap, Edge Case]

## Deterministic Chunking

- [x] CHK053 Is chunk determinism specified across all the axes that could break it — machine, run, ordering, locale, and library version? [Completeness, Spec §FR-007] [**Resolved by design**, IC §2] — determinism is specified over content, boundaries, count and ids on any machine, with the chunker version and config hash recorded in the manifest.
- [x] CHK054 Does the spec state what a chunk identifier is derived from, so "same identifiers" in SC-007 is verifiable? [Measurability, Spec §FR-007, §SC-007] [**Resolved by design**, IC §2] — `sha256(document_id ‖ chunk_index ‖ chunker_version ‖ chunk_text)` → UUID.
- [x] CHK055 Is "respect document structure where the document has any" defined well enough to distinguish compliance from a coincidence? [Ambiguity, Spec §FR-009] [**Resolved by design**, spec §FR-007a] — the order is stated — document structure first, then sentence boundaries within the 400-token budget — with the single oversized-sentence exception and its clause/whitespace fallback, so compliance is distinguishable from coincidence.
- [x] CHK056 Are chunk size and overlap requirements stated, or left entirely to planning — and if deferred, is the deferral explicit? [Gap, Spec §FR-007] [**Resolved by design**, spec §FR-007a, IC §2, research R21] — **400 BGE-M3 tokenizer tokens** maximum and **50 tokens** target overlap, both stated as requirements and both inside `chunker_config_hash`, so changing either re-ingests rather than silently mixing chunk generations.
- [ ] CHK057 Is the relationship between FR-007 (determinism) and FR-009 (structure) stated, so a structure-aware rule cannot be non-deterministic? [Consistency, Spec §FR-007, §FR-009]
- [x] CHK058 Are requirements defined for a document that produces exactly one chunk, or zero chunks, after structural splitting? [Gap, Edge Case] [**Resolved by design**, spec §FR-007a, edge cases] — a document that yields no usable text after structural splitting is refused `EMPTY_BODY`; empty and whitespace-only chunks are forbidden outright, so the one-chunk and zero-chunk cases are both defined.

## Embedding Identity

- [x] CHK059 Is "invalidate the index" defined as an outcome — refuse to serve, rebuild, or mark stale? [Ambiguity, Spec §FR-011] [**Resolved by design**, spec §FR-011i, IC §12, research R26] — **replace-then-publish**: a changed revision, checksum, dimension, tokenizer or runtime identity requires a complete replacement index; mixed identities are never active; the previous index and checksum serve until the replacement is atomically published, and a failure leaves them untouched.
- [ ] CHK060 Does the spec require the embedding model revision to be *stored with the index* in a way that a query path can check before trusting it? [Completeness, Spec §FR-011, §FR-011b]
- [x] CHK061 Is the vector dimension stated as a requirement that must match the store's configuration, and is the mismatch outcome defined? [Gap, Spec §FR-011] [**Resolved by design**, IC §1] — `index` refuses to run against a collection whose vector dimension is not 1024.
- [x] CHK062 Are requirements defined for detecting a partially re-embedded index — some chunks from one revision, some from another? [Gap, Edge Case] [**Resolved by design**, spec §FR-018a, research R23] — embedding identity, revision and checksum are inputs to the corpus-version checksum, and publication is atomic after a complete replacement index — so a partially re-embedded index is never the active one, and a mixed-revision state is detectable rather than silent.
- [ ] CHK063 Is the claim that "similarity between two embedding models is meaningless" reflected in a testable requirement, not only in rationale? [Measurability, Spec §FR-011]

## Scope Boundary

- [ ] CHK064 Is the text-only scope stated as a requirement with a defined refusal path for non-text, rather than only as an assumption? [Consistency, Spec §FR-001a, §FR-002]
- [ ] CHK065 Does the spec state what must remain true of the `code` collection while it stays out of scope, so its emptiness is checkable? [Measurability, Spec §FR-001a]
- [ ] CHK066 Is the dataset-fingerprint stability requirement stated in a way that covers ingestion side effects, not only generation? [Clarity, Spec §FR-042, §SC-014]
