---

description: "Task list for feature implementation"
---

# Tasks: NileTech Public Website

**Input**: Design documents from `specs/002-public-website/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: Mandatory here on two counts. Constitution Principle VIII requires tests written first
for tenant isolation and security-critical paths, and the specification itself requires them in
FR-050 through FR-055. Security tests are authored and observed failing before the endpoints they
guard exist.

**Environment**: every phase from 3 onward needs a seeded environment — `make up && make seed`.
This feature generates no content; it renders feature 001's dataset at the `full` profile.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to
- Paths follow the structure in [plan.md](./plan.md#project-structure)

---

## Phase 1: Setup

**Purpose**: Move `apps/web` onto the framework chosen in research R1 and prepare the workspace.
Nothing here depends on the specification remediation in Phase 2, so the two can proceed together.

- [x] T001 Add Next.js 15, React 19, and their types to `apps/web/package.json`; remove `vite`, `@vitejs/plugin-react`, and `apps/web/vite.config.ts` per research R1
- [x] T002 Create `apps/web/next.config.ts` and `apps/web/tsconfig.json` for the App Router, keeping the workspace's exact-pin discipline (feature 001 FR-012b)
- [x] T003 Create the App Router skeleton — `apps/web/app/layout.tsx` and `apps/web/app/page.tsx` — rendering a placeholder so the container has something to serve
- [x] T004 [P] Rewrite `apps/web/Dockerfile` to build and run Next.js, replacing the Vite dev-server command
- [x] T005 [P] Update the `web` service in `infrastructure/docker-compose.yml` — port, `WEB_HOST_PORT` default, and the healthcheck that currently probes 5173 per research R3
- [x] T006 [P] Update `infrastructure/.env.example` and `docs/running.md` with the new web port and URL
- [x] T007 Reconfigure Vitest for the App Router in `apps/web/vitest.config.ts`, preserving the jsdom environment and Testing Library setup
- [x] T008 [P] Add Playwright to `apps/web` with a config covering the three widths from FR-032 (360, 768, 1280) in `apps/web/playwright.config.ts`
- [x] T009 [P] Add `@axe-core/playwright` and an `e2e` script to `apps/web/package.json` per research R9
- [x] T010 [P] Create `packages/ui/src/tokens.css` with the type scale, palette, spacing, and radii that FR-031 requires, replacing the placeholder export
- [x] T011 [P] Add `pnpm --filter @eaios/web e2e` to the `web` job in `.github/workflows/ci.yml`
- [x] T012 Run `pnpm lint`, `pnpm typecheck`, and `pnpm test` to confirm the workspace is green before any feature work

**Checkpoint**: `make up` serves a placeholder page at the new port and the toolchain passes.

---

## Phase 2: Foundational (blocking)

**Purpose**: Resolve the specification conflicts the checklists surfaced, land the schema change,
and write the security tests before the surface they guard exists. **No user story may start until
this phase completes** — T013 through T017 change what gets built, and T024 through T026 must be
observed failing first.

### Specification remediation

These are amendments to `spec.md`, each traced to a checklist finding. Building before they are
settled means building something that will be rejected at review.

- [x] T013 Resolve the hero-content conflict in `specs/002-public-website/spec.md` — FR-005 requires a hero stating what the company does, FR-006 forbids hard-coded company content, and the `companies` table carries no positioning field. Either add an explicit carve-out for company positioning copy or define its source (checklists/content.md CHK001)
- [x] T014 Classify `/dataset/manifest` and the health endpoints as public or non-public in `spec.md` — feature 001 serves both anonymously today and the status shell reads them, so FR-047 as written would require refusing them (checklists/route-security.md CHK003)
- [x] T015 Scope FR-025's four-state requirement to client-fetched regions in `spec.md`, or state the exemption for server-rendered pages — otherwise loading states that never appear would satisfy the letter (checklists/states.md CHK003)
- [x] T016 Reconcile SC-005 with FR-053 in `spec.md` so a clean automated run cannot read as established WCAG 2.2 AA conformance (checklists/accessibility.md CHK016)
- [x] T017 State in `spec.md` that SC-007's "exactly one stored record" is verified through privileged database access, since FR-023b forbids a public read path (checklists/forms.md CHK019)
- [x] T018 [P] Amend FR-001 in `spec.md` to distinguish public content pages from non-content routes, so `/portal` and `/status` are enumerated rather than introduced by the plan alone (checklists/pages.md CHK007, CHK008)
- [x] T019 [P] Add retention and consent requirements for contact submissions to `spec.md`, plus a prohibition on writing submitted personal data to application logs (checklists/forms.md CHK006, checklists/data-exposure.md CHK003, CHK004)
- [x] T020 [P] Quantify the unstated thresholds in `spec.md` — field length bounds, the duplicate-suppression window, the loading-state delay, and the load timeout (checklists/forms.md CHK001, CHK002; checklists/states.md CHK001, CHK002)

### Schema and feature 001 integration

- [x] T021 Create the reversible migration `apps/api/alembic/versions/0003_contact_submissions.py` adding the table from data-model.md §2 with its RLS policy, and confirm feature 001's `test_every_tenant_table_has_a_policy` picks it up
- [x] T022 Add `contact_submissions` to the fingerprint exclusion list in `scripts/seed/src/eaios_seed/` and record it in `docs/determinism.md`, which FR-015a of feature 001 requires to document exclusions (research R8)
- [x] T023 Add `contact_submissions` to `reset_all`'s truncation set and to the seed emptiness pre-flight in `scripts/seed/src/eaios_seed/loaders/stores.py` — the pre-flight iterates `INSERT_ORDER`, which lists seeded tables only, so a submission written before seeding would leave the environment dirty and invisible (research R8)

### Security tests, written first

- [x] T024 [P] Write the failing field-allowlist test in `tests/security/test_public_field_allowlist.py` — every public response's keys must **equal** the set in `contracts/public-fields.md`, so an extra key fails and not only a missing one
- [x] T025 [P] Write the failing anonymous-refusal test in `tests/security/test_anonymous_refusal.py`, including an assertion that the refusal set is non-empty so the test cannot pass by having nothing to check
- [x] T026 [P] Write the failing cross-tenant test in `tests/security/test_public_site_isolation.py` — Delta's marker phrases absent from every public response, and no hostname, path, parameter, header, or body able to select the other tenant (FR-009a)
- [x] T027 Run the three suites and observe each failing for the right reason before any endpoint exists

### Shared surface

- [x] T028 Create the public router skeleton in `apps/api/src/eaios_api/public/router.py` and register it in `apps/api/src/eaios_api/main.py`
- [x] T029 Implement the fixed-tenant resolver in `apps/api/src/eaios_api/public/queries.py` — NileTech's identifier is read from server configuration and is not derivable from any request input (FR-009a)
- [x] T030 [P] Implement deterministic slug derivation and reverse resolution in `apps/api/src/eaios_api/public/slugs.py` per contracts/routes.md
- [x] T031 [P] Unit-test slug stability and collision behaviour in `tests/unit/test_public_slugs.py` — the same record must yield the same slug across runs, and a slug from the other tenant must resolve to nothing
- [x] T032 [P] Build the shared layout in `apps/web/app/layout.tsx` — header with navigation and portal control, footer with offices and enquiry address, skip link, token import (FR-002, FR-034)
- [x] T033 [P] Build the responsive navigation in `packages/ui/src/patterns/Navigation.tsx` — current-page indication, keyboard operable, dismissible mobile form that returns focus (FR-003, FR-033, FR-037)
- [x] T034 [P] Build the state primitives in `packages/ui/src/patterns/` — `EmptyState`, `ErrorState`, `Skeleton`, `Alert` — each announced to assistive technology (FR-025, FR-026, FR-027, FR-038)
- [x] T035 [P] Build the form primitives in `packages/ui/src/primitives/` — `Field`, `Button`, `Card`, `Tag` — with labels programmatically associated and error text linked to its control (FR-021, FR-034)
- [x] T036 Create the typed API client in `apps/web/lib/api.ts` over `@eaios/contracts`, with a single place that turns a failed request into the error state
- [x] T037 Create the metadata builders in `apps/web/lib/metadata.ts` — per-page and per-record title, description, social preview, canonical (FR-039, FR-040, FR-041)

**Checkpoint**: schema migrated, security tests failing as intended, layout and primitives available.
Feature 001's `make verify` still passes.

---

## Phase 3: User Story 1 — A Prospective Client Evaluates NileTech (P1) 🎯 MVP

**Goal**: A visitor understands what NileTech does and can browse its services, products, and
locations.

**Independent test**: open the site root and walk Home → Services → Products → About without a dead
end; every item traces to a generated record.

- [x] T038 [P] [US1] Implement `GET /public/company` and `GET /public/offices` in `apps/api/src/eaios_api/public/router.py` with response models from `apps/api/src/eaios_api/public/schemas.py`
- [x] T039 [P] [US1] Implement `GET /public/services` and `GET /public/products` with display-order sorting (FR-008)
- [x] T040 [US1] Regenerate `packages/contracts/src/generated/api.ts` from the live OpenAPI schema and export the new aliases from `packages/contracts/src/index.ts`
- [x] T041 [P] [US1] Build the home page in `apps/web/app/page.tsx` — hero plus summaries of services, products, recent news, and open vacancies (FR-005)
- [x] T042 [P] [US1] Build the services page in `apps/web/app/services/page.tsx` (FR-011)
- [x] T043 [P] [US1] Build the products page in `apps/web/app/products/page.tsx`, drawing only from public product offerings and never the internal catalog (FR-012)
- [x] T044 [P] [US1] Build the about page in `apps/web/app/about/page.tsx` with every office, its country, and the headquarters identified (FR-010)
- [x] T045 [US1] Apply per-page metadata to all four pages using `apps/web/lib/metadata.ts` (FR-039, FR-040)
- [x] T046 [P] [US1] Component-test the home page's summary blocks in `apps/web/tests/home.test.tsx`, including the case where a summary source is empty
- [x] T047 [P] [US1] Component-test services and products rendering and ordering in `apps/web/tests/catalog.test.tsx`
- [x] T048 [US1] End-to-end test the Home → Services → Products → About journey in `apps/web/e2e/client-journey.spec.ts` at all three widths
- [x] T049 [US1] Assert in `tests/integration/test_public_content.py` that the internal `products` table is unreachable through any public route (FR-012)

**Checkpoint**: a complete company brochure, independently demonstrable.

---

## Phase 4: User Story 2 — A Candidate Finds And Opens A Role (P2)

**Goal**: A job seeker browses open vacancies, filters them, and reads one in full.

**Independent test**: open Careers, confirm the count matches open vacancies in the dataset, filter
by office, open one vacancy, confirm department and location match that record.

- [x] T050 [P] [US2] Implement `GET /public/vacancies` with office and department filters, returning only open vacancies (FR-014)
- [x] T051 [P] [US2] Implement `GET /public/vacancies/{slug}` returning 404 for unknown slugs and for slugs belonging to the other tenant
- [x] T052 [US2] Regenerate `packages/contracts/src/generated/api.ts` for the vacancy endpoints
- [x] T053 [US2] Build the careers list in `apps/web/app/careers/page.tsx` with filters held in the query string so a filtered view is shareable (contracts/routes.md)
- [x] T054 [US2] Build the vacancy detail page in `apps/web/app/careers/[slug]/page.tsx` (FR-015)
- [x] T055 [US2] Implement the filter empty state — an explanation plus a way to clear the filter, distinct from the unfiltered empty state (FR-026, US2/AC5)
- [x] T056 [US2] Apply per-record metadata to vacancy pages, derived from the vacancy displayed (FR-041)
- [x] T057 [P] [US2] Component-test the filter behaviour and its empty state in `apps/web/tests/careers.test.tsx`, including announcement of the result count (FR-038)
- [x] T058 [P] [US2] Test in `tests/integration/test_public_vacancies.py` that closed vacancies are absent from the response entirely rather than flagged
- [x] T059 [US2] End-to-end test list → filter → detail → Not Found in `apps/web/e2e/careers.spec.ts`

**Checkpoint**: a working jobs board with shareable filtered views.

---

## Phase 5: User Story 3 — A Visitor Reads Company News (P3)

**Goal**: A visitor reads announcements newest-first and opens one in full.

**Independent test**: ordering matches the dataset, an article shows headline, date, and body.

- [x] T060 [P] [US3] Implement `GET /public/news` with a deterministic tie-break for items sharing a publication date (data-model.md §1)
- [x] T061 [P] [US3] Implement `GET /public/news/{slug}`, with the body present on detail and absent from the list (contracts/public-fields.md)
- [x] T062 [US3] Regenerate `packages/contracts/src/generated/api.ts` for the news endpoints
- [x] T063 [US3] Build the news list in `apps/web/app/news/page.tsx` with a mechanism to reach every item (FR-016)
- [x] T064 [US3] Build the article page in `apps/web/app/news/[slug]/page.tsx` (FR-017)
- [x] T065 [US3] Apply per-record metadata to article pages (FR-041)
- [x] T066 [P] [US3] Component-test ordering and the empty state in `apps/web/tests/news.test.tsx`
- [x] T067 [US3] End-to-end test list → article → Not Found in `apps/web/e2e/news.spec.ts`

**Checkpoint**: a company that looks active rather than dormant.

---

## Phase 6: User Story 4 — A Visitor Makes Contact (P4)

**Goal**: A visitor sends an enquiry, is told clearly what is wrong with invalid input, and gets an
unambiguous confirmation.

**Independent test**: invalid submissions are refused per field; a valid one is confirmed and stored
exactly once.

- [x] T068 [US4] Implement the `ContactIn` model with the bounds settled in T020, in `apps/api/src/eaios_api/public/schemas.py` (FR-019, FR-024)
- [x] T069 [US4] Implement `POST /public/contact` — validate, suppress duplicates by content hash, store, audit, return `202` with no echo and no identifier (FR-020, FR-022, FR-023)
- [x] T070 [US4] Implement field-addressed validation errors so the interface can attach each to its control (FR-021)
- [x] T071 [US4] Regenerate `packages/contracts/src/generated/api.ts` for the contact endpoint
- [x] T072 [US4] Build the contact page in `apps/web/app/contact/page.tsx` — offices, enquiry address, and the form (FR-018)
- [x] T073 [US4] Implement client-side validation mirroring the server rules, with errors announced to assistive technology and typed input preserved (FR-021, FR-038)
- [x] T074 [US4] Implement the success and submission-failure states, including the case where the backend is unreachable (FR-022, US4/AC5)
- [x] T075 [P] [US4] Test in `tests/integration/test_contact_submission.py` that server-side validation refuses invalid input submitted directly, bypassing the browser (FR-020, SC-006)
- [x] T076 [P] [US4] Test that an accepted submission writes exactly one row and one audit entry, and that a duplicate creates no second row (FR-022, FR-023, SC-007)
- [x] T077 [P] [US4] Test that no public route can read stored submissions and that the router declares no such path (FR-023b)
- [x] T078 [P] [US4] Test that submitted markup is stored inertly and never rendered as active content anywhere (FR-024)
- [x] T079 [P] [US4] Component-test the form's validation, success, and error states in `apps/web/tests/contact.test.tsx`
- [x] T080 [US4] Confirm `make verify` still reports the committed fingerprint after a submission — the check that T022's exclusion actually works

**Checkpoint**: the site's only write path, with the server as the control.

---

## Phase 7: User Story 5 — A Visitor Assesses Credibility Through Leadership (P5)

**Goal**: A visitor sees the executive team with public-appropriate detail only.

**Independent test**: every profile corresponds to a real generated executive; no field exposes
salary, personal contact details, or an internal identifier.

- [x] T081 [US5] Implement `GET /public/leadership`, selecting exactly one column from `users` and exposing no internal identifier (contracts/public-fields.md)
- [x] T082 [US5] Regenerate `packages/contracts/src/generated/api.ts` for the leadership endpoint
- [x] T083 [US5] Build the leadership page in `apps/web/app/leadership/page.tsx` in display order (FR-013)
- [x] T084 [US5] Implement the photograph placeholder, since feature 001 generates no images (US5/AC3)
- [x] T085 [P] [US5] Test in `tests/security/test_public_field_allowlist.py` that the leadership response contains no `user_id` and no other `users` column (FR-044)
- [x] T086 [P] [US5] Component-test the placeholder and long-biography layout in `apps/web/tests/leadership.test.tsx`

**Checkpoint**: the page carrying the sharpest disclosure risk, verified.

---

## Phase 8: User Story 6 — An Employee Reaches The Portal Entry Point (P6)

**Goal**: The portal entry exists and the anonymous boundary holds.

**Independent test**: the login control leads to the reserved address; every private route and
non-public endpoint refuses an anonymous request.

- [x] T087 [US6] Build the reserved portal page in `apps/web/app/portal/page.tsx` — a designed "sign-in not yet available" state, no credential field, a route back into the site (FR-049a)
- [x] T088 [US6] Wire the portal entry control into the header on every page (FR-049)
- [x] T089 [US6] Implement anonymous refusal with an audit entry for every non-public endpoint, per the classification settled in T014 (FR-046, FR-047)
- [x] T090 [US6] Make T024, T025, and T026 pass — the three security suites written in Phase 2
- [x] T091 [P] [US6] End-to-end test in `apps/web/e2e/boundary.spec.ts` that the portal page renders its designed state and exposes no credential field
- [x] T092 [P] [US6] Test that `/portal` and `/status` are excluded from the sitemap and from the per-page metadata audit (contracts/routes.md)

**Checkpoint**: the constitution's first principle is enforced and tested on this surface.

---

## Phase 9: Polish & Cross-Cutting Concerns

- [x] T093 [P] Build the Not Found page in `apps/web/app/not-found.tsx`, reported as not found to crawlers (FR-028, FR-043)
- [x] T094 [P] Build the Server Error page in `apps/web/app/error.tsx`, disclosing no stack trace, hostname, query text, or identifier (FR-029)
- [x] T095 [P] Migrate the feature 001 status shell to `apps/web/app/status/page.tsx` with its 13 tests, preserving the degraded-readiness coverage (research R2)
- [x] T096 [P] Implement `apps/web/app/sitemap.ts` and `apps/web/app/robots.ts`, excluding `/portal` and `/status` (FR-042)
- [x] T097 Implement section-level failure containment so one failing region does not replace the page (FR-030)
- [x] T098 [P] Add the axe sweep over every page at WCAG 2.2 A and AA tags in `apps/web/e2e/accessibility.spec.ts` (FR-053)
- [x] T099 [P] Add the keyboard-only traversal in `apps/web/e2e/keyboard.spec.ts` — focus order, focus visibility, and focus return on mobile-navigation dismissal (research R9)
- [x] T100 [P] Add the responsive assertions in `apps/web/e2e/responsive.spec.ts` — no horizontal page scroll from 320px, no clipping or overlap at the three verified widths (FR-032, SC-004)
- [x] T101 [P] Add the metadata audit in `apps/web/e2e/metadata.spec.ts` — every page in the sitemap carries a unique title and description (FR-039, SC-011)
- [x] T102 [P] Add the state-coverage test proving every content-loading region renders loading, empty, and error, per the scope settled in T015 (FR-054, SC-012)
- [x] T103 Verify contrast across the token palette in every interactive state, including hover, focus, and error (FR-035)
- [x] T104 [P] Update `docs/running.md` and `docs/README.md` with the site URL, the `e2e` command, and the new documentation entries
- [x] T105 [P] Add the public-website checks to `.github/workflows/ci.yml` so they block a change on failure (FR-055, SC-015)
- [x] T106 Run the full suite — `make test`, `pnpm test`, `pnpm e2e`, `make verify` — and confirm feature 001's fingerprint and 749 existing tests are unaffected
- [x] T107 Walk `specs/002-public-website/quickstart.md` end to end and correct anything that no longer matches

---

## Dependencies

**Phase order**: Setup (1) → Foundational (2) → user stories (3–8) → Polish (9).

**Blocking**:

- T013–T020 (specification remediation) block every user story. T013 blocks the home page directly; T014 blocks T089; T015 blocks T102; T017 blocks T076.
- T021 blocks T069. T022 and T023 block T080.
- T024–T027 must be observed failing before T090 makes them pass.
- T028–T037 block all page and endpoint work.
- T040, T052, T062, T071, T082 each regenerate the same generated file and must not run in parallel with one another.

**Story independence**: US1 through US5 are independent of each other once Phase 2 completes and can
be built in any order or in parallel by different people. US6 depends on T014's classification
decision but on no other story.

---

## Parallel Execution

**Phase 1**: T004, T005, T006 (infrastructure) alongside T008, T009, T010, T011 (tooling).

**Phase 2**: the three security tests T024, T025, T026 are independent files. So are the UI
primitives T032–T035. The specification amendments T018, T019, T020 touch different sections.

**Phase 3**: T038 and T039 (different endpoints), then T041–T044 (different pages), then T046 and
T047 (different test files).

**Across stories**: with Phase 2 complete, US1 (T038–T049), US2 (T050–T059), US3 (T060–T067), and
US5 (T081–T086) can proceed simultaneously — different routes, different endpoints, different test
files. Only the regenerated contracts file serializes them.

**Phase 9**: T093–T096 and T098–T102 are all independent files.

---

## Implementation Strategy

**MVP is Phase 1 + Phase 2 + Phase 3.** That delivers a complete, accurate company brochure — home,
services, products, about — with the security boundary already enforced and tested underneath it.
It is demonstrable on its own and is the first thing a reviewer sees.

**Then, in value order**: Careers (US2) is the highest-intent journey and has the most depth in the
dataset. News (US3) reuses its list-plus-detail pattern. Contact (US4) is the only write path and
carries the most test surface. Leadership (US5) is small but carries the sharpest disclosure risk.
US6 is last by priority but its Phase 2 tests run from the beginning.

**Do not defer Phase 9.** The accessibility, responsive, and metadata sweeps are how FR-053, SC-004,
and SC-011 are established; a feature that reaches Phase 9 with those unwritten has no evidence for
three of its success criteria.

## Notes

- **T013 is genuinely blocking, not bookkeeping.** The hero has no data source, and FR-005 and FR-006 cannot both be satisfied as written. Starting the home page before it is settled means building something that will be rejected.
- **T023 is the subtle one.** The seed's emptiness pre-flight iterates `INSERT_ORDER`, which lists seeded tables only. Without the change, a contact submission written before seeding leaves the environment non-empty in a way the pre-flight cannot see, and `seed` proceeds against a dirty database — the exact state feature 001's FR-014 exists to refuse.
- **T025's non-empty assertion is deliberate.** Feature 001 shipped a security suite that silently skipped 69 tests and reported success. A refusal test whose subject set is undefined passes by having nothing to check.
- Every task that regenerates `packages/contracts/src/generated/api.ts` writes the same file. They are sequenced rather than marked `[P]` for that reason alone.

---

## Phase 10: Convergence

*Appended 2026-08-02 after all 107 prior tasks were complete and verified (959 Python tests,
33 component tests, 199 end-to-end across three widths, zero axe violations, feature 001's
fingerprint unchanged). One constitution violation and three verification gaps. Ordered
CRITICAL first.*

- [X] T108 **CRITICAL** Write an audit entry for every anonymous refusal, in `apps/api/src/eaios_api/public/` and registered in `apps/api/src/eaios_api/main.py` — Constitution Principle X requires an audit record for authorization allows **and denies**, and FR-047 states it explicitly ("each refusal MUST write an audit entry recording what was attempted"). Neither happens: `audit_logs` held 2 rows before a request to `/internal/documents` and 2 after, because the 404 comes from FastAPI's default router with nothing in the path to record it. Record the attempted path, method, and decision — and **not** the request body, which FR-024c forbids propagating. Then extend `tests/security/test_anonymous_refusal.py`, which currently asserts status codes only and therefore passes while the requirement is unmet per Constitution X, FR-047 (missing)
- [X] T109 Bind the state-coverage check to an enumerated page list in `apps/web/e2e/` or `apps/web/tests/` — FR-054 and SC-012 require proof that *every* content region renders its states, but the only evidence is `tests/Section.test.tsx` exercising the shared component. `app/careers/page.tsx` and `app/contact/page.tsx` use `Section` zero times and hand-roll their own empty and error states, so a page that skipped one entirely would be unverified. Derive the page list from `e2e/pages.ts` so a page added later is covered by default per FR-054, SC-012 (partial)
- [X] T110 [P] Assert that submitted personal data never reaches application logs, in `tests/integration/test_contact_submission.py` — FR-024c forbids writing the sender's name, address, or message to logs at any level, and nothing checks it. The existing assertion covers the audit *row* only, so a `logger.info(payload)` in the submission path would satisfy every test in the suite. Capture the API's log output around a submission and assert none of the three values appears per FR-024c (missing)
- [X] T111 [P] Measure SC-014's three-second budget in `apps/web/e2e/performance.spec.ts` — the criterion states that main content becomes visible within 3 seconds and that no page holds an indefinite loading state, and neither half is measured. A timing assertion on a local stack is a floor rather than a guarantee, so assert the budget on the slowest content page and record what the measurement does and does not establish per SC-014 (missing)

## Phase 11: Convergence

- [X] T112 Implement the 90-day retention purge for contact submissions, in `services/worker/src/eaios_worker/tasks/` with a schedule on the Celery app or as a command in `scripts/seed/src/eaios_seed/cli.py` — FR-024b requires submissions to be retained for 90 days and then deleted, and `apps/web/components/ContactForm.tsx` already tells every visitor "we delete them after 90 days". Nothing deletes them: there is no beat schedule on the worker, no purge in the API, and the only `DELETE` against `contact_submissions` anywhere in the repo is a test cleanup fixture. A retention promise made to the public with no mechanism behind it is worse than no promise. Add a test that seeds one row older than the window and one inside it, runs the purge, and asserts exactly the aged row is gone — the boundary is the whole behaviour, and a purge that deleted everything would pass any check that only counted rows afterwards per FR-024b (missing)
- [X] T113 Give every error state a retry control, in `apps/web/components/Section.tsx`, `apps/web/app/careers/page.tsx`, and `apps/web/app/contact/page.tsx` — FR-027 requires an error state to "offer a manual retry", and `packages/ui/src/patterns/ErrorState.tsx` was built with a `retry` prop for exactly this. No caller anywhere in the application passes it. Every error state on the site instead says "Please refresh to try again", which tells the visitor to perform the retry rather than offering it. Pass a visitor-initiated control (a reload link or a form that re-requests the page — not an automatic retry, which FR-027 forbids because it amplifies a failing dependency), and extend `apps/web/tests/state-coverage.test.tsx` to assert every rendered error state contains one, so the next page written cannot omit it per FR-027 (partial)
- [X] T114 Assert that an accepted submission is delivered nowhere, in `tests/integration/test_contact_submission.py` — SC-007 requires "zero messages are delivered anywhere" and FR-023a spells out the prohibition: no email, no queued job, no notification, no external call. The only statement of this anywhere in the codebase is a docstring in `apps/api/src/eaios_api/public/router.py`, and `grep -rn "deliver" tests/` returns nothing. A future change that enqueues a notification would satisfy every existing assertion. Check the broker queue length across a submission and assert no task was enqueued, and assert no outbound HTTP call is attempted — Constitution Principle VII gates send actions on human approval, and a public site has no approver per SC-007, FR-023a (missing)
- [X] T115 [P] Apply FR-027a's 150ms threshold before the loading state appears, in `apps/web/components/ContactForm.tsx` — the requirement names two thresholds so SC-014 has bounds to test against. The 10-second bound exists in `apps/web/lib/api.ts` and is now measured by `e2e/performance.spec.ts`; the 150ms delay does not exist at all, and the form switches to "Sending…" on the first frame. While there, settle the other half of FR-025's parenthetical: it names "the careers filter and the contact form" as the feature's only client-fetched regions, but `apps/web/components/VacancyFilters.tsx` is a plain GET form that navigates, so it is server-rendered and needs no loading state. Assert that, so the spec's claim about which regions fetch on the client is a checked fact rather than a sentence per FR-027a (missing)
- [X] T116 [P] Bind the sitemap's page list to the shared one, in `apps/web/app/sitemap.ts` and `apps/web/e2e/pages.ts` — FR-042 requires a machine-readable index of the public pages and FR-001a fixes which routes are excluded from it, but the list is written out twice: `staticPaths` in the sitemap and `PUBLIC_PAGES` in `pages.ts`. The sitemap's own comment says "the per-page metadata audit derives its page list from this file", and `e2e/metadata.spec.ts` imports from `pages.ts` instead — so the comment is already wrong and the two lists are free to drift. A page added to one and not the other is either absent from the sitemap or unchecked by the metadata, accessibility, responsive, state-coverage, and performance sweeps that all read the shared list. Move the list to a module the application can import, have both read it, and assert `/portal` and `/status` are absent from the sitemap per FR-042, FR-001a (partial)

## Phase 12: Convergence

- [X] T117 **CRITICAL** Write an audit entry for every retention purge, in `services/worker/src/eaios_worker/tasks/retention.py` — Constitution Principle X requires an audit record for every consequential operation, and the deletion of a member of the public's personal data is one: it is irreversible, it is the thing an auditor asks about ("when was this person's record deleted, and by what?"), and the enumerated list in Principle X is illustrative rather than exhaustive. The purge currently emits a structlog line and nothing else — `grep -n "AuditLog" services/worker/src/eaios_worker/tasks/retention.py` returns nothing. Write one entry per run carrying actor (`SYSTEM`), tenant, action (`retention.purge`), resource type, decision, reason, sources, and timestamp, and record the **count** deleted rather than any sender, address, or subject, which FR-024c forbids propagating. A run that deletes zero rows MUST still write an entry: "the job ran and found nothing" and "the job never ran" are the two states this record exists to distinguish per Constitution X (missing)
- [X] T118 Run Celery beat so the retention schedule is actually read, in `services/worker/Dockerfile` or as a service in `infrastructure/docker-compose.yml` — FR-024b requires submissions to be deleted after 90 days, and the mechanism is complete except that nothing invokes it: the Dockerfile's command is `celery -A eaios_worker.celery_app worker --loglevel=info`, with no `-B` and no separate beat service, so `beat_schedule` is configuration no process reads. This is the same defect as the unregistered task found and fixed during T112, one layer higher — the schedule is correct, the task is registered, and the purge can still never fire. Then make the check reach the deployment: `tests/integration/test_retention.py::test_the_purge_is_scheduled_for_every_tenant` asserts the schedule exists in the config object, which was true throughout and proves nothing about whether beat runs. Assert against the container's actual command, or against beat's own startup, so "configured" and "running" stop being the same assertion per FR-024b (missing)
- [X] T119 Check that the Server Error page discloses nothing, in `apps/web/tests/` — SC-013 names the Not Found **and** Server Error pages, and only the first is checked: `apps/web/e2e/boundary.spec.ts` covers not-found, while nothing anywhere renders `apps/web/app/error.tsx`. That component receives the `Error` object as a prop and deliberately renders none of it, which is correct and entirely unverified — a `{error.message}` added during a debugging session would ship past every test in the repository. Render it directly with an error carrying a driver name, an internal hostname, a port, and a stack, and assert none of it reaches the document; assert the route onward FR-029 requires is present; and include a guard proving the probe would notice, since a component that renders nothing passes a "does not contain" assertion for the wrong reason per SC-013, FR-029 (missing)
- [X] T120 [P] Prove failure containment at the page level, in `apps/web/tests/state-coverage.test.tsx` — FR-030 requires a failing section to stay contained rather than replacing the page, and the only evidence is `tests/Section.test.tsx`, which exercises the shared component in isolation. Every page-level sweep fails *all* sources together, so no test has one region fail while a sibling succeeds — which is the actual requirement. `/` is the sharpest case with three independent regions, and `/contact` matters most: FR-030 is why the form and the office list are separate regions, so a failing office read must leave the form usable. Fail exactly one source and assert the others still render their content per FR-030 (partial)
- [X] T121 [P] Assert every news item is reachable, in `apps/web/e2e/content-journeys.spec.ts` — FR-016 requires the visitor to be able to reach every item, and `app/news/page.tsx` calls `getNews(50)` against a dataset that currently holds 11. The page therefore satisfies the requirement by volume rather than by design: there is no pagination and nothing compares what is rendered to the `total` the API reports, so the day the dataset crosses the ceiling, items disappear from the site silently and every existing test still passes. Compare the rendered item count against `total` from `/public/news` so the ceiling announces itself instead per FR-016 (partial)

## Phase 13: Convergence

- [X] T122 Summarize products on the home page and link every block to its full page, in `apps/web/app/page.tsx` — FR-005 requires the home page to summarize "services, products, recent news, and current openings with links to their full pages", and products is absent entirely: the page loads `getServices`, `getNews`, and `getVacancies`, and `grep -n "product" apps/web/app/page.tsx` returns nothing. Every "Products" string in the served HTML is a navigation link, so a visitor who lands on the home page — the P1 journey — is never shown that the company has products at all. The second clause is unmet too: `grep -c 'href="/news"\|href="/careers"\|href="/products"'` on that file returns 0, so each block summarizes without offering the way onward the requirement names. Add a products `Section` reading `getProducts` and a link from each of the four blocks to its listing page. Then extend `apps/web/tests/state-coverage.test.tsx`: its FR-030 containment cases hard-code the home page's region count and its comment reads "Three independent regions (FR-005)" — a number this task changes, and one that was wrong when written per FR-005, US1 (missing)
- [X] T123 [P] Measure SC-003's three-interaction budget, in `apps/web/e2e/client-journey.spec.ts` — the criterion states a candidate can reach the full description of a specific open role from the **site root** in three interactions or fewer, and nothing measures it: the nearest test (`content-journeys.spec.ts`, "a role opens to its full description") starts at `/careers`, which skips the interaction the criterion is mostly about, and counts nothing. The path is currently two clicks — Careers in the primary nav, then a role — so this passes today; the point is that it would stop passing if Careers left the primary navigation, if a filter had to be applied first, or if the home page's open-roles block lost its link (see T122). Start at `/`, click through, and assert the count against a named constant so the budget is a number in the file rather than an implicit property of the current layout per SC-003 (missing)

## Phase 14: Convergence

- [X] T124 Assert that a data change is visible on the next request, in `apps/web/e2e/` — FR-006b requires every displayed record to be rendered from the dataset **at request time** rather than copied into the presentation layer at build time, "so a reseed is immediately visible", and `research.md` R7 chose dynamic rendering for exactly this reason, calling build-time prerendering "the exact class of staleness feature 001 spent five convergence passes eliminating". The behaviour currently holds — updating a service name in the database and requesting `/services` shows the new name immediately — but the entire implementation is `cache: "no-store"` on one line of `apps/web/lib/api.ts`, and no test mentions it: `grep -rn "FR-006b\|no-store" apps/web/e2e apps/web/tests` returns nothing. Deleting that option, or Next deciding to prerender a page that stops using a dynamic API, would restore the staleness silently, because every other check reads a site whose content happens to match the database it was built against. Write the change through the owner engine, request the page, assert the new value appears, and restore the original in a fixture so a failure mid-test cannot leave the dataset altered — the fingerprint check would then fail for an unrelated reason per FR-006b, plan R7 (missing)
- [X] T125 [P] Make the generated-content test cover what its name claims, in `apps/web/e2e/client-journey.spec.ts` — the test at line 50 is called "services and products show real generated content" and visits `/services` only. Nothing is actually unchecked: `/products` is swept by the accessibility, metadata, responsive, performance, and state-coverage suites, which all iterate the shared page list. The defect is the name, and it is the same defect as the `// Three independent regions (FR-005)` comment T122 corrected — a statement in the suite that reads as coverage and is not. Either visit both pages or rename it for what it does per SC-002 (partial)

