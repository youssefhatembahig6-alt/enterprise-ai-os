---

description: "Task list for Foundation — Monorepo, Local Environment & Deterministic Two-Tenant Dataset"
---

# Tasks: Foundation — Monorepo, Local Environment & Deterministic Two-Tenant Dataset

**Input**: Design documents from `specs/001-foundation-tenant-seed/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: **MANDATORY and test-first.** Constitution Principle VIII (NON-NEGOTIABLE) requires TDD for
authorization, tenant isolation, database integrity, and critical workflows; the spec independently
requires the verification suite in FR-044–FR-047. Every test task below must be written and observed
**failing** before its implementation task begins.

**Organization**: Grouped by user story so each is independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1–US5 from spec.md
- Exact file paths are included in every task

## Path Conventions

Monorepo per [plan.md](./plan.md): `apps/api`, `apps/web`, `packages/core`, `packages/ui`,
`packages/contracts`, `services/worker`, `scripts/seed`, `infrastructure/`, `tests/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Monorepo skeleton and toolchain. No behavior yet.

- [x] T001 Create the monorepo directory skeleton at repo root per plan.md (`apps/`, `packages/`, `services/`, `scripts/`, `infrastructure/`, `tests/{unit,integration,security,e2e}/`)
- [x] T002 [P] Create `.gitattributes` at repo root containing `* text eol=lf` plus binary exclusions — **do this before any file generation work**; CRLF translation silently breaks byte-identical output (research R4)
- [x] T003 [P] Create root `pyproject.toml` declaring the uv workspace with members `packages/core`, `apps/api`, `services/worker`, `scripts/seed`, and pinned Python 3.12
- [x] T004 [P] Create `pnpm-workspace.yaml` and root `package.json` declaring workspaces `apps/web`, `packages/ui`, `packages/contracts`
- [x] T005 [P] Create `.gitignore` at repo root (Python, Node, Docker volumes, `.env`, generated artifacts)
- [x] T006 [P] Create `.editorconfig` at repo root enforcing LF, UTF-8, final newline
- [x] T007 [P] Configure ruff and mypy in root `pyproject.toml` with strict settings for `packages/core` and `scripts/seed`
- [x] T008 [P] Create `tsconfig.base.json`, ESLint, and Prettier configs at repo root
- [x] T009 [P] Scaffold `packages/core/pyproject.toml` and `packages/core/src/eaios_core/__init__.py`
- [x] T010 [P] Scaffold `apps/api/pyproject.toml` and `apps/api/src/eaios_api/__init__.py` with a `packages/core` path dependency
- [x] T011 [P] Scaffold `services/worker/pyproject.toml` and `services/worker/src/eaios_worker/__init__.py` with a `packages/core` path dependency
- [x] T012 [P] Scaffold `scripts/seed/pyproject.toml` and `scripts/seed/src/eaios_seed/__init__.py` with a `packages/core` path dependency and an `eaios-seed` console entry point
- [x] T013 [P] Scaffold `apps/web` with Vite + React 18 + TypeScript (`apps/web/package.json`, `vite.config.ts`, `src/main.tsx`)
- [x] T014 [P] Scaffold `packages/ui/package.json` and `packages/contracts/package.json`
- [x] T015 [P] Create `Makefile` at repo root with stub targets `up`, `down`, `seed`, `reset`, `verify`, `test`
- [x] T016 [P] Create `pytest.ini`/`pyproject` pytest config registering markers `unit`, `integration`, `security`, `e2e` and the `tests/` rootdir
- [x] T017 Create `.github/workflows/ci.yml` with an OS matrix (ubuntu, macos, windows) — the matrix is what actually proves SC-002's cross-machine determinism claim

**Checkpoint**: `uv sync` and `pnpm install` both succeed; no application code exists yet.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared primitives, configuration, and the database schema. Every user story depends on this phase.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

### Tests for foundational primitives (write FIRST, observe FAILING) ⚠️

- [x] T018 [P] Write failing unit test for deterministic ID derivation in `tests/unit/test_ids.py` — assert a frozen table of known `(entity, company, natural_key) → UUID` values so a namespace or key-format change fails loudly (research R1)
- [x] T019 [P] Write failing unit test for the pinned clock in `tests/unit/test_clock.py` — assert `reference_date()` is `2026-06-30` and that offset helpers are timezone-independent
- [x] T020 [P] Write failing AST-scan test in `tests/unit/test_no_wallclock.py` — fail if `datetime.now`, `datetime.utcnow`, `date.today`, or `time.time` appears anywhere under `packages/core/` or `scripts/seed/`
- [x] T021 [P] Write failing unit test for fingerprint order-independence in `tests/unit/test_fingerprint.py` — the same rows in a different order must produce an identical family digest (research R5)
- [x] T022 [P] Write failing unit test for key builders in `tests/unit/test_keys.py` — assert object-storage and cache keys for two companies can never collide and always carry the tenant prefix (FR-039, FR-040)
- [x] T023 [P] Write failing unit test for the classification enum in `tests/unit/test_classification.py` — exactly four levels, unknown values rejected (FR-010a, FR-010b)
- [x] T024 [P] Write failing unit test for the global-entity allowlist in `tests/unit/test_tenancy.py` — assert the allowlist is a closed set of exactly four entities (FR-009a)

### Core primitives

- [x] T025 [P] Implement the four-level classification enum in `packages/core/src/eaios_core/classification.py`
- [x] T026 [P] Implement the pinned reference clock in `packages/core/src/eaios_core/clock.py` — expose only `reference_date()` and offset helpers; no wall-clock access
- [x] T027 [P] Implement deterministic UUIDv5 derivation in `packages/core/src/eaios_core/ids.py` per research R1 (root namespace → dataset namespace → entity URN)
- [x] T028 [P] Implement object-storage and cache key builders in `packages/core/src/eaios_core/keys.py` per FR-039/FR-040
- [x] T029 [P] Implement canonical serialization and the two-level digest in `packages/core/src/eaios_core/fingerprint.py` per research R5
- [x] T030 [P] Implement the global-entity allowlist and tenant-scoping helpers in `packages/core/src/eaios_core/tenancy.py` per FR-009a

### Configuration, logging, and clients

- [x] T031 Implement pydantic-settings configuration in `apps/api/src/eaios_api/settings.py` covering all four stores, with documented local defaults and no secrets
- [x] T032 [P] Implement structlog JSON logging in `apps/api/src/eaios_api/logging.py` with `request_id` binding and a `company_id` binding hook reserved for the auth feature
- [x] T033 Implement the SQLAlchemy engine, session factory, and the `app.company_id` RLS session context manager in `apps/api/src/eaios_api/db/session.py` (research R6)
- [x] T034 [P] Implement Redis, Qdrant, and MinIO client factories in `packages/core/src/eaios_core/clients/{redis,qdrant,minio}.py`

