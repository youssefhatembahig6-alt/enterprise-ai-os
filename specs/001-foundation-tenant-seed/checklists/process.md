# Testing & Documentation Requirements Quality Checklist: Foundation

**Purpose**: Validate that requirements covering testing and documentation are complete, unambiguous, measurable, and internally consistent — before implementation begins
**Created**: 2026-08-01
**Feature**: [spec.md](../spec.md)
**Depth**: Formal gate (pre-implementation)

**Note**: These items test the **requirements**, not the tests or docs themselves. Each asks whether
something is adequately *specified*.

## Testing — Requirement Completeness

- [x] CHK001 **RESOLVED 2026-08-01** — FR-047b added. Is a multi-operating-system verification matrix required, given SC-002 claims determinism across every team member's machine while FR-047 requires only that checks "run in continuous integration"? [Gap, Spec §FR-047 vs §SC-002]
- [x] CHK002 Does the spec state which tests must be written before their implementation, given the constitution mandates test-first for tenant isolation, database integrity, and critical workflows? [Gap, Spec §FR-044–§FR-047, Constitution §VIII]
- [x] CHK003 Are requirements defined for test isolation between runs — whether each run starts from a known state and what it leaves behind? [Gap, Coverage]
- [x] CHK004 Are requirements specified for running the verification checks locally, or only in continuous integration? A check a developer cannot run before pushing is a slow feedback loop by specification [Clarity, Spec §FR-047]
- [x] CHK005 Is a reduced-volume test profile required anywhere in the spec, or does it exist only in the plan and CLI contract? [Gap, Spec §FR-020b]
- [x] CHK006 Are requirements defined for what happens to the verification suite when a check is intentionally not applicable — for example the vector-store probe under decision D2? [Gap, Spec §FR-045]
- [x] CHK007 Are negative-path test requirements specified, or do the requirements only mandate checks that confirm correct data? [Coverage, Spec §FR-044–§FR-046]
- [x] CHK008 Is a test coverage expectation defined, or is coverage left entirely to implementer discretion? [Gap]

## Testing — Clarity & Measurability

- [x] CHK009 Is "block the change" defined, given the repository is not yet under version control and no branching or review workflow is specified? [Ambiguity, Assumption, Spec §SC-012]
- [x] CHK010 Is a runtime budget defined for the full verification suite, or only for the seed step? A suite too slow to run is a suite that stops being run [Gap, Spec §SC-008]
- [x] CHK011 Are the four named check families — determinism, isolation, coherence, integrity — defined precisely enough that each requirement maps to exactly one? [Clarity, Spec §FR-047]
- [x] CHK012 Can "the data-readiness check confirms 8 of 8 scenarios" be evaluated objectively, given the scenarios are described narratively rather than as record predicates? [Measurability, Spec §SC-013, §FR-047a]
- [x] CHK013 Are the acceptance thresholds for each success criterion stated as pass/fail rather than as directional goals? [Measurability, Spec §SC-001–§SC-015]

## Documentation — Requirement Completeness

- [x] CHK014 **RESOLVED 2026-08-01** — FR-048 added. Does any requirement define where project documentation lives and what it must contain? The word "documented" appears in FR-002, FR-004, FR-005, FR-015a, FR-022, and FR-025b without a single requirement establishing the artifact it refers to [Gap, Spec §FR-002]
- [x] CHK015 Is the location of the persona reference specified? FR-025b requires personas be "listed in the feature documentation" without identifying it [Ambiguity, Spec §FR-025b]
- [x] CHK016 Is the location specified for documenting Delta Retail's intentional absences? [Ambiguity, Spec §FR-022]
- [x] CHK017 Is the location specified for documenting the fingerprint exclusion list? [Ambiguity, Spec §FR-015a]
- [x] CHK018 **RESOLVED 2026-08-01** — FR-048 requires the startup/prerequisites doc. Is onboarding documentation required, given SC-001 asserts a newcomer succeeds "without asking another team member for help" — an outcome that depends entirely on documentation no requirement mandates? [Consistency, Spec §SC-001]
- [x] CHK019 Are requirements defined for recording future design decisions, or does the decision record stop with the three confirmed in this spec? [Gap, Spec §Confirmed Scope Decisions]
- [x] CHK020 Are requirements defined for documenting the environment configuration surface, beyond the instruction that defaults work out of the box? [Gap, Spec §FR-005]

## Documentation — Consistency & Maintenance

- [x] CHK021 Are requirements defined to keep documentation synchronized with the system, so a stale setup guide is a defect rather than an inconvenience? [Gap, Coverage]
- [x] CHK022 Is terminology required to be used consistently across documentation and code, given the spec establishes a canonical glossary distinguishing Company from Customer and Product from Public Product? [Consistency, Spec §Key Entities]
- [x] CHK023 Are documentation requirements consistent about audience — a newcomer with no context, or a team member who already knows the architecture? [Clarity, Spec §SC-001]
- [x] CHK024 Is it specified whether the carry-forward list from the confirmed scope decisions must appear in the next feature's specification, or whether it is advisory? [Clarity, Spec §Confirmed Scope Decisions]

## Dependencies & Assumptions

- [x] CHK025 Is the assumption that continuous integration exists and is available validated, given no requirement establishes the CI platform? [Assumption, Spec §FR-047]
- [x] CHK026 Are the tools a newcomer must install before the documented command works stated as requirements, or assumed? [Assumption, Spec §FR-002, §SC-001]

## Notes

- `[Gap]` — the requirement appears to be **missing**; resolve by adding a requirement or explicitly recording it as out of scope.
- **CHK014 is the highest-impact item in this checklist.** The spec leans on the word "documented" six separate times as though it were a defined term. Nothing defines the artifact, its location, or its acceptance criteria — so six requirements are currently unverifiable for the same reason.
- **CHK001 and CHK002 are traceability holes**: SC-002 and the constitution both demand something the functional requirements never ask for. The plan happens to cover both, but a plan should implement requirements rather than invent them.
- CHK009 has a practical edge: this project is not yet a git repository, so "blocks the change" currently describes a workflow that does not exist.


## Closure record

All 26 items closed 2026-08-06. Five needed no change (CHK005, CHK006, CHK020, CHK022, CHK024).
The requirement closing each of the rest is named in [spec.md](../spec.md) under *Clarifications
→ Session 2026-08-06 — process checklist remediation*.

The note above was right that CHK014 was the highest-impact item: it was closed on 2026-08-01 by
adding FR-048, but FR-048 named contents without naming locations, so six requirements still
pointed at an artifact nobody could open. FR-048a is the table that finishes the job.