## Phase 15: Convergence

- [X] T126 **CRITICAL** Declare typed response models for the public error responses, in `apps/api/src/eaios_api/public/schemas.py` and the route decorators in `apps/api/src/eaios_api/public/router.py` — the constitution's Mandatory Contracts section requires every endpoint to "define typed request and response models (Pydantic on the backend, matching types on the frontend)", and the served OpenAPI currently describes responses the API never returns. `/public/contact` declares `422 -> HTTPValidationError` (FastAPI's default `{detail: [...]}`) while `public_validation_handler` actually returns `{"title": ..., "status": 422, "errors": [{"field", "message"}]}`; `/public/news/{slug}` and `/public/vacancies/{slug}` declare a bare description while returning `{"detail": "No such item."}`. `contracts/public-api.yaml` already models both correctly as `Problem` and `ValidationProblem` — the document is right and the API disagrees with it. This is not cosmetic: `packages/contracts` is generated from the API's own schema, which is why `apps/web/lib/api.ts` hand-codes the 422 shape from a comment rather than importing a generated type. Add the two models, attach them with `responses={404: ..., 422: ...}`, regenerate `packages/contracts`, and have `submitContact` use the generated type so the frontend's "matching types" clause is met by construction per Constitution: API contracts, FR-045 (contradicts)
- [X] T127 Validate the live public API against its contract, in `tests/integration/` — nothing compares the running endpoints to `specs/002-public-website/contracts/public-api.yaml`, and that absence is why T126's drift survived every phase of this feature. Feature 001 already established the pattern this needs: `tests/integration/test_health_contract.py` validates live responses against `contracts/health-api.yaml`, and the equivalent for the public surface was never written. Check every path in the contract against the served OpenAPI in both directions — a path in the document that the API does not serve is as much a defect as an endpoint the document does not describe — and validate at least one real response body per endpoint against its declared schema, including an error body, which is the case that drifted. Include a guard proving the check reads a non-empty path set, since a comparison of two empty collections is the failure mode this whole feature keeps rediscovering per plan: contracts/ (missing)

