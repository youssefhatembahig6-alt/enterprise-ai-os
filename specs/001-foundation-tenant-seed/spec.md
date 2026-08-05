# Feature Specification: Foundation — Monorepo, Local Environment & Deterministic Two-Tenant Dataset

**Feature Branch**: `001-foundation-tenant-seed`

**Created**: 2026-07-31

**Status**: Draft

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
- Q: SC-012 requires the checks to "block the change", but the project is not under version control — what does "block" mean? → A: The repository is placed under version control and the gate is a pull request whose checks must pass. `ci.yml` already exists and has never been triggered by anything.
- Q: How must a verification check behave when its subject is empty — for example FR-045's vector-store leg under decision D2? → A: Report as **skipped**, naming the deferral that emptied it. A silent pass is indistinguishable from a real one.
- Q: Should dependency direction between packages be a requirement, or a code-review convention? → A: A stated requirement, enforced by an automated import check, so a backwards dependency fails the build rather than depending on a reviewer noticing.
- Q: How is the API versioned, given `packages/contracts` generates client types from it? → A: No version segment in the path. The published OpenAPI document and the generated types are the compatibility gate, and that gate already exists.

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

- **FR-001**: The project MUST be organized as a single monorepo with one documented home for each of: application backend, application frontend, data generation and seeding, shared contracts and schemas, infrastructure definitions, tests, and documentation.
- **FR-001a**: Dependency direction between workspace members MUST be a stated rule, enforced automatically:
  - `packages/*` MUST NOT import from `apps/*`, `services/*`, or `scripts/*`;
  - `apps/*`, `services/*`, and `scripts/*` MAY import from `packages/*` but MUST NOT import from one another;
  - code needed by two members moves **down** into `packages/`, never sideways.
  An automated check MUST fail the build on a violation. The rule is written down because it has already been needed and resolved by judgement rather than by rule: the seed loader required a Redis key pattern that the API also writes, and nothing stated that `scripts/seed` may not import from `apps/api` — the pattern was moved into `packages/core` because that seemed right, which is precisely the decision a rule exists to make unnecessary. The next feature adds a second application and a second API surface, so the cost of leaving this implicit rises.
- **FR-001b**: API paths MUST NOT carry a version segment. Compatibility is governed by the **published OpenAPI document and the generated client types**, which must agree with the running service — a gate that already exists and already fails on drift. This system deploys its client and its server together and has one consumer per surface, so a `/v1/` prefix would add a permanent cost to buy an option nothing needs. If a second, independently-deployed consumer ever appears, this decision is the thing to revisit first.
- **FR-002**: The complete local system MUST start from a clean checkout via one documented command, bringing up the relational store, vector store, cache and job queue, object store, background worker, backend service, and frontend service.
- **FR-003**: The system MUST expose a health check that individually reports the reachability of each backing service, so a partially started environment is immediately visible.
- **FR-004**: The environment MUST provide documented commands to start, stop, reset (destroy all state), and re-seed, and each MUST be safe to run repeatedly.
- **FR-005**: All configuration that differs between machines MUST be supplied through environment configuration with documented defaults that work out of the box for local development; no team member may need to hand-edit committed files to start the system.
- **FR-006**: No secret values may be committed to the repository; local development MUST work from documented example configuration containing only non-production placeholder values.

**Schema and migrations**

- **FR-007**: All structured data MUST be created through versioned, ordered, reversible migrations; no schema object may exist only as a manual change.
- **FR-008**: Rebuilding the database from migrations alone MUST produce an identical schema on any machine.
- **FR-009**: Every tenant-owned entity MUST carry a company identifier as a mandatory, non-nullable attribute.
- **FR-009a**: The specification MUST name an explicit, closed **global-entity allowlist** — the small set of entities that legitimately have no company identifier. For this feature that allowlist is: the **permission catalog**, the **platform-level administrator account**, the **schema-migration history**, and the **dataset manifest**. Every entity not on this allowlist is tenant-owned and MUST satisfy FR-009.
- **FR-009b**: The permission catalog MUST be **global and shared** — one set of permission codes used identically by both companies — so that permission codes cannot drift apart between tenants. Roles remain tenant-scoped and reference the global permission codes.
- **FR-009c**: The **Platform Admin** MUST be modelled as a platform-level account bound to **no** company. It MUST NOT be a member of either company, MUST NOT appear in either company's user directory, and MUST NOT receive automatic access to any company's business data.
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

