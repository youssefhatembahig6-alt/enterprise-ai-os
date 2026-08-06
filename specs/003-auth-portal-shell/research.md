# Phase 0 Research: Authentication, Request-Time Authorization, and Employee Portal Shell

**Feature**: `003-auth-portal-shell` | **Date**: 2026-08-05

Each entry states the decision, why it was chosen, and what was rejected. Where the
existing codebase already settled a question, that is recorded too — a decision the
project made in feature 001 and forgot it made is a decision that gets remade wrongly.

---

## R1 — Password hashing

**Decision**: **Argon2id** via `argon2-cffi==25.1.0`, default parameters from
`argon2.PasswordHasher()` (t=3, m=64 MiB, p=4), pinned exactly like every other
dependency.

**Rationale**: Argon2id is the current first-choice recommendation for new password
storage. The encoded output (`$argon2id$v=19$m=65536,t=3,p=4$<salt>$<hash>`) carries its
own parameters and its own random salt, so a later parameter change is a per-hash
migration rather than a flag day, and `verify()` reads the parameters from the stored
value rather than from configuration that could drift away from it. This directly
satisfies FR-002 — the stored value is not reversible — and the per-hash random salt is
why FR-002a's separation from the generator matters (see R5).

**Alternatives rejected**:

| Option | Why not |
|--------|---------|
| `passlib[bcrypt]` | `passlib` 1.7.4 is from 2020 and breaks against `bcrypt>=4.1`; the project pins exact versions, so adopting an unmaintained shim as the *credential* layer is the wrong place to accept that risk. |
| Bare `bcrypt` | Silently truncates input at 72 bytes. Correct behaviour requires a pre-hash step the caller must remember, which is exactly the kind of "remember to" that this project keeps finding as a defect. |
| `hashlib.scrypt` (stdlib) | Works and adds no dependency, but has no encoded output format — the salt and parameters would have to be serialised by hand. Inventing a credential serialisation format is not a thing to invent. |
| PBKDF2 | Acceptable but weakest of the four against GPU attack, and there is no constraint here that argues for it. |

---

## R2 — Session credential format

**Decision**: A **JWT issued by the API**, signed **HS256**, carrying `iss`, `aud`, `sub`
(user id), `cid` (company id), `sid` (server-side session id), `typ` (`"access"`), `iat`,
`exp`, `jti`. Verification pins `algorithms=["HS256"]` explicitly and requires `iss` and
`aud`. The signing key comes from settings as a `SecretStr` with a local-only default,
following the existing `eaios_owner_local_only` pattern.

**Rationale**: The blueprint and the spec both name FastAPI-issued JWTs. HS256 is
sufficient because exactly one process both mints and verifies. Pinning the algorithm
list is not decoration — an unpinned verifier accepts `alg: none` and accepts an RS256
public key presented as an HMAC secret, and both are in the security suite (see R15).

The token is a *carrier*, not the authority. FR-004 requires active status and tenant
membership to be re-read per request, and FR-007 requires sign-out to actually end
access. So the token identifies; the database decides. That division is what keeps the
token's short expiry from being the only revocation mechanism.