### Data model

- [x] T035 [P] Implement global-table models (`permissions`, `platform_administrators`, `dataset_manifest`) in `packages/core/src/eaios_core/models/global_.py` per data-model.md §1
- [x] T036 [P] Implement organization models (`companies`, `offices`, `departments`, `roles`, `role_permissions`, `users`, `user_roles`) in `packages/core/src/eaios_core/models/organization.py` per data-model.md §2
- [x] T037 [P] Implement HR models (`employee_profiles`, `leave_balances`, `leave_requests`, `attendance_records`, `training_records`, `performance_reviews`) in `packages/core/src/eaios_core/models/hr.py` per data-model.md §3
- [x] T038 [P] Implement sales and finance models (`customers`, `products`, `orders`, `order_lines`, `invoices`, `sales_targets`, `expenses`, `budgets`, `monthly_revenue`) in `packages/core/src/eaios_core/models/sales.py` per data-model.md §4
- [x] T039 [P] Implement legal and document models (`documents`, `document_acl`, `contracts`, `policy_documents`) in `packages/core/src/eaios_core/models/legal.py` per data-model.md §5
- [x] T040 [P] Implement public-content models (`services`, `public_products`, `leadership_profiles`, `news_items`, `vacancies`) in `packages/core/src/eaios_core/models/public.py` per data-model.md §6
- [x] T041 [P] Implement platform models (`audit_logs`, `job_records`) in `packages/core/src/eaios_core/models/platform.py` per data-model.md §7

### Migrations

- [x] T042 Initialize Alembic in `apps/api/alembic/` with `env.py` wired to the `packages/core` metadata and the `eaios_owner` role
- [x] T043 Write failing integration test for migration reversibility in `tests/integration/test_migrations.py` — upgrade to head, downgrade to base, upgrade again, assert schema identity (FR-007, FR-008)
- [x] T044 Create the initial schema migration in `apps/api/alembic/versions/0001_initial_schema.py` — all tables, the `classification_level` enum, natural-key unique constraints, check constraints, and the append-only trigger on `audit_logs`
- [x] T045 Write failing security test in `tests/security/test_tenant_columns.py` — assert every table not on the global allowlist has a non-nullable `company_id` (FR-009, FR-009a)
- [x] T046 Add the `company_id` non-null constraints and foreign keys required to make T045 pass, in `apps/api/alembic/versions/0001_initial_schema.py`

**Checkpoint**: Schema migrates up and down cleanly; all foundational unit tests pass; no data exists.

---

## Phase 3: User Story 1 — One-Command Local Environment (Priority: P1) 🎯 MVP

**Goal**: A clean checkout reaches a fully healthy stack with `make up`.

**Independent Test**: On a machine with no project state, run `make up` and confirm all eight services report healthy and `/health/ready` names all four dependencies as up.

### Tests for User Story 1 ⚠️

- [x] T047 [P] [US1] Write failing contract test in `tests/integration/test_health_contract.py` — validate `/health/live`, `/health/ready`, and `/dataset/manifest` responses against `contracts/health-api.yaml`
- [x] T048 [P] [US1] Write failing integration test in `tests/integration/test_health_degraded.py` — with one dependency stopped, `/health/ready` returns 503 and names **only** the failing dependency, with the other three still reported up (FR-003)
- [x] T049 [P] [US1] Write failing e2e test in `tests/e2e/test_clean_startup.py` — from a torn-down state, `make up` reaches all-healthy within the SC-001 budget

### Infrastructure for User Story 1

- [x] T050 [P] [US1] Create `infrastructure/.env.example` with documented non-secret local defaults for all four stores (FR-005, FR-006)
- [x] T051 [P] [US1] Create `infrastructure/postgres/init/01-roles.sql` creating `eaios_owner` (schema owner, runs migrations and seed) and `eaios_app` (non-owner, RLS-enforced) per research R6
- [x] T052 [P] [US1] Create `infrastructure/minio/bootstrap.sh` creating the `eaios` bucket and denying anonymous access
- [x] T053 [P] [US1] Create `infrastructure/qdrant/collections.json` declaring collection names, vector config, and the `company_id` payload index (research R10)
- [x] T054 [P] [US1] Create `apps/api/Dockerfile` and `services/worker/Dockerfile` with `LANG=C.UTF-8` pinned
- [x] T055 [P] [US1] Create `scripts/seed/Dockerfile` and `apps/web/Dockerfile` with `LANG=C.UTF-8` pinned
- [x] T056 [US1] Create `infrastructure/docker-compose.yml` with all eight services (postgres, redis, qdrant, minio, minio-init, api, worker, web), named volumes, healthchecks, and `depends_on` conditions (FR-002)
- [x] T057 [US1] Create `infrastructure/docker-compose.override.yml` with local development conveniences (source mounts, hot reload)

### Application for User Story 1

- [x] T058 [P] [US1] Implement Pydantic response models for health and manifest in `apps/api/src/eaios_api/health/schemas.py`, matching `contracts/health-api.yaml`
- [x] T059 [US1] Implement `/health/live` and `/health/ready` in `apps/api/src/eaios_api/health/router.py` — concurrent per-dependency checks with independent timeouts, no credentials in responses (FR-003)
- [x] T060 [US1] Implement `/dataset/manifest` in `apps/api/src/eaios_api/health/manifest_router.py`, returning 404 when unseeded and `is_complete: false` when `completed_at` is null
- [x] T061 [US1] Implement the FastAPI app factory and lifespan in `apps/api/src/eaios_api/main.py`, registering routers and structured logging
- [x] T062 [P] [US1] Implement the Celery app and a worker health task in `services/worker/src/eaios_worker/celery_app.py` and `health.py`
- [x] T063 [P] [US1] Implement the web status page in `apps/web/src/pages/StatusPage.tsx` and the API client in `apps/web/src/api/health.ts` — status shell only, no product UI (decision D1)
- [x] T064 [US1] Generate TypeScript API types into `packages/contracts/src/generated/api.ts` from the FastAPI OpenAPI schema via `openapi-typescript`, and wire the generation step into the Makefile
- [x] T065 [US1] Wire `make up` and `make down` in `Makefile` — build, start, run migrations to head, and block until `/health/ready` returns 200 (FR-002, FR-004)

**Checkpoint**: `make up` from a clean checkout produces a healthy stack. US1 is independently demonstrable — this is the MVP.

---

## Phase 4: User Story 2 — Deterministic Seed From An Empty Environment (Priority: P2)

**Goal**: `make seed` populates an empty environment; two runs anywhere produce an identical fingerprint.

