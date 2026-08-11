# Feature Specification: Foundation — Monorepo, Local Environment & Deterministic Two-Tenant Dataset

**Feature Branch**: `001-foundation-tenant-seed`

**Created**: 2026-07-31

**Status**: Complete

**Evidence**: CI run [31443872819](https://github.com/youssefhatembahig6-alt/enterprise-ai-os/actions/runs/31443872819) at commit `429fdcba8b22d10e356874f0fff1995a83a36145` — API conclusion `success`, 7/7 jobs green, 86 successful steps, 3 conditional log-dump skips, 0 failures. All 172 tasks and all five checklists are closed. FR-047/FR-047c and SC-012 are met by that run; SC-002's cross-platform fingerprints agree.

**Input**: User description: "Build the foundation of the Enterprise AI Operating System according to docs/Enterprise_AI_OS_EDITED.html. Create a monorepo and a reproducible local development environment. Create two synthetic companies: NileTech Solutions (software and business automation, offices in Cairo, Alexandria and Dubai, ~200 generated employees, departments Engineering/HR/Sales/Finance/Legal/Customer Support/Operations/Executive Management) and Delta Retail Group (an independent second tenant with separate users, departments, data, files, documents, vectors, caches, jobs and audit logs, used for tenant-isolation security tests). Generate deterministic data for companies, departments, users, roles, managers and reporting relationships, employee profiles, leave balances and requests, attendance, training, performance reviews, customers, products, orders, invoices, sales targets, expenses, budgets, contracts, policies, vacancies, news, services, leadership profiles, and office information. The seed process must reproduce the same dataset from an empty environment."

## Clarifications

### Session 2026-07-31

- Q: Are any entities legitimately non-tenant-scoped, and how is the cross-tenant Platform Admin modelled? → A: Permissions are a global catalog; roles/users/everything else are tenant-scoped; Platform Admin is a platform-level user bound to no company; the spec names an explicit allowlist of global tables and the audit treats anything not on that list as a violation.
- Q: What are the permitted data-classification levels? → A: Four — PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED — where RESTRICTED is the payroll / executive-contract tier requiring an explicit grant beyond role alone.
- Q: How are roles assigned, and does the dataset include fixed demo personas? → A: Each user holds exactly one primary role, plus Manager additionally if they have direct reports. The dataset includes a fixed, documented persona set with stable identifiers covering every actor the blueprint's access-control acceptance tests require.
- Q: What transactional data volume and history window should be generated? → A: A 24-month window ending at the pinned reference date, with explicit per-entity-family target counts; attendance is capped at the most recent 6 months so seed time stays within budget.
- Q: What must the seed do when run against a non-empty environment? → A: Refuse with a clear message and a non-zero exit status; a destructive rebuild requires an explicit, separate reset action. Partial runs are detectable via a completion marker in the dataset manifest.

### Session 2026-08-01 — checklist remediation

Two confirmed conflicts and four traceability holes were found by the requirements-quality checklists
and fixed here. No requirement was removed or narrowed.

- **Conflict fixed** — FR-030 mandated public content "for NileTech" while the FR-020b volume table allocated 20 public items to Delta Retail. Resolved in favour of both companies: `PUBLIC` classification must exist for both tenants (FR-010c), and public content is itself an isolation surface.
- **Conflict fixed** — FR-024a claimed the tenants share "nothing except the global permission catalog", contradicting FR-009a's four-entity allowlist. FR-024a now defers to the allowlist.
- **Gap closed (FR-009d)** — Row-Level Security was required by Constitution Principle I and designed into the plan, but no requirement demanded it. An implementer reading only this spec could have satisfied every requirement and shipped without it.
- **Gap closed (FR-012a/b/c)** — the spec asserted reproducibility as an outcome without requiring the controls that produce it: encoding and line-ending discipline, dependency version pinning, and a fixed committed seed value.
- **Gap closed (FR-017a)** — a committed known-good fingerprint. Verification previously proved only self-consistency.
- **Gap closed (FR-047b)** — cross-platform verification, without which SC-002's cross-machine claim was never exercised.
- **Gap closed (FR-048)** — the specification used "documented" as though it were a defined term in six requirements while defining no documentation artifact, leaving all six unverifiable.

**Resolved by direct alignment with the blueprint (no question required):** company-vs-customer terminology and what the two tenants share (FR-024a, Glossary), document ownership convention (FR-031a), dataset-fingerprint scope (FR-015a), and the eight access-control acceptance scenarios the dataset must be capable of supporting (FR-047a, SC-013).

### Session 2026-08-05 — retrospective clarification

Run after this feature was implemented and converged, and after feature 002 built on it.
The questions below are the ones whose absence would cost the **next** feature — the
authenticated portal and its policy engine — rather than ones that would re-litigate
shipped work. **No requirement below is removed or narrowed.**

- Q: When an authenticated caller requests a resource that exists but belongs to another tenant, what must the response be? → A: 404, always — indistinguishable from a resource that does not exist. The audit entry records the real reason, so the trail keeps the truth the response withholds.
- Q: SC-012 requires the checks to "block the change", but the project is not under version control — what does "block" mean? → A: The repository is placed under version control and the gate is a pull request whose checks must pass. `ci.yml` already exists and has never been triggered by anything. *(Historical — true when recorded on 2026-08-05, and superseded: the repository is under version control with a remote, and CI run 31443872819 concluded `success`. The decision itself stands.)*
- Q: How must a verification check behave when its subject is empty — for example FR-045's vector-store leg under decision D2? → A: Report as **skipped**, naming the deferral that emptied it. A silent pass is indistinguishable from a real one.
- Q: Should dependency direction between packages be a requirement, or a code-review convention? → A: A stated requirement, enforced by an automated import check, so a backwards dependency fails the build rather than depending on a reviewer noticing.
- Q: How is the API versioned, given `packages/contracts` generates client types from it? → A: No version segment in the path. The published OpenAPI document and the generated types are the compatibility gate, and that gate already exists.

### Session 2026-08-06 — architecture checklist remediation

Closing the 24 open items in [checklists/architecture.md](checklists/architecture.md). **No requirement
below is removed or narrowed.** Three items needed nothing — FR-001 already defines responsibilities
rather than names (CHK001), FR-002 already closes the service set (CHK004), and FR-014c already covers
a dependency lost mid-run as an outcome rather than a case list (CHK020). The rest were genuine gaps,
and they share a pattern worth naming: **the system already behaves correctly and no requirement said
it must**. `_safe_detail` in the health probes suppresses connection strings and cites "CHK017" in its
own docstring — the code was written to satisfy a checklist item rather than a requirement, which is
the same failure FR-001a was added to fix, one layer up.

- **Added FR-002a–c** — startup ordered by readiness; frontend behaviour when the API is unreachable;
  port conflicts. The last backs an edge case that had been listed with no requirement behind it.
- **Added FR-003a–e and amended FR-003** — liveness versus readiness, bounded per-dependency timeouts,
  partial availability as degraded-and-refused, anonymous access, and disclosure limits. FR-003 now
  names the same five services as FR-002 and FR-039–FR-042, so "every backing service" is countable.
- **Added FR-005a, FR-006a** — which settings belong in example configuration, and a three-part
  checkable test for "non-production placeholder" replacing a judgement call.
- **Added FR-007a** — a failed migration leaves a known schema version. Reversibility and the
  requirement to recover are separate claims; only the first was stated.
- **Added FR-014d–f** — a stable exit-code scheme separating refusal from failure, a message-content
  standard, and reset against an already-empty environment.
- **Added FR-031b** — object-storage writes fail fast rather than retry, recorded as a decision with
  its revisit condition, not left as an omission.
- **Defined "standard developer machine"** under Assumptions. SC-001 and SC-008 both budget time
  against it and neither could be evaluated without it.

**Stated but not yet verified.** These are new requirements, and writing one does not discharge it.
Four have no executable evidence today: FR-002c's port-conflict message, FR-006a's refuse-to-start
condition outside a local environment, FR-014d's documented exit-code scheme, and FR-014f's
empty-environment reset. They are tracked as follow-up work and are **not** claimed as met.

### Session 2026-08-06 — data checklist remediation

Closing the 26 open items in [checklists/data.md](checklists/data.md). Two needed nothing: the
synthetic code repository is recorded as out of scope by decision D4 (CHK011), and migration
downgrades were covered hours earlier by FR-007a (CHK014). The remainder split into two kinds.

**Requirements that were unmeasurable as written.** "Plausible rather than uniform" (FR-020),
"complete enough to exercise every entity family" (FR-022), and "non-placeholder content" (US5)
all read as testable and were not. Each now resolves to something countable: FR-020d states the
headcount proportions, FR-022 defers to the FR-020b table as its enumeration, and FR-030a gives
four checkable conditions in place of a claim about prose quality. FR-020e settles the question
CHK025 raised — the ±10% tolerance is against the *target*, never run-to-run, which would have
made FR-011 unfalsifiable.

**Requirements the schema already satisfied in silence.** All forty foreign keys declare their
delete behaviour; identifiers are derived from stable URNs rather than from draw order; monetary
columns are fixed-point. Each was a property of the code that no requirement demanded — FR-033a–c,
FR-011a, and FR-038a now demand them. The new content requirements (FR-021a, FR-023a, FR-026a–b)
are the same story: Delta's five departments, the three marker phrases per company and their
three deliberately different shapes, the five salary bands, and the per-department job titles were
all real and all unwritten, and the isolation probe of FR-045 is only as strong as the markers it
searches for.

**Also added**: FR-010d–e (all four classifications non-empty per company; how the closed set may
change), FR-008a (indexing as a schema property, not a generator workaround), FR-043b (audit
immutability, previously only in the constitution), FR-012d and FR-016a (what a reference-date
change invalidates; when a generator-version bump is required), and FR-020f (the reduced CI
profile, which existed only in the tooling).

**Stated but not yet verified**: FR-008a's index coverage and FR-010e's classification ordering.
Added to the same follow-up as the four above.

### Session 2026-08-06 — isolation checklist remediation

Closing the 19 open items in [checklists/isolation.md](checklists/isolation.md). The checklist's own
note says a gap here is a security defect rather than a documentation one, and two of the items bear
that out.

**Three leak paths the specification had never considered** — the checklist named them and it was
right. FR-024b makes log output an isolation surface: logs aggregate across tenants by construction,
are retained longer than the database, and are read more widely. FR-024c records that a dump contains
*both* tenants, so "we have backups" is not "we can restore one tenant" — per-tenant export is out of
scope and now says so. FR-024d records tenant deletion as out of scope for the same reason: in a
shared-schema design it touches every table, prefix, namespace, and the audit trail that must outlive
it, and discovering that late is expensive.

**The one that matters most is FR-045c.** Every isolation check must be demonstrably able to fail,
with the falsification in the suite. A probe searching the wrong store, an audit whose query returns
nothing for an unrelated reason, and a genuinely clean system all report the same green — so SC-004's
0% is evidence only if a non-zero result was reachable. SC-004 now also states its denominator, since
a rate over an undefined population is not a measurement.

**Also added**: FR-009e (an unknown tenant identifier behaves as an absent one, so it cannot become an
oracle for which tenants exist), FR-014g (the seed writes both tenants and runs as the schema owner,
making it the one writer RLS cannot catch), FR-024e (identifiers are non-secret but non-authoritative —
no caller-supplied value selects a tenant), FR-039a–b and FR-040 (tenant-first keys, built by a
function that refuses to construct one without a tenant, rather than detected by audit after the object
is written), FR-042a (the job *payload* and queue, not only the job record), FR-044a (a reference to a
global-allowlist entity is not a violation, or the audit is red on every role in the system), FR-045b
and FR-045d (case-insensitive substring matching; and identical content generated by both companies is
coincidence, not a leak), and FR-043c — the guarantee here is **structural, not request-time**, which is
the over-reading this feature most invites.

Two needed nothing: FR-044 already enforced the allowlist as a closed set in both directions (CHK009),
and FR-023a had quantified the marker phrases hours earlier (CHK013).

### Session 2026-08-06 — process checklist remediation

Closing the 22 open items in [checklists/process.md](checklists/process.md), the last of the four.
Five needed nothing — FR-045a already handles a check whose subject is empty (CHK006), FR-020f the
reduced profile (CHK005), FR-048 the configuration surface (CHK020), the glossary the terminology
rule (CHK022), and the carry-forward list was already worded as an obligation (CHK024, now stated
outright).

**The traceability hole the checklist named.** Constitution Principle VIII requires tenant-isolation
and integrity tests to be written first, and no functional requirement asked for it — the plan
carried it alone. FR-047d asks for it now, including the part that is the substance rather than the
ceremony: the test must be **observed failing**, because one written afterwards is shaped by the
implementation and asserts what the code does rather than what the requirement says.

**"Documented" now resolves to a file.** FR-048 listed six things the documentation set must contain
and named no locations, so six requirements pointed at an artifact nobody could open. FR-048a is a
table mapping each to its home — `docs/running.md`, `docs/personas.md`, `docs/dataset.md`,
`docs/determinism.md` — and FR-048b makes the generated parts machine-compared, so drift fails a gate
instead of waiting for a reader to notice.

**Coverage is by requirement, not by line (FR-047h).** A line-coverage percentage is satisfiable by
tests that execute code without asserting on it, and this project's recurring defect has been checks
that cannot fail rather than code that is never run. FR-046b generalises FR-045c to all four families
for the same reason.

**Also added**: FR-046a (each verification requirement maps to exactly one check family, so "the four
checks passed" says which requirements were exercised), FR-047e–g (every check runnable locally by the
CI command; known state before and after; the CI platform named and its config in the repository),
FR-048c–d (written for a newcomer, with prerequisite tools and versions stated), FR-049 (the decision
record continues past this feature), SC-016 (a 20-minute budget for the verification suite — one too
slow to run before pushing stops being run before pushing), and record-predicate wording for
FR-047a so SC-013's "8 of 8" is computed rather than judged.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - One-Command Local Environment (Priority: P1)

A team member clones the repository onto a machine that has never run this project, runs one documented command, and ends up with every backing service of the system running and reachable: the relational store, the vector store, the cache and job queue, the object store, the background worker, and the application services. They can confirm readiness without knowing anything about how each service is configured.

**Why this priority**: Nothing else in the project can be built, seeded, tested, or demonstrated until the environment exists. This is the single blocking dependency for all five team roles, and it is the difference between "works on one laptop" and "works for the whole team and in CI".

**Independent Test**: On a clean checkout with no pre-existing local state, run the documented startup command and confirm every service reports healthy and the health endpoint responds. Delivers value on its own — the team has a shared, working environment even before any data exists.

**Acceptance Scenarios**:

1. **Given** a clean checkout on a machine with no project state, **When** the developer runs the single documented startup command, **Then** all backing services and application services start and each reports a healthy status within the documented startup budget.
2. **Given** a running environment, **When** the developer runs the documented teardown command and then starts again, **Then** the system returns to the same healthy state with no manual repair steps.
3. **Given** a running environment, **When** the developer queries the system health check, **Then** it reports the individual reachability of the relational store, vector store, cache, object store, and background worker.
4. **Given** a monorepo checkout, **When** a developer looks for where backend, frontend, data generation, shared contracts, and infrastructure definitions live, **Then** each has one obvious, documented home directory.

---

### User Story 2 - Deterministic Seed From An Empty Environment (Priority: P2)

A team member points the seed process at a completely empty environment and receives a fully populated two-company dataset. Any other team member — or a CI run — performing the same action receives an identical dataset: the same identifiers, the same relationships, the same names, the same amounts, the same dates.

**Why this priority**: Determinism is what makes a bug reproducible, a demo re-runnable, an evaluation metric comparable week to week, and a security test trustworthy. A dataset that differs per machine makes every downstream measurement meaningless.

**Independent Test**: Seed an empty environment twice, destroying all state in between, and compare a content fingerprint of every generated record and file. Both runs must produce identical fingerprints. Repeat on a second machine and confirm the fingerprint still matches.

**Acceptance Scenarios**:

1. **Given** a completely empty environment, **When** the seed process runs to completion, **Then** both companies and all their records exist and the process reports a summary count per entity family.
2. **Given** two separate empty environments, **When** the seed process runs in each, **Then** a content fingerprint of the resulting datasets is identical, including generated identifiers, record content, and generated document files.
3. **Given** an already-seeded environment, **When** the seed process is run again, **Then** it refuses with a clear message and a non-zero exit status, changes nothing, and names the explicit reset action the operator would need instead.
4. **Given** a seed run that fails partway through, **When** the operator inspects the environment, **Then** the dataset manifest carries no completion marker, the verification command reports the environment as incomplete, and a reset followed by a fresh seed produces the correct dataset.
5. **Given** machines in different timezones and locales, **When** each seeds an empty environment, **Then** all generated dates, amounts, and text are identical, because the dataset is generated against a pinned reference date rather than the current clock.

---

### User Story 3 - Two Structurally Isolated Tenants (Priority: P3)

The dataset contains two independent companies. Every record, file, document, vector entry, cache entry, background job, and audit entry belongs to exactly one of them. A probe issued in the context of one company can retrieve nothing belonging to the other, in any store.

**Why this priority**: Tenant isolation is the project's headline security claim and the constitution's first non-negotiable principle. The second tenant exists specifically so isolation can be proven rather than asserted, and it must exist in the data layer before any retrieval or agent work begins.

**Independent Test**: Run an automated structural audit over every populated store confirming no tenant-owned item lacks a company identifier, then run cross-tenant probes from each company's context and confirm zero results from the other company in every store.

**Acceptance Scenarios**:

1. **Given** the seeded dataset, **When** an automated audit inspects every tenant-owned record, file key, vector entry, cache entry, job record, and audit entry, **Then** 100% carry a company identifier and none are unattributed.
2. **Given** a query issued in NileTech's context, **When** it searches for a distinctive phrase that exists only in Delta Retail content, **Then** it returns zero records, zero files, and zero citations.
3. **Given** the seeded dataset, **When** the audit checks for records referencing an entity owned by a different company, **Then** it finds zero cross-tenant references.
4. **Given** the seeded dataset, **When** the operator inspects stored file keys and cache keys, **Then** each is namespaced so one company's keys can never collide with, or be enumerated from, the other's.
5. **Given** Delta Retail content, **When** the operator inspects it, **Then** it contains distinctive, easily searchable marker phrases that exist nowhere in NileTech content, so any leak is unambiguously detectable.

---

### User Story 4 - A Coherent, Believable Enterprise (Priority: P4)

The generated data reads as one real company rather than a pile of unrelated random rows. Policies match records, organizational relationships form a valid structure, and business documents reference the same people, departments, countries, and figures that exist elsewhere in the dataset.

**Why this priority**: Incoherent data produces answers that contradict each other. If the leave policy states one number and the leave balances state another, every grounded-answer and evaluation claim the project makes collapses in front of a reviewer — and the failure looks like an AI defect rather than a data defect.

**Independent Test**: Run automated coherence checks that cross-verify stated policy values against generated records, verify the reporting structure is a valid hierarchy, and verify referential integrity across every relationship. All checks pass with zero violations.

**Acceptance Scenarios**:

1. **Given** the leave policy document states an annual entitlement, **When** employee leave balances are inspected, **Then** the entitlements recorded match the policy for every applicable employee category and country.
2. **Given** the generated reporting relationships, **When** they are traversed, **Then** they form a valid hierarchy: every employee has at most one manager, exactly one department, no cycles exist, and each company has exactly one top-level executive.
3. **Given** generated orders and invoices, **When** they are inspected, **Then** every order references an existing customer, product, and sales representative of the same company, and every invoice total is arithmetically consistent with its order.
4. **Given** generated documents such as policies and contracts, **When** their content is read, **Then** they reference department names, office locations, countries, and role names that actually exist in that same company's structured data.
5. **Given** generated time-based records such as attendance, leave requests, orders, and invoices, **When** their dates are inspected, **Then** all fall within a plausible window relative to the pinned reference date and no record predates its parent.

---

### User Story 5 - Public Company Identity Content (Priority: P5)

The dataset includes the outward-facing content that makes NileTech look like a real company: services, product offerings, leadership profiles, news items, open vacancies, and office information — clearly separated from internal, confidential content.

**Why this priority**: The public site is a mandatory surface and cannot be built without content. Separating public from internal content at generation time also creates the first and simplest classification test: public content is the only content an unauthenticated visitor may ever see.

**Independent Test**: Confirm every public-facing content item is generated, is marked public, and that no item marked public contains employee personal data, salary information, contract terms, or internal financial figures.

**Acceptance Scenarios**:

1. **Given** the seeded dataset, **When** public content is listed, **Then** services, products, leadership profiles, news items, vacancies, and office information all exist for NileTech with non-placeholder content.
2. **Given** public leadership profiles, **When** they are compared to employee records, **Then** each corresponds to a real generated executive of that company and exposes only public-appropriate fields.
3. **Given** any item marked public, **When** it is scanned for sensitive content, **Then** it contains no salary figures, no personal contact details of non-executive staff, no contract terms, and no internal financial data.
4. **Given** office information, **When** it is inspected, **Then** the three NileTech locations — Cairo, Alexandria, Dubai — are present and are the same locations referenced by employee records and documents.

---

### Edge Cases

- **Seed run twice**: the process must not silently create a duplicate company, duplicate employees, or doubled transactional records.
- **Seed interrupted midway** (process killed, service restarted): the environment must not be left in a state that looks complete but is not.
- **Machine differences**: timezone, locale, filesystem ordering, and character encoding must not change generated content.
- **Concurrent generation**: if any part of generation runs in parallel for speed, generated identifiers and content must still be stable.
- **Name collisions**: two generated employees may plausibly share a name; identifiers, emails, and references must remain unique and stable.
- **Top of the org chart**: the single top-level executive has no manager — the reporting structure must permit exactly this one case per company and reject any other manager-less employee.
- **Smaller tenant coverage**: Delta Retail is deliberately smaller; every entity family it is meant to have must be non-empty, and any family it deliberately lacks must be documented rather than silently missing.
- **Non-working days**: attendance and leave records must handle weekends and public holidays consistently per country rather than generating impossible working days.
- **Multi-country employees**: employees in Egypt and the United Arab Emirates may fall under different policy values; records must follow the policy for the employee's own country.
- **Volume persistence**: stopping and restarting the environment must not silently discard the seeded dataset, and a full reset must be a distinct, explicit action.
- **Port or resource conflicts** on a developer machine must produce a clear, actionable message rather than a partially started environment.

## Requirements *(mandatory)*

### Functional Requirements

**Repository and environment**

- **FR-001**: The project MUST be organized as a single monorepo with one documented home for each of: application backend, application frontend, data generation and seeding, shared contracts and schemas, **shared user-interface components**, **shared domain logic used by more than one member**, infrastructure definitions, tests, and documentation. Each home MUST have a stated responsibility, not merely a name — a directory whose contents are decided case by case is where the dependency rule in FR-001a starts to erode.
- **FR-001a**: Dependency direction between workspace members MUST be a stated rule, enforced automatically:
  - `packages/*` MUST NOT import from `apps/*`, `services/*`, or `scripts/*`;
  - `apps/*`, `services/*`, and `scripts/*` MAY import from `packages/*` but MUST NOT import from one another;
  - code needed by two members moves **down** into `packages/`, never sideways.
  An automated check MUST fail the build on a violation. The rule is written down because it has already been needed and resolved by judgement rather than by rule: the seed loader required a Redis key pattern that the API also writes, and nothing stated that `scripts/seed` may not import from `apps/api` — the pattern was moved into `packages/core` because that seemed right, which is precisely the decision a rule exists to make unnecessary. The next feature adds a second application and a second API surface, so the cost of leaving this implicit rises.
- **FR-001b**: API paths MUST NOT carry a version segment. Compatibility is governed by the **published OpenAPI document and the generated client types**, which must agree with the running service — a gate that already exists and already fails on drift. This system deploys its client and its server together and has one consumer per surface, so a `/v1/` prefix would add a permanent cost to buy an option nothing needs. If a second, independently-deployed consumer ever appears, this decision is the thing to revisit first.
- **FR-002**: The complete local system MUST start from a clean checkout via one documented command, bringing up the relational store, vector store, cache and job queue, object store, background worker, backend service, and frontend service. Those seven are the whole of "the complete local system" — the set is closed, so the claim is countable rather than a matter of opinion. The **documented startup budget** referred to in the acceptance scenarios is SC-001's **15 minutes**, measured from a clean checkout on the machine defined under *Assumptions → Standard developer machine*, and including image pulls on a first run.
- **FR-002a**: Startup MUST be **ordered by readiness, not by wall-clock guesswork**: a service that depends on another MUST NOT be considered started until that dependency reports healthy, and the one documented command MUST NOT report success until every service in FR-002 reports healthy. A fixed sleep, or a service with no health probe treated as ready by default, both produce the failure this exists to prevent — a command that claims success over a system that is not up.
- **FR-002b**: The frontend MUST remain usable when the backend is unreachable: it MUST render a stated error condition within a bounded time rather than an indefinite loading state, and MUST NOT present a blank page or a raw framework error. The frontend is a required service of this environment, so "the API is down" is a state it is guaranteed to meet.
- **FR-002c**: A port or resource conflict on the developer's machine MUST produce a **clear, actionable message naming the conflicting resource**, and MUST NOT leave a partially started environment behind. Every host port the environment publishes MUST be overridable through environment configuration, so the conflict is resolvable without editing committed files (FR-005). *(This requirement backs an edge case that previously had none — the scenario was listed under Edge Cases with no requirement to satisfy it.)*
- **FR-003**: The system MUST expose a health check that individually reports the reachability of **each of the five backing services named in FR-002 and FR-039–FR-042** — the relational store, the vector store, the cache and job queue, the object store, and the background worker — so a partially started environment is immediately visible. The set MUST be the same set, named the same way, in the health requirements and the isolation requirements; two lists that drift apart make "every backing service" unverifiable.
- **FR-003a**: The health surface MUST distinguish **liveness** from **readiness**. Liveness answers whether the process is running and MUST NOT depend on any external service — a liveness probe that fails when a dependency is down causes the orchestrator to restart a healthy process, which cannot fix the dependency and destroys any in-flight work. Readiness answers whether the system can serve, and does depend on them.
- **FR-003b**: Each dependency probe MUST carry its **own bounded timeout**, so a hung dependency produces a definite answer within a stated time rather than a hanging request. The bound MUST be configurable and MUST have a documented default. A probe that waits indefinitely turns the health endpoint into a second outage.
- **FR-003c**: Partial availability MUST be reported as **degraded and refused, not as healthy**: the readiness response MUST carry a per-dependency status distinguishing *reachable*, *unreachable*, and *timed out*, and the endpoint's overall status MUST be a failure when any dependency is not reachable. Reporting "mostly up" as up is how a partially started environment passes for a working one.
- **FR-003d**: Health endpoints MUST remain reachable **without authentication** when authentication is introduced in a later feature. They are consumed by the container orchestrator, which holds no credentials; requiring one would make the system unmonitorable to protect information FR-003e already forbids it from carrying.
- **FR-003e**: A health response MUST NOT disclose connection strings, credentials, internal hostnames, ports, query text, or driver stack traces. It may name the dependency, its status, its latency, and a failure **category**. This follows from FR-003d and not the other way round: the response is unauthenticated, so its content is public by construction.
- **FR-004**: The environment MUST provide documented commands to start, stop, reset (destroy all state), and re-seed, and each MUST be safe to run repeatedly.
- **FR-005**: All configuration that differs between machines MUST be supplied through environment configuration with documented defaults that work out of the box for local development; no team member may need to hand-edit committed files to start the system.
- **FR-005a**: The example configuration file MUST surface **exactly** the settings a person may legitimately need to change — host ports, credentials, the seed value, the reference date, and the profile — and MUST NOT surface internal wiring that has one correct value, such as inter-service hostnames on the container network. The test is the reason for the boundary: a setting appears when changing it is a supported action, and stays internal when changing it can only break the system. An example file that lists everything is as unhelpful as one that lists nothing, because neither tells the reader which knobs are theirs.
- **FR-006**: No secret values may be committed to the repository; local development MUST work from documented example configuration containing only non-production placeholder values.
- **FR-006a**: "Non-production placeholder" MUST be checkable rather than a matter of judgement. A committed default satisfies FR-006 only if **all** of the following hold: it grants access to nothing outside the local environment; it is identifiable as a placeholder from its own value, without external knowledge; and the system **refuses to start** with it in any environment not marked local. The third condition is what makes the first two safe — without it, a placeholder that reaches a real deployment is a real credential, however it was labelled.

**Schema and migrations**

- **FR-007**: All structured data MUST be created through versioned, ordered, reversible migrations; no schema object may exist only as a manual change.
- **FR-007a**: A migration that fails MUST leave the schema at a **known version** — either fully applied or fully rolled back, never partway. Reversibility (FR-007) is what makes recovery possible; this requirement is what makes it necessary, and the two are not the same claim. Every migration's down path MUST be exercised, not merely written: a `down` that has never run is an assumption, and it is discovered to be wrong at the moment it is most needed.
- **FR-008**: Rebuilding the database from migrations alone MUST produce an identical schema on any machine.
- **FR-008a**: Every foreign key and every column the seed filters or joins on MUST be indexed, and the schema MUST support the SC-008 seed budget **without** the generator hand-tuning its insert order to compensate. Performance here is a schema property, not a generator trick: a missing index that the seed works around stays missing for every query the application later runs against the same table.
- **FR-009**: Every tenant-owned entity MUST carry a company identifier as a mandatory, non-nullable attribute.
- **FR-009a**: The specification MUST name an explicit, closed **global-entity allowlist** — the small set of entities that legitimately have no company identifier. For this feature that allowlist is: the **permission catalog**, the **platform-level administrator account**, the **schema-migration history**, and the **dataset manifest**. Every entity not on this allowlist is tenant-owned and MUST satisfy FR-009.
- **FR-009b**: The permission catalog MUST be **global and shared** — one set of permission codes used identically by both companies — so that permission codes cannot drift apart between tenants. Roles remain tenant-scoped and reference the global permission codes.
- **FR-009c**: The **Platform Admin** MUST be modelled as a platform-level account bound to **no** company. It MUST NOT be a member of either company, MUST NOT appear in either company's user directory, and MUST NOT receive automatic access to any company's business data.
- **FR-009e**: A tenant identifier that **matches no company** MUST behave exactly as an absent one: zero rows, no error distinguishing "no such tenant" from "no such data". An identifier that produced a different failure would be an oracle — a caller could enumerate which tenants exist by watching which value fails differently, which is FR-043a's disclosure argument applied one level up, at the tenant rather than the resource.
- **FR-009d**: Database-level **Row-Level Security MUST be enabled and forced on every tenant-owned table**, with the policy bound to a session-scoped tenant identifier. When no tenant identifier is set on the session, a tenant-scoped read MUST return **zero rows** — the system fails closed. Application-level filtering remains mandatory regardless; RLS is the final safety net, not a substitute. (Constitution Principle I; previously specified only in the plan.)
- **FR-010**: Sensitive resources MUST additionally carry owner, department, country, and classification attributes, so later authorization work has the attributes it requires.
- **FR-010a**: Data classification MUST use exactly four levels, applied consistently across document metadata, object-storage keys, and vector-store entries:

  | Level | Meaning | Example content |
  |-------|---------|-----------------|
  | `PUBLIC` | Visible without authentication; the only level the public site may render | Services, public products, leadership profiles, news, vacancies, office information |
  | `INTERNAL` | Any authenticated employee of that company | Employee handbook, leave policy, remote-work policy, code of conduct, internal announcements |
  | `CONFIDENTIAL` | Restricted to a department, role, or owner | Department reports, customer contracts, supplier agreements, performance reviews |
  | `RESTRICTED` | The most sensitive tier — role alone is insufficient, an explicit grant is required | Payroll and salary records, executive contracts, disciplinary records |

- **FR-010b**: Every classified resource MUST carry exactly one level. The level MUST be stored as a constrained value so that an unrecognized level cannot be persisted.
- **FR-010c**: `PUBLIC` and `RESTRICTED` MUST both be represented in the seeded data for both companies, so the extremes of the classification range are exercised rather than only the middle.
- **FR-010d**: **All four** levels MUST be non-empty for **both** companies. FR-010c names the extremes because they are the ones most likely to be missing; this requires the whole range, so an authorization rule that turns on `INTERNAL` or `CONFIDENTIAL` has data to be tested against for either tenant. No proportion is mandated — only that no level is empty, since a level with zero rows makes every rule about it vacuous.
- **FR-010e**: The set of four levels is **closed for this feature**. Adding or removing a level is a schema change requiring a migration that restates the constrained value and assigns every existing row a level from the new set; it MUST NOT be possible for a stored row to hold a level the constraint no longer permits. The ordering is significant — `PUBLIC` < `INTERNAL` < `CONFIDENTIAL` < `RESTRICTED` — and any future level MUST state its position in that ordering, because comparisons like "above INTERNAL" (FR-028a) are meaningless otherwise.

**Deterministic generation**

- **FR-011**: The seed process MUST be deterministic: given the same fixed seed value it MUST produce an identical dataset on every machine and every run — identical identifiers, relationships, names, amounts, dates, text, and generated files.
- **FR-011a**: Generated identifiers MUST be **derived from stable content**, not from consumption order of a shared random stream. An identifier that depends on how many values were drawn before it changes when an unrelated generator is reordered, when a family is added, or when a loop is refactored — so an innocuous change produces a whole-dataset fingerprint mismatch with no wrong output to point at, and the natural response is to re-baseline the fingerprint, which discards the guarantee. Each entity's identifier MUST be reproducible from the root seed plus that entity's own stable key, independently of everything generated around it.
- **FR-012**: Generation MUST NOT depend on the current clock, machine timezone, machine locale, unseeded random sources, or filesystem iteration order. All dates MUST derive from a single pinned reference date recorded with the dataset.
- **FR-012a**: The controls that make byte-identical output achievable MUST be in place and enforced: all generated text is written as UTF-8 with **LF** line endings and no byte-order mark; the repository declares LF as the checked-out line ending; and container locale is pinned so number and date formatting cannot vary by host. A single fixture document MUST be asserted against an exact content digest, so a byte-level regression is caught at the file rather than surfacing as an unexplained whole-dataset mismatch.
- **FR-012b**: Every dependency that can influence generated content MUST be version-pinned with a committed lockfile. Generated names, words, and text come from library data that changes between releases, so an unpinned upgrade would silently change the dataset.
- **FR-012c**: The **root seed value MUST be fixed and committed** as the project default. It may be overridden for experimentation, but the committed default is the one every team member, every verification run, and every demo uses.
- **FR-012d**: The pinned reference date MUST be **changeable only as a deliberate, documented act**, and the specification MUST state what the change invalidates: every committed known-good fingerprint (FR-017a), every date-bearing assertion in the test suites, and any documentation quoting concrete dates. A reference-date change is a dataset change — it is not a configuration tweak, and treating it as one produces a verification failure whose cause is invisible in the diff that caused it.
- **FR-013**: The seed process MUST populate an empty environment end to end in a single invocation, with no manual intervening steps.
- **FR-014**: The seed process MUST **refuse to run against a non-empty environment**, exiting with a clear message and a non-zero status. It MUST NOT attempt a partial top-up, and it MUST NOT be possible to produce a doubled or partially doubled dataset by accident.
- **FR-014a**: Destroying an existing dataset MUST require an explicit, separate reset action — never a side effect of running the seed. The reset action MUST state what it is about to destroy before proceeding.
- **FR-014b**: The seed MUST write a **completion marker** to the dataset manifest only after every entity family has been written successfully. An environment whose manifest lacks the completion marker MUST be treated as incomplete by the seed, the verification command, and continuous integration alike.
- **FR-014c**: A seed run that fails partway MUST leave the environment detectably incomplete rather than plausibly complete: relational writes roll back where the store supports it, and any object-storage or vector-store content written before the failure is reported by the verification command as inconsistent with the manifest. This covers a dependency that becomes unavailable **mid-run** as well as one that was unavailable at the start; the requirement is stated as an outcome precisely so it does not have to enumerate the ways a run can die.
- **FR-014d**: Every command MUST distinguish an **expected refusal** from an **unexpected failure** by its exit status, so an operator and continuous integration can tell them apart without parsing prose. The scheme MUST be documented and stable: `0` success; a distinct non-zero code for a deliberate refusal (a non-empty environment, a non-local environment, a missing confirmation); and a distinct non-zero code for a verification that ran and disagreed. Collapsing these onto a single `1` makes "the seed refused because data already exists" indistinguishable from "the seed crashed", and only the second is a defect.
- **FR-014e**: Every refusal and failure message MUST **name the failing component, state what was expected, and state the next action**. It MUST NOT contain credentials, connection strings, or a raw stack trace as its primary content. A message that says only that something went wrong sends the reader to the source code, which is the cost this requirement exists to avoid.
- **FR-014g**: The seed writes **both tenants** and is therefore the one component that legitimately holds both at once. It MUST NOT become a cross-tenant path: each company's data is generated from that company's own inputs, no value derived from one company may be reused in the other's records, and the generator MUST NOT resolve a reference by searching across companies. Its privilege is the reason, not an exemption — the seed runs as the schema owner and so bypasses FR-009d's row-level security, which means it is the single writer that RLS cannot catch, and the structural audit of FR-044 is what checks its output instead.
- **FR-014f**: The reset action MUST be **safe against an already-empty environment**: it MUST report that there is nothing to destroy and complete successfully rather than failing, so it is usable as an unconditional first step in a script. This is the FR-004 repeatability guarantee applied to the one command whose repetition is frightening.
- **FR-015**: The seed process MUST report a per-entity-family summary of counts and a dataset fingerprint on completion, so two runs can be compared without manual inspection.
- **FR-015a**: The dataset fingerprint MUST cover the **content** of every generated record and file — including identifiers, relationships, text, amounts, dates, and classification — and MUST exclude values that legitimately vary between environments, namely wall-clock insertion timestamps, connection or session identifiers, and physical storage locations. The fingerprint MUST be independent of row-retrieval order, so two runs that insert in different orders but produce the same content still match. The exclusion list MUST be documented, because an over-broad exclusion would silently weaken the determinism guarantee in SC-002. The list is **closed**, and the principle governing it is stated so it stays that way: a value may be excluded **only if it is required to differ between two correct environments**. Convenience is not a reason — an exclusion added because a value "keeps changing" is very often the determinism defect itself, removed from view rather than fixed. Every addition MUST record which of two correct environments differs, and why that difference is itself correct.
- **FR-016**: The dataset MUST record its own generation metadata — seed value, reference date, generator version, per-family realized counts, fingerprint, and completion marker — so any environment can state exactly which dataset it holds.
- **FR-016a**: The generator version MUST be incremented **whenever a change alters generated output**, and MUST NOT be incremented otherwise. That is what makes the version informative: a fingerprint mismatch between two environments at the same generator version is a defect, while one across a version change is expected and its cause is recorded. A change that alters output without a version bump is the failure this prevents — it makes an accidental change indistinguishable from an intended one, and the committed fingerprint of FR-017a is then updated to match whatever the code now produces.
- **FR-017**: A verification command MUST exist that recomputes the dataset fingerprint from the live environment and reports whether it matches the expected value.

**Tenant content — NileTech Solutions**

- **FR-017a**: A **known-good dataset fingerprint MUST be committed to version control** and asserted against on every change. Without a pinned expected value, verification only proves the dataset matches its own manifest — a code change that alters generation produces a new dataset and a new manifest that agree with each other perfectly, and the drift goes undetected.
- **FR-018**: The system MUST generate NileTech Solutions as a software and business-automation company with offices in Cairo, Alexandria, and Dubai.
- **FR-019**: NileTech MUST have approximately 200 employees distributed across eight departments: Engineering, HR, Sales, Finance, Legal, Customer Support, Operations, and Executive Management.
- **FR-020**: Employee distribution across departments and offices MUST be plausible for a company of this type and size rather than uniform, and MUST be stable across runs.
- **FR-020d**: "Plausible rather than uniform" MUST be expressed as **stated proportions**, not left to a reviewer's judgement. Headcount is allocated by these fixed weights, deterministically, with every department and office receiving at least one employee:

  | NileTech department | Share | | NileTech office | Share |
  |---|---:|---|---|---:|
  | Engineering | 30% | | Cairo | 60% |
  | Sales | 18% | | Alexandria | 22% |
  | Customer Support | 14% | | Dubai | 18% |
  | Operations | 12% | | | |
  | Finance | 8% | | **Delta Retail office** | **Share** |
  | HR | 7% | | Cairo | 70% |
  | Executive Management | 6% | | Dubai | 30% |
  | Legal | 5% | | | |

  Delta Retail: Sales 40%, Operations 28%, Finance 12%, HR 12%, Executive Management 8% — a
  retail shape, deliberately unlike NileTech's engineering-led one, so a distribution copied
  between tenants is visible as a defect rather than passing as plausible.
- **FR-020a**: Historical data MUST span a **24-month window ending at the pinned reference date**, so that year-over-year and quarter-over-quarter comparisons are possible. **Attendance is the sole exception**: it MUST cover only the most recent **6 months**, because per-employee-per-working-day rows dominate total volume and would otherwise threaten the seed-time budget in SC-008.
- **FR-020b**: The seed MUST generate approximately the following volumes, within ±10%, and MUST record the exact realized counts in the dataset manifest:

  | Entity family | NileTech | Delta Retail |
  |---------------|---------:|-------------:|
  | Departments | 8 | 5 |
  | Offices | 3 | 2 |
  | Users / employees | 200 | 40 |
  | Leave requests (24 mo) | 1,200 | 240 |
  | Attendance records (6 mo) | 26,000 | 5,200 |
  | Training records | 400 | 80 |
  | Performance reviews (4 cycles) | 800 | 160 |
  | Customers | 120 | 60 |
  | Products | 25 | 80 |
  | Orders (24 mo) | 2,400 | 1,200 |
  | Invoices | one per order | one per order |
  | Sales targets (per rep, per quarter) | 120 | 40 |
  | Expenses (24 mo) | 2,000 | 400 |
  | Budgets (per department, per quarter) | 64 | 40 |
  | Contracts | 60 | 25 |
  | Policy documents | 8 | 8 |
  | Public content items | 45 | 20 |

- **FR-020e**: The ±10% tolerance in FR-020b applies **only to the relationship between a target and the realized count**, never to run-to-run variance. Two runs at the same seed and profile MUST produce **exactly** the same counts — the tolerance exists because a target like "one invoice per order" or a per-quarter budget cannot always land on a round number, not to permit drift. FR-011 is unaffected by it, and reading the tolerance as run-to-run latitude would make the determinism guarantee unfalsifiable.
- **FR-020f**: A **reduced profile** MUST exist for continuous integration and MUST be specified here rather than only in the tooling: it scales every entity-family target by a fixed published factor while preserving the **shape** of the dataset — both companies, every department and office, every entity family non-empty, every persona present, and a valid reporting hierarchy. The profile is a smaller dataset, not a different one, so a check that passes on it means something. Each profile MUST have its own committed known-good fingerprint under FR-017a, because a single fingerprint cannot describe two datasets.
- **FR-020c**: Transactional volumes MUST show plausible variation over the window — seasonality, growth, and per-representative differences — rather than a flat rate, so that trend questions have a real trend to find. The variation MUST be deterministic.

**Tenant content — Delta Retail Group**

- **FR-021**: The system MUST generate Delta Retail Group as a fully independent second company with its own departments, employees, roles, business data, documents, and files.
- **FR-021a**: Delta Retail MUST have exactly **five departments — HR, Sales, Finance, Operations, and Executive Management** — and **two offices, Cairo and Dubai**. This was previously stated only under Assumptions, which cannot carry it: SC-010 and the isolation checks count these, and a countable acceptance criterion sourced from an assumption is a criterion nothing is obliged to meet.
- **FR-022**: Delta Retail Group MUST be smaller than NileTech but complete enough to exercise every entity family used in isolation tests. **"Every entity family" means every row of the FR-020b volume table with a non-zero Delta Retail figure** — that table is the enumeration, so the phrase is countable rather than a judgement about completeness. Where Delta deliberately lacks something NileTech has — it has no Engineering and no Legal department — that absence MUST be documented as intentional rather than left to look like a generation gap.
- **FR-023**: Delta Retail content MUST include distinctive marker phrases appearing nowhere in NileTech content, so any cross-tenant leak is unambiguously detectable by search.
- **FR-023a**: Marker phrases MUST be specified in **number, form, and placement**, because a probe (FR-045) is only as strong as what it searches for. Each company carries **exactly three**, in three different shapes, so a leak is caught however the content was transformed on its way out: an **uppercase hyphenated token** that survives case-insensitive matching and tokenization; a **lowercase natural-language clause fragment** that reads as ordinary prose and would survive a summarizer; and a **structured reference code** in the form a citation or identifier would take. Both companies carry a set — NileTech's exist so the reverse-direction probe is real rather than one-sided. Every marker MUST appear in generated document text (not only in structured columns), because document text is what retrieval will later return, and MUST NOT appear in any content belonging to the other company.
- **FR-024**: No generated record, file, document, vector entry, cache entry, job, or audit entry may belong to both companies or reference an entity owned by the other company.
- **FR-024b**: **Log output is an isolation surface.** Every log line written while serving a tenant MUST carry that tenant's identifier, and MUST NOT carry another tenant's data. Logs aggregate across tenants by construction — that is what a log is — so a line that omits its tenant is unattributable forever, and one that carries the wrong tenant's content is a leak into a store that is usually retained longer, and read more widely, than the database it came from.
- **FR-024c**: A database dump, backup, or export produced by this feature MUST be understood as **containing both tenants**, and MUST be handled accordingly: it is not a per-tenant artifact and MUST NOT be given to anyone entitled to only one tenant's data. Per-tenant export is **out of scope** for this feature and is recorded here rather than omitted, because "we have backups" is otherwise read as "we can restore one tenant", which is not true of a shared-schema design.
- **FR-024d**: Tenant offboarding and deletion are **out of scope** for this feature. Nothing here deletes a company, and the delete semantics of FR-033b are what a future offboarding would build on. It is recorded rather than left silent because shared-schema multi-tenancy makes tenant deletion a genuinely hard operation — it touches every table, every storage prefix, every cache namespace, and the audit trail that must survive it — and discovering that late is expensive.
- **FR-024e**: Tenant identifiers MUST be treated as **non-secret but non-authoritative**. Human-readable slugs are permitted and are used, because unguessable identifiers would be security through obscurity in a system whose real control is FR-009d's row-level security and request-time authorization. What follows is the requirement that matters: **no identifier supplied by a caller may select a tenant**. Knowing another company's identifier must be worth nothing, and if it is worth anything, an unguessable one only raises the price.
- **FR-024a**: The two companies MUST share **nothing** except the entities on the global allowlist defined in FR-009a. They have no shared users, no shared customers, no shared products, no shared documents, no shared storage prefix, and no shared cache namespace. Customer records belonging to one company MUST NOT be reused as customer records of the other, even where a plausible real-world overlap would exist.

**Generated entity families**

- **FR-025**: The system MUST generate **organizational** data: companies, departments, offices and locations, roles, permissions, role-to-permission assignments, users, user-to-role assignments, and manager and reporting relationships.
- **FR-025a**: Every user MUST hold **exactly one primary role**. A user who has at least one direct report MUST additionally hold the Manager role. No other multi-role combinations are generated, so role assignment is unambiguous and predictable.
- **FR-025b**: The dataset MUST include a **fixed, documented persona set** with stable identifiers and stable credentials-in-waiting, covering at minimum: a NileTech Employee with their own leave balance; that employee's Manager, holding at least three direct reports; an employee in a different department whose records the Manager must not reach; an HR user with company-wide HR access; a Finance user; a Legal user holding an explicit resource-level grant on restricted contracts; an Auditor; a Company Admin; a Delta Retail employee; and a user permitted to draft and send communications. Personas MUST be listed in the feature documentation with their company, department, role, country, and manager.
- **FR-025c**: Persona identifiers, email addresses, department assignments, and reporting relationships MUST NOT change between seed runs or between generator versions unless the change is deliberate and documented, because acceptance tests, evaluation sets, and the demo script all reference them by name.
- **FR-026**: The system MUST generate **HR** data: employee profiles, job titles, salary bands, leave balances, leave requests, attendance records, training records, and performance reviews.
- **FR-026a**: **Salary bands MUST be a named, ordered, closed set with stated ranges**, because salary is the payload behind the flagship denial scenario (FR-047a) and "a salary figure exists somewhere" is not enough to test a denial against. Five bands, ascending and non-overlapping, spanning roughly 28,000 to 190,000 in the company's reporting currency, with every employee assigned exactly one and an amount inside its range. The bands MUST be consistent across both companies so a cross-tenant comparison is meaningful.
- **FR-026b**: **Job titles MUST come from a fixed per-department set**, not free text. A title must be recognisable as belonging to its department — a Finance employee never holds an Engineering title — because generated documents quote job titles (FR-036) and a title that contradicts its department makes the document incoherent in a way no structural check would catch.
- **FR-027**: The system MUST generate **sales and finance** data: customers, products, sales representatives, orders, invoices, sales targets, regions, expenses, budgets, and monthly revenue aggregates.
- **FR-028**: The system MUST generate **legal** data: customer contracts, supplier agreements, non-disclosure agreements, and employment templates, each with realistic clause content including terms that differ meaningfully between comparable documents.
- **FR-028a**: The legal data MUST include at least one **matched pair of comparable contracts** assigned to Legal that differ in specific, quotable terms — differing notice periods, differing liability caps, and at least one clause category where the two agree — so that the blueprint's contract-comparison scenario has a real, verifiable answer. Both MUST be classified above INTERNAL and reachable by the Legal persona through an explicit resource-level grant.
- **FR-029**: The system MUST generate **policy documents**: employee handbook, leave policy, remote-work policy, expense policy, security policy, code of conduct, travel policy, and benefits guide.
- **FR-030**: The system MUST generate **public company content** for **both companies**: services, product offerings, leadership profiles, news items, open vacancies, and office information. NileTech's public content is the richer set (it is the company whose public site is a mandatory surface); Delta Retail receives a smaller but complete set, because `PUBLIC` classification must exist for both tenants (FR-010c) and public content is itself an isolation surface that must be provable per tenant.
- **FR-030a**: "Non-placeholder content" MUST be **checkable**, not a claim about prose quality. Generated public and document text satisfies it when: it contains no lorem-ipsum or filler vocabulary; every named entity in it resolves to a real record of the same company (FR-036); two items of the same kind differ in substance rather than only in an interpolated name or number; and its length falls within a stated range for its type. Those are testable. "Reads well" is not, and a requirement nothing can fail is a requirement nothing has to meet.
- **FR-031**: Every generated document MUST exist both as a stored file in the object store and as a metadata record carrying company, department, owner, classification, country, and document type.
- **FR-031a**: Every stored file MUST have **exactly one owning user, of the same company**. Ownership follows a fixed convention so it is predictable and testable: policy documents are owned by the head of the department that governs them (HR policies by the HR head, security policy by the Operations head); contracts and agreements are owned by a Legal user where the company has a Legal department, and otherwise by the head of Executive Management; departmental reports and expense records are owned by that department's head; public content is owned by the head of Executive Management; and employee-specific documents are owned by the employee they concern. No file may be ownerless, and no file may be owned by a user of the other company.
- **FR-031b**: Object-storage writes during seeding MUST **fail fast rather than retry**. This is a decision, not an omission: the seed runs against a local store on the same host, so an upload failure means the store is genuinely unavailable, and retrying converts a clear failure into a slow one. Recovery is FR-014a's reset followed by a fresh run — cheap, deterministic, and total — rather than a partial dataset repaired in place. Any failure MUST surface through FR-014c's detectable-incompleteness guarantee. *(Revisit if seeding ever targets a remote store across a network, where a transient failure becomes the common case rather than the signal.)*
- **FR-032**: Generated document files MUST be byte-identical across runs for a given seed value.

**Coherence and integrity**

- **FR-033**: All generated relationships MUST have referential integrity — zero orphaned references across every entity family.
- **FR-033a**: Referential integrity MUST be enforced by **declared database foreign keys**, not by the generator's care or by a test that runs afterwards. A test proves the data is currently clean; a constraint makes the bad state unreachable, including by hand-written SQL and by every feature built on this schema later. The audit in FR-044 remains required — it catches what no single-column constraint can, such as a reference that resolves to a row belonging to the other company.
- **FR-033b**: Deletion semantics MUST be **declared for every relationship** rather than left to the database default. A parent whose children are meaningless without it cascades; a parent whose children must outlive it restricts. Nothing in this feature deletes, which is exactly why this is written down now: the first feature that deletes will otherwise discover the policy by finding out what happens, and audit and financial records are among the rows involved. Audit entries MUST be restricted against deletion in every case (FR-043b).
- **FR-033c**: Uniqueness MUST be declared for every entity that has a natural key, and MUST be **scoped by company wherever the key is only unique within a tenant** — employee email is the case that matters, since two companies may legitimately hold the same address and a globally unique constraint would make one of them unseedable. An entity with no natural key MUST say so; silence is how a duplicate becomes possible.
- **FR-034**: Reporting relationships MUST form a valid hierarchy per company: no cycles, at most one manager per employee, exactly one manager-less top-level executive, and every department headed by an employee of that department.
- **FR-034a**: The specification MUST state, for each integrity rule, **whether it is enforced by a database constraint or verified by an automated check**, and the reason. Constraints are preferred because they hold against every writer. Acyclicity of the reporting hierarchy is the deliberate exception — it is not expressible as a simple constraint and is enforced by the FR-044 audit — and naming it as an exception is what stops "verified by test" from becoming the default for rules that could have been constraints.
- **FR-034b**: Every nullable column whose nullability exists for a **structural** reason rather than a business one MUST name that reason here and MUST have a check that closes it. There is exactly one in this feature: `manager_id` on a user, nullable because the reporting hierarchy is a tree and its root has no parent — an employee also cannot reference a manager who has not been inserted yet, so the column cannot be non-null at insert time either. The closing check is FR-034's own count: **exactly one manager-less user per company**, verified by the FR-044 audit. A nullable column with no closing check is indistinguishable from an optional one, and the schema then permits forever a state that was meant to hold for one row.
- **FR-035**: Values stated in generated documents MUST match the corresponding structured records — most importantly, leave entitlements stated in the leave policy MUST match generated leave balances for the employee's country and employment type.
- **FR-036**: Generated documents MUST reference only department names, office locations, countries, role names, and people that exist in that same company's structured data.
- **FR-037**: All generated dates MUST fall within a plausible window relative to the pinned reference date, and no child record may predate its parent — an order cannot precede its customer, a leave request cannot precede the employee's hire date.
- **FR-038**: Monetary values MUST record an explicit currency and MUST be internally consistent: invoice totals derive from their order lines, and budgets and expenses share the same currency basis within a company. Currency scope is **per company, not per office** — NileTech reports in one currency across Cairo, Alexandria, and Dubai. A multi-office company reporting in one currency is ordinary; the alternative would require exchange rates, and a rate that varies over a 24-month window cannot be pinned without inventing a rate table, which is content this feature has no reason to generate.
- **FR-038a**: Monetary amounts MUST use a **fixed-point decimal type with two decimal places**, never a binary floating-point type, and derived totals MUST be computed by summing stored values rather than recomputed from percentages at read time. Rounding is applied once, at the point a value is generated, using half-up. This is a determinism requirement as much as a correctness one: floating-point summation depends on order, so the same records summed differently would produce different fingerprints on different runs, and FR-011 would fail for a reason that had nothing to do with generation.

**Isolation scaffolding across stores**

- **FR-039**: Object-storage keys MUST be namespaced by company and classification so one company's files cannot collide with, or be enumerated from, the other's.
- **FR-039a**: "Namespaced" MUST mean something checkable: the company identifier is the **leading segment** of the key, followed by a separator that cannot occur inside an identifier. Leading matters and is not stylistic — a prefix listing is the enumeration primitive both an object store and a cache offer, so a company-first key makes "list everything belonging to the other tenant" unrepresentable rather than merely unauthorized. A key with the tenant in the middle satisfies "contains the company" and defeats the whole purpose.
- **FR-039b**: A tenant-scoped key MUST be **impossible to construct without a tenant**: keys are built by a single shared function that requires the company and rejects an empty or unknown one, never by string concatenation at the call site. Detecting an unprefixed key by audit afterwards is strictly worse — by then the object is written, and the audit only reports what the type system could have refused.
- **FR-040**: Cache keys MUST be namespaced by company so no cached value can be shared across companies, under the same construction rule as FR-039a and FR-039b.
- **FR-041**: Vector-store collections and entries MUST be structured so every stored entry carries its company identifier and can be filtered by it before any similarity result is returned. **Under decision D2 this feature delivers the structure and no content**: the requirement is on the schema and the filter path, and it is satisfied here by a correctly structured, empty, tenant-partitioned collection. It does not imply entries that will not exist until ingestion, and the semantic probe that needs them is carried forward with D2.
- **FR-042**: Background job records MUST carry the company identifier of the work they perform.
- **FR-042a**: Isolation MUST extend to the **job payload and the queue itself**, not only to the job record. A payload MUST NOT carry another company's data, and a worker MUST bind the tenant context from the job's own company identifier before doing any work — never from anything the payload asserts about itself. The record and the payload are separate surfaces: a correctly attributed job whose payload was assembled under a different tenant carries the leak past every check that reads only the record.
- **FR-043**: Audit entries MUST carry the company identifier, and the seed process itself MUST record audit entries for the dataset creation it performs.
- **FR-043b**: The audit log MUST be **append-only, enforced at the database**: no update and no delete, including by the schema-owning role. An audit trail an application can edit is not evidence, and "the application never deletes audit rows" is a property of today's code rather than of the record. The one operation that may remove rows is a documented retention policy applied by an explicit, separately authorized action — never an ordinary write path. *(Constitution Principle X, previously stated only there and in the data model.)*
- **FR-043a**: A request for a resource belonging to another company MUST be answered as **not found**, never as forbidden. A response that distinguishes "exists but denied" from "does not exist" is itself a disclosure: it confirms the resource's existence and lets a caller enumerate another tenant's identifiers without ever receiving their data. The **audit entry MUST record the real reason** — a cross-tenant denial, not a missing record — so the trail keeps what the response withholds. This applies to every surface: the public site already answers this way (spec 002 FR-046), and the authenticated portal MUST NOT diverge from it.

**Verification**

- **FR-043c**: What this feature delivers is **structural isolation, not request-time enforcement**, and the distinction MUST be stated wherever the guarantee is claimed. Structural means: every tenant-owned row carries its company, no reference crosses companies, no key or namespace is shared, and row-level security is in place and fails closed. It does **not** mean a request has been refused, because there is no authenticated request yet — decision D1 defers that. A reader who takes SC-003's and SC-004's zeros as evidence that one tenant cannot reach another's data at runtime has over-read them by exactly one feature, and this specification MUST NOT invite that reading.
- **FR-044**: An automated structural audit MUST exist that reports any tenant-owned item lacking a company identifier, any cross-tenant reference, and any referential-integrity violation — across **the same five backing services named in FR-002 and FR-003**, so the health, isolation, and verification requirements all count the same set — and MUST report zero of each against a correctly seeded dataset. The audit MUST evaluate every entity against the global-entity allowlist of FR-009a: an entity that lacks a company identifier and is **not** on the allowlist is a violation, and an entity that appears on the allowlist but has grown a company identifier is also a violation.
- **FR-044a**: A reference to an entity on the FR-009a **global allowlist is never a cross-tenant violation**, and the audit MUST NOT report one. A tenant-scoped role referencing a global permission code is the intended design (FR-009b), so an audit that flagged it would produce a false positive on every role in the system — and a check that is always red is turned off, or worse, its output is skimmed.
- **FR-045**: An automated cross-tenant probe MUST exist that searches for Delta Retail marker phrases in NileTech's context, and the reverse, across every populated store, and MUST return zero results.
- **FR-045b**: The probe's **search method MUST be specified**, because "found nothing" means nothing without it: matching is **case-insensitive substring** over the full text of every candidate field, not exact equality on a whole value. Exact matching would miss a marker embedded in a larger passage, which is the shape a real leak takes — a fragment carried into a summary, a chunk, or a generated answer.
- **FR-045c**: Every isolation check MUST be **demonstrably able to fail**. For each, a deliberately planted violation MUST produce a failure, and that falsification MUST itself be part of the suite. This is the strongest requirement in this section and the least obvious: a probe that searches the wrong store, an audit whose query returns no rows for a reason unrelated to correctness, and a genuinely clean system all report the same green. SC-004's 0% is only evidence if a non-zero result was reachable.
- **FR-045d**: Two companies MAY legitimately generate **identical content** — the same policy sentence, the same job title, the same city. Identical content is therefore **not** evidence of a leak, and the probe MUST distinguish them: it searches for the FR-023a marker phrases, which are unique to one company by construction, rather than for general similarity. A probe that flagged coincidental overlap would fail on a correct dataset, and the fix applied under time pressure is to weaken the probe.
- **FR-045a**: A verification check whose subject is empty MUST report as **skipped, with the reason**, and MUST NOT report as passed. It MUST name the decision that emptied it, so the skip resolves itself when that decision is revisited — FR-045's vector-store leg is vacuous under decision D2 and becomes real when ingestion lands. This is a general rule for every check in this section, not an exemption for one of them: a green result meaning "nothing was examined" is indistinguishable from one meaning "nothing was wrong", and a suite that cannot tell those apart reports confidence it has not earned. The count of skipped checks MUST be visible in the verification output rather than buried in it.
- **FR-046**: An automated coherence check MUST exist that verifies policy-to-record agreement, organizational-hierarchy validity, and date-window plausibility.
- **FR-046a**: The four check families MUST be **defined so that every verification requirement maps to exactly one**, with no requirement in two families and none in none: **determinism** compares two generations of the same inputs (FR-011, FR-012, FR-032); **integrity** checks references and constraints within one dataset (FR-033, FR-034); **isolation** checks that nothing crosses between tenants (FR-039–FR-045); **coherence** checks that generated prose agrees with the structured records it describes (FR-035–FR-038, FR-046). Without the mapping, "the four checks passed" is not a statement about which requirements were exercised, and a requirement can sit permanently between two families with neither owning it.
- **FR-046b**: **Every** check family, not only isolation, MUST include negative-path evidence: for each family, a deliberately broken input MUST produce a failure, and that falsification MUST be part of the suite. FR-045c states this for isolation because that is where it matters most; the reasoning is general. A suite built only from correct data proves the checks run, not that they discriminate — and a check that cannot distinguish a good dataset from a bad one is measuring the harness.
- **FR-047**: The determinism, isolation, coherence, and integrity checks MUST run in continuous integration against a freshly seeded environment on every change.
- **FR-047d**: **Tenant-isolation and database-integrity checks MUST be written before the code they verify**, and MUST be observed failing first. Constitution Principle VIII requires this and no functional requirement asked for it, which is the traceability hole the checklist named. Observing the failure is the substance of the rule, not ceremony: a test written afterwards is shaped by the implementation it was written against and tends to assert what the code does rather than what the requirement says.
- **FR-047e**: Every verification check MUST be **runnable locally by one documented command**, the same command continuous integration runs. A check that only exists in CI has a feedback loop measured in pushes, and the predictable response is to stop running it and let CI find out — which is the slowest possible way to learn.
- **FR-047f**: Each verification run MUST start from a **known state and leave a known state**. A run that depends on residue from a previous one passes in the order it was developed and fails in any other, and a run that leaves residue makes the *next* suite's result conditional on this one. Where a check is destructive — reset and reseed are — it MUST say so and MUST restore a seeded environment before finishing, so the ordering between suites is not load-bearing.
- **FR-047g**: The continuous-integration platform MUST be **named in the documentation set** with its configuration under version control in the repository, so the assumption that CI "exists" resolves to something specific. The checks themselves MUST NOT depend on any platform-specific feature beyond running a documented command — FR-047e already requires that command to work on a laptop, which is what keeps a change of platform a configuration exercise rather than a rewrite.
- **FR-047h**: Coverage is measured by **requirement, not by line**. Every functional requirement and every success criterion in this specification MUST map to at least one automated check, and that mapping MUST be recorded. A line-coverage percentage is deliberately **not** specified: it is satisfiable by tests that execute code without asserting on it, and this project's recurring defect is checks that cannot fail rather than code that is never run.
- **FR-047c**: The project MUST be under version control, and the continuous-integration workflow MUST be triggered by changes to it. This is stated as a requirement rather than assumed because SC-012's guarantee rests entirely on it: without a repository there is no event to run the checks and no change to block, so every verification requirement in this section describes a gate that cannot close.
- **FR-047b**: The determinism check MUST run on **more than one operating system**, because the cross-machine guarantee in SC-002 is otherwise asserted but never exercised. At minimum the verification suite runs on a Linux host and on the team's primary development platform.
- **FR-048**: The project MUST maintain a defined **documentation set**, and every requirement in this specification that refers to something being "documented" MUST resolve to a named location within it. At minimum it contains: the startup and reset commands with prerequisites; the environment configuration surface; the persona reference; Delta Retail's intentional absences; the fingerprint exclusion list and its rationale; and the platform-specific setup caveats. Documentation whose instructions no longer work is a defect, not an inconvenience.
- **FR-048a**: Each of those MUST have a **named home**, so "documented" resolves to a file rather than to a hope:

  | What | Where | Required by |
  |---|---|---|
  | Startup, reset, and every other command, with prerequisites | `docs/running.md` | FR-002, FR-004 |
  | Environment configuration surface | `docs/running.md` and the committed example configuration | FR-005, FR-005a |
  | Persona reference — company, department, role, country, manager | `docs/personas.md` | FR-025b |
  | Delta Retail's intentional absences | `docs/dataset.md` | FR-022 |
  | Fingerprint exclusion list and its rationale | `docs/determinism.md` | FR-015a |
  | Platform-specific setup caveats | `docs/running.md` | SC-001 |
  | Continuous-integration platform | `docs/running.md` | FR-047g |
  | Decision record | `docs/` — see FR-049 | FR-049 |

- **FR-048b**: Documentation generated from the dataset — the persona reference and the realized counts — MUST be **regenerated and compared automatically**, and a mismatch MUST fail the same gate the tests do. This is what makes FR-048's closing sentence enforceable rather than aspirational: prose that drifts from the system is caught by a check, not by a reader noticing. Hand-written documentation cannot be compared this way and is instead the responsibility of the change that invalidates it.
- **FR-048c**: The documentation set MUST be written for a **newcomer with no prior context**, since SC-001 measures exactly that person. Where a document must assume knowledge, it MUST name what it assumes and link to it. "Obvious to someone who already knows the architecture" is the failure mode, and it is invisible to the person writing it.
- **FR-048d**: The tools a newcomer must install before the one documented command works MUST be **stated as a requirement, with versions**, not assumed. SC-001's fifteen minutes is measured from a clean checkout, and an unlisted prerequisite is discovered as a failure partway through — which is precisely the "asking another team member for help" that SC-001 forbids.
- **FR-049**: Design decisions that materially change scope or shape the system MUST be **recorded as they are made**, each with its alternatives, the choice, and its consequence — in the same form as the confirmed scope decisions in this specification. The record MUST continue past this feature: the four decisions here were captured because they were contentious at the time, and the next unrecorded one will be re-litigated by whoever meets it without the reasoning.
- **FR-047a**: The seeded dataset MUST be **capable of expressing all eight of the blueprint's access-control acceptance scenarios** once enforcement is built in the next feature. This feature does not enforce them (decision D1), but it MUST guarantee the data exists to express them: a general policy document readable by any employee; an employee with their own leave balance; another employee's salary record to be denied; a manager with direct reports and their leave data; a second department whose employee records lie outside that manager's scope; two comparable Legal-assigned contracts; distinctive Delta Retail phrasing absent from NileTech; and a report plus a send-capable user for the approval scenario. A data-readiness check MUST verify each of the eight has its required records present. **Each scenario MUST be expressed as a record predicate, not narrative prose** — a query that returns rows or does not — so SC-013's "8 of 8" is computed rather than judged. "A manager with direct reports and their leave data" becomes: a user holding the Manager role, with at least three direct reports in the same company, at least one of whom has a leave balance and a leave request. A scenario nobody can turn into a query cannot be confirmed, and its entry in the count is an opinion.

### Key Entities

**Canonical terminology** — used consistently throughout this specification and required in downstream
plans, tasks, and code:

- **Company** (synonym: **Tenant**) — one of the two isolated organizations that own data: NileTech Solutions or Delta Retail Group. Never used to mean a client organization.
- **Customer** — a client organization that buys from a Company. A Customer is *owned by* exactly one Company and is never itself a tenant. (Some source material uses "company" loosely for both; this spec does not.)
- **User** — an account that can sign in. **Employee** is a User with an employment profile. Every Employee is a User; the Platform Administrator is a User who is not an Employee of either Company.
- **Persona** — one of the fixed, documented Users referenced by name in acceptance tests and the demo script (FR-025b). A Persona is an ordinary User, distinguished only by having stable, documented identity.
- **Product** — an internally sellable catalog item that Orders reference. **Public Product** — a marketing item shown on the public site. These are separate entities and are not interchangeable.
- **Classification** — one of exactly four levels defined in FR-010a. Terms such as "sensitive", "secret", or "private" are not used as classification values.

**Organization**

- **Company (Tenant)**: The isolation boundary. Name, domain, status. Every other tenant-owned entity references exactly one.
- **Office / Location**: A physical site belonging to a company — city, country, address, and which departments it hosts. NileTech has Cairo, Alexandria, and Dubai.
- **Department**: A named unit within a company, headed by one employee.
- **Role**: A named bundle of permissions within a company — Company Admin, Employee, Manager, HR, Finance, Legal, Auditor. Tenant-scoped: each company has its own role rows. (Platform Admin is platform-level, not a per-company role — see below.)
- **Permission**: A stable capability code that roles grant and that later authorization work checks. **Global** — a single shared catalog, identical for both companies, deliberately carrying no company identifier (FR-009a, FR-009b).
- **User**: A person who can sign in. Belongs to one company and one department, may have one manager, carries country and employment type.
- **Platform Administrator**: A single platform-level account bound to **no** company. Not a member of either company, absent from both user directories, and holding no automatic access to any company's business data. The only user-like entity on the global allowlist.

**HR**

- **Employee Profile**: Employment detail for a user — job title, salary band, hire date, employment type.
- **Leave Balance**: Entitlement and remaining days per user and leave type, consistent with the leave policy for that user's country.
- **Leave Request**: A dated request by a user, with type, span, status, and approver.
- **Attendance Record**: Presence data per user per working day, respecting that country's non-working days.
- **Training Record**: A course or certification a user completed, with date and outcome.
- **Performance Review**: A periodic review of a user by their manager, with period, rating, and narrative.

**Sales & Finance**

- **Customer**: A client organization of a Company, with region and account owner. Owned by exactly one Company; never shared between the two (FR-024a).
- **Product**: A sellable offering with a tier and price.
- **Order**: A dated purchase by a customer, attributed to a sales representative, containing product lines.
- **Invoice**: The billing record for an order, with totals arithmetically derived from that order.
- **Sales Target**: A goal for a period, region, or representative, against which actual orders can be measured.
- **Expense**: A dated, categorized cost belonging to a department.
- **Budget**: A departmental allocation for a period, against which expenses can be measured.

**Legal & Documents**

- **Contract**: A customer contract, supplier agreement, NDA, or employment template, with clause content and meaningful differences between comparable documents.
- **Policy Document**: An internal governing document — handbook, leave, remote work, expense, security, code of conduct, travel, benefits.
- **Document Metadata**: The record describing any stored file — company, department, owner, title, storage key, classification, country, and document type.

**Public Content**

- **Service**: A NileTech service offering shown on the public site.
- **Public Product**: A product offering presented publicly, distinct from the internal sellable product catalog.
- **Leadership Profile**: A public profile of a company executive, corresponding to a real generated employee, exposing only public-appropriate fields.
- **News Item**: A dated public announcement.
- **Vacancy**: An open position with department, location, and description.

**Platform**

- **Audit Entry**: A record of a consequential operation — actor, company, action, resource type and identifier, decision, reason, and timestamp. Seeding itself produces audit entries.
- **Job Record**: A background job with its owning company and status.
- **Dataset Manifest**: The record of how this dataset was produced — seed value, pinned reference date, generator version, per-entity counts, and fingerprint.

## Success Criteria *(mandatory)*

### Measurable Outcomes

Every criterion below is stated as **pass or fail against a stated threshold**, never as a direction
to improve in. "Fast", "reliable", and "mostly isolated" are not outcomes anything can be held to;
a number, a count, or a zero is. Where a criterion admits a range — SC-005's employee count — the
range is the threshold, and a result outside it fails.

- **SC-001**: A team member with no prior project setup goes from a clean checkout to a fully running, healthy local system in under 15 minutes using one documented command, without asking another team member for help.
- **SC-002**: Seeding two separate empty environments produces datasets whose content fingerprints match exactly — 100% identical across every entity family and every generated file, on every team member's machine and in continuous integration.
- **SC-003**: 100% of tenant-owned items across every populated store carry a company identifier; the structural audit reports zero unattributed items and zero cross-tenant references. Exactly the four entities on the global allowlist (permission catalog, platform administrator, migration history, dataset manifest) are unscoped — no more, no fewer.
- **SC-004**: Cross-tenant probes return zero results in every populated store, in both directions, on every run — an unauthorized-visibility rate of 0%. **The denominator is stated so the rate is computable**: it is the number of *probe executions*, being every marker phrase (FR-023a: three per company) searched against every populated store in both directions, and the numerator is the executions returning at least one match. A rate over an undefined population is not a measurement, and 0% divided by zero probes is the result a suite that examined nothing would also report — which is why FR-045c requires each probe to be demonstrably able to fail, and FR-045a requires an empty subject to report as skipped rather than passed.
- **SC-005**: NileTech contains between 190 and 210 employees spanning all eight named departments and all three named offices, with every employee resolving to exactly one department and a valid position in a cycle-free reporting hierarchy.
- **SC-006**: Referential-integrity checks report zero orphaned references across all generated relationships.
- **SC-007**: Coherence checks report zero disagreements between values stated in generated documents and the corresponding structured records.
- **SC-008**: The full seed completes on a standard developer machine in under 10 minutes, and a full reset-and-reseed cycle completes in under 15 minutes.
- **SC-009**: A full stop, reset, and restart cycle returns the environment to a verified-identical dataset with no manual repair steps, on 100% of attempts.
- **SC-010**: Every entity family named in this specification is present and non-empty for NileTech, and every family required for isolation testing is present and non-empty for Delta Retail.
- **SC-011**: Zero items marked as public content contain salary figures, contract terms, internal financial data, or personal contact details of non-executive staff.
- **SC-012**: The determinism, isolation, coherence, and integrity checks all run automatically on every change and block the change when any of them fails. **"Block" means a pull request whose checks must pass before merge**, which requires the repository to be under version control — it was not when this criterion was written, so `ci.yml` existed with nothing to trigger it and the criterion could not be evaluated at all. A check that no event runs is not a gate.
- **SC-013**: The data-readiness check confirms that all eight blueprint access-control scenarios have their required records present — 8 of 8, with zero scenarios unsupported.
- **SC-014**: Every persona in the fixed persona set resolves to exactly one user with the documented company, department, role, country, and manager, on 100% of seed runs.
- **SC-015**: Both `PUBLIC` and `RESTRICTED` classifications are present and non-empty for both companies, and every classified item carries exactly one of the four permitted levels — zero items carry an unrecognized or absent classification.
- **SC-016**: The full verification suite completes in under **20 minutes** against the reduced profile of FR-020f, and every check is runnable locally by the same command continuous integration uses. A suite too slow to run before pushing stops being run before pushing, and then its results arrive too late to change the change.

## Assumptions

**Scope boundaries**

- This feature delivers the repository structure, the runnable local environment, the schema, and the generated dataset. It does **not** deliver working authentication, the authorization policy engine, retrieval, agents, or any user interface — those are separate features built on this foundation. Roles and permissions are generated **as data** here so the later authorization feature has them available. *(See Open Question Q1.)*
- Document files are generated and stored, and their metadata records are created, but documents are **not** chunked, embedded, or indexed for semantic search in this feature. The vector store is provisioned and structured for tenant-scoped entries; populating it is ingestion work belonging to a later feature. *(See Open Question Q2.)*
- Continuous integration runs the verification checks defined here; broader deployment pipelines and hosted environments are out of scope.

**Standard developer machine**

SC-001 and SC-008 both state time budgets, and a budget against an undefined machine is not a
measurement. For this project a standard developer machine is: **4 physical CPU cores, 16 GB RAM,
20 GB free disk, and an SSD**, running a supported container runtime, on a broadband connection
capable of pulling the container images within the first-run allowance. Slower hardware does not
make the system incorrect; it makes SC-001 and SC-008 inapplicable, and that is the distinction
this definition exists to permit.

The environment MUST fit within that machine while the whole stack runs — all seven services of
FR-002 together, including the peak of a full seed. Fitting is the requirement; per-service memory
and disk caps are deliberately **not** specified, because pinning a limit per container would
bind implementation choices this specification has no reason to make, and would need revising
every time a service is added. The observable budget is the one stated here.

**Data and content**

- The dataset is generated against a **pinned reference date** rather than the current clock, so historical windows — orders, attendance, reviews, invoices — stay fixed permanently. The pinned date is recorded in the dataset manifest.
- Delta Retail Group is assumed to be roughly one fifth the size of NileTech: large enough to populate every entity family used in isolation tests, small enough to keep seeding fast.
- All generated content is in English. Employee names and locations reflect the Egypt and UAE setting. Content is entirely fictional and contains no real personal data.
- Monetary amounts are generated in a single reporting currency per company, with the currency recorded explicitly, rather than modelling live exchange rates.
- Public holidays and weekend patterns are approximated per country from a fixed, committed table rather than an external calendar service, to preserve determinism.
- The role set and permission vocabulary come from the blueprint and are generated as-is: seven tenant-scoped roles per company (Company Admin, Employee, Manager, HR, Finance, Legal, Auditor) plus the single platform-level Platform Administrator. Custom per-company roles are not generated.
- Delta Retail Group's five departments are a plausible retail subset (HR, Sales, Finance, Operations, and Executive Management); it deliberately has no Engineering or Legal department, which is documented rather than accidental.

**Inherited constraints** *(from the project constitution and blueprint — not decisions made by this specification)*

- The complete local system runs through Docker Compose, covering the backend, frontend, relational store, vector store, cache and queue, object store, and background worker.
- Every schema change ships as a reversible migration; seeds are deterministic and idempotent.
- Tests for tenant isolation are written before the code they verify.
- The seed process writes audit records for what it creates.

## Confirmed Scope Decisions

Three scope decisions materially change the size of this feature. Each was presented to the project
owner with alternatives and **confirmed on 2026-07-31**. They are applied consistently throughout the
specification above and are no longer open.

| # | Decision | Confirmed choice | Consequence for this feature |
|---|----------|------------------|------------------------------|
| D1 | Authentication and authorization scope | Roles, permissions, and role assignments are generated **as data only**. No login flow and no authorization policy engine. | Isolation is proven **structurally** here (every item tenant-scoped, zero cross-tenant references), not yet at request time. Request-time enforcement is the next feature. |
| D2 | Vector store scope | The vector store is **provisioned with tenant-scoped structure but left unpopulated**. | The semantic cross-tenant probe (searching Delta marker phrases via similarity search) cannot run until ingestion lands. FR-045's vector-store probe is therefore satisfied here by asserting the collection is empty and correctly structured; the semantic version of that probe becomes a required acceptance test of the ingestion feature. |
| D3 | Generated document file format | Documents are generated as **text-based files** with deterministic byte content, not PDF/DOCX binaries. | Byte-identical output (FR-032) is straightforward. The document-parsing pipeline gets no real exercise until the ingestion feature introduces binary formats. |

| D4 | Synthetic code repository | **Deferred to the ingestion feature.** | The blueprint lists a small synthetic repository (authentication, leave, reporting, notification modules) enabling the code-aware RAG demo. It is generated content, but nothing in *this* feature can consume it: code-aware chunking, a code-specific index, and the "explain the authentication module" scenario all belong to ingestion (D2). Generating it here would produce files that sit unread until that feature arrives, and its chunking strategy would be designed without the retriever that has to use it. |

**Carried forward** — these are **binding, not advisory**. Each must appear in the next feature's
specification, and that feature's planning is incomplete until each is either addressed or
re-deferred with a new recorded decision under FR-049. A carry-forward list nobody is obliged to
read is a list of things that quietly stop being anyone's job:

- Request-time authorization enforcement and the login flow (from D1).
- Chunking, embedding, and indexing of the seeded documents, plus the **semantic** cross-tenant leak
  test that only becomes possible once the vector store holds real content (from D2).
- Binary document formats (PDF/DOCX) to exercise parsing (from D3).
- **The synthetic code repository** — authentication, leave, reporting, and notification modules —
  together with code-aware chunking and the blueprint's "explain the authentication module"
  scenario (from D4).
