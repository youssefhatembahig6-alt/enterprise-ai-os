# Implementation Plan: Foundation — Monorepo, Local Environment & Deterministic Two-Tenant Dataset

**Branch**: `001-foundation-tenant-seed` | **Date**: 2026-08-01 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-foundation-tenant-seed/spec.md`

## Summary

Stand up the monorepo, a one-command Docker Compose environment, the tenant-scoped relational schema,
and a deterministic generator that seeds two isolated synthetic companies (NileTech Solutions and
Delta Retail Group) from empty — reproducibly, on any machine, verified by fingerprint.

The technical core is **determinism**. Everything else is conventional plumbing; the part that will
silently break is data generation reading a clock, an unseeded RNG, a locale, a dictionary iteration
order, or a platform newline. The design therefore pins four things: a **fixed reference date**
(`2026-06-30`), a **root seed**, **UUIDv5 identifiers derived from stable natural keys** (never from
insertion order or randomness), and **byte-level output controls** (LF newlines, UTF-8, sorted keys,
fixed decimal quantization). A content fingerprint over every row and file makes any drift a test
failure rather than a discovery three months later.

Row-Level Security is included even though the spec's requirements stop at application-level
`company_id`. Constitution Principle I (NON-NEGOTIABLE) requires RLS as the final safety net, and the
schema is being created in this feature — adding the policies now costs one migration, whereas
retrofitting them later means revisiting every table and every query.

## Technical Context

**Language/Version**: Python 3.12 (api, worker, seed) · TypeScript 5.6 / React 18 (web)

**Primary Dependencies**: FastAPI · SQLAlchemy 2.0 (typed ORM) · Alembic · Pydantic v2 + pydantic-settings · structlog · Celery 5 · redis-py · qdrant-client · MinIO SDK (S3) · Faker (seeded) · pytest · Vite · openapi-typescript

**Storage**: PostgreSQL 16 (system of record, RLS) · Qdrant (provisioned, empty — decision D2) · Redis 7 (cache namespace + Celery broker) · MinIO (S3-compatible object storage)

**Testing**: pytest (unit, integration, security) · integration tests run against the Compose stack · Vitest for `apps/web` · a fingerprint-comparison harness for determinism

**Target Platform**: Docker Compose on Linux, macOS, and Windows 11 + Docker Desktop (the team's primary OS is Windows — this drives explicit newline and path handling)

**Project Type**: Monorepo — web frontend + API + background worker + data tooling + shared packages

**Performance Goals**: Full seed < 10 min (SC-008) · reset + reseed < 15 min · clean checkout to healthy stack < 15 min (SC-001)

**Constraints**: Byte-identical generated output across OS and locale · no wall-clock reads in generation · no unseeded randomness · deterministic UUIDs · `company_id` non-nullable on every tenant-owned table

**Scale/Scope**: ~40,000 rows across 2 tenants · ~180 generated document files · 24-month history window ending 2026-06-30 · ~240 employees total

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Evaluated pre-research and re-evaluated post-design. Both passes give the same result.

| Gate | Principle | Status |
|------|-----------|--------|
| Every artifact carries and filters on `company_id` | I (NON-NEGOTIABLE) | **PASS** — non-nullable FK on every tenant table; MinIO and Redis keys namespaced by company; Qdrant payload schema and payload index defined; job and audit records carry it |
| Cross-tenant behavior covered by a NileTech ↔ Delta isolation test | I (NON-NEGOTIABLE) | **PASS** — `tests/security/` holds the structural audit, cross-store probe, and RLS enforcement tests; all written before the generator |
| Authorization decisions are deterministic code; no LLM involved | II (NON-NEGOTIABLE) | **PASS (trivially)** — no LLM exists in this feature; RLS predicates and key builders are pure deterministic code |
| Authorization layers applied in order | II | **N/A** — request-time authorization deferred by confirmed decision D1; roles and permissions are seeded as data only |
| Filtering before retrieval; no unauthorized text reaches a prompt | III (NON-NEGOTIABLE) | **N/A** — no retrieval and no prompt in this feature (D2). Qdrant is provisioned with a `company_id` payload index so the filter path exists before any content does |
| Cache keys include tenant + permission fingerprint + question + version | III | **PASS (structure only)** — the key builder and its tests ship here; nothing is cached yet |
| Answers carry citations and pass the hallucination checker | IV | **N/A** — no answers are generated |
| Business facts from parameterized read-only queries | V | **N/A** — no query agent |
| New tools declare typed I/O, permissions, scope, audit, approval class | VI | **N/A** — no agent tools |
| Irreversible actions pause at the approval gate | VII (NON-NEGOTIABLE) | **PASS** — the one irreversible operation here is `reset`, gated behind a separate explicit command and a typed confirmation (FR-014a) |
| Security-critical paths have failing tests written first | VIII (NON-NEGOTIABLE) | **PASS** — isolation, RLS, determinism, and integrity tests are authored and observed failing before the generator exists |
| New data is deterministic, seeded, coherent | IX | **PASS** — the entire feature |
| Consequential operations write audit records | X | **PASS** — seed and reset both write audit entries (FR-043) |
| Public site / portal surfaces role-aware and complete | Mandatory Surfaces | **N/A** — no product UI in this feature (D1). `apps/web` ships as a health/status shell only, so the Compose stack is complete per FR-002 |
| Typed request/response models at every boundary | Mandatory Surfaces | **PASS** — Pydantic v2 models on the API, TS types generated from OpenAPI into `packages/contracts`, typed CLI contracts for seed/reset/verify |
| Schema changes as reversible migrations; seeds idempotent | Mandatory Surfaces | **PASS** — Alembic with tested downgrades; seed refuses on a non-empty environment (FR-014) |
| Everything new runs inside Docker Compose | Mandatory Surfaces | **PASS** — 9 Compose services, one command |
| Frontend responsive, accessible, loading/empty/error/access-denied | Mandatory Surfaces | **N/A** — no user-facing frontend features; deferred with D1 |

**Result: no violations.** Every `N/A` traces to confirmed scope decision D1 or D2, not to a shortcut.
Complexity Tracking is empty.

**One addition beyond the spec's literal requirements**: PostgreSQL Row-Level Security. Constitution
Principle I mandates it and forbids weakening it; the spec's FR set stops at application-level
scoping. Included here rather than deferred — see Summary for the cost rationale.

## Project Structure

### Documentation (this feature)

```text
specs/001-foundation-tenant-seed/
├── plan.md              # This file
├── spec.md              # Feature specification (clarified)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── health-api.yaml
│   ├── seed-cli.md
│   └── dataset-manifest.schema.json
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
apps/
├── api/                         # FastAPI service
│   ├── src/eaios_api/
│   │   ├── main.py              # app factory, lifespan, router registration
│   │   ├── settings.py          # pydantic-settings; single source of config
│   │   ├── logging.py           # structlog config; JSON output; company_id binding
│   │   ├── health/              # health + readiness routers
│   │   └── db/                  # engine, session, RLS session context
│   ├── alembic/versions/        # migrations (schema + RLS policies)
│   ├── alembic.ini
│   └── pyproject.toml
└── web/                         # React + TS + Vite (status shell only, per D1)
    ├── src/{App.tsx,api/,pages/StatusPage.tsx}
    ├── vite.config.ts
    └── package.json

