# Implementation Plan: NileTech Public Website

**Branch**: `002-public-website` | **Date**: 2026-08-02 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/002-public-website/spec.md`

## Summary

Build the twelve-page public NileTech website in `apps/web`, rendered on the server, sourced
entirely from feature 001's seeded `PUBLIC` content, and served by a small set of read-only
public endpoints plus one write path for contact submissions.

The interesting part is not the pages. It is the **boundary**: an anonymous surface sitting on
a database that also holds payroll records, executive contracts, and a second tenant. The
design therefore makes disclosure require an explicit act rather than an omission —
responses are built from a **declared field allowlist** rather than by serializing rows and
hoping nothing sensitive rides along; the tenant is **fixed in server code** and not derivable
from anything a caller sends; and the reserved portal address exists *now* so its anonymous
refusal is tested before the portal it guards is ever built.

`apps/web` moves from a Vite SPA to **Next.js 15 (App Router)**. The spec's search-engine
requirements (FR-039–FR-043) are almost exactly Next's Metadata API surface, and server
rendering removes the loading-then-content flash that SC-014 budgets for. The existing status
shell from feature 001 migrates to `/status` rather than being deleted — it is what FR-002 and
FR-003 of that feature are demonstrated with.

## Technical Context

**Language/Version**: TypeScript 5.6 / React 19 on Next.js 15 (web) · Python 3.12 (api)

**Primary Dependencies**: Next.js 15 (App Router) · React 19 · FastAPI 0.115 · SQLAlchemy 2.0 · Alembic · Pydantic v2 · `packages/ui` (new design system) · `packages/contracts` (generated OpenAPI types) · Playwright · axe-core · Vitest · pytest

**Storage**: PostgreSQL 16 — read-only for all seeded content; one new tenant-scoped table, `contact_submissions`, under Row-Level Security like every other tenant table

**Testing**: Vitest + Testing Library (components) · Playwright (navigation, responsive widths, end-to-end) · `@axe-core/playwright` (WCAG 2.2 AA per page) · pytest (public-field allowlist, anonymous refusal, cross-tenant probe)

**Target Platform**: Docker Compose on Linux, macOS, and Windows 11 + Docker Desktop; browsers at 360px, 768px, and 1280px

**Project Type**: Web application — server-rendered public frontend + read-only public API on the existing backend

**Performance Goals**: Main content visible within 3s on a typical connection (SC-014); no page holds an indefinite loading state

**Constraints**: No authentication anywhere on this surface · tenant fixed in server code · every response field explicitly declared · content changes only by reseeding · no outbound delivery of any kind

**Scale/Scope**: 12 pages · ~40 seeded public records · 6 read endpoints + 1 write endpoint · 3 verified viewport widths

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Evaluated pre-research and re-evaluated post-design. Both passes give the same result.

| Gate | Principle | Status |
|------|-----------|--------|
| Every artifact this feature creates/reads carries and filters on `company_id` | I (NON-NEGOTIABLE) | **PASS** — `contact_submissions` carries a non-nullable `company_id` under RLS; every read is filtered by a server-fixed NileTech identifier (FR-009a); no new object, cache, vector, or job artifact is created |
| Cross-tenant behavior covered by a NileTech ↔ Delta Retail isolation test | I (NON-NEGOTIABLE) | **PASS** — FR-052 probes every public response for Delta's marker phrases, and a test asserts no caller-supplied hostname, path, parameter, header, or body can select the other tenant |
| Authorization decisions are deterministic code; no LLM influences access | II (NON-NEGOTIABLE) | **PASS (trivially)** — no LLM exists on this surface; the public/private decision is a static route and field allowlist |
| Applicable layers applied in order: tenant → RBAC → ABAC → resource ACL | II | **N/A beyond the tenant layer** — there is no authenticated principal to carry roles or attributes. The tenant layer *is* applied and is not caller-selectable. RBAC/ABAC/ACL arrive with the authorization feature (001 decision D1) |
| Filtering happens before retrieval; no unauthorized text can reach the prompt | III (NON-NEGOTIABLE) | **N/A** — no retrieval and no prompt in this feature |
| Cache keys include tenant + permission fingerprint + question + version | III | **N/A** — no answer cache. Page responses are not cached in Redis (see research R7) |
| Answers carry citations and pass the Hallucination Checker | IV | **N/A** — no generated answers |
| Business values come from parameterized read-only queries | V | **PASS** — every figure and name on the site is read from PostgreSQL through parameterized queries; nothing is composed or restated by a model |
| Every new tool declares typed I/O, permissions, scope, audit, approval class | VI | **N/A** — no agent tools |
| Send/delete/publish/modify paths pause at the human approval gate | VII (NON-NEGOTIABLE) | **PASS** — the single write path deliberately delivers nothing (FR-023a). Storing a message is not an irreversible outward action, so there is nothing to gate. If delivery is ever added, it becomes a send action and the gate applies — recorded in `contracts/public-api.yaml` |
| Security-critical paths have failing tests written first | VIII (NON-NEGOTIABLE) | **PASS** — the allowlist test, the anonymous-refusal test, and the cross-tenant probe are authored and observed failing before the endpoints exist |
| New data is deterministic, seeded, and coherent | IX | **PASS** — this feature generates no content. `contact_submissions` holds runtime data and is **excluded from the dataset fingerprint** (see research R8), so feature 001's committed fingerprints are unaffected |
| Consequential operations write audit records (allow and deny) | X | **PASS** — accepted submissions and refused anonymous requests both write audit entries (FR-023, FR-047) |
| Public site / employee portal surfaces are role-aware and complete | Mandatory Surfaces | **PASS** — this *is* the public site. Role-awareness is `N/A` for an anonymous surface; the access-denied state is delivered as the reserved portal page (FR-049a) |
| Request/response models are typed at every boundary | Mandatory Surfaces | **PASS** — Pydantic response models on the API, regenerated TypeScript types in `packages/contracts`, no free-form JSON |
| Schema changes ship as reversible migrations; seeds stay idempotent | Mandatory Surfaces | **PASS** — one reversible migration adds `contact_submissions` with its RLS policy; the seed is untouched |
| Everything new runs inside the Docker Compose stack | Mandatory Surfaces | **PASS** — the `web` service builds and runs Next.js; no new service is introduced |
| Frontend work includes responsive, accessible, loading, empty, error, access-denied states | Mandatory Surfaces | **PASS** — FR-025–FR-030 cover the states, FR-032 pins the widths, FR-033–FR-038 and FR-053 pin WCAG 2.2 AA |

**Result: no violations.** Every `N/A` traces to the absence of an authenticated principal or an
LLM on this surface — both deferred by feature 001's confirmed decisions, not by a shortcut
taken here. Complexity Tracking is empty.

**Two additions beyond the spec's literal requirements**, both recorded in research:

1. The **status shell moves to `/status`** rather than being deleted. It is the demonstration for feature 001's FR-002 and FR-003, and deleting it would silently retire that coverage.
2. `contact_submissions` is **explicitly excluded from the fingerprint** and **added to the reset path**. Neither is requested by this spec, but both are required for feature 001's guarantees to keep holding.

## Project Structure

### Documentation (this feature)

```text
specs/002-public-website/
├── plan.md              # This file
├── spec.md              # Feature specification (clarified 2026-08-02)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── public-api.yaml       # OpenAPI for the public endpoints
│   ├── public-fields.md      # The declared approved-public field allowlist (FR-045)
│   └── routes.md             # Page addresses and slug derivation (FR-004)
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
apps/
├── web/                              # Next.js 15 App Router — replaces the Vite SPA
│   ├── app/
│   │   ├── layout.tsx                # Root layout: header, footer, skip link, tokens
│   │   ├── page.tsx                  # Home (hero + summaries)
│   │   ├── about/page.tsx
│   │   ├── services/page.tsx
│   │   ├── products/page.tsx
│   │   ├── leadership/page.tsx
│   │   ├── careers/page.tsx          # list + office/department filters
│   │   ├── careers/[slug]/page.tsx   # vacancy detail
│   │   ├── news/page.tsx
│   │   ├── news/[slug]/page.tsx      # article detail
│   │   ├── contact/page.tsx          # form (client island) + offices
│   │   ├── portal/page.tsx           # reserved address — "sign-in not yet available"
│   │   ├── status/page.tsx           # migrated from the feature 001 status shell
│   │   ├── not-found.tsx             # 404
│   │   ├── error.tsx                 # 500
│   │   ├── sitemap.ts                # machine-readable page index (FR-042)
│   │   └── robots.ts
│   ├── lib/
│   │   ├── api.ts                    # typed client over @eaios/contracts
│   │   └── metadata.ts               # per-page and per-record metadata builders
│   ├── tests/                        # component tests (Vitest + Testing Library)
│   ├── e2e/                          # Playwright: navigation, widths, axe, refusals
│   ├── next.config.ts
│   └── Dockerfile
└── api/
    └── src/eaios_api/
        └── public/                   # NEW — the public surface
            ├── router.py             # 6 read endpoints + contact submission
            ├── schemas.py            # response models = the field allowlist
            ├── queries.py            # parameterized reads, tenant fixed server-side
            └── slugs.py              # deterministic slug derivation (FR-004)

