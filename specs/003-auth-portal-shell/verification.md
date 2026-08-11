# Verification Record: Feature 003

**Executed**: 2026-08-06 · **Environment**: local Docker Compose, full profile,
fingerprint `abc407d70e90672cf5696aaa6e020e4c5112ecef78c7d970d7626c75912147ba`

Evidence for T119–T121. Each quickstart scenario is listed with what was actually
observed, not what was expected. Where a scenario names a false-pass mode, the guard
that closes it is named too — an assertion nobody has tried to defeat is a claim, not
evidence.

---

## Suite totals

Re-run in full after the post-review defect fixes (2026-08-06, second pass):

| Suite | Result |
|-------|--------|
| `tests/` entire Python suite, one process | **1432 passed, 0 skipped** (19m12s, includes the destructive resets) |
| `apps/web` components (Vitest) | **225 passed, 9 files** (includes `portal-states.test.tsx`, 42) |
| Playwright, 3 viewports | **356 passed, 4 skipped** |
| `ruff` | clean |
| `mypy` (104 source files) | clean |
| `eslint` / `tsc` | clean |
| `make contracts-check` | types match the live schema |
| `make docs-check` | documentation matches the dataset |

The Python figure is one run of everything except `tests/e2e/test_clean_startup.py`, which
tears the stack down and is now its own CI job for that reason. **Zero skipped** is the
number to read: a skip in these suites means an absent dependency, and a suite that skips
itself reports the same green as one that passed.

These are local figures. The CI evidence FR-037 and SC-012 require is recorded in
*Continuous integration* below, and it is now the authoritative record.

---

## Scenario-by-scenario

### 1 — Sign in and read your own record (US1, FR-023)

Driven in a real browser against the deployed container, not only in-process.
Signed in as `majid.alzaabi@niletech.example`; the portal greeted "Welcome, Majid" and
`/portal/profile` showed department Engineering, office Dubai, manager Tarek Darwish,
employment type FULL_TIME, and an annual leave balance of 22 entitled / 2 taken / 20
remaining. No salary appeared anywhere.

`tests/integration/test_auth_login.py` and `test_hr_profile.py` assert the same fields
against the database row by row.

### 2 — Sign-out actually ends access (FR-007, SC-002a)

`tests/security/test_session_lifecycle.py` — 12 passed.

**False pass named in the quickstart**: asserting that a *new* unauthenticated request
is refused. Closed by `test_the_exact_token_is_refused_after_sign_out`, which keeps the
token and replays it, and by `test_the_token_is_still_cryptographically_valid`, which
shows the replay fails because the server withdrew the session — not because the token
became malformed.

### 3 — A manager sees their team and nobody else (US2, SC-003)

`tests/security/test_manager_scope.py` — 16 passed.

**False pass**: a manager with zero direct reports. Closed by
`TestTheScenarioHasSubjects`, which asserts both the direct-report set and the
unrelated-colleague set are non-empty before anything else runs.

`test_moving_a_report_moves_the_reachable_set` changes one `manager_id` in the database
and shows the reachable set follows, with no code change (FR-026).

### 4 — Salary is denied before the query runs (FR-025, FR-036, SC-007)

`tests/security/test_authorize_before_read.py` — 9 passed.

**Falsified deliberately.** Moving `load_compensation_payload` above `authorize` in
`hr/router.py` made `test_a_manager_denied_compensation_runs_no_salary_query` fail,
naming the offending `SELECT employee_profiles.salary_amount …`. Reverted; green.

**False pass**: a recorder that captured nothing. Closed by `TestTheRecorderWorks`,
which proves the recorder sees statements, sees table names, and finds `salary_amount`
when an authorised caller genuinely reads it.

### 5 — Zero cross-tenant access (US3, FR-034, SC-004)

`tests/security/test_cross_tenant_authenticated.py` — 17 passed.

Every subject-taking endpoint answers **404**, byte-identical to a request for an
identifier belonging to nobody. Holds in both directions, and `hr:read_all` — the widest
permission there is — does not cross.

**False pass**: a caller who can reach nothing. Closed by
`test_the_caller_can_reach_their_own_records`.