packages/
├── core/                        # shared Python domain: models, ids, fingerprint, keys
│   ├── src/eaios_core/
│   │   ├── models/              # SQLAlchemy 2.0 declarative models (all tables)
│   │   ├── ids.py               # deterministic UUIDv5 derivation
│   │   ├── clock.py             # pinned reference date; forbids wall-clock reads
│   │   ├── fingerprint.py       # canonical serialization + digests
│   │   ├── keys.py              # object-storage and cache key builders
│   │   ├── classification.py    # the four-level enum
│   │   └── tenancy.py           # global-entity allowlist; scoping helpers
│   └── pyproject.toml
├── ui/                          # reusable React components (design primitives only)
└── contracts/                   # generated TS API types + JSON schemas
    ├── src/generated/api.ts     # from FastAPI OpenAPI via openapi-typescript
    └── schemas/dataset-manifest.schema.json

services/
└── worker/                      # Celery worker
    ├── src/eaios_worker/{celery_app.py,tasks/,health.py}
    └── pyproject.toml

scripts/
└── seed/                        # deterministic generator + CLI
    ├── src/eaios_seed/
    │   ├── cli.py               # seed | reset | verify | fingerprint
    │   ├── config.py            # root seed, reference date, volume profile
    │   ├── generators/          # org, hr, sales, finance, legal, public, personas
    │   ├── documents/           # deterministic document rendering (LF, UTF-8)
    │   ├── loaders/             # postgres, minio, qdrant, redis provisioning
    │   └── manifest.py          # counts, fingerprint, completion marker
    └── pyproject.toml

infrastructure/
├── docker-compose.yml           # 9 services (incl. minio-init + seed one-shots)
├── docker-compose.override.yml  # local dev conveniences
├── .env.example                 # documented non-secret defaults
├── postgres/init/               # roles: eaios_owner (migrations/seed), eaios_app (RLS-enforced)
├── qdrant/                      # collection provisioning config
└── minio/                       # bucket + policy bootstrap

tests/
├── unit/                        # ids, fingerprint, keys, clock, classification
├── integration/                 # migrations up/down, seed end-to-end, health
├── security/                    # tenant isolation, RLS enforcement, global allowlist
└── e2e/                         # clean checkout → up → seed → verify

Makefile                         # `make up`, `make reset` — the two documented commands
pnpm-workspace.yaml              # TS workspaces
pyproject.toml + uv.lock         # Python workspace (uv); members: core, api, worker, seed
.gitattributes                   # * text eol=lf — protects byte-identical output on Windows
```

**Structure Decision**: The monorepo uses the directory layout the project owner specified, plus one
addition: **`packages/core`**. The SQLAlchemy models, deterministic ID derivation, fingerprint logic,
and key builders are needed identically by `apps/api`, `services/worker`, and `scripts/seed`. The
alternatives were to host them inside `apps/api` and have the seed script import the API package — a
backwards dependency in which the data generator depends on the web service — or to duplicate them,
which guarantees drift in exactly the code where drift is a security bug. A shared package under the
already-specified `packages/` directory keeps the dependency direction clean: `core ← api`,
`core ← worker`, `core ← seed`.

The two documented commands required by the spec:

- **`make up`** — build and start all 9 Compose services, run migrations, wait for health. One command from a clean checkout (FR-002, SC-001). The nine are: `postgres`, `redis`, `qdrant`, `minio`, `minio-init` (one-shot bucket bootstrap), `api`, `worker`, `web`, and `seed` (a one-shot command container, not a long-running service).
- **`make reset`** — destroy all state in every store, re-run migrations, and regenerate the full dataset (FR-004, FR-014a). Requires typed confirmation and refuses to run against any non-local target.

## Complexity Tracking

No constitution violations. Table intentionally empty.
