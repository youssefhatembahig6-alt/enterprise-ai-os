# Verification Record: Feature 004

**Environment**: Windows 11, Python 3.12.13, pytest 8.3.4, local Docker Compose stack
(`documents` and `code` collections present and empty). Every later task **updates** this
file rather than starting a new one (Principle VIII).

Each entry records what was actually observed, not what was expected. Where a result is
weaker than it looks, the weakness is stated in the entry rather than left to be found.

---

## A note on the interpreter

The task text specifies `uv run python -m pytest …`. On this machine Windows App Control
blocks the `uv` trampoline executables (`os error 4551`), so every figure below comes from
the project's locked environment invoked directly:

```
C:/Users/youss/AppData/Local/Temp/claude/venv-audit/Scripts/python.exe -m pytest …
```

That environment is built by `uv sync` from the committed `uv.lock`, so the dependency set
is the one the task names. The substitution is in the invocation, not in what was run.

---

## Feature 004 · Phase 1 red

**Executed**: 2026-08-15, before `qdrant_filter` gained its `document_id` grant branch
(T045) and before payload-index provisioning existed (T047).

### The invocation

```
python -m pytest tests/unit/test_qdrant_filter.py tests/unit/test_qdrant_filter_null_scope.py \
  tests/security/test_filter_invariants.py tests/unit/test_qdrant_filter_grants.py \
  tests/security/test_no_service_verifies_browser_tokens.py \
  tests/integration/test_payload_indexes.py -v
```

```
collected 156 items / 1 error

=================================== ERRORS ====================================
_________ ERROR collecting tests/integration/test_payload_indexes.py __________
E   ImportError: cannot import name 'ensure_payload_indexes' from 'eaios_core.clients.stores'
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
============================== 1 error in 1.33s ===============================
```

The exact invocation stops at collection, because T043 imports a provisioning function
T047 has not written yet. That is a truthful red but an uninformative one, so the same
selection was re-run with `--continue-on-collection-errors` to see the rest:

```
=================== 62 failed, 94 passed, 1 error in 2.34s ====================
```

### Per file

| File | Task | Result | Failing because |
|------|------|--------|-----------------|
| `tests/unit/test_qdrant_filter.py` | T038 | **26 failed, 1 passed** | seven clauses expected; `qdrant_filter` has six and rejects `granted_document_ids` |
| `tests/unit/test_qdrant_filter_null_scope.py` | T039 | 17 passed | FR-014a null semantics, unaffected by the grant branch |
| `tests/security/test_filter_invariants.py` | T040 | 52 passed | see the disclosure below |
| `tests/unit/test_qdrant_filter_grants.py` | T041 | **36 failed, 4 passed** | no `document_id` reach; the keyword argument does not exist |
| `tests/security/test_no_service_verifies_browser_tokens.py` | T042 | 20 passed | the boundary it fixes already held |
| `tests/integration/test_payload_indexes.py` | T043 | **collection error** | `ensure_payload_indexes` / `REQUIRED_PAYLOAD_INDEXES` do not exist |

The T038 and T041 failures are the same defect seen from two angles: the filter has no
resource-grant reach, so a document reachable **only** through a `document_acl` READ grant
is reachable by nobody. The T043 error is the other half of R3's finding — `allowed_roles`
is used by the filter and has no payload index, and nothing yet provisions one.

### Disclosure: what this red run does and does not prove

**It is a reconstruction, and it is not chronologically earlier than the first T045 draft.**
An earlier draft of `qdrant_filter`'s structured shape was written before T040–T044 existed.
That draft has since been amended — the explicit-ACL layer it carried was wrong, and the
correction is recorded in R5 — but the ordering defect is not undone by the correction. The
run above was executed against the pre-grant-branch filter on 2026-08-15; it proves the
tests fail without the branch, which is what a red run is for. It does not prove the tests
were authored without knowledge of the implementation, and no claim to that effect is made
here or in `tasks.md`.

