---

description: "Task list for feature 003 — Authentication, Request-Time Authorization, and Employee Portal Shell"
---

# Tasks: Authentication, Request-Time Authorization, and Employee Portal Shell

**Input**: Design documents from `specs/003-auth-portal-shell/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: **MANDATORY and written FIRST.** Constitution Principle VIII (NON-NEGOTIABLE)
names authorization decisions and tenant isolation as strict-cycle areas, and spec FR-038
says so again for this feature. Every phase below that touches those areas writes its
tests, **runs them, and records the failure**, before any enforcement code exists. The
"record the failure" tasks are real tasks; a test suite nobody watched fail is a test suite
nobody knows can fail.

**Constitution-driven categories this feature touches**: tenant scoping and cross-tenant
isolation tests · deterministic authorization · pre-retrieval filtering · audit-record
writes · reversible migrations and deterministic seeds · Docker Compose integration ·
frontend responsive / accessible / loading / empty / error / access-denied states.
Not touched: agent tool declarations, approval-gate wiring (this feature reads only).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel — different files, no dependency on an incomplete task
- **[Story]**: US1–US4, mapping to the user stories in [spec.md](spec.md)
- Exact file paths in every description

## Path conventions

uv + pnpm monorepo: `packages/core/src/eaios_core/`, `apps/api/src/eaios_api/`,
`apps/web/`, `packages/ui/src/`, `scripts/seed/src/eaios_seed/`, `tests/` at the
repository root. Paths below are as they appear in [plan.md](plan.md).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Dependencies and configuration the rest of the feature reads.

- [X] T001 Pin `argon2-cffi==25.1.0` and `PyJWT==2.10.1` in `pyproject.toml` dependencies, then run `uv sync` and confirm `uv.lock` updated
- [X] T002 [P] Add `AuthSettings` (JWT signing key as `SecretStr`, issuer, audience, 30-minute idle and 8-hour absolute lifetimes, demo password) to `packages/core/src/eaios_core/settings.py`, following the existing local-only-default convention
- [X] T003 [P] Add the new `AUTH_*` variables with working local defaults to `infrastructure/.env.example`
- [X] T004 [P] Add the `login:account` and `login:address` bucket names and their thresholds to `packages/core/src/eaios_core/keys.py`, reusing `RATE_LIMIT_PREFIX` so `reset_all` clears them
- [X] T005 [P] Add `B008` per-file-ignores for `apps/api/src/eaios_api/auth/*.py`, `authz/*.py`, `me/*.py`, and `hr/*.py` in `pyproject.toml`, matching the existing entries for `health/` and `public/`
- [X] T006 [P] Add `AUTH_JWT_SIGNING_KEY` and `AUTH_DEMO_PASSWORD` to the `api` and `seed` service environments in `infrastructure/docker-compose.yml`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Schema, the pure policy engine, credentials, authentication, and the
enforcement layer. **No user story can be demonstrated until this phase is complete** —
every story begins with signing in.

**CRITICAL**: No user story work begins until the checkpoint at the end of this phase.

### 2A — Schema and lifecycle

- [X] T007 Create `UserCredential` and `Session` models in `packages/core/src/eaios_core/models/auth.py` per [data-model.md](data-model.md) §1, both using `TenantMixin`, with the three `Session` check constraints and the `(company_id, user_id, ended_at)` index
- [X] T008 Export both from `packages/core/src/eaios_core/models/__init__.py` and add `"user_credentials"` and `"sessions"` to `POST_BASELINE_TABLES` — omitting them makes migration 0001 create tables that 0004 then recreates, and a fresh `alembic upgrade head` fails while migrated databases keep working
- [X] T009 Add both table names to `RUNTIME_TABLES` in `scripts/seed/src/eaios_seed/loaders/stores.py:53`; that one constant feeds both `reset_all`'s `TRUNCATE` and the emptiness pre-flight
- [X] T010 Write reversible migration `apps/api/alembic/versions/0004_authentication.py`: create both tables, `ENABLE ROW LEVEL SECURITY`, create the `tenant_isolation` policy in the same form as `0002_row_level_security.py`, `GRANT SELECT, INSERT, UPDATE` to `eaios_app`, and a `downgrade()` that reverses all four
- [X] T011 Run `uv run python -m pytest tests/integration/test_migrations.py -m integration -v` and confirm the full up/down/up round trip passes from an empty database

### 2B — The pure policy engine (tests first)

- [X] T012 [P] Write **failing** `tests/unit/test_authz_ordering.py`: a descriptor failing several layers at once must report the **earliest** layer and its reason code
- [X] T013 [P] Write **failing** `tests/unit/test_authz_default_deny.py`: parametrised over every nullable attribute, dropping each in turn from an otherwise-allowing descriptor, asserting `CONTEXT_INCOMPLETE`
- [X] T014 [P] Write **failing** `tests/unit/test_authz_sensitivity.py`: the four enumerated sensitive cases audit, an own non-compensation profile read does not, and denials always do
- [X] T015 [P] Write **failing** `tests/unit/test_permission_fingerprint.py`: distinct permission sets give distinct digests; the same set reordered gives the same digest
- [X] T016 Run `uv run python -m pytest tests/unit -m unit -v` and record which of T012–T015 failed and with what error
- [X] T017 [P] Implement `AccessContext` in `packages/core/src/eaios_core/authz/context.py` — `@dataclass(frozen=True, slots=True)`, `frozenset` collections, `has()`, `manages()`, `permission_fingerprint`
- [X] T018 [P] Implement `Decision`, `ReasonCode`, `Scope`, `Action`, `ResourceKind`, `ResourceDescriptor`, `AclGrant` in `packages/core/src/eaios_core/authz/decision.py` per [data-model.md](data-model.md) §3
- [X] T019 Implement the `(ResourceKind, Action) → permission code` table in `packages/core/src/eaios_core/authz/rules.py` from [contracts/policy-engine.md](contracts/policy-engine.md) §3
- [X] T020 Implement `is_sensitive()` in `packages/core/src/eaios_core/authz/sensitivity.py` — the single definition FR-017b requires
- [X] T021 Implement `evaluate()` in `packages/core/src/eaios_core/authz/policy.py` — five layers, short-circuiting, `tenant_absent` set only by layer 1
- [X] T022 [P] Implement `qdrant_filter()` in `packages/core/src/eaios_core/authz/filters.py` — declared for feature 004, unit-tested, importing no Qdrant client
- [X] T023 Add to `tests/unit/test_authz_policy.py` an AST assertion that the engine modules never read `AccessContext.role_names` (FR-014), and confirm `tests/unit/test_dependency_direction.py` still passes with the new package

### 2C — Credential provisioning

- [X] T024 Write **failing** `tests/integration/test_credentials_provisioning.py`: one row per active user, re-running leaves the row count unchanged and the same password still verifying, and a duplicate email across tenants refuses the run
- [X] T025 Implement `scripts/seed/src/eaios_seed/credentials.py` — the cross-tenant duplicate-email assertion, one Argon2id hash per user with its own salt, rewrite-not-skip semantics
- [X] T026 Add the `credentials` command to `scripts/seed/src/eaios_seed/cli.py`: refuse unless `environment == "local"`, print the password used and the row count, and make `reset` print that credentials must be re-provisioned
- [X] T027 [P] Add a `credentials` target to `Makefile` and document the `up → seed → credentials` order in `docs/running.md`
- [X] T028 Write `tests/e2e/test_credentials_lifecycle.py`: fingerprint byte-identical before and after provisioning (SC-014), then reset → re-provision → sign-in works again

### 2D — Authentication (tests first)

- [X] T029 [P] Write **failing** `tests/unit/test_passwords.py`: the stored value is not the password, verification succeeds for the right one and fails for the wrong one, two hashes of the same password differ (per-hash salt)
- [X] T030 [P] Write **failing** `tests/unit/test_tokens.py`: mint/verify round trip, and rejection of a token whose `iss`, `aud`, `typ`, or `exp` is wrong
- [X] T031 [P] Write **failing** token-tampering cases: forged signature, `alg: none`, algorithm confusion, wrong issuer, wrong audience, expired, wrong token type — each mutating exactly one property, with a control asserting the unmutated token is accepted. Written into `tests/unit/test_tokens.py` alongside T030 rather than a separate `tests/security/` file, because they exercise the same `verify_access_token` and the control belongs beside the round trip; `TestEachCheckCanRefuse` and `TestAlgorithmConfusion` are these cases
- [X] T032 [P] Write **failing** `tests/security/test_login_enumeration.py`: responses identical across unknown email, wrong password, inactive user, no credential, and locked-out; the dummy-hash path asserted to execute when no user matches; both bounds asserted at their stated numbers
- [X] T033 [P] Write **failing** `tests/security/test_session_lifecycle.py`: sign in, keep the exact token, sign out, replay that token, expect 401 (SC-002a)
- [X] T034 [P] Write **failing** `tests/integration/test_session_expiry.py`: idle past 30 minutes gives `ended_reason='IDLE'`, continuous activity past 8 hours gives `'ABSOLUTE'` — advancing time by writing timestamps, never by sleeping
- [X] T035 Run `uv run python -m pytest tests/unit tests/security tests/integration -v` and record which of T029–T034 failed and with what error
- [X] T036 [P] Implement `apps/api/src/eaios_api/auth/passwords.py` — Argon2id hash/verify plus the module-level dummy hash the no-match path verifies against (research R12)
- [X] T037 [P] Implement `apps/api/src/eaios_api/auth/tokens.py` — mint and verify with `algorithms=["HS256"]` pinned, `iss`/`aud` required, `leeway=0`
- [X] T038 Implement `apps/api/src/eaios_api/auth/sessions.py` — create, validate (ended → absolute → idle → advance `last_seen_at`), and end
- [X] T039 [P] Implement `apps/api/src/eaios_api/auth/login_bounds.py` — the two Redis counters, success clearing the account counter, every lockout audited
- [X] T040 [P] Implement `apps/api/src/eaios_api/auth/schemas.py` — `LoginRequest`, `LoginAccepted`, `SessionState` per [contracts/auth-api.yaml](contracts/auth-api.yaml)
- [X] T041 Implement `apps/api/src/eaios_api/auth/router.py` — `POST /auth/login` with per-tenant email resolution over derived company ids (research R4), `POST /auth/logout`, `GET /auth/session`
- [X] T042 Implement `apps/api/src/eaios_api/errors.py` — 401/403/404 handlers returning the `Problem` envelope with no internal detail (FR-022), and register the auth router and handlers in `apps/api/src/eaios_api/main.py`
- [X] T043 Re-run `tests/unit/test_passwords.py`, `tests/unit/test_tokens.py`, `tests/security/test_login_enumeration.py`, `test_session_lifecycle.py`, and `tests/integration/test_session_expiry.py`; confirm every one now passes

### 2E — Access context and enforcement (tests first)

- [X] T044 [P] Build the SQL-recording harness in `tests/security/conftest.py` — a `before_cursor_execute` listener capturing every statement of one request, with a self-test proving the recorder captures a known query
- [X] T045 [P] Write **failing** `tests/integration/test_access_context.py`: every field of `/me/access-context` matches the seeded record; deactivating a user mid-session fails the **next** request, with a control asserting it succeeded before
- [X] T046 [P] Write **failing** `tests/security/test_request_supplied_claims.py`: the same request repeated with `company_id` in query, path, header, cookie, and body, plus `roles` and `permissions` fields, must return a response **equal** to the clean one — not merely empty (FR-035)
- [X] T047 [P] Write **failing** `tests/security/test_authz_audit.py`: before/after deltas for denials and sensitive allows, zero for an own non-compensation read asserted beside a sensitive read that writes exactly one, and no entry containing a credential or token fragment
- [X] T048 Run `tests/integration/test_access_context.py`, `tests/security/test_request_supplied_claims.py`, and `tests/security/test_authz_audit.py`; record which failed and with what error
- [X] T049 Implement `apps/api/src/eaios_api/authz/context_builder.py` — one query set building `AccessContext` from current rows, both manager directions, permission codes via `user_roles ⋈ role_permissions ⋈ permissions`
- [X] T050 Implement `apps/api/src/eaios_api/authz/dependencies.py` — `require_context()` returning the context and a session already inside `tenant_scope(session, context.company_id)`
- [X] T051 [P] Implement `apps/api/src/eaios_api/authz/tenant_guard.py` — detect a tenant, role, or permission value anywhere in the request, act on none, write the `authz.tenant_value_supplied` audit entry (FR-010)
- [X] T052 [P] Implement `apps/api/src/eaios_api/authz/audit.py` — the eight actions in [data-model.md](data-model.md) §4.1, actor's company as `company_id`, no email on `auth.sign_in_failed`, a field allowlist that cannot carry a credential
- [X] T053 Implement `apps/api/src/eaios_api/authz/enforce.py` — call `evaluate`, map `tenant_absent`→404 / other denial→403 / allow→200 with no status chosen locally, write the audit entry when `Decision.audit_required`
- [X] T054 Re-run `tests/integration/test_access_context.py`, `tests/security/test_request_supplied_claims.py`, and `tests/security/test_authz_audit.py`; confirm every one now passes

### 2F — Credential and column safety

- [X] T055 [P] Write and pass `tests/security/test_credential_never_logged.py` — the password and the hash appear in no serialiser, log record, or audit row, with a control asserting the log capture itself works
- [X] T056 [P] Write and pass `tests/security/test_password_hash_column_unused.py` — AST scan proving no application code reads or writes `users.password_hash` (plan deviation D1, closed by a check rather than a comment)

**Checkpoint**: The API authenticates, builds a trusted context, and decides — and exposes
no protected data yet. Every security test written so far has been observed failing and now
passes.

---

## Phase 3: User Story 1 — An Employee Signs In And Sees Their Own Record (Priority: P1) 🎯 MVP

**Goal**: The vertical slice — credentials become a verified identity, identity becomes a
server-built access context, and that context governs a real data read.

**Independent Test**: Sign in as a known seeded employee, confirm the portal shows that
person's own profile and nobody else's, sign out, and confirm protected addresses are no
longer reachable.

### Tests for User Story 1 (MANDATORY - write first, watch fail)

- [X] T057 [P] [US1] Write **failing** `tests/integration/test_auth_login.py` — a *seeded* user (not a fixture) signs in, reaches `/me`, and signs out
- [X] T058 [P] [US1] Write **failing** `tests/integration/test_hr_profile.py` — `/me/hr-profile` matches the seeded record field by field, and carries **no** compensation field of any kind
- [X] T059 [US1] Run `tests/integration/test_auth_login.py` and `tests/integration/test_hr_profile.py`; record both failures

### Implementation for User Story 1

- [X] T060 [P] [US1] Implement `apps/api/src/eaios_api/me/schemas.py` — `CurrentUser`, `AccessContextView`, `HrProfile`, `LeaveBalance` per [contracts/auth-api.yaml](contracts/auth-api.yaml)
- [X] T061 [US1] Implement `apps/api/src/eaios_api/hr/queries.py` — the descriptor/payload split: `load_descriptor()` selecting access attributes only, `load_profile_payload()` selecting the profile fields, and no function selecting both
- [X] T062 [US1] Implement `apps/api/src/eaios_api/me/router.py` — `GET /me`, `GET /me/access-context`, `GET /me/hr-profile`, each going through `enforce` before any payload read
- [X] T063 [US1] Register the `me` router in `apps/api/src/eaios_api/main.py` and confirm `/openapi.json` publishes the new models
- [X] T064 [US1] Run `make contracts` and commit the regenerated `packages/contracts/src/generated/api.ts`; confirm `make contracts-check` exits 0
- [X] T065 [US1] Re-run `tests/integration/test_auth_login.py` and `tests/integration/test_hr_profile.py`; confirm both pass
- [X] T066 [P] [US1] Add `SessionExpiredState` to `packages/ui/src/patterns/SessionExpiredState.tsx`, export it from `packages/ui/src/index.ts`, and style it in `packages/ui/src/components.css`
- [X] T067 [P] [US1] Implement `apps/web/lib/session.ts` — read the cookie via `next/headers`, forward it on the `Authorization` header for server-component fetches (a server `fetch` does not inherit the browser's cookie jar)
- [X] T068 [US1] Implement `apps/web/lib/portal-api.ts` — typed client over `@eaios/contracts`, with `Unauthenticated`, `SessionExpired`, and `Forbidden` as distinct outcomes rather than one error
- [X] T069 [US1] Implement `apps/web/app/portal/api/login/route.ts` — forward to `POST /auth/login`, set `eaios_session` (`httpOnly`, `Secure`, `SameSite=Strict`, `Path=/`, 8-hour `Max-Age`) and a readable `eaios_csrf`, return `{ ok: true }` and never the token
- [X] T070 [US1] Implement `apps/web/app/portal/api/logout/route.ts` — require `X-CSRF-Token` to match `eaios_csrf`, forward to `POST /auth/logout`, clear both cookies **regardless of the API's answer**
- [X] T071 [P] [US1] Implement `apps/web/components/portal/SignInForm.tsx` (client) — labelled controls, `aria-describedby` errors, failure announced in a live region, one generic message for every refusal
- [X] T072 [P] [US1] Implement `apps/web/components/portal/SignOutButton.tsx` (client)
- [X] T073 [US1] Replace `apps/web/app/portal/page.tsx` with the sign-in surface — **same address** (FR-027, spec 002 FR-049a), redirecting to `/portal/home` when a live session exists
- [X] T074 [US1] Implement `apps/web/app/portal/(authed)/layout.tsx` — the authenticated shell, redirecting to `/portal` when unauthenticated and to the expired state when the session ended
- [X] T075 [P] [US1] Implement `apps/web/app/portal/(authed)/home/page.tsx` — greeting by name, session state, focus moved to the heading after sign-in
- [X] T076 [US1] Implement `apps/web/app/portal/(authed)/profile/page.tsx` — My HR Profile with department, office, manager, employment type, and leave balance, and all six states
- [X] T077 [US1] Add `/portal/home` and `/portal/profile` to `NON_CONTENT_ROUTES` in `apps/web/lib/pages.ts` so the existing sweeps visit them and `sitemap.ts` does not
- [X] T078 [P] [US1] Write `apps/web/tests/SignInForm.test.tsx` — labels, error association, live-region announcement, one message for every refusal
- [X] T079 [US1] Write `apps/web/tests/portal-states.test.tsx` — every portal surface against loading, empty, error, unauthenticated, **expired**, and access-denied, driven by the `lib/pages.ts` inventory. Each of the 35 route/state cells is classified route-specific, shared-boundary, or unreachable-with-a-reason, and the suite fails if any cell is unclassified (contracts/portal-routes.md §3). Writing it found five gaps: no loading boundary existed, the shell and `/portal` both collapsed *error* into *unauthenticated*, the error boundary had to move up a segment to catch the shell, and `/portal/team/[userId]` had no retry
- [X] T080 [US1] Write `apps/web/e2e/portal.spec.ts` — sign in, land on the profile, sign out, confirm the protected address is no longer reachable, and confirm the expiry state is reached and named

**Checkpoint**: User Story 1 is fully functional and independently testable. This is the
MVP — the whole security claim is demonstrable from here.

---

## Phase 4: User Story 2 — A Manager Sees Their Team And No One Else (Priority: P2)

**Goal**: The first requirement identity alone cannot satisfy. The same request succeeds or
fails depending on who asks.

**Independent Test**: Sign in as a seeded manager, read a direct report's profile, request
an unrelated employee's profile and confirm refusal, then check the audit trail holds both
events.

### Tests for User Story 2 (MANDATORY - write first, watch fail)

- [X] T081 [P] [US2] Write **failing** `tests/security/test_manager_scope.py` — the seeded engineering manager reads every direct report and is refused for an unrelated employee; the direct-report set **and** the unrelated set are both asserted non-empty first
- [X] T082 [P] [US2] Write **failing** `tests/security/test_authorize_before_read.py` — using the T044 recorder: a manager denied compensation executes **no** statement referencing `employee_profiles.salary_amount`, and an `hr:read_all` caller's request **does** (FR-036, SC-007)
- [X] T083 [US2] Run `tests/security/test_manager_scope.py` and `tests/security/test_authorize_before_read.py`; record both failures

### Implementation for User Story 2

- [X] T084 [P] [US2] Implement `apps/api/src/eaios_api/hr/schemas.py` — `DirectReport` and `Compensation` per [contracts/auth-api.yaml](contracts/auth-api.yaml), with `salary_amount` serialised as a string, never a float
- [X] T085 [US2] Extend `apps/api/src/eaios_api/hr/queries.py` with `load_direct_reports()` and `load_compensation_payload()`, keeping the descriptor/payload split intact
- [X] T086 [US2] Implement `apps/api/src/eaios_api/hr/router.py` — `GET /hr/profiles/{user_id}` and `GET /hr/profiles/{user_id}/compensation` (`hr:read_all`, the flagship denial)
- [X] T087 [US2] Add `GET /me/direct-reports` to `apps/api/src/eaios_api/me/router.py` — an empty list for a permitted caller with no reports, never a refusal
- [X] T088 [US2] Register the `hr` router in `apps/api/src/eaios_api/main.py`, run `make contracts`, and commit the regenerated client
- [X] T089 [US2] Re-run `tests/security/test_manager_scope.py` and `tests/security/test_authorize_before_read.py`; confirm both pass
- [X] T090 [P] [US2] Implement `apps/web/app/portal/(authed)/team/page.tsx` — the direct-reports list with its empty state held distinct from access-denied
- [X] T091 [US2] Implement `apps/web/app/portal/(authed)/team/[userId]/page.tsx` — one report's profile, rendering the designed access-denied state on 403
- [X] T092 [US2] Add the team routes to `apps/web/lib/pages.ts` and extend `apps/web/tests/portal-states.test.tsx` to cover them — `/portal/team` in `PORTAL_PAGES`, and `/portal/team/[userId]` in the new `PORTAL_DYNAMIC_ROUTES` descriptor, kept apart so the browser sweeps that navigate to each `PORTAL_PAGES` entry are never sent to an unresolved `[userId]` template
- [X] T093 [US2] Extend `apps/web/e2e/portal.spec.ts` with the manager journey: read a report, request an unrelated employee, land on the designed denial

**Checkpoint**: User Stories 1 and 2 both work independently.

---

## Phase 5: User Story 3 — A Delta Retail User Cannot Reach NileTech Data (Priority: P3)

**Goal**: The constitution's first principle, proven for an *authenticated* caller for the
first time.

**Independent Test**: Sign in as a Delta Retail user, attempt to read a NileTech record by
its identifier, and confirm the response is indistinguishable from that record not
existing.

### Tests for User Story 3 (MANDATORY - write first, watch fail)

- [X] T094 [P] [US3] Write **failing** `tests/security/test_cross_tenant_authenticated.py` — a Delta Retail identity requesting a NileTech record gets **404**, byte-identical to a request for an identifier belonging to nobody; the NileTech caller's own reachable set is asserted non-empty in the same run so "zero" is not vacuous
- [X] T095 [US3] Run `tests/security/test_cross_tenant_authenticated.py` and record the failure

### Implementation for User Story 3

- [X] T096 [US3] Confirm and, where needed, correct the `tenant_absent` → 404 mapping in `apps/api/src/eaios_api/authz/enforce.py`, and assert no code path can turn a layer-1 refusal into a 403 (FR-021, FR-030)
- [X] T097 [US3] Confirm audit entries for cross-tenant attempts carry the **actor's** company in `apps/api/src/eaios_api/authz/audit.py`, and add the assertion to `tests/security/test_authz_audit.py` — writing under the target's tenant would put one company's record inside another's trail (research F3)
- [X] T098 [US3] Extend `tests/security/test_request_supplied_claims.py` with the cross-tenant selectors: a valid token for one tenant presented against the other's resource, and a company identifier supplied alongside it
- [X] T099 [US3] Extend `tests/security/test_cross_tenant_authenticated.py` to sweep **every** endpoint added by this feature, so a new address cannot be added without an isolation case (FR-034)
- [X] T100 [US3] Re-run `tests/security/test_cross_tenant_authenticated.py` and confirm it passes
- [X] T101 [US3] Extend `apps/web/e2e/portal.spec.ts` — a Delta Retail user signs in and the portal shows only Delta Retail content, with a NileTech identifier reached directly rendering not-found rather than denied

**Checkpoint**: All three data-access stories are independently functional.

---

## Phase 6: User Story 4 — Navigation Shows Only What The User Can Use (Priority: P4)

**Goal**: A portal that feels designed rather than like a permissions error surface.

**Independent Test**: Sign in as users with different role sets and compare the visible
navigation against each user's permission codes.

### Tests for User Story 4 (write first, watch fail)

- [X] T102 [P] [US4] Write **failing** `apps/web/tests/PortalNav.test.tsx` — the permitted user **sees** the entry and the unpermitted user's markup does not contain the string at all, asserted in the same test; `display: none` is still in the DOM and still read by a screen reader
- [X] T103 [US4] Run `apps/web/tests/PortalNav.test.tsx` and record the failure

### Implementation for User Story 4

- [X] T104 [P] [US4] Add `AccessDeniedState` to `packages/ui/src/patterns/AccessDeniedState.tsx`, export it from `packages/ui/src/index.ts`, and style it in `packages/ui/src/components.css`
- [X] T105 [US4] Implement `apps/web/components/portal/PortalNav.tsx` — rendering from `CurrentUser.permissions` (codes, never role names), omitting unpermitted entries entirely
- [X] T106 [US4] Implement `apps/web/app/portal/(authed)/denied/page.tsx` and wire every 403 outcome in `apps/web/lib/portal-api.ts` to it — never a blank screen, never a raw 403
- [X] T107 [US4] Add `PortalNav` to `apps/web/app/portal/(authed)/layout.tsx` with focus management on route change
- [X] T108 [US4] Add to `tests/security/test_manager_scope.py` a case requesting each navigation-hidden address **directly** and asserting the server refuses it regardless of what the interface showed (FR-028, SC-008)
- [X] T109 [US4] Re-run `apps/web/tests/PortalNav.test.tsx` and confirm it passes
- [X] T110 [US4] Extend `apps/web/e2e/portal.spec.ts` — navigation compared across two seeded users with different role sets, both the present and the absent entries asserted

**Checkpoint**: All four user stories are independently functional.

---

## Phase 7: Polish & Cross-Cutting Concerns

**T111 and T112 are complete, and the evidence is a run rather than a file.** Both
add steps to `.github/workflows/ci.yml`. They were briefly marked [X] once on the
grounds that the YAML was correct — the reasoning Principle VIII exists to reject — and
reopened. They are closed now against **CI run 31443872819** at commit `429fdcb`, API
conclusion `success`: 7/7 jobs green, 86 successful steps, 3 conditional log-dump skips,
0 failures. FR-037, SC-012, and spec 001 FR-047c are met by that run.

**Purpose**: The evidence, the pipeline, and the documentation that make the feature *done*
rather than working.

- [X] T111 [P] Add a `Provision credentials` step to the `stack` job in `.github/workflows/ci.yml`, after the seed step and before the test steps — green in run 31443872819. A second step, `Re-provision credentials after the destructive lifecycle tests`, was needed for the same reason one step later: `tests/e2e/test_determinism.py` resets twice and never re-provisions, so the browser suite below it found no credentials and every sign-in answered 401
- [X] T112 [P] Add the authorization and authentication suites as their own named step in `.github/workflows/ci.yml` so a failure names itself, and confirm the step's exit code gates the job (FR-037) — 128 passed in run 31443872819. The gating half is proven by two earlier runs of the same step: in 31426053623 it exited 4 and the job failed; in 31427580344 it passed and the job continued. The step also named a stale path, `tests/security/test_token_tampering.py`, which never existed and made `pytest` abort before collection
- [X] T113 [P] Confirm the existing accessibility, keyboard, responsive, and metadata sweeps in `apps/web/e2e/` reach the new portal routes through `apps/web/lib/pages.ts`; extend them if any filters by path prefix
- [X] T114 [P] Confirm the `Committed API types match the running API` step in `.github/workflows/ci.yml` covers the new surface and still runs before the browser suite
- [X] T115 [P] Document the `up → seed → credentials` order and credential re-provisioning after reset in `docs/running.md` and `README.md`
- [X] T116 [P] Add a sign-in note to `docs/personas.md` generation in `scripts/seed/src/eaios_seed/docgen.py`, and run `make docs` then `make docs-check`
- [X] T117 Run `uv run python -m ruff check .` and `uv run python -m mypy packages/core/src apps/api/src services/worker/src scripts/seed/src`; fix everything
- [X] T118 Run `pnpm lint`, `pnpm typecheck`, `pnpm test`, and `pnpm --filter @eaios/web build`; fix everything
- [X] T119 Run the full suite in CI order — `make test && make test-site && make contracts-check` — and confirm every feature 001 and 002 check passes **unchanged** (FR-031, FR-032, SC-011)
- [X] T120 Run the fixed access-control acceptance suite — `uv run python -m pytest tests/security -m security -v` — and confirm unauthorized information leakage measures **0%** (Constitution Principle VIII, FR-037, SC-012); record the number
- [X] T121 Execute all thirteen scenarios in [quickstart.md](quickstart.md) and record the observed evidence for each, including each stated false-pass check

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)**: no dependencies — start immediately
- **Foundational (Phase 2)**: depends on Setup — **blocks every user story**
- **User Stories (Phases 3–6)**: all depend on Foundational
  - US1 (P1) has no dependency on another story
  - US2 (P2) is independently testable but reuses the descriptor/payload split US1 builds
  - US3 (P3) is independently testable; its API work is verification of Foundational behaviour
  - US4 (P4) needs the authenticated layout US1 builds
- **Polish (Phase 7)**: depends on every story that is being shipped

### Within Phase 2

2A (schema) blocks everything. 2B (the pure engine) is independent of 2A and can run
alongside it — it performs no I/O. 2C (credentials) needs 2A. 2D (authentication) needs
2A and 2C. 2E (context and enforcement) needs 2B and 2D. 2F can run any time after 2D.

### Within each user story

1. Tests written
2. Tests **run and observed failing** — this is its own task, not a footnote
3. Schemas → queries → routers → registration
4. Contracts regenerated and committed
5. Tests re-run and confirmed passing
6. Portal surfaces
7. Component and browser tests

### Parallel opportunities

- Setup: T002–T006 all in parallel after T001
- Phase 2B: T012–T015 in parallel; then T017, T018, T022 in parallel
- Phase 2D: T029–T034 in parallel; then T036, T037, T039, T040 in parallel
- Phase 2E: T044–T047 in parallel; then T051, T052 in parallel
- Phase 2F: T055 and T056 in parallel with each other and with anything in 2E
- US1: T057–T058 in parallel; T066, T067, T071, T072, T075, T078 in parallel
- US2: T081–T082 in parallel; T084 and T090 in parallel
- Polish: T111–T116 all in parallel
- With multiple people, US2 / US3 / US4 can proceed in parallel once Phase 2 closes —
  but note that T092, T093, T101, and T110 all edit `apps/web/e2e/portal.spec.ts` and
  `apps/web/lib/pages.ts`, so those four must be serialised regardless of who writes them

---

## Parallel Example: Phase 2D

```bash
# Write all five failing tests together, then run them once:
Task: "tests/unit/test_passwords.py"
Task: "tests/unit/test_tokens.py"
Task: "tests/security/test_login_enumeration.py"
Task: "tests/security/test_session_lifecycle.py"
Task: "tests/integration/test_session_expiry.py"

# Then implement the independent modules together:
Task: "apps/api/src/eaios_api/auth/passwords.py"
Task: "apps/api/src/eaios_api/auth/tokens.py"
Task: "apps/api/src/eaios_api/auth/login_bounds.py"
Task: "apps/api/src/eaios_api/auth/schemas.py"
```

---

## Implementation Strategy

### MVP first (Phase 1 + Phase 2 + User Story 1)

1. Phase 1: Setup
2. Phase 2: Foundational — the long one, and the one the whole feature rests on
3. Phase 3: User Story 1
4. **STOP and VALIDATE**: quickstart scenarios 1, 2, 8, 10, and 11
5. Demo: a seeded employee signs in, sees their own record, signs out, and the replayed
   credential is refused

### Incremental delivery

1. Setup + Foundational → the API authenticates and decides, exposing nothing
2. + US1 → the vertical slice, end to end (**MVP**)
3. + US2 → the manager demonstration and the flagship salary denial
4. + US3 → authenticated cross-tenant isolation
5. + US4 → role-aware navigation and the designed denial states
6. + Polish → CI, documentation, and the recorded leakage number

Each step adds value without breaking the previous one, and every step after Foundational
is demonstrable on its own.

---

## Notes

- **Every "run and record the failure" task is real work.** Principle VIII's cycle is write
  → *watch fail* → implement. Skipping the middle step is how this project has repeatedly
  produced checks that could never fail: an assertion that reduced to `11 == 11`, a
  contract test for a response body the server never sent, an error state whose retry
  control no caller ever wired, and 1,487 automated checks that had never once run.
- Anti-vacuity guards are named inline in the test tasks rather than left to judgement.
  [research.md](research.md) §R15 carries the full table.
- `[P]` means different files with no dependency on an incomplete task.
- Commit after each task or logical group; stop at any checkpoint to validate a story.
- Windows: App Control blocks the virtualenv's `.exe` shims — run `uv run python -m pytest`
  rather than `uv run pytest`.
