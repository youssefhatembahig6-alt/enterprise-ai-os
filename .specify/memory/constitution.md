<!--
SYNC IMPACT REPORT
==================
Version change: (unversioned template) → 1.0.0
Bump rationale: Initial ratification. All placeholder tokens replaced with concrete,
project-specific governance derived from docs/Enterprise_AI_OS_EDITED.html and the
19 mandatory principles supplied by the project owner.

Modified principles:
  [PRINCIPLE_1_NAME] → I. Tenant Isolation Is Absolute
  [PRINCIPLE_2_NAME] → II. Deterministic Authorization, Never Delegated To A Model
  [PRINCIPLE_3_NAME] → III. No Unauthorized Data Enters The Context Window
  [PRINCIPLE_4_NAME] → IV. Grounded Answers Only
  [PRINCIPLE_5_NAME] → V. Business Facts Come From Systems Of Record
  (added)            → VI. Every Agent Tool Is A Declared Contract
  (added)            → VII. Human Approval Gates Irreversible Actions
  (added)            → VIII. Test-First For Security And Correctness
  (added)            → IX. Reproducible Synthetic Enterprise Data
  (added)            → X. Audit By Default

Added sections:
  [SECTION_2_NAME] → Mandatory Surfaces, Contracts & Environment
  [SECTION_3_NAME] → Development Workflow & Quality Gates
  Governance filled with amendment procedure, versioning policy, compliance review.
  Principle Traceability table mapping all 19 owner mandates to constitution clauses.

Removed sections: none.

Templates requiring updates:
  ✅ .specify/templates/plan-template.md   — Constitution Check gates filled in
  ✅ .specify/templates/tasks-template.md  — "Tests are OPTIONAL" corrected to mandatory
                                             for constitution-critical categories
  ✅ .specify/templates/spec-template.md   — no change needed; structure already
                                             accommodates security requirements and
                                             measurable success criteria
  ✅ .specify/templates/checklist-template.md — no change needed (generic)
  ✅ .claude/skills/speckit-*/SKILL.md     — reviewed; no agent-specific stale references

Follow-up TODOs: none. No deferred placeholders remain.
-->

# Enterprise AI Operating System Constitution

The authoritative product blueprint for this project is `docs/Enterprise_AI_OS_EDITED.html`.
That document is the primary source of truth for scope, architecture, components, tenants,
roles, permissions, data model, acceptance tests, and timeline. This constitution governs
*how* that blueprint is built. Where a specification, plan, or task conflicts with the
blueprint, the blueprint wins on **what** to build; this constitution wins on **how** it
must be built and what may not be compromised.

## Core Principles

### I. Tenant Isolation Is Absolute (NON-NEGOTIABLE)

Every company-owned artifact MUST carry and be filtered by `company_id`: relational rows,
document metadata, object-storage keys, vector payloads, cache entries, background jobs,
generated reports, evaluation records, and audit events. No query, retrieval, tool call,
cache read, file download, or scheduled job may execute without a tenant constraint derived
from the server-built access context.

`NileTech Solutions` and `Delta Retail Group` MUST exist as completely isolated tenants and
MUST remain the standing proof of this principle. A NileTech identity retrieving any Delta
Retail record, chunk, file, cached answer, or citation — including under semantic search
using distinctive Delta phrasing — is a release-blocking defect, not a bug to triage.

PostgreSQL Row-Level Security MUST be enabled on the highest-risk tables as the final safety
net; application-level filters remain mandatory regardless, because RLS is a backstop and not
an excuse for an unscoped query.

**Rationale**: Cross-tenant leakage is the one failure mode that cannot be apologised for or
patched after the fact. Making tenancy a property of every artifact — rather than a check at
one chokepoint — means a forgotten filter fails closed instead of silently leaking.

### II. Deterministic Authorization, Never Delegated To A Model (NON-NEGOTIABLE)

Authorization decisions MUST be made by deterministic code — the Authorization Policy Engine —
and MUST NOT be made, influenced, softened, or overridden by an LLM. The model may *propose* a
tool call, a query, or a retrieval; a deterministic function decides whether it runs. The model
never grants itself permission, never widens its own scope, and never changes tenant.

The authorization model MUST layer, in this order:

1. **Multi-tenancy** — the tenant boundary, checked first and never bypassed.
2. **RBAC** — permission codes granted through roles (`documents:read`, `hr:read_self`,
   `hr:read_team`, `hr:read_all`, `sales:read`, `finance:read`, `contracts:read`,
   `reports:generate`, `actions:approve`, `audit:read`, `communications:draft`,
   `communications:send`, and the rest of the blueprint vocabulary). Code checks permission
   codes, never role names.