**Deterministic generation**

- **FR-011**: The seed process MUST be deterministic: given the same fixed seed value it MUST produce an identical dataset on every machine and every run — identical identifiers, relationships, names, amounts, dates, text, and generated files.
- **FR-012**: Generation MUST NOT depend on the current clock, machine timezone, machine locale, unseeded random sources, or filesystem iteration order. All dates MUST derive from a single pinned reference date recorded with the dataset.
- **FR-012a**: The controls that make byte-identical output achievable MUST be in place and enforced: all generated text is written as UTF-8 with **LF** line endings and no byte-order mark; the repository declares LF as the checked-out line ending; and container locale is pinned so number and date formatting cannot vary by host. A single fixture document MUST be asserted against an exact content digest, so a byte-level regression is caught at the file rather than surfacing as an unexplained whole-dataset mismatch.
- **FR-012b**: Every dependency that can influence generated content MUST be version-pinned with a committed lockfile. Generated names, words, and text come from library data that changes between releases, so an unpinned upgrade would silently change the dataset.
- **FR-012c**: The **root seed value MUST be fixed and committed** as the project default. It may be overridden for experimentation, but the committed default is the one every team member, every verification run, and every demo uses.
- **FR-013**: The seed process MUST populate an empty environment end to end in a single invocation, with no manual intervening steps.
- **FR-014**: The seed process MUST **refuse to run against a non-empty environment**, exiting with a clear message and a non-zero status. It MUST NOT attempt a partial top-up, and it MUST NOT be possible to produce a doubled or partially doubled dataset by accident.
- **FR-014a**: Destroying an existing dataset MUST require an explicit, separate reset action — never a side effect of running the seed. The reset action MUST state what it is about to destroy before proceeding.
- **FR-014b**: The seed MUST write a **completion marker** to the dataset manifest only after every entity family has been written successfully. An environment whose manifest lacks the completion marker MUST be treated as incomplete by the seed, the verification command, and continuous integration alike.
- **FR-014c**: A seed run that fails partway MUST leave the environment detectably incomplete rather than plausibly complete: relational writes roll back where the store supports it, and any object-storage or vector-store content written before the failure is reported by the verification command as inconsistent with the manifest.
- **FR-015**: The seed process MUST report a per-entity-family summary of counts and a dataset fingerprint on completion, so two runs can be compared without manual inspection.
- **FR-015a**: The dataset fingerprint MUST cover the **content** of every generated record and file — including identifiers, relationships, text, amounts, dates, and classification — and MUST exclude values that legitimately vary between environments, namely wall-clock insertion timestamps, connection or session identifiers, and physical storage locations. The fingerprint MUST be independent of row-retrieval order, so two runs that insert in different orders but produce the same content still match. The exclusion list MUST be documented, because an over-broad exclusion would silently weaken the determinism guarantee in SC-002.
- **FR-016**: The dataset MUST record its own generation metadata — seed value, reference date, generator version, per-family realized counts, fingerprint, and completion marker — so any environment can state exactly which dataset it holds.
- **FR-017**: A verification command MUST exist that recomputes the dataset fingerprint from the live environment and reports whether it matches the expected value.

**Tenant content — NileTech Solutions**

- **FR-017a**: A **known-good dataset fingerprint MUST be committed to version control** and asserted against on every change. Without a pinned expected value, verification only proves the dataset matches its own manifest — a code change that alters generation produces a new dataset and a new manifest that agree with each other perfectly, and the drift goes undetected.
- **FR-018**: The system MUST generate NileTech Solutions as a software and business-automation company with offices in Cairo, Alexandria, and Dubai.
- **FR-019**: NileTech MUST have approximately 200 employees distributed across eight departments: Engineering, HR, Sales, Finance, Legal, Customer Support, Operations, and Executive Management.
- **FR-020**: Employee distribution across departments and offices MUST be plausible for a company of this type and size rather than uniform, and MUST be stable across runs.
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