**Independent Test**: Seed twice from empty, comparing `root_fingerprint`; both runs match, and a second machine reproduces the same value.

### Tests for User Story 2 ⚠️

- [x] T066 [P] [US2] Write failing e2e determinism test in `tests/e2e/test_determinism.py` — seed, capture fingerprint, reset, seed again, assert identical `root_fingerprint` (FR-011, SC-002)
- [x] T067 [P] [US2] Write failing integration test in `tests/integration/test_seed_refusal.py` — seeding a non-empty environment exits `2`, modifies nothing, and names `make reset` (FR-014)
- [x] T068 [P] [US2] Write failing integration test in `tests/integration/test_seed_incomplete.py` — an interrupted seed leaves `completed_at` null and `verify` reports *incomplete*, not *mismatch* (FR-014b, FR-014c)
- [x] T069 [P] [US2] Write failing unit test in `tests/unit/test_document_bytes.py` — a fixture document renders to an exact SHA-256, with LF newlines, UTF-8, and no BOM (FR-032, research R4)
- [x] T070 [P] [US2] Write failing integration test in `tests/integration/test_manifest_schema.py` — the emitted manifest validates against `contracts/dataset-manifest.schema.json`
- [x] T071 [P] [US2] Write failing integration test in `tests/integration/test_volume_targets.py` — realized counts fall within ±10% of the FR-020b profile targets for both companies

### Generator infrastructure

- [x] T072 [US2] Implement seed configuration in `scripts/seed/src/eaios_seed/config.py` — root seed, reference date, `full`/`smoke` volume profiles from FR-020b
- [x] T073 [US2] Implement sub-seed derivation and the seeded Faker factory in `scripts/seed/src/eaios_seed/rng.py` per research R3, with a pinned Faker version and explicit locale list
- [x] T074 [P] [US2] Implement the committed per-country working-calendar table (EG/AE weekends and holidays) in `scripts/seed/src/eaios_seed/calendars.py` — no external calendar service (FR-012)

### Entity generators

- [x] T075 [US2] Implement the organization generator in `scripts/seed/src/eaios_seed/generators/organization.py` — companies, offices, departments, roles, permissions, role_permissions, users, user_roles, and the manager hierarchy (FR-018–FR-022, FR-025, FR-025a)
- [x] T076 [US2] Implement the fixed persona set in `scripts/seed/src/eaios_seed/generators/personas.py` — all ten `persona_key` values with stable IDs per data-model.md §2 (FR-025b, FR-025c)
- [x] T077 [P] [US2] Implement the HR generator in `scripts/seed/src/eaios_seed/generators/hr.py` — profiles, leave balances and requests, attendance capped at 6 months, training, reviews (FR-026, FR-020a)
- [x] T078 [P] [US2] Implement the sales and finance generator in `scripts/seed/src/eaios_seed/generators/sales.py` — customers, products, orders, order lines, invoices, targets, expenses, budgets, monthly revenue, with a deterministic seasonal curve (FR-027, FR-020c)
- [x] T079 [P] [US2] Implement the legal generator in `scripts/seed/src/eaios_seed/generators/legal.py` — contracts, supplier agreements, NDAs, employment templates, including the matched comparison pair with differing notice periods and liability caps (FR-028, FR-028a)
- [x] T080 [P] [US2] Implement the policy generator in `scripts/seed/src/eaios_seed/generators/policies.py` — eight policy types per company, each with machine-readable `stated_values` (FR-029)
- [x] T081 [US2] Implement Delta Retail marker phrases in `scripts/seed/src/eaios_seed/generators/markers.py` — distinctive, greppable strings appearing nowhere in NileTech content (FR-023)

### Document rendering and loading

- [x] T082 [US2] Implement deterministic document rendering in `scripts/seed/src/eaios_seed/documents/renderer.py` — Jinja2 templates, forced `newline="\n"`, UTF-8, no BOM, quantized decimals, no generation timestamps (FR-032, research R4)
- [x] T083 [P] [US2] Create the document templates in `scripts/seed/src/eaios_seed/documents/templates/` for all eight policy types plus contract and public-content bodies
- [x] T084 [P] [US2] Implement the PostgreSQL loader in `scripts/seed/src/eaios_seed/loaders/postgres.py` — single transaction, insertion via `eaios_owner`
- [x] T085 [P] [US2] Implement the object-storage loader in `scripts/seed/src/eaios_seed/loaders/minio.py` — writes files under `{company}/{classification}/{type}/` and records `content_sha256` (FR-031, FR-039)
- [x] T086 [P] [US2] Implement Qdrant provisioning in `scripts/seed/src/eaios_seed/loaders/qdrant.py` — create collections with the `company_id` payload index, leave them empty (decision D2, FR-041)
- [x] T087 [P] [US2] Implement Redis namespace provisioning in `scripts/seed/src/eaios_seed/loaders/redis.py` (FR-040)

### Manifest and CLI

- [x] T088 [US2] Implement manifest construction and the completion marker in `scripts/seed/src/eaios_seed/manifest.py` — counts, family digests, root fingerprint, `completed_at` written last (FR-015, FR-016, FR-014b)
- [x] T089 [US2] Implement the emptiness pre-flight check across all four stores in `scripts/seed/src/eaios_seed/preflight.py` (FR-014)
- [x] T090 [US2] Implement the `seed` command in `scripts/seed/src/eaios_seed/cli.py` following the ordering in `contracts/seed-cli.md` §seed
- [x] T091 [US2] Implement the `reset` command in `scripts/seed/src/eaios_seed/cli.py` with all three safety gates — `--yes`, local-host check, `EAIOS_ENV` check (FR-014a, Constitution VII)
- [x] T092 [US2] Implement the `verify` and `fingerprint` commands in `scripts/seed/src/eaios_seed/cli.py`, reporting per-family divergence by name (FR-017)
- [x] T093 [US2] Write `SEED` and `RESET` audit entries for both companies in `scripts/seed/src/eaios_seed/audit.py` (FR-043, Constitution X)
- [x] T094 [US2] Wire `make seed`, `make reset`, and `make verify` in `Makefile` (FR-004)

**Checkpoint**: A full seed runs from empty, twice, producing an identical fingerprint. US1 and US2 both work independently.

---

## Phase 5: User Story 3 — Two Structurally Isolated Tenants (Priority: P3)

**Goal**: Every artifact is tenant-attributed and no probe crosses the boundary in any store.

**Independent Test**: Run the structural audit and the cross-store probe in both directions; zero violations and zero cross-tenant results.

### Tests for User Story 3 ⚠️