## Phase 16: Convergence

- [X] T128 Verify the committed contract types against the served schema in CI, in `.github/workflows/ci.yml` and `packages/contracts/package.json` — `packages/contracts/src/generated/api.ts` is committed on purpose (`.gitignore` line 34 states the decision) and produced by a manual `pnpm generate`, so nothing keeps it in step with the API. `grep -n "generate" .github/workflows/ci.yml` returns nothing, and the `web` job's `pnpm typecheck` runs against the committed file — a stale one typechecks perfectly and the frontend builds against types describing an API that no longer exists. This is the drift T126 and T127 just fixed one layer up, moved down a level: there the contract *document* disagreed with the served schema, here the *generated client* can. The evidence is T126 itself — changing the API's error models required remembering to regenerate by hand, and nothing would have caught the omission. In the `stack` job, where the API is already running, regenerate into a temporary path and fail if it differs from the committed file, reporting the diff so the fix is obvious (`pnpm --filter @eaios/contracts generate`). Add the same check to whatever a developer runs locally, so the failure is not first discovered in CI per plan: contracts/, Constitution: API contracts (missing)
- [X] T129 [P] Correct the two statements in `specs/002-public-website/data-model.md` that the schema contradicts — the Contact Submission section says migration 0003 "enables and **forces** RLS on this table". It does not, and must not: `SELECT relforcerowsecurity FROM pg_class WHERE relname='contact_submissions'` returns `f`, and migration 0002's own docstring records that `FORCE ROW LEVEL SECURITY` is deliberately withheld because PostgreSQL exempts table owners from RLS and that exemption is what lets `eaios_owner` run migrations and seed both tenants — and now what lets the FR-024b retention purge delete rows at all. A reader who trusted this document and "fixed" the migration would break the seed, the migration path, and the purge in one change. The same section gives `sender_email` as 1–254 characters where both FR-019 and the `ck_contact_submissions_sender_email_length` check constraint say 3–254. Neither is a code defect; both are design-document statements that a future reader would act on per plan: data-model.md (contradicts)