- **FR-020c**: Transactional volumes MUST show plausible variation over the window — seasonality, growth, and per-representative differences — rather than a flat rate, so that trend questions have a real trend to find. The variation MUST be deterministic.

**Tenant content — Delta Retail Group**

- **FR-021**: The system MUST generate Delta Retail Group as a fully independent second company with its own departments, employees, roles, business data, documents, and files.
- **FR-022**: Delta Retail Group MUST be smaller than NileTech but complete enough to exercise every entity family used in isolation tests. Where Delta deliberately lacks something NileTech has — it has no Engineering and no Legal department — that absence MUST be documented as intentional rather than left to look like a generation gap.
- **FR-023**: Delta Retail content MUST include distinctive marker phrases appearing nowhere in NileTech content, so any cross-tenant leak is unambiguously detectable by search.
- **FR-024**: No generated record, file, document, vector entry, cache entry, job, or audit entry may belong to both companies or reference an entity owned by the other company.
- **FR-024a**: The two companies MUST share **nothing** except the entities on the global allowlist defined in FR-009a. They have no shared users, no shared customers, no shared products, no shared documents, no shared storage prefix, and no shared cache namespace. Customer records belonging to one company MUST NOT be reused as customer records of the other, even where a plausible real-world overlap would exist.

**Generated entity families**

- **FR-025**: The system MUST generate **organizational** data: companies, departments, offices and locations, roles, permissions, role-to-permission assignments, users, user-to-role assignments, and manager and reporting relationships.
- **FR-025a**: Every user MUST hold **exactly one primary role**. A user who has at least one direct report MUST additionally hold the Manager role. No other multi-role combinations are generated, so role assignment is unambiguous and predictable.
- **FR-025b**: The dataset MUST include a **fixed, documented persona set** with stable identifiers and stable credentials-in-waiting, covering at minimum: a NileTech Employee with their own leave balance; that employee's Manager, holding at least three direct reports; an employee in a different department whose records the Manager must not reach; an HR user with company-wide HR access; a Finance user; a Legal user holding an explicit resource-level grant on restricted contracts; an Auditor; a Company Admin; a Delta Retail employee; and a user permitted to draft and send communications. Personas MUST be listed in the feature documentation with their company, department, role, country, and manager.
- **FR-025c**: Persona identifiers, email addresses, department assignments, and reporting relationships MUST NOT change between seed runs or between generator versions unless the change is deliberate and documented, because acceptance tests, evaluation sets, and the demo script all reference them by name.
- **FR-026**: The system MUST generate **HR** data: employee profiles, job titles, salary bands, leave balances, leave requests, attendance records, training records, and performance reviews.
- **FR-027**: The system MUST generate **sales and finance** data: customers, products, sales representatives, orders, invoices, sales targets, regions, expenses, budgets, and monthly revenue aggregates.
- **FR-028**: The system MUST generate **legal** data: customer contracts, supplier agreements, non-disclosure agreements, and employment templates, each with realistic clause content including terms that differ meaningfully between comparable documents.
- **FR-028a**: The legal data MUST include at least one **matched pair of comparable contracts** assigned to Legal that differ in specific, quotable terms — differing notice periods, differing liability caps, and at least one clause category where the two agree — so that the blueprint's contract-comparison scenario has a real, verifiable answer. Both MUST be classified above INTERNAL and reachable by the Legal persona through an explicit resource-level grant.
- **FR-029**: The system MUST generate **policy documents**: employee handbook, leave policy, remote-work policy, expense policy, security policy, code of conduct, travel policy, and benefits guide.
- **FR-030**: The system MUST generate **public company content** for **both companies**: services, product offerings, leadership profiles, news items, open vacancies, and office information. NileTech's public content is the richer set (it is the company whose public site is a mandatory surface); Delta Retail receives a smaller but complete set, because `PUBLIC` classification must exist for both tenants (FR-010c) and public content is itself an isolation surface that must be provable per tenant.
- **FR-031**: Every generated document MUST exist both as a stored file in the object store and as a metadata record carrying company, department, owner, classification, country, and document type.
- **FR-031a**: Every stored file MUST have **exactly one owning user, of the same company**. Ownership follows a fixed convention so it is predictable and testable: policy documents are owned by the head of the department that governs them (HR policies by the HR head, security policy by the Operations head); contracts and agreements are owned by a Legal user where the company has a Legal department, and otherwise by the head of Executive Management; departmental reports and expense records are owned by that department's head; public content is owned by the head of Executive Management; and employee-specific documents are owned by the employee they concern. No file may be ownerless, and no file may be owned by a user of the other company.
- **FR-032**: Generated document files MUST be byte-identical across runs for a given seed value.

