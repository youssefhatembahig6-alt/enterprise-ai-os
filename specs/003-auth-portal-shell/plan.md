# Implementation Plan: Authentication, Request-Time Authorization, and Employee Portal Shell

**Branch**: `003-auth-portal-shell` | **Date**: 2026-08-05 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/003-auth-portal-shell/spec.md`

**Companion artifacts**: [research.md](research.md) · [data-model.md](data-model.md) ·
[contracts/auth-api.yaml](contracts/auth-api.yaml) ·
[contracts/policy-engine.md](contracts/policy-engine.md) ·
[contracts/portal-routes.md](contracts/portal-routes.md) · [quickstart.md](quickstart.md)

---

## Summary

This feature turns a system that *structures* data for access control into one that
*enforces* it. Sign-in exchanges a credential for a JWT bound to a server-side session
row. Every protected request re-verifies signature, issuer, audience, expiry, token type,
session liveness, active-user status, and tenant membership against **current records**,
then builds an immutable access context from the database — never from the request. A pure,
five-layer policy engine in `packages/core` decides, in fixed order, with stable reason
codes and default-deny. The `/portal` holding page becomes a sign-in surface and an
authenticated shell whose only complete area is My HR Profile, plus the minimum manager
view the direct-report demonstration needs.

The three technical decisions that shape everything else:

1. **Sign-in resolves the tenant by deriving each known company's id and looking the email
   up under each in turn** — reusing the circularity-breaker feature 002 already wrote down
   at `apps/api/src/eaios_api/public/queries.py:74`. No new global table, no widening of
   the tenant-boundary allowlist, and no request path that touches the RLS-exempt owner
   engine.
2. **The read is split into access attributes and protected payload.** Deciding needs
   `company_id`, `owner_id`, `manager_id`, `classification`; answering needs the profile
   fields. Only the first runs before the decision. That is what makes "authorization
   precedes retrieval" a checkable property rather than a claim, and it is proven by
   recording executed SQL in both directions.
3. **Credentials are written by a post-seed command, not the generator.** The dataset
   fingerprint is computed from in-process generated rows, so a later write cannot move it —
   which is the only reason FR-002a and SC-014 can both hold.

Compensation is a separate address requiring `hr:read_all`, so the blueprint's flagship
denial is a rule with a query that never runs, not a field omitted from a response.

---

## Technical Context

**Language/Version**: Python 3.12 (pinned `==3.12.*`), TypeScript 5.6.3, Node 20

**Primary Dependencies**: FastAPI 0.115.6 · SQLAlchemy 2.0.36 · Alembic 1.14.0 ·
Pydantic 2.10.5 · redis-py 5.2.1 · Next.js 15.5.22 (App Router) · React 19 ·
**new**: `argon2-cffi==25.1.0` (password hashing, research R1), `PyJWT==2.10.1`
(token mint/verify, research R2)

**Storage**: PostgreSQL 16 with Row-Level Security on every tenant-owned table
(`eaios_owner` bypasses as table owner; `eaios_app` is enforced; `FORCE ROW LEVEL
SECURITY` deliberately unset). Redis for sign-in attempt bounds. Qdrant and MinIO are
untouched — this feature reads neither.

**Testing**: pytest 8.3.4 with the existing four markers (`unit`, `integration`,
`security`, `e2e`); Vitest 3.0.5 for components; Playwright 1.51.1 across the three
configured viewport projects (360 / 768 / 1280)

**Target Platform**: Docker Compose — PostgreSQL, Qdrant, Redis, MinIO, FastAPI, Next.js,
Celery worker + beat. Developed on Windows 11, CI on ubuntu-latest and windows-latest.

**Project Type**: Web application in a uv + pnpm monorepo — `apps/api`, `apps/web`,
`packages/core`, `packages/ui`, `packages/contracts`, `services/worker`, `scripts/seed`

**Performance Goals**: Not a stated requirement of this feature. One bound is noted because
it is a security parameter rather than a performance target: Argon2id at t=3 / m=64 MiB /
p=4 costs tens of milliseconds per verification, deliberately, and the sign-in path pays it
on **every** attempt including ones with no matching user (research R12).

**Constraints**:

- 30-minute idle and 8-hour absolute session bounds, enforced server-side (FR-005)
- The committed dataset fingerprints — smoke and full — must not move (SC-014)
- Every feature 001 and 002 check must pass **unchanged** (FR-031, FR-032, SC-011)
- `packages/*` must not import from `apps/*`, `services/*`, or `scripts/*` (spec 001
  FR-001a), enforced by AST scan in `tests/unit/test_dependency_direction.py`
- No API version segment in any path (spec 001 FR-001b)
- Tests for tenant isolation and authorization written before implementation (FR-038,
  Constitution Principle VIII NON-NEGOTIABLE)

**Scale/Scope**: 2 tenants · 240 seeded users on the full profile · 17 permission codes ·
7 roles per tenant · 8 new API endpoints · 6 new portal routes · 2 new tables · 1 migration

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design — see
[§ Constitution Check (post-design)](#constitution-check-post-design).*

| Gate | Principle | Status |
|------|-----------|--------|
| Every artifact this feature creates/reads carries and filters on `company_id` | I (NON-NEGOTIABLE) | **PASS** — `user_credentials` and `sessions` both use `TenantMixin` and get an RLS policy in migration 0004. Redis sign-in counters are deliberately not tenant-scoped: the caller has no tenant until sign-in succeeds, the same reasoning already written for the anonymous bounds at `keys.py:112-118`. |
| Cross-tenant behavior covered by a NileTech ↔ Delta Retail isolation test | I (NON-NEGOTIABLE) | **PASS** — US3, `tests/security/test_cross_tenant_authenticated.py`, with a non-empty own-tenant assertion so "zero" is not vacuous. |
| Authorization decisions are deterministic code; no LLM influences access | II (NON-NEGOTIABLE) | **PASS** — `eaios_core.authz.evaluate` is pure. This feature introduces no model at all. |
| Layers applied in order: tenant → RBAC → ABAC → resource ACL | II | **PASS** — FR-013; ordering and short-circuiting asserted by a test that fails several layers at once and checks which one is reported. |
| Filtering happens before retrieval | III (NON-NEGOTIABLE) | **PASS** — descriptor/payload split (research R7); proven by recorded SQL in both directions. |
| Cache keys include tenant + permission fingerprint + normalized question + data version | III | **N/A** — no cache read or answer cache exists in this feature. The missing component, `permission_fingerprint`, is defined here and unit-tested, so feature 004 consumes a definition rather than inventing one. |
| Answers carry citations and pass the Hallucination Checker | IV | **N/A** — no generated answers. |
| Financial/HR values come from parameterized read-only queries or verified tools | V | **PASS** — every HR and compensation value is a parameterized SQLAlchemy query against the system of record. The read-only-role requirement attaches to agent-generated SQL, which arrives in feature 004. |
| Every new tool declares typed I/O, permissions, scope, audit, approval class | VI | **N/A** — no agent tools. Deliberately not pre-declared: an approval classification for a feature with no write path would be fitted to nothing. |
| Send/delete/publish/modify paths pause at the human approval gate | VII (NON-NEGOTIABLE) | **N/A** — reads only. Stated in the spec's assumptions because the first write action changes what this feature must satisfy. |
| Security-critical paths have failing tests written first | VIII (NON-NEGOTIABLE) | **PASS** — Phase 2 of the ordering below is entirely tests, observed failing, before Phase 3 writes a line of enforcement. |
| New data is deterministic, seeded, and coherent | IX | **PASS** — no generated data changes. Credentials and sessions are runtime state, outside `dataset.rows` and therefore outside the fingerprint; a test asserts the fingerprint is byte-identical across provisioning. |
| Consequential operations write audit records (allow and deny) | X | **PASS** — FR-017 / FR-017a; eight new audit actions, one definition of sensitivity. |
| Public site / portal surfaces are role-aware and complete | Mandatory Surfaces | **PASS** — FR-028, FR-029; six states per surface, permission-code-driven navigation. |
| Request/response models are typed at every boundary | Mandatory Surfaces | **PASS** — Pydantic request, success, and error models per endpoint; TypeScript regenerated and drift-checked. |
| Schema changes ship as reversible migrations; seeds stay idempotent | Mandatory Surfaces | **PASS** — migration 0004 with a real `downgrade()`. The credentials command is **outcome-idempotent**, not byte-idempotent; see [§ Credential provisioning](#credential-provisioning-and-reset-behaviour) for why that distinction is load-bearing and not a dodge. |
| Everything new runs inside the Docker Compose stack | Mandatory Surfaces | **PASS** — no new service; `make credentials` runs in the existing `seed` container. |
| Frontend work includes responsive, accessible, loading, empty, error, and access-denied states | Mandatory Surfaces | **PASS** — plus an **expired** state, held distinct from unauthenticated because FR-005's edge case requires the difference to be visible. |

**No gate fails.** The Complexity Tracking table is intentionally empty.

---

## Project Structure

### Documentation (this feature)

```text
specs/003-auth-portal-shell/
├── plan.md                      # This file
├── research.md                  # Phase 0 — decisions, rejected alternatives, findings
├── data-model.md                # Phase 1 — entities, policy types, audit actions
├── quickstart.md                # Phase 1 — validation scenarios and false-pass warnings
├── contracts/
│   ├── auth-api.yaml            # OpenAPI intent for the authenticated surface
│   ├── policy-engine.md         # The pure engine's contract and guarantees
│   └── portal-routes.md         # Route inventory, BFF handlers, required states
├── checklists/
│   └── requirements.md          # Spec quality — 16/16
└── tasks.md                     # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source code (repository root)

Existing structure, extended. No new application.

```text
packages/core/src/eaios_core/
├── authz/                              # NEW — pure, no I/O, no FastAPI
│   ├── context.py                      #   AccessContext (frozen, slots)
│   ├── decision.py                     #   Decision, ReasonCode, Scope, Action,
│   │                                   #   ResourceKind, ResourceDescriptor, AclGrant
│   ├── rules.py                        #   (kind, action) -> permission code table
│   ├── policy.py                       #   evaluate() — the five layers
│   ├── sensitivity.py                  #   is_sensitive() — FR-017b's single definition
│   └── filters.py                      #   qdrant_filter() — declared for 004, unused
├── models/auth.py                      # NEW — UserCredential, Session
├── models/__init__.py                  # + exports, + POST_BASELINE_TABLES entries
├── keys.py                             # + login bucket names
└── settings.py                         # + AuthSettings (JWT key, issuer, audience,
                                        #   lifetimes, demo password)

apps/api/src/eaios_api/
├── auth/                               # NEW
│   ├── router.py                       #   POST /auth/login, /auth/logout · GET /auth/session
│   ├── schemas.py                      #   LoginRequest, LoginAccepted, SessionState
│   ├── passwords.py                    #   Argon2id hash/verify + the dummy-hash path
│   ├── tokens.py                       #   mint/verify; algorithms pinned
│   ├── sessions.py                     #   create / validate / end; both expiry bounds
│   └── login_bounds.py                 #   the two Redis counters
├── authz/                              # NEW — the enforcement layer
│   ├── context_builder.py              #   SQL that builds AccessContext from current rows
│   ├── dependencies.py                 #   require_context() -> (AccessContext, scoped Session)
│   ├── enforce.py                      #   Decision -> HTTP status + audit, no reinterpretation
│   ├── audit.py                        #   the authorization audit writer
│   └── tenant_guard.py                 #   FR-010: detect and record supplied tenant/role/permission
├── me/router.py, schemas.py            # NEW — /me, /me/access-context, /me/hr-profile,
│                                       #        /me/direct-reports
├── hr/router.py, schemas.py, queries.py# NEW — /hr/profiles/{id}[/compensation];
│                                       #        queries.py holds the descriptor/payload split
├── errors.py                           # NEW — 401/403/404 handlers reusing `Problem`
└── main.py                             # + routers, + handlers

apps/api/alembic/versions/
└── 0004_authentication.py              # NEW — two tables, RLS policies, grants; reversible

scripts/seed/src/eaios_seed/
├── credentials.py                      # NEW — the post-seed provisioning step
├── cli.py                              # + `credentials` command; reset message
└── loaders/stores.py                   # + both tables in reset and emptiness

apps/web/
├── app/portal/page.tsx                  # REPLACED — sign-in (was the holding page)
├── app/portal/(authed)/layout.tsx       # NEW — authenticated shell
├── app/portal/(authed)/home/page.tsx    # NEW
├── app/portal/(authed)/profile/page.tsx # NEW — My HR Profile, the complete area
├── app/portal/(authed)/team/page.tsx    # NEW — direct reports
├── app/portal/(authed)/team/[userId]/page.tsx  # NEW
├── app/portal/(authed)/denied/page.tsx  # NEW — designed access-denied
├── app/portal/api/login/route.ts        # NEW — sets the httpOnly cookie
├── app/portal/api/logout/route.ts       # NEW — clears it, CSRF-guarded
├── components/portal/SignInForm.tsx     # NEW (client)
├── components/portal/PortalNav.tsx      # NEW — renders from permission codes
├── components/portal/SignOutButton.tsx  # NEW (client)
├── lib/session.ts                       # NEW — cookie read + server-side forwarding
├── lib/portal-api.ts                    # NEW — typed client for the authed surface
└── lib/pages.ts                         # + portal routes in the shared inventory

packages/ui/src/patterns/
├── AccessDeniedState.tsx                # NEW
└── SessionExpiredState.tsx              # NEW — held distinct from unauthenticated

tests/
├── unit/          test_authz_policy.py · test_authz_ordering.py ·
│                  test_authz_default_deny.py · test_authz_sensitivity.py ·
│                  test_permission_fingerprint.py · test_tokens.py · test_passwords.py
├── integration/   test_auth_login.py · test_session_expiry.py · test_access_context.py ·
│                  test_hr_profile.py · test_credentials_provisioning.py
├── security/      test_session_lifecycle.py · test_manager_scope.py ·
│                  test_authorize_before_read.py · test_cross_tenant_authenticated.py ·
│                  test_request_supplied_claims.py · test_login_enumeration.py ·
│                  test_authz_audit.py · test_token_tampering.py ·
│                  test_credential_never_logged.py · test_password_hash_column_unused.py
└── e2e/           test_credentials_lifecycle.py

apps/web/tests/     portal-states.test.tsx · SignInForm.test.tsx · PortalNav.test.tsx
apps/web/e2e/       portal.spec.ts  (+ existing accessibility / keyboard / responsive
                                     sweeps pick up the new routes via lib/pages.ts)
```

**Structure Decision**: extend, do not add an application. The policy engine goes to
`packages/core` because two rules point there independently — spec 001 FR-001a's dependency
direction, and the brief's requirement that shared policy types not depend on FastAPI or
frontend code. Everything that performs I/O (building the context, fetching descriptors,
writing audit rows, mapping decisions to statuses) stays in `apps/api`, which is what keeps
the engine unit-testable with no services running — the practical precondition for writing
its tests first.

---

## Threat model and trust boundaries

| # | Boundary | Crossing | Control |
|---|----------|----------|---------|
| TB1 | Browser → site | Sign-in credentials, session cookie | Cookie is `httpOnly` + `Secure` + `SameSite=Strict`; JS never holds the token; double-submit CSRF on both POST routes |
| TB2 | Site → API | Bearer token on every protected call | Signature, `iss`, `aud`, `exp`, `typ`, algorithm pinned to HS256; session row consulted; user re-read |
| TB3 | Request → tenant | The one field that is the entire boundary | `company_id` comes only from the verified token, confirmed against the user's current row; `tenant_guard` records any request-supplied tenant/role/permission and acts on none |
| TB4 | Application → database | Every tenant-owned query | `app.company_id` bound from the access context; RLS enforced against the non-owner `eaios_app` role; unset tenant returns zero rows |
| TB5 | Decision → data | The read itself | Descriptor query selects access attributes only; payload query runs only after `Decision.allowed`; both directions asserted by recorded SQL |
| TB6 | Sign-in → tenant resolution | The one legitimately pre-tenant operation | Each candidate tenant is bound explicitly and read under RLS; the owner engine is never used; a test asserts the response contains data from at most the matched tenant |

**Attacks explicitly in the security suite**: forged signature · `alg: none` · algorithm
confusion (RS256 public key presented as an HMAC secret) · wrong issuer · wrong audience ·
expired token · token-type confusion (a non-`access` token presented as one) · replay after
sign-out · replay after idle expiry · replay after the absolute cap · a valid token for
tenant A presented to tenant B's resource · tenant/role/permission injected via query,
path, header, cookie, and body · account enumeration by response, by status, and by
work-performed · credential stuffing across addresses · targeted lockout of one account ·
resource-existence probing across tenants · reading another employee's profile · reading a
direct report's compensation.

**Residual risks, stated rather than hidden**:

1. **Sign-in bounds fail open when Redis is down.** Refusing every sign-in because a cache
   is unavailable turns a cache outage into a total outage. The credential check itself is
   unaffected, so the exposure is unbounded guessing for the duration, not free entry.
2. **A per-account lockout is a bounded denial of service against that account.** The
   spec's clarification chose both dimensions knowing this. Fifteen minutes bounds it and
   the lockout is audited, so it is visible rather than mysterious.
3. **One shared demo password across all seeded users.** Local-only, refused outside
   `ENVIRONMENT=local`, and never committed in plain text. It is a demonstration dataset
   with no real person behind any account.
4. **HS256 means the verifier can also mint.** Correct while one process does both; the
   migration to RS256 is a settings change plus a key pair, not a redesign (research R2).

---

## Migration and rollback strategy

**Forward**: `0004_authentication.py` creates `user_credentials` and `sessions`, enables
`ROW LEVEL SECURITY` on both, creates the `tenant_isolation` policy in the same form
migration 0002 uses, and grants `SELECT, INSERT, UPDATE` to `eaios_app`. `DELETE` is
withheld, matching the existing posture — ending a session is an `UPDATE`.

**Backward**: `downgrade()` drops both policies, disables RLS, revokes the grants, and
drops both tables. Credentials and sessions are runtime state; losing them on a downgrade
loses nothing that `make credentials` does not restore.

**The trap this migration must not fall into**: migration 0001 builds the schema from
`Base.metadata`, read at migration time. A model that is not listed in
`POST_BASELINE_TABLES` is created by 0001 *and* by 0004, and a fresh `alembic upgrade head`
fails with *relation already exists* while every already-migrated database keeps working.
This is documented at `packages/core/src/eaios_core/models/__init__.py:82-94` because it
has already happened once. `tests/integration/test_migrations.py` runs the full round trip
and is the check that catches it.

**Ordering**: 0004 depends on 0003. No data migration is required — there is no existing
credential or session to move.

---

## Contract generation strategy

Unchanged machinery, second surface. `openapi-typescript` reads the whole
`/openapi.json`, so the new endpoints are covered by `make contracts`; `make
contracts-check` regenerates against the running API and diffs, naming the drifted line and
exiting 1.

Two obligations follow from feature 002's experience:

- **Declare the error models actually returned.** The API once published FastAPI's
  `HTTPValidationError` for a 422 it never sent, and nothing compared contract to reality.
  The 401 and 403 bodies here are `Problem`, declared in the route's `responses`, and the
  drift check is what keeps them honest.
- **Regenerate and commit in the same change as the schema.** `pnpm typecheck` passes
  against a stale generated file quite happily; the CI step placed before the browser suite
  is what does not.

---

## Credential provisioning and reset behaviour

`make credentials` → `eaios_seed.cli credentials`, run after `seed`.

- **Refuses outside `ENVIRONMENT=local`**, the same guard `reset` already applies.
- **Reads one password** from `AUTH_DEMO_PASSWORD` (a `SecretStr` with a local-only
  default, following the existing `eaios_owner_local_only` convention) or `--password`.
- **Asserts no email appears in more than one tenant** before writing, so sign-in's
  tenant resolution can never be ambiguous (research R4). A duplicate refuses the run.
- **Writes one row per active user**, each hashed independently with its own random salt.
- **Prints the password it used and the row count.** A provisioning step whose result is
  invisible is one nobody notices failing.

**Idempotence, precisely.** The seed's idempotence is byte-identical output. This
command's cannot be — Argon2 salts are random per hash, so two runs produce different
stored bytes. What is idempotent is the **observable outcome**: after any number of runs,
the same password signs in and the row count is unchanged. The command rewrites every row
rather than skipping rows that already have one, so a changed `--password` always takes
effect; skipping would make it silently not apply, which is a worse failure than the
rewrite.

**Why the fingerprint does not move**: it is computed from the in-process generated rows
(`dataset.rows`, hashed in `manifest.py`), not from the database. A row written after the
generator ran is invisible to it. `tests/e2e/test_credentials_lifecycle.py` measures the
fingerprint before and after and asserts equality (SC-014).

**Reset**: `reset_all` truncates both new tables. Credentials must be re-provisioned
afterwards, and the reset output says so — a reset that silently leaves the portal
unusable is exactly the failure mode this project keeps finding.

---

## Implementation phases and dependency ordering

Constitution Principle VIII is NON-NEGOTIABLE for this feature's subject matter: the tests
in Phase 2 are written and **observed failing** before Phase 3 begins.

| Phase | Contents | Depends on |
|-------|----------|------------|
| **P0 — Schema and configuration** | Models, migration 0004, `POST_BASELINE_TABLES`, `AuthSettings`, `.env.example`, reset/emptiness lists, dependency pins | — |
| **P1 — The pure engine** | `eaios_core.authz`: context, decision types, rules, `evaluate`, sensitivity, fingerprint, `qdrant_filter` stub. Its unit tests run with no services and are written alongside, first. | P0 (types only) |
| **P2 — Security tests, failing** | Every file under `tests/security/`, plus the integration tests for login, expiry, and context. Run. Watch fail. Record which failed and why. | P1 |
| **P3 — Authentication** | `passwords`, `tokens`, `sessions`, `login_bounds`, `auth/router` | P2 |
| **P4 — Context and enforcement** | `context_builder`, `dependencies`, `enforce`, `audit`, `tenant_guard` | P3 |
| **P5 — The vertical slice** | `me/` and `hr/` routers, descriptor/payload split, error handlers, `main.py` wiring | P4 |
| **P6 — Credential provisioning** | `credentials.py`, the CLI command, the Makefile target, docs | P0, P3 |
| **P7 — Contracts** | `make contracts`, commit the regenerated client, confirm drift check | P5 |
| **P8 — Portal shell** | Route handlers, sign-in, authenticated layout, navigation, profile, team, denied; the two new UI patterns; `lib/pages.ts` | P7 |
| **P9 — Browser verification** | Component state sweep, Playwright portal spec, accessibility / keyboard / responsive at three widths | P8 |
| **P10 — CI and documentation** | CI steps for `credentials` and the new suites; README, runbook, persona documentation | P9 |

**MVP checkpoint — end of P5.** At that point the whole security claim is demonstrable from
the API: sign in, read your own profile, read a direct report's, be refused for an
unrelated employee, be refused for compensation, get 404 across tenants, and find all of it
in the audit trail. Everything after P5 is the surface a person uses, which matters for the
defense but proves nothing the API has not already proven.

---

## Requirement → component traceability

| FR | Component |
|----|-----------|
| FR-001 | `auth/router.login`, `auth/passwords`, `authz/context_builder` (tenant resolution) |
| FR-002 | `auth/passwords` — Argon2id encoded output |
| FR-002a | `eaios_seed/credentials.py`, `cli.credentials`; generator untouched |
| FR-003 | `auth/tokens.verify`, `auth/sessions.validate`, `authz/dependencies` |
| FR-004 | `authz/context_builder` — every attribute re-read per request |
| FR-005 | `models/auth.Session` (two bounds), `auth/sessions.validate` |
| FR-006 | `apps/web/app/portal/page.tsx`; spec 002 FR-048 check untouched |
| FR-007 | `models/auth.Session.ended_at`, `auth/sessions.end`, consulted per request |
| FR-007a | `auth/login_bounds`, `keys.py` buckets |
| FR-008 | `eaios_core.authz.context.AccessContext`, `authz/context_builder` |
| FR-009 | `AccessContext` — frozen dataclass, frozenset collections |
| FR-010 | `authz/tenant_guard`, `authz/dependencies` |
| FR-011 | `me/router.access_context`, `AccessContextView` |
| FR-012 | `eaios_core.authz.policy` — pure; no model exists in this feature |
| FR-013 | `authz/policy.evaluate` — five layers, short-circuiting |
| FR-014 | `authz/rules` — codes only; `role_names` unread by the engine |
| FR-015 | `hr/queries` descriptor/payload split; `authz/enforce` ordering |
| FR-016 | `AccessContext.permission_fingerprint` + existing `keys.cache_key` (**partial** — mechanism defined; no cache exists to scope) |
| FR-017 | `authz/audit` — every denial, no coalescing |
| FR-017a | `authz/sensitivity.is_sensitive` → `Decision.audit_required` |
| FR-017b | `authz/sensitivity` — the single definition |
| FR-018 | `authz/audit` field allowlist; `auth/*` logging discipline |
| FR-019 | `errors.unauthenticated_handler` → 401 |
| FR-020 | `authz/enforce` → 403 |
| FR-021 | `Decision.tenant_absent` → 404 |
| FR-022 | `errors.py` bodies; `auth/router` uniform refusal; `passwords` dummy-hash path |
| FR-023 | `me/router.hr_profile`, `hr/queries.profile_payload` |
| FR-024 | `hr/router.profile`, `authz/rules` HR_PROFILE rows |
| FR-025 | `hr/router.compensation` — `hr:read_all`, separate address |
| FR-026 | `authz/context_builder.direct_report_ids` — read from `users.manager_id` |
| FR-027 | `app/portal/*`; address unchanged |
| FR-028 | `components/portal/PortalNav`; `authz/enforce` server-side refusal |
| FR-029 | `packages/ui` `AccessDeniedState`, `SessionExpiredState`; all six states per surface |
| FR-030 | `authz/policy` layer 1 → `tenant_absent`; `enforce` mapping |
| FR-031 | No change to `public/`, `health/`, manifest routers |
| FR-032 | `refusal_audit._SERVED_PREFIXES` deliberately not extended |
| FR-033–FR-036 | `tests/security/*` — see the test table below |
| FR-037 | `.github/workflows/ci.yml` — new steps in the `stack` job |
| FR-038 | Phase ordering P2 before P3 |

---

## Requirement → test traceability

| Requirement | Test | Anti-vacuity guard |
|-------------|------|--------------------|
| FR-001, FR-006 | `integration/test_auth_login.py` | Asserts a *known seeded* user signs in, not a fixture |
| FR-002, FR-018 | `security/test_credential_never_logged.py` | Asserts the hash and password appear in no serialiser, log record, or audit row; a control asserts the log capture itself works |
| FR-002a, SC-014 | `e2e/test_credentials_lifecycle.py` | Fingerprint before/after equality, then reset → re-provision → sign-in |
| FR-003, FR-019 | `security/test_token_tampering.py` | One property mutated per case; a control asserts the unmutated token is accepted |
| FR-004 | `integration/test_access_context.py` | Deactivate mid-session, assert the *next* request fails; a control asserts it succeeded before |
| FR-005, SC-002 | `integration/test_session_expiry.py` | Timestamps written, not slept; both `ended_reason` values asserted |
| FR-007, SC-002a | `security/test_session_lifecycle.py` | Replays the exact token after sign-out |
| FR-007a, FR-022, SC-013 | `security/test_login_enumeration.py` | Responses compared for equality across five causes; the dummy-hash path asserted to execute |
| FR-008–FR-011 | `integration/test_access_context.py`, `unit/test_permission_fingerprint.py` | Fingerprint differs across permission sets and is order-independent |
| FR-010, FR-035, SC-005 | `security/test_request_supplied_claims.py` | Manipulated response asserted **equal** to the clean one, not merely empty |
| FR-012–FR-014 | `unit/test_authz_ordering.py`, `test_authz_default_deny.py` | Multi-layer failures assert the earliest layer; every nullable attribute dropped in turn |
| FR-015, FR-036, SC-007 | `security/test_authorize_before_read.py` | The allowed path must show the payload statement **did** run |
| FR-016 | `unit/test_permission_fingerprint.py` | Positive: distinct sets → distinct digests; same set reordered → same digest |
| FR-017, FR-017a, FR-017b, SC-006 | `security/test_authz_audit.py` | Before/after deltas; own-profile zero asserted beside sensitive-read one |
| FR-020, FR-021, FR-030, SC-004 | `security/test_cross_tenant_authenticated.py` | Own-tenant reachable set asserted non-empty |
| FR-023 | `integration/test_hr_profile.py` | Field-by-field against the seeded record |
| FR-024, FR-033, SC-003 | `security/test_manager_scope.py` | Direct-report and unrelated-employee sets both asserted non-empty first |
| FR-025 | `security/test_authorize_before_read.py` | Manager denied; `hr:read_all` allowed, in the same test |
| FR-026 | `security/test_manager_scope.py` | Reachable set recomputed from `users.manager_id`, not hard-coded |
| FR-027, FR-029, SC-009 | `apps/web/tests/portal-states.test.tsx` | Every surface × every state, driven by the `lib/pages.ts` inventory |
| FR-028, SC-008 | `apps/web/tests/PortalNav.test.tsx`, `e2e/portal.spec.ts` | Permitted user sees the entry, asserted in the same test as the hidden case; hidden address requested directly |
| FR-031, FR-032, SC-011 | Existing feature 001 + 002 suites, unchanged | Any edit to those files is itself the failure signal |
| SC-001 | `e2e/portal.spec.ts` | Interaction count from arrival to profile |
| SC-010 | `e2e/portal-accessibility` (existing sweeps) | Zero violations at 360 / 768 / 1280 + keyboard traversal |
| FR-037, SC-012 | `.github/workflows/ci.yml` | The security step's exit code gates the job |
| FR-038 | Phase ordering | P2's failures are recorded in the task log before P3 starts |
| `users.password_hash` unused | `security/test_password_hash_column_unused.py` | AST scan; the deviation is closed by a check, not a comment |

---

## Verification commands and expected evidence

| Command | Expected evidence |
|---------|-------------------|
| `make up && make seed && make credentials` | Migrations through 0004; fingerprint matches the committed value; N credential rows reported |
| `make fingerprint` before and after `make credentials` | Byte-identical (SC-014) |
| `uv run python -m pytest tests/unit -m unit` | Policy ordering, default-deny, sensitivity, fingerprint, tokens, passwords — all green with no services running |
| `uv run python -m pytest tests/security -m security` | Every attack in the threat model refused; leakage **zero** (SC-012) |
| `uv run python -m pytest tests/integration -m integration` | Login, expiry, context, profile, provisioning |
| `uv run python -m pytest tests/e2e -m e2e` | Reset → re-provision → sign-in, fingerprint stable |
| `make contracts-check` | Exit 0; drift names the line and exits 1 |
| `pnpm --filter @eaios/web test` | Every portal surface renders all six states |
| `pnpm --filter @eaios/web exec playwright test` | Zero WCAG 2.2 AA violations at three widths; keyboard traversal; role-aware navigation both ways |
| `uv run python -m ruff check . && uv run python -m mypy …` | Clean, including the new packages |

---

## Explicit deviations

| # | Deviation | From | Why |
|---|-----------|------|-----|
| D1 | `users.password_hash` stays and is never used | Feature 001, which added it "so the auth feature does not need a migration to start using it" | The credential belongs in its own table with its own lifecycle. Dropping the column would change the generated row shape and move **both** committed fingerprints, which SC-014 forbids. The trap is closed by an AST test asserting no application code reads or writes it. |
| D2 | The portal's browser traffic goes through Next.js route handlers rather than directly to the API | Feature 002, where the contact form posts cross-origin from the browser | Research F1: the API registers **no CORS middleware**, and every browser test of that form stubs the request with `page.route`, so the cross-origin path has never actually been exercised. Building sign-in on an untested assumption is the wrong trade; same-origin also removes the credentialed-CORS configuration entirely. |
| D3 | Sign-in reads under each tenant in turn | The general rule that a request has one tenant | Sign-in is the one legitimately pre-tenant operation. Every read is still individually RLS-scoped with an explicit tenant bound, and the owner engine is never used (research R4). |
| D4 | No AI Assistant placeholder in the portal | The Constitution's *Mandatory Surfaces* list, which names it | That list is the full system's requirement, not this feature's. The spec places RAG, chat, and the assistant out of scope, and FR-028 forbids an entry point to something the user cannot use — which a dead placeholder would be. |
| D5 | Compensation is a separate endpoint, not a field | The obvious modelling, where a profile carries salary | FR-025's denial must happen **before** the query. A field omitted from a response has already been read. |

| D6 | Password primitives live in `packages/core`, not `apps/api` | The plan put them in the API. The seed's `credentials` command must hash, and `scripts/seed` may not import from `apps/api` (spec 001 FR-001a) — so they moved down. |
| D7 | `apps/web/e2e/boundary.spec.ts` changed | It asserted `/portal` carried no input at all, which FR-006 deliberately reverses. Its FR-048 check was replaced with a sweep over the eight content pages — the requirement's actual subject, which had never been checked anywhere. |
| D8 | T111–T112 are written but cannot run | The CI steps exist in `ci.yml` and are correct; the repository was removed at the user's request partway through, so nothing triggers them. Recorded as an open risk rather than marked done-in-spirit. |

**Not a deviation, recorded to prevent one**: research F1's contact-form CORS gap is a
feature 002 defect. This feature does not fix it and does not depend on it — it is the
reason the portal routes browser traffic same-origin (D2) rather than inheriting an
untested pattern. It is reported so it is decided rather than inherited.

**Also found while building, and fixed**: the Docker images install each workspace
member from its *own* `pyproject.toml`, so `PyJWT` and `argon2-cffi` added only to the
root manifest passed every local check and killed the API container on startup.
`tests/unit/test_package_dependencies.py` now compares each member's imports against its
own manifest, and its falsification removes `pyjwt` from the API's and asserts the check
fires.

---

## Constitution Check (post-design)

Re-evaluated against the design above. Every gate holds; three are worth restating because
the design changed what they rest on.

| Gate | Before design | After design |
|------|---------------|--------------|
| Tenant isolation (I) | PASS, on the assumption credentials could be tenant-scoped | **PASS, and stronger.** Research R4 removed the need for a global credential table entirely, so `GLOBAL_ENTITIES` is unchanged and `tests/unit/test_tenancy.py`'s exact-membership assertion needs no edit. |
| Filtering before retrieval (III) | PASS, as an intention | **PASS, as a checkable property.** The descriptor/payload split gives FR-015 a definition a test can falsify, and the recorded-SQL harness asserts both directions. |
| Test-first (VIII) | PASS, as a commitment | **PASS, and practical.** Making the engine pure means its ordering, default-deny, and reason-code tests need no database — which is what turns "write the test first" from a discipline into the path of least resistance. |

All other gates are unchanged: no LLM touches an authorization decision, no tool is
declared, no write path exists to gate, no generated data changes, audit covers allows and
denies under one definition of sensitivity, contracts are typed at every boundary, the
migration is reversible, everything runs in Compose, and every portal surface carries all
six states.

**No violations.** Complexity Tracking is empty.

---

## Complexity Tracking

> Filled only when the Constitution Check has violations that must be justified.

None. No gate failed, and no NON-NEGOTIABLE principle was approached.
