# Architecture & Runtime Requirements Quality Checklist: Foundation

**Purpose**: Validate that requirements covering architecture completeness, service health checks, and error handling are complete, unambiguous, measurable, and internally consistent — before implementation begins
**Created**: 2026-08-01
**Feature**: [spec.md](../spec.md)
**Depth**: Formal gate (pre-`/speckit-tasks`)

**Note**: These items test the **requirements**, not the system. Each asks whether something is
adequately *written down*, not whether it works.

## Architecture Completeness

- [ ] CHK001 Are the responsibilities of each monorepo directory defined, rather than only the directory names listed? [Completeness, Spec §FR-001]
- [x] CHK002 Are dependency-direction rules between packages stated as a requirement, so a backwards dependency is a spec violation rather than a code-review opinion? [Gap, Spec §FR-001]
- [ ] CHK003 Do requirements exist for `packages/ui` and `packages/contracts`, or do these appear only in the plan's directory tree with no requirement governing their content? [Gap, Spec §FR-001]
- [ ] CHK004 Is the set of services that must start under one command enumerated exhaustively, so "complete local system" is countable? [Clarity, Spec §FR-002]
- [ ] CHK005 Are service startup-ordering and inter-service dependency requirements specified, or is ordering left implicit? [Gap, Spec §FR-002]
- [x] CHK006 Is the API versioning approach specified, given that `packages/contracts` will generate client types from it? [Gap, Spec §FR-001]
- [ ] CHK007 Are requirements defined for how the frontend behaves when the API is unreachable, given the frontend is a required Compose service? [Coverage, Gap, Spec §FR-002]
- [ ] CHK008 Is "standard developer machine" quantified (CPU, RAM, disk), given two success criteria depend on it? [Ambiguity, Spec §SC-008]
- [ ] CHK009 Are resource-limit requirements (memory, disk footprint) specified for the five stateful services? [Gap, Spec §FR-002]
- [ ] CHK010 Are requirements stated for what configuration must be surfaced in `.env.example` versus what may remain internal? [Clarity, Spec §FR-005, §FR-006]
- [ ] CHK011 Is the boundary between "no secrets committed" and "defaults that work out of the box" defined precisely enough to be checkable? [Ambiguity, Spec §FR-005, §FR-006]

## Service Health Checks

- [ ] CHK012 Is the distinction between liveness and readiness stated as a requirement, or does it exist only as a design decision in the plan? [Gap, Spec §FR-003]
- [ ] CHK013 Are per-dependency timeout thresholds specified, so a hung dependency produces a definite answer rather than a hanging request? [Gap, Spec §FR-003]
- [ ] CHK014 Is the "documented startup budget" referenced in the acceptance scenarios quantified anywhere in the requirements? [Ambiguity, Spec §US1 AS1]
- [ ] CHK015 Are requirements defined for whether partial availability is reported as failure or as degraded-but-usable? [Clarity, Spec §FR-003]
- [ ] CHK016 Is it specified whether health endpoints are reachable without authentication once authentication exists in a later feature? [Gap, Assumption]
- [ ] CHK017 Are requirements defined constraining what health responses may disclose (connection strings, credentials, internal hostnames)? [Gap, Security]
- [ ] CHK018 Are the health-check requirements consistent with the four stores named in the isolation requirements — same four, named the same way? [Consistency, Spec §FR-003 vs §FR-039–§FR-042]

## Error Handling

- [ ] CHK019 Are process exit codes specified in the requirements, or only in the CLI contract — making the contract the de facto requirement? [Gap, Spec §FR-014, contracts/seed-cli.md]
- [ ] CHK020 Are requirements defined for a dependency becoming unavailable *mid-seed*, as distinct from being unavailable at startup? [Coverage, Gap, Spec §FR-014c]
- [ ] CHK021 Are retry and backoff requirements specified for object-storage uploads during seeding? [Gap, Spec §FR-031]
- [ ] CHK022 Is the port-conflict scenario listed under Edge Cases backed by an actual functional requirement? [Conflict, Spec §Edge Cases vs §FR-002]
- [ ] CHK023 Are error-message content standards defined (actionable, no secrets, names the failing component)? [Gap, Spec §FR-003, §FR-014]
- [ ] CHK024 Are requirements defined distinguishing an expected refusal from an unexpected failure, so operators and CI can tell them apart? [Clarity, Spec §FR-014]
- [ ] CHK025 Is the behavior specified when the reset action is invoked against an already-empty environment? [Edge Case, Gap, Spec §FR-014a]
- [ ] CHK026 Are requirements defined for migration failure and rollback, given migrations must be reversible? [Coverage, Gap, Spec §FR-007]

## Notes

- Items with `[Gap]` indicate the requirement appears to be **missing** — resolve by adding a requirement or explicitly recording it as out of scope.
- Items with `[Conflict]` indicate two parts of the spec disagree; one must change.
- `[Ambiguity]` items are testable-sounding but not objectively measurable as written.
- CHK003, CHK012, and CHK019 share a pattern worth noting: the **plan** and **contracts** specify things the **spec** does not require. That is backwards — a design document should implement requirements, not create them.
