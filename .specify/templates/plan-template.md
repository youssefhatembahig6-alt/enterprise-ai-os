# Implementation Plan: [FEATURE]

**Branch**: `[###-feature-name]` | **Date**: [DATE] | **Spec**: [link]

**Input**: Feature specification from `/specs/[###-feature-name]/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

[Extract from feature spec: primary requirement + technical approach from research]

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: [e.g., Python 3.11, Swift 5.9, Rust 1.75 or NEEDS CLARIFICATION]

**Primary Dependencies**: [e.g., FastAPI, UIKit, LLVM or NEEDS CLARIFICATION]

**Storage**: [if applicable, e.g., PostgreSQL, CoreData, files or N/A]

**Testing**: [e.g., pytest, XCTest, cargo test or NEEDS CLARIFICATION]

**Target Platform**: [e.g., Linux server, iOS 15+, WASM or NEEDS CLARIFICATION]

**Project Type**: [e.g., library/cli/web-service/mobile-app/compiler/desktop-app or NEEDS CLARIFICATION]

**Performance Goals**: [domain-specific, e.g., 1000 req/s, 10k lines/sec, 60 fps or NEEDS CLARIFICATION]

**Constraints**: [domain-specific, e.g., <200ms p95, <100MB memory, offline-capable or NEEDS CLARIFICATION]

**Scale/Scope**: [domain-specific, e.g., 10k users, 1M LOC, 50 screens or NEEDS CLARIFICATION]

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Mark each gate PASS / FAIL / N/A with a one-line justification. Any FAIL on a NON-NEGOTIABLE
gate blocks the plan — it may not be moved to Complexity Tracking.

| Gate | Principle | Status |
|------|-----------|--------|
| Every artifact this feature creates/reads carries and filters on `company_id` (rows, docs, files, vectors, cache keys, jobs, reports, audit) | I (NON-NEGOTIABLE) | |
| Cross-tenant behavior covered by a NileTech ↔ Delta Retail isolation test | I (NON-NEGOTIABLE) | |
| Authorization decisions are deterministic code; no LLM influences access | II (NON-NEGOTIABLE) | |
| Applicable layers applied in order: tenant → RBAC permission codes → ABAC → resource ACL | II | |
| Filtering happens before retrieval; no unauthorized text can reach the prompt | III (NON-NEGOTIABLE) | |
| Cache keys include tenant + permission fingerprint + normalized question + data version | III | |
| Answers carry citations and pass the Hallucination Checker before display | IV | |
| Financial/HR/sales/legal/ops values come from parameterized read-only queries or verified tools | V | |
| Every new tool declares typed I/O, required permissions, tenant scope, audit behavior, approval class | VI | |
| Send/delete/publish/modify paths pause at the human approval gate | VII (NON-NEGOTIABLE) | |
| Security-critical paths have failing tests written first | VIII (NON-NEGOTIABLE) | |
| New data is deterministic, seeded, and coherent with existing synthetic records | IX | |
| Consequential operations write audit records (allow and deny) | X | |
| Public site / employee portal surfaces affected are role-aware and complete | Mandatory Surfaces | |
| Request/response models are typed at every boundary | Mandatory Surfaces | |
| Schema changes ship as reversible migrations; seeds stay idempotent | Mandatory Surfaces | |
| Everything new runs inside the Docker Compose stack | Mandatory Surfaces | |
| Frontend work includes responsive, accessible, loading, empty, error, and access-denied states | Mandatory Surfaces | |

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)
<!--
  ACTION REQUIRED: Replace the placeholder tree below with the concrete layout
  for this feature. Delete unused options and expand the chosen structure with
  real paths (e.g., apps/admin, packages/something). The delivered plan must
  not include Option labels.
-->

```text
# [REMOVE IF UNUSED] Option 1: Single project (DEFAULT)
src/
├── models/
├── services/
├── cli/
└── lib/

tests/
├── contract/
├── integration/
└── unit/

# [REMOVE IF UNUSED] Option 2: Web application (when "frontend" + "backend" detected)
backend/
├── src/
│   ├── models/
│   ├── services/
│   └── api/
└── tests/

frontend/
├── src/
│   ├── components/
│   ├── pages/
│   └── services/
└── tests/

# [REMOVE IF UNUSED] Option 3: Mobile + API (when "iOS/Android" detected)
api/
└── [same as backend above]

ios/ or android/
└── [platform-specific structure: feature modules, UI flows, platform tests]
```

**Structure Decision**: [Document the selected structure and reference the real
directories captured above]

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