**Coherence and integrity**

- **FR-033**: All generated relationships MUST have referential integrity — zero orphaned references across every entity family.
- **FR-034**: Reporting relationships MUST form a valid hierarchy per company: no cycles, at most one manager per employee, exactly one manager-less top-level executive, and every department headed by an employee of that department.
- **FR-035**: Values stated in generated documents MUST match the corresponding structured records — most importantly, leave entitlements stated in the leave policy MUST match generated leave balances for the employee's country and employment type.
- **FR-036**: Generated documents MUST reference only department names, office locations, countries, role names, and people that exist in that same company's structured data.
- **FR-037**: All generated dates MUST fall within a plausible window relative to the pinned reference date, and no child record may predate its parent — an order cannot precede its customer, a leave request cannot precede the employee's hire date.
- **FR-038**: Monetary values MUST record an explicit currency and MUST be internally consistent: invoice totals derive from their order lines, and budgets and expenses share the same currency basis within a company.

**Isolation scaffolding across stores**

- **FR-039**: Object-storage keys MUST be namespaced by company and classification so one company's files cannot collide with, or be enumerated from, the other's.
- **FR-040**: Cache keys MUST be namespaced by company so no cached value can be shared across companies.
- **FR-041**: Vector-store collections and entries MUST be structured so every stored entry carries its company identifier and can be filtered by it before any similarity result is returned.
- **FR-042**: Background job records MUST carry the company identifier of the work they perform.
- **FR-043**: Audit entries MUST carry the company identifier, and the seed process itself MUST record audit entries for the dataset creation it performs.
- **FR-043a**: A request for a resource belonging to another company MUST be answered as **not found**, never as forbidden. A response that distinguishes "exists but denied" from "does not exist" is itself a disclosure: it confirms the resource's existence and lets a caller enumerate another tenant's identifiers without ever receiving their data. The **audit entry MUST record the real reason** — a cross-tenant denial, not a missing record — so the trail keeps what the response withholds. This applies to every surface: the public site already answers this way (spec 002 FR-046), and the authenticated portal MUST NOT diverge from it.

**Verification**