3. **ABAC** — conditions on department, country, ownership, classification, employment type,
   and manager relationship.
4. **Resource ACL** — per-document, per-folder, per-contract exceptions.
5. **Human approval** — see Principle VII; a separate control that applies *after* authorization
   has already passed.

The Backend MUST build a trusted access context (`company_id`, user, department, country,
roles, permissions, manager relationships, ownership) from verified identity only. That context
is immutable once handed to the Orchestrator. Every denial MUST return 403 and write a denied
audit event.

**Rationale**: A probabilistic system cannot be a security boundary. Prompt injection, jailbreaks,
and ordinary model error all become access-control failures the moment a model is trusted to
decide who may see what.

### III. No Unauthorized Data Enters The Context Window (NON-NEGOTIABLE)

Authorization MUST be applied *before* retrieval, not after generation. Unauthorized chunks,
rows, files, or tool results MUST never reach the LLM prompt — the system does not retrieve
confidential material and then ask the model to withhold it.

Concretely: Qdrant payload filters (`company_id`, `department_id`, `country`, `classification`,
`allowed_roles`, `owner_id`) are applied at search time; PostgreSQL access goes through scoped,
read-only, parameterized queries; Object Storage URLs are short-lived and issued only after an
authorization check; Redis cache keys MUST include tenant plus a user-or-permission fingerprint
plus the normalized question plus a data/document version, so an HR-scoped answer can never be
served to an Employee.

The ingestion pipeline MUST attach complete access metadata to every chunk. A chunk without
access metadata MUST NOT be indexed.

**Rationale**: Once text is in the context window it can be paraphrased, summarized, or leaked
through the answer. Filtering at retrieval is the only enforceable point; filtering after
generation is theatre.

### IV. Grounded Answers Only

Every user-facing AI answer MUST be traceable to authorized retrieved sources or verified tool
results, and MUST carry citations to those sources. The LLM is instructed to answer only from
provided context and to say it does not know when the context does not support an answer.

The Hallucination Checker MUST run on the response path before any answer is returned, and MUST
verify that claims — including names, figures, clauses, and function signatures — are supported
by the retrieved material. A failed check triggers the self-correction path (broader retrieval or
a revised generation pass), never a silent pass-through to the user.

**Rationale**: An enterprise answer that is fluent and wrong is worse than no answer, because it
is acted upon. Grounding plus verification is what separates this system from a chatbot.

### V. Business Facts Come From Systems Of Record

Financial, HR, sales, legal, and operational values MUST originate from a database query or a
verified tool result. The LLM's role for such questions is translating natural language into a
query and translating the result back into prose — never producing, estimating, rounding, or
recalling the figure itself.

SQL generated by an agent MUST be parameterized (never string-interpolated), executed through a
restricted read-only role, and constrained to an approved schema. Verification MUST confirm that
figures stated in the narrative match the rows actually returned.

**Rationale**: Model memory is stale, generic, and confidently wrong about specifics. A revenue
number invented by an LLM is indistinguishable, to the reader, from one that was queried.

### VI. Every Agent Tool Is A Declared Contract

No tool may be callable by an agent until it declares, in code and in documentation, all of:

- **Typed inputs and typed outputs** (Pydantic schemas or equivalent).
- **Required permission code(s)** and any relationship conditions (e.g. `hr:read_team` plus a
  manager relationship).
- **Tenant scope** — how `company_id` constrains its effect.
- **Audit behavior** — what it records on success and on denial.
- **Approval classification** — `Read`, `Prepare`, `Write`, or `Delete`, and whether it requires
  human approval.

An undeclared, untyped, or unclassified tool MUST NOT be registered with the Orchestrator.

**Rationale**: Tools are where the system stops talking and starts acting. A tool whose blast
radius, permissions, and reversibility are not written down cannot be reviewed, tested, or safely
granted to a planner.

### VII. Human Approval Gates Irreversible Actions (NON-NEGOTIABLE)

Any action that sends, deletes, publishes, or modifies company information MUST pause for
explicit human confirmation before execution, even when the actor is fully authorized. Approval
is a separate control from authorization and MUST NOT be collapsed into it.

The gate MUST sit inside the Orchestrator after verification and before execution, be exposed
through a dedicated confirm/reject endpoint, be surfaced in the UI as an explicit prompt showing
what will happen, and record approver, decision, and timestamp in the audit log. Read-only
operations MUST NOT be gated — the gate exists for writes, not for friction.