## Phase 17: Convergence

- [X] T130 Prove the open-vacancy filter actually filters, in `tests/integration/test_public_content.py` — FR-014 serves "every open vacancy", `contracts/public-fields.md` states that `is_open` is "a filter applied server-side, not a field — closed vacancies are absent from the response entirely", and `apps/api/src/eaios_api/public/queries.py` line 281 implements it. Nothing demonstrates it works. `scripts/seed/src/eaios_seed/generators/public.py` line 203 hard-codes `is_open=True`, so NileTech has 11 open vacancies and 0 closed ones in both profiles, and `test_only_open_vacancies_are_served` asserts `len(served) == open_count` where `open_count` equals the total — the assertion is `11 == 11` whether the `is_open` predicate is present or deleted. The spec's edge case "Closed vacancy reached directly", which requires that a no-longer-open vacancy must not appear as though applications are welcome, has never been exercised. Create the condition rather than waiting for the seed to supply it: in a fixture, flip one vacancy to closed, assert it disappears from `/public/vacancies`, assert its detail address returns 404 rather than a page inviting applications, assert the remaining count drops by exactly one, and restore the row — restoring in the fixture, not the test body, because a mid-test failure that left a vacancy closed would fail the fingerprint check later and blame the generator. Do **not** change the generator to emit closed vacancies: `vacancies` is fingerprinted, so that moves the committed digest per FR-014, Edge Case: closed vacancy, contracts/public-fields.md (partial)
- [X] T131 [P] Enforce the token property R4 names, and fix the file that breaks it, in `apps/web/app/status/StatusPage.tsx` plus a check in `apps/web/tests/` — research decision R4's implementation amendment states that the property the styling decision "actually wanted" is "no hard-coded colour or spacing outside the token layer", and FR-031 requires a defined palette applied uniformly. `packages/ui/src/components.css` honours it completely — zero hex literals. `StatusPage.tsx` does not: it renders `border: "1px solid #b00"` and `borderBottom: "1px solid #ddd"` inline, and `tokens.css` already defines `--danger: #a3262c` and `--border: #d3dde6` for exactly these. Two consequences, neither cosmetic: those colours have never been through the palette-level contrast check FR-035 depends on, and the property has no enforcement, so the next inline colour is equally invisible. Replace both with `var(--danger)` and `var(--border)`, then add a check that scans `app/` and `components/` for hex literals in style props and fails on any — with a guard proving the scan reads real files, since a scan that matches nothing passes exactly like a clean codebase per plan: research.md R4, FR-031 (partial)