- [x] T095 [P] [US3] Write failing security test in `tests/security/test_rls.py` — as `eaios_app` with `app.company_id` set to NileTech, Delta rows are invisible; set to Delta, NileTech rows are invisible; **with the variable unset, zero rows return** (Constitution I, research R6)
- [x] T096 [P] [US3] Write failing security test in `tests/security/test_cross_tenant_refs.py` — no foreign key resolves to an entity of a different company (FR-024, FR-024a)
- [x] T097 [P] [US3] Write failing security test in `tests/security/test_cross_tenant_probe.py` — search Delta marker phrases scoped to NileTech and the reverse, across PostgreSQL, object storage, and cache; zero results (FR-045)
- [x] T098 [P] [US3] Write failing security test in `tests/security/test_global_allowlist.py` — exactly the four allowlisted entities lack `company_id`, and none of them has gained one (FR-009a, FR-044, SC-003)
- [x] T099 [P] [US3] Write failing security test in `tests/security/test_storage_namespacing.py` — every object key and every cache key begins with a company namespace (FR-039, FR-040)
- [x] T100 [P] [US3] Write failing security test in `tests/security/test_vector_isolation.py` — Qdrant collections exist, carry the `company_id` payload index, and are empty (decision D2, FR-041)
- [x] T101 [P] [US3] Write failing security test in `tests/security/test_scenario_readiness.py` — all eight blueprint access-control scenarios have the records needed to express them (FR-047a, SC-013)

### Implementation for User Story 3

- [x] T102 [US3] Create the RLS migration in `apps/api/alembic/versions/0002_row_level_security.py` — `ENABLE` + `FORCE ROW LEVEL SECURITY` and a `company_id = current_setting('app.company_id', true)::uuid` policy on every tenant-owned table, plus grants to `eaios_app`
- [x] T103 [US3] Implement the structural audit in `scripts/seed/src/eaios_seed/audit_checks/structural.py` — unattributed rows, allowlist violations in both directions, cross-tenant references, referential integrity (FR-044)
- [x] T104 [US3] Wire the structural audit into `verify` in `scripts/seed/src/eaios_seed/cli.py`, exiting `3` on any violation
- [x] T105 [US3] Implement the cross-store probe helper in `scripts/seed/src/eaios_seed/audit_checks/probe.py` (FR-045)
- [x] T106 [US3] Add job-record tenant attribution in `services/worker/src/eaios_worker/tasks/base.py` — every task records the `company_id` of the work it performs (FR-042)

**Checkpoint**: Isolation is enforced at the database level and verified across all four stores.

---

## Phase 6: User Story 4 — A Coherent, Believable Enterprise (Priority: P4)

**Goal**: The generated data reads as one company — policies match records, the org chart is valid, arithmetic ties out.

**Independent Test**: Run the coherence, hierarchy, and date-window checks; zero violations.

### Tests for User Story 4 ⚠️

- [x] T107 [P] [US4] Write failing integration test in `tests/integration/test_coherence.py` — leave policy `stated_values` equals `leave_balances.entitlement_days` for every user, per country and employment type (FR-035, SC-007)
- [x] T108 [P] [US4] Write failing integration test in `tests/integration/test_invoice_math.py` — `line_total = quantity × unit_price`, `subtotal = Σ line_total`, `total = subtotal + tax`, `invoice.amount = order.total`, and `monthly_revenue` equals aggregation over orders (FR-038)
- [x] T109 [P] [US4] Write failing integration test in `tests/integration/test_org_hierarchy.py` — exactly one manager-less user per company, no cycles, department heads belong to their department, every user with reports holds the Manager role (FR-034, FR-025a, SC-005)
- [x] T110 [P] [US4] Write failing integration test in `tests/integration/test_date_windows.py` — all dates within the 24-month window, attendance within 6 months, no child predating its parent (FR-037, FR-020a)
- [x] T111 [P] [US4] Write failing integration test in `tests/integration/test_referential_integrity.py` — zero orphaned references across every relationship (FR-033, SC-006)
- [x] T112 [P] [US4] Write failing integration test in `tests/integration/test_document_references.py` — generated documents reference only departments, offices, countries, roles, and people that exist in the same company (FR-036)

### Implementation for User Story 4

- [x] T113 [US4] Bind policy `stated_values` to HR generation in `scripts/seed/src/eaios_seed/generators/hr.py` so entitlements are derived from the policy rather than generated independently (FR-035)
- [x] T114 [US4] Enforce exact decimal arithmetic and derive invoices and `monthly_revenue` from order lines in `scripts/seed/src/eaios_seed/generators/sales.py` (FR-038)
- [x] T115 [US4] Enforce hierarchy invariants during generation in `scripts/seed/src/eaios_seed/generators/organization.py` — single root, acyclic, department heads in-department (FR-034)
- [x] T116 [US4] Constrain every generated date to the reference window and to parent-record bounds in `scripts/seed/src/eaios_seed/generators/` (FR-037)
- [x] T117 [US4] Implement the coherence check suite in `scripts/seed/src/eaios_seed/audit_checks/coherence.py` and wire it into `verify` (FR-046)

**Checkpoint**: The dataset is internally consistent and defensible under inspection.

---

## Phase 7: User Story 5 — Public Company Identity Content (Priority: P5)

**Goal**: Public-facing content exists for the tenants, clearly separated from internal material.

**Independent Test**: All public content is present, marked `PUBLIC`, and contains no sensitive values.

### Tests for User Story 5 ⚠️

- [x] T118 [P] [US5] Write failing security test in `tests/security/test_public_content.py` — no `PUBLIC` row contains salary figures, contract terms, internal financial data, or non-executive contact details (SC-011)
- [x] T119 [P] [US5] Write failing integration test in `tests/integration/test_public_content_completeness.py` — services, public products, leadership profiles, news, vacancies, and office information all exist and are non-placeholder (FR-030, SC-010)
- [x] T120 [P] [US5] Write failing integration test in `tests/integration/test_leadership_profiles.py` — each profile maps to a real Executive Management employee of the same company and exposes only public-appropriate fields (FR-030)
- [x] T121 [P] [US5] Write failing integration test in `tests/integration/test_classification_coverage.py` — both `PUBLIC` and `RESTRICTED` are present and non-empty for both companies, and every classified item carries exactly one of the four levels (FR-010c, SC-015)

### Implementation for User Story 5

- [x] T122 [US5] Implement the public-content generator in `scripts/seed/src/eaios_seed/generators/public.py` — services, public products, leadership profiles, news items, vacancies, office information (FR-030)
- [x] T123 [US5] Apply the document-ownership convention in `scripts/seed/src/eaios_seed/generators/ownership.py` — including the Executive Management fallback for companies without a Legal department (FR-031a)
- [x] T124 [US5] Implement the public-content safety scan in `scripts/seed/src/eaios_seed/audit_checks/public_safety.py` and wire it into `verify` (SC-011)