**Rationale**: A plan can be subtly wrong — right action, wrong recipient; right record, wrong
row. One deliberate click is what makes granting an AI real-world actions defensible.

### VIII. Test-First For Security And Correctness (NON-NEGOTIABLE)

Test-driven development is mandatory for: authorization decisions, tenant isolation, agent tools,
RAG retrieval and grounding, business rules, and critical workflows. For these areas the cycle is
strict — write the test, watch it fail, then implement.

The fixed access-control acceptance suite from the blueprint MUST exist as executable tests and
MUST run in CI, including at minimum: general-policy allow, own-data allow, other-employee salary
deny (denied *before* retrieval or SQL), manager direct-reports allow, cross-department deny,
Legal restricted multi-document allow with citations, cross-tenant semantic-search returning
nothing, and an authorized send action correctly pausing for approval.

**Unauthorized information leakage MUST measure 0% on this suite.** A non-zero result blocks
merge, blocks phase gates, and blocks any stretch-goal work. Authorization precision,
denied-request correctness, tenant-isolation success rate, and the percentage of irreversible
actions that correctly triggered approval MUST also be reported.

**Rationale**: Security properties are invisible when they work and catastrophic when they do not.
Writing the attack first is the only way to know the defence was ever real.

### IX. Reproducible Synthetic Enterprise Data

The system MUST run on deterministic synthetic company data — no private data from a real
company. Generation MUST be seeded so every team member and every CI run produces identical IDs,
relationships, and content.

The generated enterprise MUST be internally coherent: a leave policy stating 21 days MUST match
the leave balances, the HR records, and the answers the system gives. Documents, HR records,
sales and finance records, contracts, operations records, and the synthetic code repository MUST
reference the same departments, countries, roles, and classifications. Delta Retail Group MUST be
seeded with distinctive, greppable content specifically so isolation failures are detectable.

**Rationale**: Reproducibility is what makes a demo re-runnable, a bug reproducible, and an
evaluation metric comparable across weeks. Incoherent seed data produces "correct" answers that
contradict each other and destroys the demo's credibility.

### X. Audit By Default

Every consequential operation MUST write an audit record: AI requests and answers, authorization
allows *and* denies, tool invocations, retrieved document IDs, SQL tool usage, report generation,
workflow transitions, approvals and rejections, exports, role and permission changes, and policy
version changes.

Each record MUST capture actor, tenant, action, resource type and ID, decision, reason, sources,
and timestamp. Audit records are append-only and readable only by the `audit:read` permission.

**Rationale**: The project's central claim is that every answer and action was authorized. Without
an audit trail that claim is unprovable — to a user, to a committee, or to an auditor persona in
the demo.

## Mandatory Surfaces, Contracts & Environment

**Public NileTech website (mandatory)** — Home, About, Services, Products, Leadership, Careers,
News, and Contact. It is unauthenticated, tenant-branded, and MUST NOT expose any internal data.

**Private employee portal (mandatory)** — AI Assistant, My HR Profile, Leave Requests, Documents,
Reports, Contracts, Company Directory, Approvals, Administration, and Audit Log. Navigation MUST
be role-aware: a user never sees an entry point to something they cannot use.

**Frontend completeness** — no frontend feature is complete unless it implements all of:
responsive layout, accessibility (keyboard navigation, focus management, semantic markup,
sufficient contrast, screen-reader labels), loading states, empty states, error states, and
explicit access-denied states. Access-denied MUST be a designed, informative state — never a
blank screen, a silent omission, or a raw 403.

**API contracts** — every endpoint MUST define typed request and response models (Pydantic on the
backend, matching types on the frontend). Validation happens before business logic. Untyped or
free-form JSON payloads are not acceptable at any boundary, including the Orchestrator↔Backend
and tool interfaces.

**Migrations and seeds** — all schema changes MUST ship as versioned, ordered, reversible
migrations. Seed scripts MUST be idempotent and deterministic. Dropping and rebuilding the
database from migrations plus seeds MUST yield a byte-identical logical dataset. Manual database
edits are prohibited.

**Docker Compose** — the complete local system MUST run through Docker Compose: FastAPI backend,
frontend, PostgreSQL, Qdrant, Redis, MinIO (object storage), and the Celery worker. A single
documented command MUST bring the stack up from a clean checkout. Any component that cannot run
in Compose is not part of the system.