## Phase 18: Convergence

- [X] T132 Bound both anonymous write paths, in `apps/api/src/eaios_api/public/` and `specs/002-public-website/contracts/public-api.yaml` — FR-024d requires contact submissions to be limited to **5 accepted submissions per client address per hour**, and FR-047b requires refusal auditing to be limited to **60 entries per address per hour**, after which further refusals are still refused but recorded as one coalesced entry stating the count. Neither exists: `grep -rniE "rate.?limit|throttl|429"` across `apps/api/src`, `packages/core/src`, and the web client returns a single hit, and it is `refusal_audit.py` line 27 describing rate limiting as "an open item" — a docstring the clarification has now made stale, so update it too. The refusal path is the more urgent of the two, because FR-047 makes an anonymous request to any non-public address write a row, so a loop against `/admin` grows `audit_logs` without limit and buries the real signal the audit trail exists to carry. Requirements that follow from the wording: a refused submission MUST NOT create a stored record and MUST NOT be reported to the visitor as success (FR-024d); every refusal MUST still be refused when the audit bound is reached (FR-047b); public reads MUST stay unbounded. Declare the new refusal response in `contracts/public-api.yaml` and give it a Pydantic model — `tests/integration/test_public_contract.py` compares the served schema against the document and will fail if the endpoint starts answering with a status the contract does not describe. Then satisfy SC-016 with tests that exceed each bound and assert the stored-record count and the audit-entry count, not merely the status code per FR-024d, FR-047b, SC-016 (missing)
- [X] T133 [P] Render a defined fallback for an empty field, in `packages/ui/src/` and the six call sites in `apps/web/app/` — FR-008a requires content that is short but present to render as written, and a field that is **empty or whitespace-only** to render a defined fallback rather than a blank region that reads as a broken card. Every such field currently renders bare: `{service.summary}` (services page and the home summary), `{product.tagline}`, `{leader.bio}`, and `{office.address}` on both About and Contact. An empty value renders nothing at all, which is the gap the requirement names. Add the fallback once in the shared layer rather than at six call sites, so the seventh field added later inherits it. Then extend `apps/web/tests/state-coverage.test.tsx`, whose fixtures currently supply well-formed values for every field: add a mode that renders each page with empty and whitespace-only strings, and assert no region collapses and no card renders a heading above nothing. The dataset contains no empty fields today, so this is territory no existing test covers and none would notice regressing per FR-008a (missing)
- [X] T134 [P] Record a leadership profile that cannot be resolved, in `apps/api/src/eaios_api/public/queries.py` — FR-013a requires such a profile to be omitted from the public response **and** the condition to be recorded so it is discoverable. Omission already holds, by accident rather than by decision: line 185 uses an inner `.join(User, User.id == LeadershipProfile.user_id)`, so a profile whose user row is missing simply never appears. The recording half does not exist, which means a profile silently vanishing from a public page is indistinguishable from one the generator never produced — and feature 001's coherence checks would be the only thing to notice, long after the page had been served incomplete. Compare the count of profiles for the tenant against the count the join returns, and when they differ, record the difference identifying the *profile* — never the person, since FR-013 forbids exposing any other attribute of that individual and an identifier in a diagnostic record is still an exposure. Prove it with a test that unlinks one profile at runtime and restores it in a fixture, asserting the profile leaves the response, the remaining profiles still render (FR-030), and the condition was recorded; the dataset resolves every profile today, so the behaviour is otherwise unreachable — the same shape as the closed-vacancy gap T130 closed per FR-013a (partial)