**Alternatives rejected**: RS256 — buys the ability to verify without the ability to mint,
which matters when a *separate* service verifies. Feature 004's orchestrator is called by
the backend and receives an already-built access context (Constitution Principle II: "that
context is immutable once handed to the Orchestrator"), so it never verifies a token. If
that changes, the migration is a settings change plus a key pair, not a redesign.

---

## R3 — Where the credential lives in the browser, and how it gets to the API

**Decision**: The portal's browser traffic goes to **Next.js Route Handlers on the site's
own origin** (`/portal/api/*`), which attach the token server-side and call the API. The
session is held in an **`httpOnly`, `Secure`, `SameSite=Strict`, `Path=/` cookie** set by
Next, holding the JWT. Browser JavaScript never reads or holds the token. A
**double-submit CSRF token** in a second, readable cookie plus an `X-CSRF-Token` header
guards the two state-changing routes (sign-in, sign-out).

**Rationale**: The brief forbids `localStorage`; `httpOnly` is the version of that
prohibition a browser enforces rather than a convention a future component can break. And
`SameSite=Strict` is not sufficient on its own: it is a same-site policy, not a
same-origin one, so it does not by itself defeat a request forged from another origin on
the same registrable domain, and login-CSRF (forcing a victim into an attacker's session)
is a real attack that `Strict` does not address. Hence the explicit token.

Same-origin routing is chosen over cross-origin calls for a specific reason found while
surveying the codebase — see **F1** below. It also gives one place where "the browser must
never see the token" is enforced, rather than a rule every component must observe.

Server components read the cookie through `next/headers` `cookies()` and forward it
explicitly. A `fetch` from a server component does **not** inherit the browser's cookie
jar; that has to be done by hand, and forgetting it produces a portal that renders as
signed-out on the server and signed-in in the browser.

**Alternatives rejected**:

- **CORS with `allow_credentials=True` and an explicit origin.** Fewer moving parts, but it
  requires the credentialed cross-origin configuration to be correct in every deployment,
  and it puts the session cookie on the API's origin where the site's own server code then
  has to reach across for it.
- **Token in a JS variable, refresh cookie for renewal.** Standard, but it puts the access
  token where a single XSS reads it, and it needs a refresh endpoint the spec does not ask
  for.

---

## R4 — Resolving the tenant at sign-in

**Constraint**: `users` is unique on `(company_id, email)`, not on `email`. Sign-in
supplies an email and no tenant. But the tenant must be known before any tenant-scoped
read, and an `eaios_app` session with no tenant bound sees **zero rows** by design.

**Decision**: Iterate the **known tenant slugs** (`eaios_core.constants.COMPANY_SLUGS`),
**derive** each `company_id` with the existing deterministic id function, bind each in turn
with `tenant_scope`, and look up the email under each. Exactly one match proceeds. Zero
matches, or more than one, produce the identical generic failure. A **provisioning-time
check** (R5) fails loudly if any email exists in more than one tenant, so the ambiguous
case is prevented in the data rather than papered over at sign-in.

**Rationale**: This reuses a circularity-breaker the project already established and wrote
down. `apps/api/src/eaios_api/public/queries.py:74` derives `PUBLIC_COMPANY_ID` rather
than querying it, with the comment: looking it up "would need a query against `companies`,
which is itself under RLS — and RLS needs the tenant already set, so the lookup cannot run
before the scope it exists to establish." Sign-in is the same shape of problem and takes
the same answer. Every read stays under RLS, and no code path in this feature touches the
owner engine.

**Alternatives rejected**:

- **A company selector on the sign-in form.** Adds a field the user must get right and
  publishes the tenant list on an unauthenticated page.
- **A global `user_credentials` table keyed by email.** Would work, but a password hash is
  unambiguously a company-owned artifact, and Principle I (NON-NEGOTIABLE) says every
  company-owned artifact carries and is filtered by `company_id`. Putting hashes outside
  RLS to make one lookup easier inverts the principle. It would also require widening
  `GLOBAL_ENTITIES`, whose membership `tests/unit/test_tenancy.py` asserts exactly.
- **The owner engine for the sign-in lookup.** `apps/api/src/eaios_api/db/session.py`
  states the API "only ever uses the *app* engine". A request path that reaches for the
  RLS-exempt connection is precisely the exception that stops being an exception.

---

## R5 — Establishing demo credentials

**Decision**: A new seed CLI command, **`credentials`**, run after `seed`. It refuses to
run unless `environment == "local"` — the same guard `reset` already applies. It reads one
password from configuration (`AUTH_DEMO_PASSWORD`, `SecretStr`, local-only default
`eaios-demo-local-only`, overridable with `--password`), hashes it **once per user** with a
fresh salt, and writes one `user_credentials` row per active seeded user. It also asserts
that no email appears in more than one tenant (R4) and refuses to write if one does.

**Idempotent means something specific here.** The seed's idempotence is byte-identical
output. This command's is not and cannot be: Argon2 salts are random per hash, so running
it twice produces different stored bytes. What is idempotent is the **observable
outcome** — after any number of runs, the same password signs in, and the row count is
unchanged. The command rewrites every row rather than skipping rows that already have a
hash, so `--password` always takes effect; skipping would make a changed password silently
not apply, which is worse than the rewrite.

**Why this does not move the fingerprint**: the dataset fingerprint is computed from the
**in-process generated rows** (`dataset.rows`, hashed in `manifest.py`), not from the
database. A row written after the generator has run is invisible to it. This is the
property FR-002a depends on and SC-014 measures, and it is why generating hashes inside
the seed would be worse in two ways at once: it would need a fixed salt (weakening the
hash by construction) *and* it would change the generated row set (invalidating both
committed fingerprints).

**`users.password_hash` stays, unused.** Feature 001 added it "so the auth feature does not
need a migration to start using it". This feature does not use it, because the credential
belongs in its own table with its own lifecycle. Dropping the column is the tidier
outcome but is rejected: the generator writes `"password_hash": None` into every user row,
that key is part of the hashed row, and removing it would move both committed fingerprints
— which SC-014 forbids. A column that looks like it holds a password and never does is a
trap, so it is closed by a check rather than a comment: a test asserts no application code
reads or writes it.

---

## R6 — Where the policy engine lives, and what it is allowed to know

**Decision**: A new package `packages/core/src/eaios_core/authz/`, containing only pure
functions and frozen dataclasses. It performs **no I/O**: no database, no Redis, no
HTTP, no FastAPI import. It receives an already-built `AccessContext` and a
`ResourceDescriptor` and returns a `Decision`.

**Rationale**: FR-001a (spec 001) fixes the dependency direction — `packages/*` must not
import from `apps/*`, and `tests/unit/test_dependency_direction.py` enforces it by AST
scan. The brief independently requires that shared policy types not depend on FastAPI or
frontend code. Both point at `packages/core`.

Purity is the more consequential half. A policy engine that can query is a policy engine
whose ordering tests need a database, whose default-deny test needs a fixture, and whose
"missing attribute" case is hard to construct. As a pure function, layer ordering,
short-circuiting, reason codes, and default-deny are all `tests/unit` material with no
services running — which is what makes writing them first (FR-038) practical rather than
aspirational.

---

## R7 — "Authorization before retrieval", made provable

**The tension**: FR-015 forbids reading data before authorizing. But layers 4 and 5
(resource ACL, classification) need attributes *of the resource*, which requires a read.
Taken literally, the requirement is unsatisfiable.

**Decision**: Split the read in two, and name the halves.

1. **Access attributes** — the columns needed to decide: `company_id`, `owner_id`,
   `department_id`, `manager_id`, `classification`, matching ACL rows. Reading these is
   part of the decision, not part of the answer. A resource-attribute query never selects
   a protected payload column.
2. **Protected payload** — what the caller asked for: the HR profile fields, the
   compensation figure, the document body. Read only after `Decision.allowed` is true.

FR-015's real content is then precise and checkable: **no query selecting a protected
payload column may execute on a path that ends in a denial.**

**How it is proven** (FR-036, SC-007): a SQLAlchemy `before_cursor_execute` listener
records every statement executed during a request. The security test asserts that the
denied request's recorded statements contain no reference to the payload table or column.
The same harness asserts the *allowed* request **does** execute it — without that half the
check passes whenever nothing queries at all, which is the failure mode this project has
found repeatedly. A response-only assertion cannot establish either direction, which is
why FR-036 says so explicitly.

---

## R8 — Bounding sign-in attempts

**Decision**: Redis fixed-window counters, extending the machinery feature 002 built for
the anonymous write paths (`apps/api/src/eaios_api/public/rate_limit.py`, keys via
`eaios_core.keys` so `reset_all` clears them).

| Bound | Threshold | Window | Lockout |
|-------|-----------|--------|---------|
| Per account (`email_lower` digest) | **5** failures | 15 minutes | 15 minutes |
| Per client address (address digest) | **20** failures | 15 minutes | 15 minutes |

A successful sign-in deletes the account counter (FR-007a). Every lockout writes an audit
entry. The refusal is **byte-identical** to a wrong-password refusal — same status, same
body, no `Retry-After`, no remaining-attempts count — because each of those distinguishes
"this account exists and is locked" from "these credentials are wrong" (FR-022).

**Why both dimensions, and what each costs**: an address-only bound is defeated by
spreading attempts across addresses, which is the ordinary shape of credential stuffing.
An account-only bound lets an attacker lock a real user out on purpose. The spec's
clarification accepted both knowing the second is a bounded denial-of-service against one
account; 15 minutes keeps it bounded, and the audit entry makes it visible rather than
mysterious.

**Fail-open, deliberately, and differently from feature 002.** If Redis is unavailable the
bound is not enforced — refusing every sign-in because a cache is down converts a cache
outage into a total outage. The credential check itself is unaffected, so the failure mode
is "unbounded guessing for the duration", not "anyone gets in". This is recorded as a
residual risk rather than hidden as an implementation detail.

---

## R9 — Audit volume

**Decision**: One module, `eaios_core.authz.sensitivity`, holds the enumerated sensitive
set (FR-017b). The `Decision` returned by the engine carries `audit_required: bool`
computed there, so call sites never restate the rule and adding a resource type is one
edit.

Denials: always written, no coalescing (FR-017). Allows: only for the four enumerated
sensitive cases. Reading one's own non-compensation profile writes nothing — and the spec
names that in its edge cases so the absence is not later read as a bug.

**Rationale**: feature 002 learned this the expensive way in the opposite direction — a
bound was added to refusal auditing only after the requirement had created its own
denial-of-service surface. The same reasoning, applied before the fact, is why allows are
filtered by sensitivity rather than bounded by a counter: for reads, "which reads matter"
is answerable in advance, so the filter can be a definition instead of a rate.

---

## R10 — Session lifetime enforcement

**Decision**: The `sessions` row carries `issued_at`, `absolute_expires_at`
(`issued_at + 8h`), `last_seen_at`, and `ended_at`. On every protected request the server
checks, in order: `ended_at IS NULL`, `now < absolute_expires_at`, and
`now - last_seen_at < 30m`; then updates `last_seen_at`. The JWT's own `exp` is set to the
**absolute** cap, so an expired token is rejected before a database round trip, but the
token expiry is a fast path — never the mechanism.

**Rationale**: FR-005 requires the *server* to enforce both bounds. Two columns rather than
one because the two bounds answer different questions and a single "expires at" that gets
pushed forward on activity silently loses the absolute cap — which is the whole point of
having a second bound.

**Clock skew** (spec edge case): verification uses `leeway=0`. A credential marginally
outside the window fails closed. Server-side timestamps are `TIMESTAMP(timezone=True)` in
UTC, matching the existing convention.

---

## R11 — Cache scoping

**Decision**: No cache reads are introduced by this feature. The **permission
fingerprint** required by Principle III and FR-016 is defined now and computed on the
access context: a stable digest over `(company_id, sorted(permission_codes))`, exposed as
`AccessContext.permission_fingerprint` and consumed by the existing
`eaios_core.keys.cache_key`, which already takes that parameter.

**Rationale**: `cache_key` has required a `permission_fingerprint` since feature 001 and
nothing has ever produced one. Defining it here — where the permission set first exists —
means feature 004 consumes it rather than inventing a second definition. A unit test
asserts two contexts with different permission sets produce different fingerprints, and
that the same set in a different order produces the same one.

---

## R12 — Not disclosing which accounts exist

**Decision**: The sign-in path performs **the same work in every outcome**. When no user
matches, it verifies the supplied password against a fixed dummy Argon2 hash computed at
import time, then fails. The failure body, status, and headers are identical for: unknown
email, known email with a wrong password, inactive user, user with no credential row, and
a locked-out account.

**Rationale**: Argon2 at t=3/m=64MiB takes tens of milliseconds. Skipping it when the user
is unknown makes "does this account exist?" answerable with a stopwatch, which is
precisely FR-022's "no distinction between 'no such account' and 'wrong credentials'"
being satisfied in the response body and violated in the timing. The test asserts the
dummy verification actually runs, not that the two timings happen to be close on the
runner — a wall-clock comparison is exactly the flaky, low-power check that would pass
by accident.

---

## R13 — Binding the tenant for a request

**Decision**: A FastAPI dependency builds the access context and hands back a session
already inside `tenant_scope(session, context.company_id)`. The `company_id` comes from
the verified token, is confirmed against the user's current record, and is the only
source. Nothing in the request — path, query, header, cookie, body — is consulted for it
(FR-010).

**Rationale**: `tenant_scope` sets `app.company_id` transaction-locally and clears it on
exit, which is already correct for pooled connections. What is new is that the value now
comes from an identity rather than a constant. Attempts to supply a tenant are recorded:
a dependency inspects the request for a small set of tenant-ish names and audits the
attempt without acting on it (FR-010's SHOULD).

---

## R14 — Contracts for a second API surface

**Decision**: The existing generator and drift check cover the new endpoints with no
change — `openapi-typescript` reads the whole `/openapi.json`, and
`packages/contracts/scripts/verify.mjs` regenerates and diffs. Every new endpoint declares
a Pydantic request model, a success model, and an error model, following the `Problem` /
`ValidationProblem` envelope feature 002 introduced in `public/schemas.py`.

**Carried finding**: feature 002 had to add `Problem` and `ValidationProblem` because the
API published FastAPI's `HTTPValidationError` for a 422 it never sent. The lesson applies
directly here: the 401 and 403 bodies must be declared as the models actually returned,
and the drift check is what keeps them honest.

---

## R15 — Making the security suite falsifiable

Every security check ships with the thing that makes it capable of failing. This is the
project's recurring defect class and is treated as a first-class design concern.

| Check | Anti-vacuity guard |
|-------|--------------------|
| Manager reads direct reports (FR-033) | Assert the direct-report set is **non-empty** before asserting access; assert the unrelated-employee set is non-empty too. |
| Zero cross-tenant access (FR-034) | Assert the NileTech identity's reachable set is non-empty, so "zero Delta records" is not trivially true because zero records were reached. |
| Authorization precedes retrieval (FR-036) | The same recorder must show the payload query **does** run on the allowed path. |
| Request-supplied tenant is ignored (FR-035) | Assert the manipulated request returns the caller's own data — not that it returns nothing, which an unrelated failure also produces. |
| Denials are audited (FR-017) | Count entries before and after; assert the delta and the content, not merely that the table is non-empty. |
| Own-profile read is not audited (FR-017a) | Paired with a sensitive read in the same test that **does** write an entry, so a silently broken audit writer fails. |
| Token verification rejections | Each rejection test mutates exactly one property of an otherwise-valid token, and a control asserts the unmutated token is accepted. |
| Role-aware navigation (SC-008) | Assert the permitted user **sees** the entry, in the same test that asserts the unpermitted user does not. |

---

## Findings from the existing codebase

### F1 — The public contact form's browser submission has never been exercised

`apps/web/components/ContactForm.tsx` POSTs from the browser to `http://localhost:8000`
(`apiBase()` → `apiBaseBrowser()`), a cross-origin request with
`content-type: application/json`, which requires a CORS preflight. **The API registers no
CORS middleware** (`apps/api/src/eaios_api/main.py` adds only the request-context and
refusal-audit middlewares; a search of `apps/api/src` for CORS finds nothing). Every
browser-level test of that form intercepts the request with Playwright's `page.route`
(`apps/web/e2e/performance.spec.ts:108,134`), so the real request is never made. The
server-side tests exercise the endpoint directly and cannot see the browser's origin
check.

This is a **feature 002 defect, not a feature 003 one**, and it is out of this feature's
scope. It is recorded because it is the reason R3 chose same-origin routing rather than
inheriting the existing cross-origin pattern: adopting that pattern for sign-in would
build the portal on top of an untested assumption. Recommendation: a separate change adds
either a CORS policy scoped to the site origin or a route handler for the contact form,
with a browser test that does not stub the request.

### F2 — `audit_logs` already grants INSERT to the app role

Migration 0002 grants `SELECT, INSERT, UPDATE` on every tenant table including
`audit_logs`, then re-grants `SELECT` on line 55 with a comment about withholding DELETE.
The authorization audit therefore needs no new grant. Append-only is enforced by the
trigger from migration 0001, not by the grant.

### F3 — Anonymous refusals are attributed to the NileTech tenant

`refusal_audit.py` writes its entries under `PUBLIC_COMPANY_ID`. Authorization denials in
this feature have a real actor and a real tenant, so they are written under the actor's
company — but the cross-tenant case needs care: a NileTech user probing a Delta Retail
identifier produces an entry under **NileTech**, the actor's tenant. Writing it under
Delta Retail would put a record of a NileTech action inside another company's audit trail,
which is itself a cross-tenant leak. FR-030 makes this consistent: at layer 1 the other
tenant's resource is *absent*, so there is nothing of Delta Retail's to attribute.

---

## Open questions carried into `/speckit-tasks`

None block design. Two are recorded so they are decided deliberately rather than by
whoever writes the code first:

1. **Direct-report scope depth.** FR-024 says "direct reports". The dataset has a
   multi-level hierarchy, so "my reports' reports" is a reachable set the requirement does
   not mention. Planned as **strictly one level**, matching the literal wording; a
   transitive reading would need the spec changed, not the code widened.
2. **Sign-in bound storage on reset.** The new Redis keys use `RATE_LIMIT_PREFIX`, so
   `reset_all` clears them by pattern already. A test asserts it, because that is the
   exact failure feature 002 found (`keys.py:30-38`) — a prefix declared in two places
   drifts silently.