- **FR-044**: An automated structural audit MUST exist that reports any tenant-owned item lacking a company identifier, any cross-tenant reference, and any referential-integrity violation — and MUST report zero of each against a correctly seeded dataset. The audit MUST evaluate every entity against the global-entity allowlist of FR-009a: an entity that lacks a company identifier and is **not** on the allowlist is a violation, and an entity that appears on the allowlist but has grown a company identifier is also a violation.
- **FR-045**: An automated cross-tenant probe MUST exist that searches for Delta Retail marker phrases in NileTech's context, and the reverse, across every populated store, and MUST return zero results.
- **FR-045a**: A verification check whose subject is empty MUST report as **skipped, with the reason**, and MUST NOT report as passed. It MUST name the decision that emptied it, so the skip resolves itself when that decision is revisited — FR-045's vector-store leg is vacuous under decision D2 and becomes real when ingestion lands. This is a general rule for every check in this section, not an exemption for one of them: a green result meaning "nothing was examined" is indistinguishable from one meaning "nothing was wrong", and a suite that cannot tell those apart reports confidence it has not earned. The count of skipped checks MUST be visible in the verification output rather than buried in it.
- **FR-046**: An automated coherence check MUST exist that verifies policy-to-record agreement, organizational-hierarchy validity, and date-window plausibility.
- **FR-047**: The determinism, isolation, coherence, and integrity checks MUST run in continuous integration against a freshly seeded environment on every change.
- **FR-047c**: The project MUST be under version control, and the continuous-integration workflow MUST be triggered by changes to it. This is stated as a requirement rather than assumed because SC-012's guarantee rests entirely on it: without a repository there is no event to run the checks and no change to block, so every verification requirement in this section describes a gate that cannot close.
- **FR-047b**: The determinism check MUST run on **more than one operating system**, because the cross-machine guarantee in SC-002 is otherwise asserted but never exercised. At minimum the verification suite runs on a Linux host and on the team's primary development platform.
- **FR-048**: The project MUST maintain a defined **documentation set**, and every requirement in this specification that refers to something being "documented" MUST resolve to a named location within it. At minimum it contains: the startup and reset commands with prerequisites; the environment configuration surface; the persona reference; Delta Retail's intentional absences; the fingerprint exclusion list and its rationale; and the platform-specific setup caveats. Documentation whose instructions no longer work is a defect, not an inconvenience.
- **FR-047a**: The seeded dataset MUST be **capable of expressing all eight of the blueprint's access-control acceptance scenarios** once enforcement is built in the next feature. This feature does not enforce them (decision D1), but it MUST guarantee the data exists to express them: a general policy document readable by any employee; an employee with their own leave balance; another employee's salary record to be denied; a manager with direct reports and their leave data; a second department whose employee records lie outside that manager's scope; two comparable Legal-assigned contracts; distinctive Delta Retail phrasing absent from NileTech; and a report plus a send-capable user for the approval scenario. A data-readiness check MUST verify each of the eight has its required records present.

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

- **SC-001**: A team member with no prior project setup goes from a clean checkout to a fully running, healthy local system in under 15 minutes using one documented command, without asking another team member for help.
- **SC-002**: Seeding two separate empty environments produces datasets whose content fingerprints match exactly — 100% identical across every entity family and every generated file, on every team member's machine and in continuous integration.
- **SC-003**: 100% of tenant-owned items across every populated store carry a company identifier; the structural audit reports zero unattributed items and zero cross-tenant references. Exactly the four entities on the global allowlist (permission catalog, platform administrator, migration history, dataset manifest) are unscoped — no more, no fewer.
- **SC-004**: Cross-tenant probes return zero results in every populated store, in both directions, on every run — an unauthorized-visibility rate of 0%.
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

## Assumptions

**Scope boundaries**

- This feature delivers the repository structure, the runnable local environment, the schema, and the generated dataset. It does **not** deliver working authentication, the authorization policy engine, retrieval, agents, or any user interface — those are separate features built on this foundation. Roles and permissions are generated **as data** here so the later authorization feature has them available. *(See Open Question Q1.)*
- Document files are generated and stored, and their metadata records are created, but documents are **not** chunked, embedded, or indexed for semantic search in this feature. The vector store is provisioned and structured for tenant-scoped entries; populating it is ingestion work belonging to a later feature. *(See Open Question Q2.)*
- Continuous integration runs the verification checks defined here; broader deployment pipelines and hosted environments are out of scope.

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

**Carried forward** — these must appear in the next feature's specification, because this one
deliberately defers them:

- Request-time authorization enforcement and the login flow (from D1).
- Chunking, embedding, and indexing of the seeded documents, plus the **semantic** cross-tenant leak
  test that only becomes possible once the vector store holds real content (from D2).
- Binary document formats (PDF/DOCX) to exercise parsing (from D3).
- **The synthetic code repository** — authentication, leave, reporting, and notification modules —
  together with code-aware chunking and the blueprint's "explain the authentication module"
  scenario (from D4).