## Phase 19: Convergence

- [X] T135 Tell the visitor what actually happened when a submission is bounded, in `apps/web/lib/api.ts` and `apps/web/components/ContactForm.tsx` — FR-024d requires the refusal to be "designed, informative"; the API produces exactly that (`{"title": "Too many messages", "status": 429, "detail": "We have received several messages from you recently..."}`) and the site throws it away. `lib/api.ts` line 141 raises `ApiError` for any status that is not 202 or 422, `ContactForm`'s catch sets `status="failed"`, and that branch renders one fixed sentence: "We could not reach our systems just now. Nothing was saved — please try again in a moment." Every clause of it is false for a 429 — the systems were reached, the message was understood and rejected deliberately, and the visitor is told to try again *in a moment* when the window is an hour. Being wrong is worse here than being generic, because it invites exactly the retry the bound exists to stop. Return the 429 as a distinct outcome from `submitContact` rather than an exception, render the server's `detail` rather than a second copy of the sentence written in the client, and keep the form's contents so the visitor can send it later (FR-021 already requires that on validation failure and the same reasoning applies). Then extend `apps/web/tests/ContactForm.test.tsx`, which currently drives only 202, 422, and a thrown error — a 429 has never reached that component per FR-024d (partial)
- [X] T136 [P] Apply the empty-field fallback to the news body, in `apps/web/app/news/[slug]/page.tsx` — FR-008a requires a field that is empty or whitespace-only to render a defined fallback rather than a blank region. Line 51 renders `item.body.split(/\n\s*\n/).map(...)`, and an empty body splits to `['']`, producing a single empty paragraph under the headline: the exact gap the requirement names. This was missed by T133, which routed thirteen call sites through the shared `Text` primitive but only the ones rendering a single value — a field rendered as a *list* of paragraphs did not match the pattern being looked for. Render the fallback when the body has no non-whitespace content, and extend the empty-field sweep in `apps/web/tests/state-coverage.test.tsx` to cover the two detail pages, which its page registry does not include at all: it is bound to `PUBLIC_PAGES`, and detail routes are reached only through their lists per FR-008a (partial)