packages/
├── ui/                               # design system — reserved by 001, filled here
│   └── src/
│       ├── tokens.css                # type scale, palette, spacing (FR-031)
│       ├── primitives/               # Button, Field, Card, Tag, Skeleton, Alert
│       └── patterns/                 # PageHeader, SectionGrid, EmptyState, ErrorState
└── contracts/
    └── src/generated/api.ts          # regenerated: public endpoints added

apps/api/alembic/versions/
└── 0003_contact_submissions.py       # table + RLS policy, reversible

tests/
├── security/
│   ├── test_public_field_allowlist.py    # FR-044, FR-045, FR-050
│   ├── test_anonymous_refusal.py         # FR-046, FR-047, FR-051
│   └── test_public_site_isolation.py     # FR-009a, FR-052
└── integration/
    └── test_contact_submission.py        # FR-019–FR-024
```

**Structure Decision**: The layout the project owner specified — the site lives in `apps/web`,
its reusable pieces in `packages/ui`, its types in `packages/contracts`, its data behind the
existing `apps/api`. Two things are worth naming explicitly:

**`packages/ui` is finally used.** Feature 001 created it and left it empty on purpose, with a
comment saying so: decision D1 deferred every UI surface, so there were no components to share.
This feature fills it rather than putting components in `apps/web`, because the employee portal
is the next surface and will need the same primitives. Building them inside the website first
and extracting later is how two divergent design systems get created.

**The public API is a sibling of `health`, not a layer on top of it.** `apps/api/src/eaios_api/public/`
holds its own response models and its own queries rather than reusing an internal serializer.
That duplication is deliberate: a shared serializer is exactly how an internal field reaches a
public response, and FR-045 requires the public shape to be declared, not derived.

## Complexity Tracking

No constitution violations. Table intentionally empty.