**Checkpoint**: All five user stories are independently functional.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [x] T125 [P] Write `README.md` at repo root documenting prerequisites, `make up`, `make reset`, and the Windows `core.autocrlf` requirement
- [x] T126 [P] Write `docs/personas.md` documenting all ten personas with company, department, role, country, and manager (FR-025b)
- [x] T127 [P] Write `docs/dataset.md` documenting the seed value, reference date, volume profile, and Delta Retail's intentional absences — no Engineering, no Legal department (FR-022)
- [x] T128 [P] Document the fingerprint exclusion list and its rationale in `docs/determinism.md` (FR-015a)
- [x] T129 Pin a known-good `root_fingerprint` in `tests/e2e/expected_fingerprint.txt` and assert against it in CI — without this, `verify` only proves self-consistency and cannot detect drift introduced by a code change
- [x] T130 Wire the full suite into `.github/workflows/ci.yml` across the OS matrix — unit → integration → security → e2e, with any failure blocking the change (FR-047, SC-012)
- [x] T131 [P] Add seed duration reporting against the SC-008 budget in `scripts/seed/src/eaios_seed/manifest.py`
- [x] T132 [P] Add structured-log tenant-leakage review to `tests/security/test_log_safety.py` — log output must not contain cross-tenant content
- [x] T133 Run the full `quickstart.md` validation end to end and record the results

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies
- **Foundational (Phase 2)**: depends on Setup — **blocks every user story**
- **US1 (Phase 3)**: depends on Foundational
- **US2 (Phase 4)**: depends on Foundational; needs US1's Compose stack running to execute against
- **US3 (Phase 5)**: depends on Foundational; needs US2's seeded data for the probe to be meaningful
- **US4 (Phase 6)**: depends on US2 (data must exist before coherence can be enforced)
- **US5 (Phase 7)**: depends on US2 (extends the generator)
- **Polish (Phase 8)**: depends on all desired stories

### User Story Dependencies

Unlike a typical feature, these stories form a chain rather than a fan-out — each later story operates
on the artifact the previous one produces:

```text
Setup → Foundational → US1 (environment)
                          ↓
                       US2 (seed) ─┬→ US3 (isolation)
                                   ├→ US4 (coherence)
                                   └→ US5 (public content)
```

US3, US4, and US5 are mutually independent and can proceed in parallel once US2 lands.

### Within Each User Story

- Tests are written and observed **failing** before implementation (Constitution VIII)
- Models before generators; generators before loaders; loaders before CLI
- Story complete and independently demonstrable before moving on

### Parallel Opportunities

- All Setup tasks marked `[P]` (T002–T016)
- All foundational primitive tests (T018–T024) — then all primitive implementations (T025–T030)
- All model modules (T035–T041) — separate files, no shared state
- All US1 infrastructure files (T050–T055)
- All entity generators after the organization generator lands (T077–T080)
- All loaders (T084–T087)
- All US3 security tests (T095–T101)
- All US4 coherence tests (T107–T112)
- US3, US4, and US5 as whole phases, by different team members

---

## Parallel Example: Foundational primitives