## Development Workflow & Quality Gates

**Definition of Done.** No feature is complete until all four are true:

1. **Implementation** — the code works end to end in the Compose stack.
2. **Tests** — required tests exist, run in CI, and pass; TDD areas from Principle VIII were
   written test-first.
3. **Documentation** — the change is documented (API contract, tool declaration, README or
   runbook entry, and any deviation from the blueprint).
4. **Verified acceptance criteria** — the acceptance criteria from the spec were executed and
   observed to pass, not merely assumed.

Work that satisfies three of four is in progress, not done, and MUST NOT be reported as complete.

**Review gates.** Every change MUST be reviewed against this constitution. A reviewer MUST
explicitly confirm: tenant scoping present, authorization deterministic and applied pre-retrieval,
tools declared and classified, audit events written, tests present for security-critical paths,
and typed contracts at boundaries.

**Phase gates.** The blueprint's phase gates are binding. In particular: no agent work begins
until RAG and authorization are both stable; no verification work begins until the four core
scenarios plus the scheduled report and approval gate work; and no stretch goal (adaptive
re-planning, formalized multi-agent handoff) may be attempted until leakage measures 0% on the
fixed test set.

**Evaluation.** The Evaluation Module MUST run against the full test set on a schedule and before
each phase gate, reporting both AI-quality metrics and security/access-control metrics. Both
categories are first-class evidence for the defense.

## Governance

This constitution supersedes ad-hoc practice, individual preference, and convenience. When this
document and a plan, task list, tutorial, or habit disagree, this document wins.

**Amendment procedure.** Amendments MUST be proposed as a written change to this file, stating the
principle affected, the rationale, and the migration impact on existing code, tests, and templates.
An amendment takes effect only when the team agrees and the dependent templates
(`plan-template.md`, `spec-template.md`, `tasks-template.md`) have been updated in the same change.
Principles marked NON-NEGOTIABLE (I, II, III, VII, VIII) MUST NOT be weakened or suspended to meet
a deadline; scope is cut instead.

**Versioning policy.** Semantic versioning applies to this document:

- **MAJOR** — a principle is removed or redefined in a backward-incompatible way.
- **MINOR** — a principle or section is added, or guidance is materially expanded.
- **PATCH** — clarification, wording, or non-semantic refinement.

**Compliance review.** Constitution compliance is checked at three points: at planning time via the
Constitution Check gate in `plan-template.md`, at review time via the review gate above, and at each
phase gate via the evaluation and access-control test suites. Violations that must ship anyway MUST
be recorded in the plan's Complexity Tracking table with the justification and the rejected simpler
alternative — and NON-NEGOTIABLE principles are never eligible for that table.

**Runtime guidance.** `docs/Enterprise_AI_OS_EDITED.html` remains the reference for architecture and
scope; this constitution is the reference for engineering conduct. Read both before implementation.

### Principle Traceability

| # | Owner mandate | Governed by |
|---|---------------|-------------|
| 1 | All company artifacts tenant-scoped | Principle I |
| 2 | Deterministic authorization, never an LLM | Principle II |
| 3 | Unauthorized information never enters context | Principle III |
| 4 | Multi-tenancy, RBAC, ABAC, ACLs, approval gates | Principle II (layers), VII |
| 5 | Answers grounded in authorized sources | Principle IV |
| 6 | Business values from databases/verified tools | Principle V |
| 7 | Tool contracts: types, permissions, scope, audit, approval | Principle VI |
| 8 | Send/delete/publish/change requires approval | Principle VII |
| 9 | TDD for security and critical logic | Principle VIII |
| 10 | Reproducible synthetic company data | Principle IX |
| 11 | NileTech and Delta Retail fully isolated | Principle I |
| 12 | Public NileTech website mandatory | Mandatory Surfaces |
| 13 | Private employee portal mandatory | Mandatory Surfaces |
| 14 | Typed API request/response contracts | Mandatory Surfaces (API contracts) |
| 15 | Reproducible migrations and seeds | Mandatory Surfaces (Migrations and seeds) |
| 16 | Full local system via Docker Compose | Mandatory Surfaces (Docker Compose) |
| 17 | Frontend responsive, accessible, all states | Mandatory Surfaces (Frontend completeness) |
| 18 | Audit records for important operations | Principle X |
| 19 | Done = implementation + tests + docs + verified AC | Development Workflow (Definition of Done) |

**Version**: 1.0.0 | **Ratified**: 2026-07-31 | **Last Amended**: 2026-07-31