**T040 passes in this run**, and a security test that is green before the work it guards is
not evidence by itself. What carries it instead is falsification: `TestRemovingAnInvariantIsDetected`
induces each defect it claims to catch — deleting `company_id` and `classification` from the
`must` set, and separately **demoting** each into a should-group, which is the realistic
regression — and requires the detector to fire. `TestTheDetectorsSeeRealStructure` additionally
requires the `_must_keys` and `_should_keys` walkers to find real clauses, so a walker that
returned nothing would fail rather than pass everything. Those thirteen falsification cases,
not the green tally, are why T040 is treated as verified.

**T042 passes in this run** for a plainer reason: it fixes a boundary that already held.
Neither `services/worker/` nor `scripts/seed/` has ever imported a JWT library, and the test
exists so that stops being an accident. Its three vacuity guards run the same scanners
against `apps/api/`, where they must *find* the verifier, the signing key and the decode
call — a scanner silent everywhere would otherwise report the boundary intact while it was
wide open.

---

## Feature 004 · Phase 1 green — T038–T046 block (HISTORICAL · SUPERSEDED)

> **This section is not the current status.** It records the state at the end of the
> T038–T046 block only, and is **superseded by
> [*Feature 004 - Phase 1 green*](#feature-004---phase-1-green)** further down, which is
> the authoritative Phase 1 result. It is kept because the red evidence above is only
> meaningful against the green that immediately followed it — deleting it would leave a
> red run with nothing to compare to. Read it as history, not as status.

**Executed**: 2026-08-15, after T045 and before T047.

| File | Task | Result at the end of that block |
|------|------|--------|
| `tests/unit/test_qdrant_filter.py` | T038 | **27 passed** |
| `tests/unit/test_qdrant_filter_null_scope.py` | T039 | **17 passed** |
| `tests/security/test_filter_invariants.py` | T040 | **52 passed** |
| `tests/unit/test_qdrant_filter_grants.py` | T041 | **40 passed** |
| `tests/security/test_no_service_verifies_browser_tokens.py` | T042 | **20 passed** |
| `tests/integration/test_payload_indexes.py` | T043 | **was red at that point** — it imported provisioning that T047 had not yet written |

T043 was red deliberately at the end of that block. It is the test that drove T047's
payload-index provisioning, and T047 was outside that block's scope; closing it then would
have meant writing the provisioning it existed to demand. **T047 has since been
implemented**, and T043 now passes against a live Qdrant — 23 tests, recorded in the
superseding section below.

### Regression surface re-run alongside

| Suite | Result |
|-------|--------|
| `tests/unit/` + `tests/security/`, one process | **1471 passed, 4 failed** — see *Pre-existing failures* |
| policy engine, `AccessContext`, fingerprint (`test_authz_*`, `test_permission_fingerprint`, `test_access_context`) | **78 passed** |
| `ruff check .` | clean (one `I001` import-order finding in `test_filter_invariants.py` fixed here) |
| `mypy packages/core/src apps/api/src scripts/seed/src services/worker/src` | **clean, 111 source files** |
| `git diff --check` | clean |

### Pre-existing failures, neither caused nor fixed by this block

Both were re-checked in isolation to establish that.

* `tests/unit/test_benchmark_imports.py::…::test_it_reaches_preflight_from_outside_the_repository`
  fails **in isolation too**, on `os error 4551` — Windows App Control blocking the `uv`
  trampoline, the same environment limitation recorded at the top of this file. It passes
  on CI's Linux runner.
* `tests/security/test_login_enumeration.py::TestTheBoundFailsClosed` (3 cases) **passes in
  isolation, 24/24**, and fails only in the full-suite run. That is order dependence in a
  rate-limiter test from feature 003, not a filter regression. It is recorded here rather
  than silently tolerated; fixing it is not in this block's scope.

---

## Environment after the block

| Check | Observed |
|---|---|
| Qdrant collections | `code`, `documents` only — **no temporary collection left behind** |
| Production point counts | `documents` 0, `code` 0 — unchanged, nothing ingested |
| Payload indexes present | `classification`, `company_id`, `country`, `department_id`, `document_id`, `owner_id` |
| Payload index **missing** | `allowed_roles` — R3's finding, still open, and exactly what T043 fails on |
| Phase 0 evidence | byte-identical: `GATE.md` `77f5028f…`, record `1fcdfc00…`, manifest `cf3d94c0…` |

---

## Falsification log · T045

Every clause and branch of `qdrant_filter` was removed or weakened in turn, the suite run,
and the file restored to byte-identical content (verified by SHA-256 before and after).
Recorded per branch in the table below.

`filters.py` before mutation: `a94f1fd4b27b232a9f3e486885136d1e9aba489498d8219c6cbd102cfeafcbf4`
After restore: **`a94f1fd4b27b232a9f3e486885136d1e9aba489498d8219c6cbd102cfeafcbf4` — byte-identical.**

Each mutation was applied to `qdrant_filter` (or `attribute_clause`) in turn, T038–T041 run,
and the file restored. **All 20 were detected.**

| Mutation | Detected | First test to fail |
|---|---|---|
| delete the tenant clause | yes | `test_qdrant_filter.py::TestTheFilterHasSubstance::test_it_references_several_payload_keys` |
| demote the tenant clause into the reach group | yes | `test_filter_invariants.py::TestTheInvariantsAreTopLevelMustClauses::test_the_invariant_is_a_must_clause[company_id-many-roles]` |
| delete the classification ceiling | yes | `test_qdrant_filter.py::TestTheFilterHasSubstance::test_it_references_several_payload_keys` |
| raise the ceiling to include RESTRICTED | yes | `test_filter_invariants.py::TestNoBranchWidensTheClassificationCeiling::test_restricted_is_never_offered` |
| delete the attribute branch | yes | `test_qdrant_filter.py::TestTheFilterHasSubstance::test_it_references_several_payload_keys` |
| loosen the attribute conjunction to a disjunction | yes | `test_qdrant_filter_grants.py::TestTheAttributeBranch::test_both_dimensions_must_admit_the_caller` |
| omit the attribute clause for a null caller | yes | `test_qdrant_filter_null_scope.py::TestACallerWithAValueReachesMatchingOrCompanyWide::test_the_clause_offers_both_branches[department_id]` |
| drop the null branch (equality only) | yes | `test_qdrant_filter_null_scope.py::TestACallerWithAValueReachesMatchingOrCompanyWide::test_the_clause_offers_both_branches[department_id]` |
| delete the role branch | yes | `test_qdrant_filter.py::TestTheFilterHasSubstance::test_it_references_several_payload_keys` |
| match roles by name instead of id | yes | `test_qdrant_filter_grants.py::TestTheRoleBranch::test_it_carries_role_ids_not_names` |
| delete the owner branch | yes | `test_qdrant_filter.py::TestTheFilterHasSubstance::test_it_references_several_payload_keys` |
| delete the grant branch | yes | `test_qdrant_filter.py::TestTheFilterHasSubstance::test_it_references_several_payload_keys` |
| render the grant branch even when empty | yes | `test_qdrant_filter_grants.py::TestTheGrantBranchIsTheOnlyReachLeft::test_the_negative_twin_has_no_grant_branch_at_all` |
| drop the deterministic ordering of grants | yes | `test_qdrant_filter_grants.py::TestUserReadGrantsAreRepresentable::test_the_order_is_deterministic` |
| keep the caller's collection live instead of copying it | yes | `test_qdrant_filter_grants.py::TestTheGrantBranchIsTheOnlyReachLeft::test_the_grant_branch_carries_the_resolved_id` |
| make the grant argument positional | yes | `test_qdrant_filter_grants.py::TestTheGrantIdsCannotComeFromTheRequest::test_the_argument_is_keyword_only` |
| widen the grant default from empty to a wildcard | yes | `test_qdrant_filter_grants.py::TestTheGrantIdsCannotComeFromTheRequest::test_omitting_the_argument_yields_no_grant_reach` |
| make the reach group satisfiable by nothing (min_should 0) | yes | `test_qdrant_filter_grants.py::TestTheReachGroupExists::test_any_one_reach_suffices` |
| drop document_id from FILTER_KEYS | yes | `test_qdrant_filter.py::TestTheFilterHasSubstance::test_the_declared_key_set_matches_the_expectation` |
| drop allowed_roles from FILTER_KEYS | yes | `test_qdrant_filter.py::TestTheFilterHasSubstance::test_the_declared_key_set_matches_the_expectation` |

**A note on the harness itself.** The first pass reported 13 of these as "not applicable"
and would have been read as a thin falsification log. The cause was mechanical: the file is
CRLF and the patterns were LF, so every multi-line mutation silently failed to match while
the single-line ones applied. The run above normalises to LF and writes back with
`newline="

"`. The lesson is the one this file keeps recording — a falsification harness
that cannot induce the defect reports the same clean result as a codebase that has none.

---

## Feature 004 - Phase 1 green — complete Phase 1 (AUTHORITATIVE)

**Executed**: 2026-08-15, after T043 and T047-T055. This section supersedes the
T038–T046 green section above and is the current Phase 1 status. The red section above and its
chronology disclosure are unchanged and remain the record for T038-T046.

### Targeted suites

| File | Task | Result |
|------|------|--------|
| `tests/unit/test_qdrant_filter.py` | T038 | **27 passed** |
| `tests/unit/test_qdrant_filter_null_scope.py` | T039 | **17 passed** |
| `tests/security/test_filter_invariants.py` | T040 | **52 passed** |
| `tests/unit/test_qdrant_filter_grants.py` | T041 | **40 passed** |
| `tests/security/test_no_service_verifies_browser_tokens.py` | T042 | **20 passed** |
| `tests/integration/test_payload_indexes.py` | T043 | **23 passed** - real execution against live Qdrant |
| `tests/unit/test_ensure_payload_indexes.py` | T047 | **23 passed** |
| `tests/unit/test_ingestion_preflight.py` | T048 | **35 passed** |
| `tests/security/test_cache_isolation.py` | T050 / T053 | **28 passed** |
| `tests/security/test_cache_data_version.py` | T051 / T052 | **15 passed** |
| `tests/unit/test_table_registration.py` | T055 | **60 passed, 0 skipped** |
| **Combined** | | **330 passed** |

`tests/integration/test_migrations.py` (T054): **14 passed**, including the six-case
ephemeral sweep.

### Regression surface

| Suite | Result |
|-------|--------|
| `tests/unit/` | **925 passed, 1 failed** - the known `uv` trampoline failure, see below |
| `tests/security/` | **700 passed, 0 failed** |
| Feature 003 auth/authz (`test_auth_login`, `test_access_context`, `test_authz_*`, `test_permission_fingerprint`, `test_tokens`, `test_login_enumeration`, `test_rls`) | **168 passed** |
| Phase 0 regressions, `-m "not phase0_controlled"` | **212 passed, 1 failed** (the same one) |
| Controlled live test, read-only, `-m phase0_controlled` | **24 passed** - observation only, no measurement written |
| `tests/integration/` (payload / coherence / health / manifest) | **72 passed** |
| `ruff check .` | clean |
| `mypy` (4 source trees) | **clean, 115 source files** |
| `git diff --check` | clean |

The single unit failure is `test_it_reaches_preflight_from_outside_the_repository`, which
shells out through `make` to `uv run` and hits Windows App Control (`os error 4551`). It
fails in isolation too, is unrelated to this block, and passes on CI's Linux runner.

---

## A defect this block found and fixed: the provisioning did not survive a reset

T047 provisioned `allowed_roles` into both production collections and T043 passed against
them. A later full run of `tests/integration/test_migrations.py` reseeded the environment,
and the index was **gone**.

`reset_all` deletes every Qdrant collection, and `provision_qdrant` rebuilds them from
`eaios_seed.loaders.stores.PAYLOAD_INDEXES` - a **third** hand-written list, still six
fields, still missing `allowed_roles`. So R3's defect had a second home: the index was
created, verified, and then silently dropped by an unrelated command. A fix that any
`make reset` undoes is not a fix, and nothing in the suite would have said so.

**Resolved** by deriving `PAYLOAD_INDEXES` from `REQUIRED_PAYLOAD_INDEXES` (itself derived
from `FILTER_KEYS`), delegating `provision_qdrant` to `ensure_payload_indexes`, and
re-exporting `missing_payload_indexes` rather than defining a second copy. Pinned by
`test_the_seed_provisions_the_same_set` and `test_the_seed_shares_the_detector_too`, which
fail if the lists ever diverge again. `provision_qdrant()` was then run to confirm the path
a reset takes now yields all seven.

---

## Registry-timing correction - T055

T055 originally added all eight Feature 004 table names to `POST_BASELINE_TABLES` and
`RUNTIME_TABLES` during Phase 1 - before any of the tables existed. That inverts the
failure it was meant to prevent: `reset_all` would `TRUNCATE` tables that are not there,
and the emptiness pre-flight would count a table it cannot query.

Corrected to a **durable invariant** instead. `tests/unit/test_table_registration.py` runs
in both directions - a table in the metadata must already be in both registries and in a
migration; a registered name must have a table and a migration - so registration is forced
to happen *with* the model. T057, T078, T138 and T193 now carry the registration in their
own task text. **No Feature 004 name was added to either registry in Phase 1**, and a test
asserts that too.

The invariant is vacuous today, which is why `TestTheDetectorFires` plants a real
`corpus_versions` table in `Base.metadata` and requires each gap to be reported, removing
it in `finally`. No repository file is touched by the plant.

---

## Cache semantics - T050-T053

`RetrievalCache` wraps `cache_key` **unchanged** and supplies the two components nothing
had ever filled: `permission_fingerprint` from the verified `AccessContext`, and
`data_version` from a `CorpusVersionProvider`.

* **Entitlement is in the key.** Tenant, permission codes, and - since FR-014a made the
  filter narrow by them - department and country. Two callers who reach different document
  sets derive different keys, so cross-reading is unconstructible rather than merely
  detected.
* **Retirement is in the key.** A permission change or a corpus republish changes the key,
  so the old entry becomes **unreachable without anything being deleted**. Asserted
  directly: the backend's contents are compared before and after a miss and must be
  identical. No sweep, no window in which a stale answer is still served, no correctness
  that depends on a cleanup having run.
* **Rollback is free.** Re-activating a previous corpus version makes its still-live
  entries reachable again - a consequence of retiring by key, asserted so that switching
  to a sweep would show up as a behaviour change.
* **The checksum is read per call**, never captured at construction; a captured value is
  the same staleness bug one level up.
* **No passage bodies.** `set` refuses any value carrying `passages`, `text`, `content`,
  `excerpt`, `question` and similar, **at any depth** - the first version only checked the
  top level, and a cached answer nests by nature.
* **Phase 1 stays independent of Phase 2** through in-test provider stubs; the real
  provider reads `corpus_versions`, which T078 creates.

---

## Migration sweep - T054

Every revision under `alembic/versions/` now round-trips up/down/up, serially, one
revision at a time so a failure names the migration that broke.

It runs against a **uniquely named ephemeral database** (`eaios_migration_sweep_<hex>`),
created by the superuser and owned by `eaios_owner`, and dropped in `finally` - sessions
terminated first, since `DROP DATABASE` fails while any connection is attached. The shared
development database is never migrated, truncated or dropped by it.

`_alembic` now runs `python -m alembic` rather than the bare console script, which was
absent from this environment and surfaced as an unrelated `FileNotFoundError`.

**Cleanup proven on the failure path**, not only the happy one: `_snapshot_of` was patched
to raise, both sweep tests failed as intended, and no `eaios_migration_sweep_%` database
survived.

---

## Falsification log - Phase 1

Every mutation was applied to the module under test, the suites re-run, and the file
restored. **All 20 behavioural mutations were detected; all targets restored
byte-identical.**

| Target | Mutation | Detected | First test to fail |
|---|---|---|---|
| `stores` | provision from a restated list instead of FILTER_KEYS | yes | `TestTheRequiredSetIsDerived::test_it_equals_the_filter_s_own_keys` |
| `stores` | treat an unknown point count as empty | yes | `TestItNeverDestroys::test_an_unknown_point_count_is_refused` |
| `stores` | index a populated collection without being asked | yes | `TestItNeverDestroys::test_a_populated_collection_is_refused_by_default` |
| `stores` | lose idempotence — recreate every index each call | yes | `TestItProvisionsWhatIsMissing::test_it_creates_only_what_is_absent` |
| `stores` | treat a null payload schema as fully indexed | yes | `TestTheDetectorSeesRealAbsence::test_a_bare_collection_is_missing_everything` |
| `preflight` | accept any dimension | yes | `TestItRefusesTheWrongDimension::test_any_other_dimension_is_refused[384]` |
| `preflight` | accept missing indexes | yes | `TestItRefusesEachMissingIndexIndependently::test_the_missing_field_is_named[allowed_roles]` |
| `preflight` | refuse without naming the field | yes | `TestItRefusesEachMissingIndexIndependently::test_the_missing_field_is_named[allowed_roles]` |
| `preflight` | swallow an unreadable schema | yes | `TestItRefusesAnUnverifiableSchema::test_an_unreachable_collection_is_refused` |
| `preflight` | pin the wrong dimension | yes | `TestAHealthyCollectionPasses::test_it_returns_without_raising` |
| `cache` | drop the permission fingerprint from the key | yes | `TestDifferentPermissionsCannotShareAnEntry::test_three_permission_sets_yield_three_keys` |
| `cache` | drop the corpus checksum from the key | yes | `TestTwoCorpusVersionsDoNotShare::test_different_checksums_yield_different_keys` |
| `cache` | let a miss mutate the cache | yes | `TestAPermissionChangeMakesTheOldEntryUnreachable::test_nothing_was_deleted_to_achieve_that` |
| `cache` | allow passage bodies to be cached | yes | `TestNoPassageBodyIsStored::test_storing_a_passage_body_is_refused` |
| `filters` | drop document_id from FILTER_KEYS | yes | `TestTheRequiredSetIsDerived::test_it_contains_the_two_fields_r3_found` |
| `stores` | delete and recreate the collection instead of indexing it | yes | `TestItProvisionsWhatIsMissing::test_it_creates_only_what_is_absent` |
| `cache` | capture the corpus checksum once (call site) | yes | `TestTwoCorpusVersionsDoNotShare::test_the_checksum_is_read_per_call_not_captured_once` |
| `preflight` | let an absent dimension fall through to the mismatch branch | yes | `TestItRefusesTheWrongDimension::test_an_absent_dimension_is_not_reported_as_a_mismatch` |
| `cache` | stop recursing into nested dict values | yes | `TestNoPassageBodyIsStored::test_a_body_buried_anywhere_is_refused[nested-dict]` |
| `cache` | stop recursing into list items | yes | `TestNoPassageBodyIsStored::test_a_body_buried_anywhere_is_refused[through-a-list]` |

Two further mutations were **inert** rather than missed - adding an unused attribute, and
a `getattr` that deleted nothing - and are excluded above. The first falsification pass
also recorded four "misses"; two were bad mutations of that kind, and **two were real gaps
in the tests**, now closed:

* an absent vector dimension fell through to the mismatch branch and produced *"has
  dimension None"*, a message about a value the collection did not have;
* `_refuse_passage_bodies` only checked the top level of a dict, so a body nested one
  level down was cacheable.

### T049 - the induced `allowed_roles` defect

| Step | Result |
|---|---|
| T043 with provisioning sabotaged to skip `allowed_roles` | **10 failed, 13 passed** - including `test_the_field_is_indexed[allowed_roles]` and every `test_deleting_one_index_is_reported` case |
| Direct `preflight()` against a temporary collection with the index dropped | **refused**, naming `allowed_roles` and blaming no innocent field |
| Restore through `ensure_payload_indexes` | created `['allowed_roles']`; `preflight` passes again |
| Temporary collection | removed |
| Production collections | **unchanged before and after** - never touched |

The defect was injected through a `-p` pytest plugin in the scratchpad, so no repository
file was edited to produce it.

---

## Environment after Phase 1

| Check | Observed |
|---|---|
| Qdrant collections | `code`, `documents` only - no temporary collection remains |
| Production point counts | `documents` 0, `code` 0 |
| Payload indexes | **all seven** on both: `allowed_roles`, `classification`, `company_id`, `country`, `department_id`, `document_id`, `owner_id` |
| Durable across a reset | yes - `provision_qdrant()` re-run and verified |
| Ephemeral databases | none (`eaios`, `postgres` only) |
| Phase 0 evidence | byte-identical: `GATE.md` `77f5028f...`, record `1fcdfc00...`, manifest `cf3d94c0...` |

---

## Phase 1 exit

T038-T055 are all `[X]`. The remaining Phase 1 gate is **T056**, which has not been run -
this block stopped before it, as instructed.