## Phase 20: Convergence

- [X] T137 Correct the state inventory in `specs/002-public-website/data-model.md` — section 5, "What this feature does not add", asserts "No new object-storage keys, vector entries, cache namespaces, or background jobs." Two of those four are now wrong. `apps/api/src/eaios_api/public/rate_limit.py` writes `eaios:ratelimit:{bucket}:{identity}` keys into Redis for FR-024d and FR-047b, which is a new cache namespace, and `services/worker/src/eaios_worker/tasks/retention.py` registers `eaios.retention.purge_expired_submissions` on a beat schedule for FR-024b, which is a background job — the first this project has. Neither existed when that sentence was written and both were added by later convergence phases without anyone revisiting it. This is a design document, so the cost is not a broken system but a reader auditing the feature's state surfaces and missing two of them; the Redis keyspace and the scheduled job are precisely the things an operator needs to know exist. Replace the claim with what the feature *does* add, and say for each whether it is durable or ephemeral, since the counters expire and the job runs forever per plan: data-model.md (contradicts)
- [X] T138 Clear the rate-limit counters on reset, in `scripts/seed/src/eaios_seed/loaders/stores.py` — `make reset` announces "This destroys every row, object, vector, and cache entry in the local environment", and `reset_all` honours that for Redis by scanning `cache_namespace(slug)`, which expands to `eaios:cache:{company}:*`. FR-024d's counters are keyed `eaios:ratelimit:{bucket}:{identity}`: a different prefix, and deliberately not tenant-scoped because the caller is anonymous and has no tenant. A reset therefore leaves them behind, and a developer who resets to get a clean environment keeps whatever bound they had accumulated for up to an hour. The consequence is small; the pattern is the one this feature has repeatedly got wrong, and `data-model.md` section 3 gives `contact_submissions` its own row in the integration table for exactly this class of concern — new state, and the paths that manage state not learning about it. Delete the rate-limit keys in `reset_all` alongside the cache namespaces, extend `tests/integration/test_reset.py` (or the equivalent) to assert a counter written before a reset is gone after it, and add the row to `data-model.md` section 3 that this concern deserves per plan: data-model.md, FR-024d (partial)

## Phase 21: Convergence

- [X] T139 [P] Remove the unread `degraded` field, or the comment that claims it is read, in `apps/api/src/eaios_api/public/rate_limit.py` — `Decision.degraded` is assigned once, at line 124 in `consume`'s fail-open path, and read nowhere: `grep -rn "\.degraded" apps/api/src packages/core/src` returns only that assignment. Its comment states "True when the counter could not be reached, so `allowed` is a fail-open default rather than an observation. Callers that log should say which" — describing a responsibility no caller takes, and one that is already discharged inside `consume`, which logs `ratelimit.unavailable` itself. So the field is redundant rather than pending: there is no half-finished feature here, only a comment asserting a use that does not exist. Either drop the field and let the internal log stand as the record of a degraded bound, or keep it and correct the comment to say what it is actually for. Small, and worth doing for the same reason two larger instances of this pattern were: `ErrorState.retry` was a prop no caller passed until a convergence pass found every error state on the site telling visitors to refresh, and `// Three independent regions (FR-005)` read as a citation while the requirement named four. A statement in code is read as true per plan: rate_limit.py (unrequested)