**A real gap this scenario exposed.** Deleting `if decision.tenant_absent:` from
`enforce.py` changed nothing — every test still passed. RLS answers first: the other
tenant's row is invisible to the scoped session, so the router returns not-found before
the engine is consulted. That is defence in depth working, and it meant the mechanism
FR-030 documents was untested. `TestTheLayerOneMappingItself` now exercises it directly,
and the same deletion now fails.

### 6 — Request-supplied tenant, role, and permission are ignored (FR-035, SC-005)

`tests/security/test_request_supplied_claims.py` — 23 passed. Query, header, cookie, and
body, plus `roles`, `permissions`, `user_id`, and `sub`.

**False pass**: asserting the manipulated request returns nothing. Every assertion is
**equality with the unmanipulated response**.

### 7 — Sign-in reveals nothing about which accounts exist (FR-022, FR-007a, SC-013)

`tests/security/test_login_enumeration.py` — 19 passed. Five causes produce identical
status, body, and headers.

**False pass**: comparing wall-clock timings. Closed structurally —
`test_a_verification_happens_even_when_no_user_matches` counts Argon2 verifications and
proves the dummy-hash path runs, so the work is the same rather than the measurement
being lucky.

A malformed address is a 422 and is *deliberately* distinguished:
`TestSyntaxErrorsAreNotEnumeration` holds that line and asserts the 422 body names only
the field.

### 8 — Session expiry, both bounds (FR-005, SC-002)

`tests/integration/test_session_expiry.py` — 25 passed. Time advanced by writing
timestamps, never by sleeping.

`test_continuous_activity_does_not_extend_the_cap` is the one that matters: a session
used every 25 minutes for over eight hours still ends, with `ended_reason = 'ABSOLUTE'`.
An implementation with a single moving expiry passes every other test in the file.

### 9 — The audit trail (FR-017, FR-018, SC-006)

`tests/security/test_authz_audit.py` — 14 passed. Every count is a **delta**;
`audit_logs` is never empty because the seed writes to it.

Reading one's own non-compensation profile writes **zero** entries, asserted beside a
sensitive read that writes exactly one, in the same run.

### 10 — Determinism survives credentials (FR-002a, SC-014)

`tests/e2e/test_credentials_lifecycle.py` — 6 passed, including two full resets.

Fingerprint byte-identical before and after provisioning. `reset` clears credentials;
`make credentials` restores a working sign-in; `make verify` still matches the committed
value afterwards.

### 11 — The public site is untouched (FR-031, FR-032, SC-011)

Every feature 001 and 002 check passes. The one file that changed is
`e2e/boundary.spec.ts`, and it changed because FR-006 deliberately puts the sign-in form
at `/portal` — see the deviations section below.

### 12 — The portal is complete, accessible, and role-aware (FR-028, FR-029, SC-008–SC-010)

`apps/web/tests/` — 183 passed. Playwright — 352 passed across 360 / 768 / 1280.

`e2e/portal-accessibility.spec.ts` sweeps every portal page with axe at all three
widths: **zero WCAG 2.2 AA violations**. Keyboard traversal, focus visibility, and
horizontal-overflow checks included.

Role-aware navigation is asserted **both ways in the same test** — the manager sees "My
team", the employee's markup does not contain `/portal/team` at all — and the hidden
address is separately shown to be refused by the server.

### 13 — Contracts have not drifted

`make contracts-check` — exit 0. `packages/contracts/src/generated/api.ts` regenerated
from the live schema (28 KB → 50 KB) and committed.

---

## Deviations from the plan, and why