```bash
# Write all failing primitive tests together:
Task: "Deterministic ID test in tests/unit/test_ids.py"
Task: "Pinned clock test in tests/unit/test_clock.py"
Task: "Wall-clock AST scan in tests/unit/test_no_wallclock.py"
Task: "Fingerprint order-independence test in tests/unit/test_fingerprint.py"
Task: "Key-builder collision test in tests/unit/test_keys.py"

# Then implement all primitives together:
Task: "Implement packages/core/src/eaios_core/ids.py"
Task: "Implement packages/core/src/eaios_core/clock.py"
Task: "Implement packages/core/src/eaios_core/fingerprint.py"
Task: "Implement packages/core/src/eaios_core/keys.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1: Setup
2. Phase 2: Foundational — **blocks everything**
3. Phase 3: US1
4. **STOP and VALIDATE**: `make up` on a teammate's machine, unaided
5. This alone unblocks all five team roles and is worth demonstrating

### Incremental Delivery

1. Setup + Foundational → schema exists, primitives proven
2. US1 → environment runs (MVP) → demo
3. US2 → deterministic dataset exists → demo the fingerprint match across two machines
4. US3 → isolation enforced and proven → this is the security story for the defense
5. US4 → data becomes defensible under inspection
6. US5 → public identity content complete
7. Polish → documentation, CI matrix, pinned fingerprint

### Parallel Team Strategy

Once Foundational completes:

- **Backend Engineer**: US1 (Compose, health, roles) then US3 (RLS, isolation)
- **Data Engineer**: US2 (generators, loaders, manifest) then US4 (coherence)
- **Frontend Engineer**: US1 status shell, then US5 public content generation
- **AI Engineers**: foundational primitives (ids, fingerprint) — these are the highest-risk components and benefit from a second pair of eyes

---

## Notes

- `[P]` tasks touch different files and have no incomplete dependencies
- Verify every test fails before implementing against it — a test that passes immediately is testing nothing
- Commit after each task or logical group
- **T002 (`.gitattributes`) must land before any generation work.** If CRLF translation is active when documents are first generated, the fingerprint diverges on Windows and the cause is genuinely hard to see
- **T129 (pinned fingerprint) is not optional polish.** Without a committed known-good value, `verify` only proves the dataset matches its own manifest — it cannot detect that a code change altered the dataset

---

## Phase 9: Convergence

*Appended 2026-08-01 by `/speckit-converge`. These are gaps that no existing task covers —
Phases 4–8 remain tracked above and are not duplicated here. Ordered CRITICAL first.*

- [x] T134 **CRITICAL** Write a unit test for the RLS tenant session scope in `tests/unit/test_tenant_scope.py` — assert `eaios_core.db.tenant_scope` sets `app.company_id`, clears it on exit, and clears it when the body raises, so a pooled session cannot carry one request's tenant into the next per Constitution VIII + FR-009d (missing)
- [x] T135 Make the determinism comparison genuinely cross-platform in `.github/workflows/ci.yml` — the `stack` job that computes the fingerprint currently runs on ubuntu only, so the cross-machine claim cannot fail; run the seed and fingerprint on a second platform and compare the two values per FR-047b, SC-002 (partial)
- [x] T136 Generate `packages/contracts/src/generated/api.ts` from the running API's OpenAPI schema and replace the hand-declared duplicates in `apps/web/src/api/health.ts` with imports from `@eaios/contracts` per Mandatory Surfaces (typed contracts); note T064 was marked complete but produced no artifact (partial)
- [x] T137 Assert NileTech's named composition in `tests/integration/test_niletech_composition.py` — the eight departments (Engineering, HR, Sales, Finance, Legal, Customer Support, Operations, Executive Management) and the three offices (Cairo, Alexandria, Dubai) by name, not merely by count per FR-018, FR-019 (missing)
- [x] T138 Assert Delta Retail's documented composition in `tests/integration/test_delta_composition.py` — five departments present, and Engineering and Legal deliberately absent, so the absence is provably intentional rather than a generation gap per FR-022 (missing)
- [x] T139 Reconcile the `timeout` dependency status in `packages/core/src/eaios_core/clients/stores.py` — the contract documents `up`/`down`/`timeout` but the probes can only ever return `up` or `down`, leaving a documented value unreachable; either distinguish timeout from failure or remove it from `contracts/health-api.yaml` per FR-003 (contradicts)
- [x] T140 Establish the documentation set as a named artifact in `docs/README.md` and make every "documented" reference in the spec resolve to a location within it — startup and reset commands, environment configuration surface, persona reference, Delta's intentional absences, fingerprint exclusion list, platform caveats per FR-048 (partial)
- [x] T141 Extend `tests/integration/test_public_content_completeness.py` to assert public content exists for **both** companies, not only NileTech — FR-030 was amended during checklist remediation and the volume table allocates 20 public items to Delta Retail per FR-030, FR-010c (partial)
- [x] T142 Decide and record whether the synthetic code repository is in scope for this feature — the blueprint specifies one (authentication, leave, reporting, notification modules) enabling the code-aware RAG demo, but no functional requirement or task covers it; generate it in `scripts/seed/src/eaios_seed/generators/code_repo.py` or record it in the carry-forward list per Blueprint §Generated dataset, checklists/data.md CHK011 (missing)
- [x] T143 Verify the emitted schema matches `data-model.md` in `tests/integration/test_schema_matches_model.py` — migration 0001 builds the schema via `Base.metadata.create_all` rather than explicit DDL, so assert every documented check constraint, unique constraint, and enum is actually present per plan: migrations (partial)
- [x] T144 Run `mypy --strict` across `packages/core/src`, `apps/api/src`, `services/worker/src`, `scripts/seed/src` and make it pass — it is wired into `make lint` and CI but has never been executed per plan: tooling (partial)
- [x] T145 Add settings tests in `tests/unit/test_settings.py` — assert local defaults contain no production-shaped secrets, that `SecretStr` values never appear in `repr`, and that `is_local` correctly gates the destructive reset path per FR-006, FR-014a (missing)
- [x] T146 Generate and commit `pnpm-lock.yaml` at the repo root — `uv.lock` is committed but the TypeScript ecosystem has no lockfile, and the plan requires one committed lockfile per ecosystem per FR-012b, plan R8 (partial)
- [x] T147 Reconcile the Docker service count across `plan.md`, `quickstart.md`, and the task descriptions — `infrastructure/docker-compose.yml` defines nine services (postgres, redis, qdrant, minio, minio-init, api, worker, web, seed) while the documents all say eight per FR-002 (contradicts)
- [x] T148 Record a decision on tenant-identifier enumerability in `docs/determinism.md` or the spec's assumptions — slugs `niletech` and `delta-retail` are predictable and appear in object-storage and cache keys; confirm that is acceptable for a demo dataset or switch to opaque identifiers per checklists/isolation.md CHK012 (missing)
- [x] T149 Cover `infrastructure/wait-for-healthy.sh` with a test or fold it into T065's acceptance — it is load-bearing for `make up` but was not called for by any task and nothing exercises its unhealthy and timeout branches (unrequested)
- [x] T150 Remove the duplicated migration step from the `reset` target in `Makefile` — it runs `alembic upgrade head` before `eaios-seed reset --yes`, which the CLI contract states already re-runs migrations per contracts/seed-cli.md §reset (partial)

---

## Phase 10: Convergence

*Appended 2026-08-01 by a second `/speckit-converge` run, after all 150 prior tasks were
complete. The Python side verified clean (642 tests, ruff, mypy). Every finding below is in
the TypeScript workspace or in behaviour that exists but is never exercised — surfaced only
by running `pnpm` for the first time. Ordered HIGH first.*

- [x] T151 Fix the TypeScript errors blocking `pnpm typecheck` in `apps/web` — add `"types": ["vite/client", "vitest"]` (or a `vite-env.d.ts` reference) to `apps/web/tsconfig.json` so `import.meta.env` resolves at `src/api/health.ts:26`, and import `defineConfig` from `vitest/config` in `apps/web/vite.config.ts` so the `test` key is a known property per Mandatory Surfaces (typed contracts) (contradicts)
- [x] T152 Add `.venv/`, `.git/`, and `**/site-packages/**` to the `ignores` list in `eslint.config.js` — `pnpm lint` currently reports 19 errors from JavaScript inside the Python virtualenv, so the CI `web` job fails for reasons unrelated to project source per FR-047 (contradicts)
- [x] T153 Give `apps/web` a real test suite in `apps/web/src/pages/StatusPage.test.tsx` covering the loading, error, and ready states the status shell implements — `pnpm test` currently exits 1 with "No test files found", so the declared script has never passed per FR-047, SC-012 (missing)
- [x] T154 Add a healthcheck to the `web` service in `infrastructure/docker-compose.yml` — it is the only long-running service without one, and `wait-for-healthy.sh` treats a missing healthcheck as ready, so `make up` reports success without ever confirming the frontend serves per FR-002, FR-003 (partial)
- [x] T155 Test the worker's tenant-attribution contract in `tests/security/test_job_tenancy.py` — assert `TenantTask` rejects an invocation without `company_slug` and that `record_job` writes a `job_records` row carrying the correct tenant; the mechanism exists in `services/worker/src/eaios_worker/tasks/base.py` but nothing exercises it and the table is empty per FR-042 (missing)
- [x] T156 Assert the document-ownership convention in `tests/integration/test_document_ownership.py` — policies owned by the governing department head, contracts by a Legal user or the Executive Management head where no Legal department exists, public content by the Executive Management head; current tests only check that owner and document share a company per FR-031a (missing)

---

## Phase 11: Convergence

*Appended 2026-08-01 by a third `/speckit-converge` run, after all 156 prior tasks were
complete and both stacks verified (661 Python tests, 10 TypeScript tests, ruff, mypy, eslint,
tsc all clean). No constitution violation was found. Every finding below concerns the
**full profile** — the default the documented workflow produces and the one nothing exercises —
or a check that runs locally but not in CI. Ordered HIGH first.*

- [x] T157 Report the background worker in the readiness probe — `apps/api/src/eaios_api/health/router.py` checks four stores, and `health/schemas.py` hard-pins `name` to a four-value `Literal` with `dependencies` at `min_length=4, max_length=4`, so the omission is enforced by the schema; US1/AC3 names the background worker alongside the four stores, `services/worker/src/eaios_worker/health.py` from the plan's structure was never created, and a wedged worker is currently invisible to `/health/ready`. Add the probe, widen the contract in `specs/001-foundation-tenant-seed/contracts/health-api.yaml`, regenerate `packages/contracts/src/generated/api.ts`, and extend `apps/web/src/pages/StatusPage.test.tsx` per FR-003, US1/AC3 (partial)
- [x] T158 Stop hardcoding `--profile smoke` across the test suite — `SeedConfig.profile` defaults to `full`, so the documented path (`make up && make seed`) produces a full dataset, but 16 call sites in `tests/e2e/test_determinism.py`, `tests/integration/test_migrations.py`, `test_seed_incomplete.py`, and `test_seed_refusal.py` pass `smoke` unconditionally; against a full environment `test_reset_and_reseed_reproduce_the_same_fingerprint` reseeds at smoke and then fails with "generation is not deterministic (SC-002)" — accusing the generator of a defect that is really a profile switch — and `test_migrations.py`'s restore fixture silently replaces the developer's full dataset with a smoke one. Read the profile from the manifest (as `verify` already does) and fall back to smoke only when the environment is empty per FR-004, FR-011, SC-002 (contradicts)
- [x] T159 Assert `EXPECTED_FINGERPRINTS["full"]` in `tests/e2e/test_determinism.py` — the full known-good value is committed at line 44 and never read; all three pinned assertions use the smoke value, and `test_profiles_are_distinct_datasets` only proves the two profiles differ, which stays true however far the full dataset drifts. `_generate("full")` already runs in that test, so the value is computed and thrown away — asserting it costs nothing per FR-017a, SC-002 (partial)
- [x] T160 Assert SC-005's employee range in `tests/integration/test_volume_targets.py` — nothing checks that NileTech holds between 190 and 210 employees; `test_family_is_present_and_non_empty` applies ±10% to the *profile's* scaled targets, which at smoke is roughly 28 users and at full is 180–220, neither of which is the criterion. Gate the assertion on the manifest's profile being `full` and add a full-profile seed to the CI `stack` job (or a scheduled run) so the number the specification commits to is exercised rather than asserted per SC-005, FR-019 (missing)
- [x] T161 Add `scripts/seed/src` to the mypy invocation in `.github/workflows/ci.yml:45` — it currently type-checks `packages/core/src apps/api/src services/worker/src` while `Makefile`'s `lint` target includes the seed package, so the largest package, and the one every determinism guarantee runs through, is the only one a type regression could enter without blocking the change per SC-012, plan: tooling (partial)
- [x] T162 Resolve the empty `packages/contracts/schemas/` directory — the plan's structure names `schemas/dataset-manifest.schema.json` there so the TypeScript side can validate a manifest, but the only copy lives under `specs/001-foundation-tenant-seed/contracts/` where `tests/integration/test_manifest_schema.py:31` reads it. Either move the schema into the package and repoint the test at it, or delete the directory and record the deviation in `docs/README.md` — an empty directory that a design document promises content for reads as unfinished work per plan: contracts package (partial)

---

## Phase 12: Convergence

*Appended 2026-08-02 by a fourth `/speckit-converge` run, after all 162 prior tasks were
complete and both stacks verified (676 Python tests, 13 TypeScript tests, ruff, mypy, eslint,
tsc all clean). No constitution violation was found. Every finding below is a guarantee that
holds in the current data but that nothing asserts — the failure mode this feature has hit
repeatedly. Ordered HIGH first.*

- [x] T163 Verify the Qdrant payload indexes actually exist, in `scripts/seed/src/eaios_seed/audit_checks/probe.py` and `tests/security/test_cross_tenant_probe.py` — `probe_vector_store`'s docstring says it asserts the collections are "tenant-filterable" and `infrastructure/qdrant/collections.json` says the probe asserts they "carry the payload index", but it only checks that the collections exist and hold zero points. Two things make that gap real rather than cosmetic: `loaders/stores.py:219-236` creates the indexes only inside `if name not in existing:`, so a collection created once without them never gains them, and each `create_payload_index` call is wrapped in `except Exception: continue`, so every index could fail to be created and the seed would still report success. Decision D2 leaves the collections empty, which makes the index the *only* structural guarantee FR-041 has in this feature — and the ingestion work in the next feature builds its tenant filter on it per FR-041, plan: Qdrant payload schema and payload index (partial)
- [x] T164 Give sensitive documents the attributes FR-010 exists to provide, in `scripts/seed/src/eaios_seed/generators/legal.py` and a new assertion in `tests/integration/test_document_ownership.py` — at the full profile 25 of 89 `CONFIDENTIAL` documents carry no `department_id` and 4 carry no `country`, and both `RESTRICTED` documents carry no `country`. FR-010 requires these "so later authorization work has the attributes it requires", and Constitution Principle II layers ABAC on department, country, ownership, and classification: a RESTRICTED payroll record with a null country cannot be filtered by the country rule that is supposed to protect it. Either populate the attributes for every classification above INTERNAL, or record in `docs/dataset.md` which document types legitimately have no department or country (a company-wide handbook plausibly has neither) and assert that every type outside that list carries both per FR-010, FR-010a, Constitution II (partial)
- [x] T165 Assert the employee distribution is skewed rather than uniform in `tests/integration/test_org_hierarchy.py` — FR-020 requires the spread across departments and offices to be "plausible for a company of this type and size rather than uniform", and the generated data satisfies it (Engineering 60, Legal 10; Cairo 116, Alexandria 55, Dubai 29), but nothing checks it. `test_volume_targets.py` only measures the total, so an allocator change that gave all eight departments 25 employees each would pass every existing test while destroying the premise that makes departmental questions interesting per FR-020 (partial)
- [x] T166 Enforce dependency pinning with a test in `tests/unit/test_dependency_pinning.py` — FR-012b requires every dependency that can influence generated content to be version-pinned with a committed lockfile. All five `pyproject.toml` files currently use `==` throughout and both `uv.lock` and `pnpm-lock.yaml` are committed, so the requirement holds today, but nothing prevents a future `faker>=33.3.0`. Faker's word and name data changes between releases, so that single character would silently produce a different dataset and invalidate the committed fingerprints — the precise failure FR-012b was written to prevent. Parse each `pyproject.toml`, reject any specifier that is not an exact pin, and assert both lockfiles exist per FR-012b, FR-011 (missing)

---

## Phase 13: Convergence

*Appended 2026-08-02 by a fifth `/speckit-converge` run, after all 166 prior tasks were
complete (716 Python tests, 13 TypeScript tests, ruff, mypy, eslint, tsc clean; full-profile
fingerprint verified against a live seed). No constitution violation was found in the code.
All three findings concern the **documentation set and persona stability** — the one area
every prior run took at face value because `docs/README.md` asserted it could not drift.
Ordered HIGH first.*

- [x] T167 **Correct `docs/personas.md` and `docs/dataset.md` — both are factually wrong today.** The persona table names the wrong person for eight of the ten personas and the wrong country for two: the live dataset has `manager.engineering` = Farida Mansour (doc: Tarek Darwish), `legal.counsel` = Hassan Lotfy, EG (doc: Sultan AlSuwaidi, AE), `hr.generalist` = Mariam Lotfy (doc: Sherif Hafez), `employee.engineering` = Latifa AlNuaimi (doc: Majid AlZaabi), `employee.sales` = Aisha AlShamsi, AE (doc: Sherif Fahmy, EG), `finance.analyst` = Amir Adel (doc: Salma ElGendy), `auditor.readonly` = Nadia Fahmy (doc: Hassan Zaki), and `employee.delta` = Omar Adel (doc: Dina Shafik); only `admin.company` and `comms.sender` match. The "Reports to" column chains off those stale names, so the reporting structure it describes is wrong too. Both files also stamp generator version `0.1.5` while the generator is at `0.1.6`. FR-025b requires personas to be listed in the feature documentation with company, department, role, country, and manager — a list that names the wrong people satisfies the letter and defeats the purpose, since acceptance tests, the evaluation set, and the defense demo script all reference these personas by name per FR-025b, FR-048 (contradicts)
- [x] T168 **Provide the documentation generator `docs/README.md` claims exists, or withdraw the claim.** That file states personas.md and dataset.md are "generated from the live database rather than written by hand, so they cannot drift into describing records that do not exist — regenerate them after any change to the dataset", but no generator exists: searching `Makefile`, `scripts/`, and every `*.py` and `*.sh` in the repo for `personas.md` or `dataset.md` returns nothing, so there is no command to run and the instruction cannot be followed. That false assurance is the direct cause of T167 — four convergence runs read the claim and did not re-check the content. Either add a `make docs` target that renders both files from the seeded database and regenerate them, or replace the claim with an honest statement that they are maintained by hand. Whichever is chosen, add a test that fails when the committed documents disagree with the live dataset (persona keys, names, countries, managers, realized counts, and the generator-version stamp), because FR-048 states that documentation whose instructions no longer work is a defect, not an inconvenience per FR-048, Constitution Development Workflow (Definition of Done, item 3) (missing)
- [x] T169 **Pin persona identities as a tripwire in `tests/security/test_scenario_readiness.py`.** FR-025c states that persona identifiers, email addresses, department assignments, and reporting relationships MUST NOT change between seed runs or between generator versions unless the change is deliberate and documented — but nothing asserts which user any `persona_key` resolves to. `tests/unit/test_ids.py:91` pins the derivation *function* (that `derive("user", "niletech", "employee-0042")` is stable), not the persona *assignment*; `TestPersonaSet` pins company and department for six of ten personas and never checks id, email, full name, or manager. The only remaining control is the whole-dataset fingerprint, which changes for any row in any table and is re-pinned deliberately whenever a dataset change is intended — it was re-pinned twice in this session alone, and would have silently blessed a persona reassignment. This is not hypothetical: the eight names in T167 moved at some point and no check noticed. Assert the frozen `persona_key` → (id, email, full name, country, manager persona) mapping for all ten, so a reassignment fails with a message naming the persona rather than surfacing as a fingerprint mismatch per FR-025c, SC-014 (missing)

## Phase 14: Convergence

- [ ] T170 **CRITICAL** Put the project under version control and confirm the workflow runs, at the repository root and in `.github/workflows/ci.yml` — FR-047c requires it, SC-012's "block the change" is defined in terms of it, and FR-047 requires the determinism, isolation, coherence, and integrity checks to run "in continuous integration on every change". None of that is happening: `git rev-parse --git-dir` fails and there is no `.git` directory, so `ci.yml` — which correctly declares `on: push` and `on: pull_request` — has never been triggered by anything. The constitution's Development Workflow section defines done as four conditions including "required tests exist, **run in CI**, and pass", and states that work satisfying three of four "MUST NOT be reported as complete". This is the largest instance of the defect this project has spent both features hunting: **1,487 automated checks that have never once run automatically**, a gate that reports nothing because no event reaches it. Initialize the repository, commit the working tree, add a remote, push, and then **verify from the run log that the workflow actually executed and what it reported** — a green badge nobody has read is the same failure one level up. Expect the first run to fail: it will be the first time `uv sync`, the cross-platform determinism matrix, and the full stack job have run anywhere but this machine. Record what it finds per FR-047c, SC-012, Constitution: Development Workflow (missing)
- [X] T171 Add the import-direction check FR-001a requires, in `tests/` or as a CI step — the rule is now specified (packages/* must not import from apps/*, services/*, or scripts/*; those three must not import from each other; shared code moves down into packages/) and nothing enforces it. `grep -rln "import-linter|tach|no-restricted-imports"` across `tests/`, `.github/`, `eslint.config.js`, and `pyproject.toml` finds nothing. The rule exists because it was already needed once and resolved by judgement: the seed loader required a Redis key pattern the API also writes, and the pattern was moved into `packages/core` because that seemed right rather than because a rule said so. The next feature adds a second application and a second API surface, which is when an unwritten layering rule usually breaks. A Python import scan plus an ESLint `no-restricted-imports` rule for the TypeScript workspaces covers both halves; include a case asserting the check **fails** on a deliberately backwards import, since a layering check that cannot fail is the shape this project keeps finding per FR-001a (missing)
- [X] T172 [P] Report skipped checks and their reasons in the verification output, in `scripts/seed/src/eaios_seed/` — FR-045a requires a check whose subject is empty to report as **skipped with its reason**, to name the decision that emptied it, and requires the skip count to be visible in the verification output rather than buried. `seed verify` currently prints three `OK` lines and nothing else, so an operator cannot tell how much was examined. Note what is **already right** and must not be undone: `TestVectorStoreProbe` does not fake a pass over the empty vector store — it substitutes a payload-index check that verifies the structural guarantee FR-041 actually has under decision D2, and carries `test_the_probe_reports_a_missing_index` as an anti-vacuity guard. The gap is reporting, not substance: nothing states that the marker-phrase search across the vector store was not performed and why. Add a skipped line naming D2 to `verify`'s output and a count, so "three checks passed" is never mistaken for "everything was checked" per FR-045a (partial)