| # | Deviation | Reason |
|---|-----------|--------|
| D1–D5 | As recorded in [plan.md](plan.md) | unchanged |
| D6 | Password primitives live in `eaios_core`, not `apps/api` | The seed's `credentials` command must hash, and `scripts/seed` may not import from `apps/api` (spec 001 FR-001a) |
| D7 | `e2e/boundary.spec.ts` changed | It asserted `/portal` carried no input. FR-006 puts the sign-in form there. Its FR-048 check was replaced with the one the requirement is actually about — the eight content pages — which had never existed |
| D8 | T111–T112 unrunnable *(resolved)* | *Historical, superseded.* The CI steps were in `ci.yml` with no repository to trigger them. Both are closed against run 31443872819; a third step, `Re-provision credentials after the destructive lifecycle tests`, proved necessary once the browser suite finally ran |
| D9 | FR-029's states are classified, not a cross-product | Nine of the 35 route/state cells cannot exist — the denied page reads nothing, `/me` cannot be forbidden, a profile is never empty. `contracts/portal-routes.md` §3 now states the enforced rule: every reachable route-specific state tested, shared boundaries tested once and proven to cover their children, unreachable cells classified with reasons. Nothing is narrowed; the classification is what makes a gap visible |

---

## Corrections made after review

**T111 and T112 were wrongly marked complete** *(recorded 2026-08-06; since resolved).*
They add CI steps; at the time the YAML was correct and nothing could trigger it. Marking
them done on the grounds that the file was right is precisely the reasoning Principle VIII
rejects — a check that has never run is not a check. They were reopened, and are now
closed against run 31443872819: **FR-037, SC-012, and spec 001 FR-047c are met**. The
judgement was vindicated rather than merely overtaken — when the step finally ran it
aborted before collection on a path that never existed, so the YAML had never been
correct.

**FR-007a's bound now fails closed.** The limiter previously failed open when Redis was
unreachable, recorded as a "residual risk". FR-007a says attempts **MUST** be bounded
and admits no exception for a dependency being down, so that was the requirement unmet
rather than a risk accepted. Sign-in now refuses with a generic **503** — raised before
any account lookup, so it is identical for every caller and leaks nothing.
`TestTheBoundFailsClosed` covers it, including the control that sign-in works again once
the limiter returns.

**Feature 002's CORS defect is fixed, and it had a third instance.** Confirmed
empirically against the running stack: `OPTIONS /public/contact` answers **405**, so the
contact form could never have submitted from a browser; and `GET /health/live` answers
200 with **no `Access-Control-Allow-Origin`**, so the status page could never read its
response either. Both now go through same-origin route handlers, matching the portal.
`apiBase` and `apiBaseBrowser` are deleted — nothing in the browser needs the API's
address, and a function that hands one out is how this gets reintroduced.
`e2e/contact-submission.spec.ts` submits for real, with no `page.route`, and asserts the
request reaches the API.

**The fix broke two tests that had been passing vacuously, and one draft of its own.**
`performance.spec.ts` stubbed `**/public/contact`; after the form moved to `/api/contact`
the pattern matched nothing, so the "stalled submission" tests submitted for real,
succeeded, and asserted an error state they had not produced. Both patterns now match the
path the form uses. And the draft that claimed "the submission reached the database" did
so by re-posting and expecting 202 — but the endpoint answers 202 for a stored row and a
suppressed duplicate alike, so it would have passed against a form that stored nothing.
The row is now counted in Postgres by `tests/e2e/test_contact_network_path.py`, which
posts to the *site's* origin: the request a browser actually makes, which neither the
server-side suite (it posts to the API directly) nor the browser suite (it stubbed the
network) had ever exercised. That is why the defect survived feature 002's verification.

**CI destroyed its own evidence, and reported success.** `tests/e2e/test_clean_startup.py`
opens with `docker compose down -v` and sorts first in its directory, so the single
`pytest tests/e2e` step wiped the dataset and credentials provisioned two steps earlier.
The consequence was worse than a failure: `test_credentials_lifecycle.py` hit its
"environment not seeded" guard and **skipped the entire authentication lifecycle suite**,
green. Clean startup is now its own job with its own stack, and CI sets `EAIOS_NO_SKIPS=1`
— every skip guard in these suites asks "is the stack up?", which in CI is true by
construction, so a skip there is an unchecked requirement. The control is falsified both
ways: without the flag the probe skips, with it the same skips fail.

## Continuous integration

**Authoritative evidence.** Run **31443872819**, commit `429fdcba8b22d10e356874f0fff1995a83a36145`,
API conclusion **`success`** — 7/7 jobs green, **86 successful steps, 3 skips, 0 failures,
0 cancellations**. All three skips are the `Dump logs on failure` step in the jobs that had
no failure to dump.

| Job | Result | What it establishes |
|-----|--------|---------------------|
| `unit (ubuntu-latest)` / `unit (windows-latest)` | green | `ruff`, `mypy`, unit suite, and the platform fingerprint, on both OSes |
| `cross-platform determinism` | green | Ubuntu and Windows agree: `6d0b5c64b3fd8e06c3158213b62e65f7e2d88491a8110cfe7187ed551e151fbf`. **SC-002 holds** |
| `web` | green | `pnpm lint`, `typecheck`, `test` (225), `build` |
| `clean startup (SC-001)` | green | one command from a torn-down state |
| `full profile (FR-020b, SC-005)` | green | full seed, volumes, hierarchy, committed full-profile fingerprint |
| `integration + security + e2e` | green | 23/23 steps — see below |

Inside the long job, every gate this feature depends on ran on a runner:

* **`Authentication and authorization (FR-037, Principle VIII)` — 128 passed.** The step
  also **gates the job**, proven rather than asserted: in run 31426053623 it exited 4 and
  the job failed; in 31427580344 it passed and the job advanced. FR-037 and SC-012 are met.
* **`Tenant isolation` — 579 passed.** Unauthorized information leakage measures zero.
* **`Integrity, coherence, and provenance` — 456 passed, 3 skipped** (the profile-guarded
  SC-005 cases, which pass in the `full profile` job).
* **`Determinism and lifecycle` — 24 passed**, followed by the re-provisioning step the
  destructive resets made necessary.
* **`Public website end-to-end, accessibility, and metadata` — 356 passed, 4 skipped**
  across three viewports, including the portal sign-in, role-aware navigation, and
  cross-tenant isolation specs.
* **`Fingerprint matches the committed known-good value` — green.** This step had been
  skipped in every previous run; it has now executed and the dataset matches
  `abc407d70e90672cf5696aaa6e020e4c5112ecef78c7d970d7626c75912147ba`.

**Portal states.** `apps/web/tests/portal-states.test.tsx` — 42 tests — classifies all 35
route/state cells and fails if any is unclassified. Writing it exposed five defects, all
fixed: no loading boundary existed; the `(authed)` shell and `/portal` both collapsed
*error* into *unauthenticated*; the error boundary had to move to the parent segment to
catch the shell at all; and `/portal/team/[userId]` had no retry control.

**What the first runs found.** The prediction in spec 001's T170 held: the first runs
failed, and everything they found was invisible locally — a CRLF defect in the fingerprint
comparison (which had made SC-002 *look* false), three smoke-profile assumptions in
`test_public_content.py`, a stale test path that aborted the FR-037 step before
collection, an ambient-config leak in the trusted-proxy test, hardcoded full-profile
personas in the browser suite, credentials destroyed by the destructive lifecycle suite,
and a header wider than a 320px viewport.

---

## Open risks

*Superseded and removed:* the entries that stood here claiming **CI has never run**, that
**nothing can be pushed**, that **FR-037/SC-012/FR-047c remain unmet**, and that
**cross-platform determinism is failing, making SC-002 false**. All four were true when
written and are now false: run 31443872819 is green, and the fingerprints are identical.
The determinism entry was wrong in substance as well as currency — generation always
agreed across platforms; the comparison was reading a Windows `` as a different digest.

**A per-account lockout is a bounded denial of service** against that account, the demo
password is shared across all seeded users, and HS256 means the verifier can also mint.
All three are stated in [plan.md](plan.md) and none is a defect.

**HS256 holds only while FastAPI alone verifies.** Feature 004's orchestrator must receive
the immutable access context from FastAPI and must never receive the signing key. The day
a second service verifies tokens, this becomes an asymmetric key pair —
`AuthSettings.jwt_algorithm` is pinned as a list at every call site precisely so that
change is one edit and not a hunt.

**`eaios-seed --help` crashes** with `TypeError: Parameter.make_metavar() missing 1
required positional argument: 'ctx'` — a typer/click version drift. Every command works;
only `--help` is broken. Found while closing this feature, unrelated to it, and not yet
filed against a feature.
