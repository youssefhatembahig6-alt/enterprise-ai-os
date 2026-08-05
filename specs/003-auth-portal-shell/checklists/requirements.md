# Specification Quality Checklist: Authentication, Request-Time Authorization, and Employee Portal Shell

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-05
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- **Two conflicts were found and resolved before this checklist passed**, both recorded in the spec's Clarifications section rather than deferred. Constitution Principle II ("every denial MUST return 403") contradicted spec 001 FR-043a ("another company's resource MUST be answered as not found"); FR-030 resolves it by placing the tenant boundary at layer 1, before authorization is consulted, so a cross-tenant resource is absent rather than denied. Separately, spec 002 FR-048 forbids the public site accepting credentials; FR-006 resolves it by placing sign-in at the reserved portal address, which spec 002 FR-001a already classifies as a non-content route.
- The feature brief named FastAPI and JWT. Neither appears in any requirement — the spec says "session credential" and "verified identity" throughout, so the requirements stay testable against behaviour rather than against a library. Both terms survive only in the verbatim Input quote, which is the user's own wording.
- One technology term did leak on the first pass ("Qdrant population" in Scope Boundaries) and was corrected to "vector-store population" before this checklist was marked complete.
- **A clarification session on 2026-08-05 asked all five permitted questions** and raised the spec from 38 requirements to 42, and from 12 success criteria to 15. Re-validated after: still 16/16, no regressions. The five answers bounded sign-in attempts (absent entirely), settled how credentials are established without moving the dataset fingerprint, made sign-out genuinely revoke, scoped which authorization allows are audited, and put numbers on session expiry.
- **One answer rested on a property verified rather than assumed**: FR-002a relies on the dataset fingerprint being computed from the in-process generated rows rather than from the database, which was traced in `manifest.py` before the option was recommended. Had it read from the database, provisioning credentials post-seed would have moved the committed fingerprint.
- **FR-036 and SC-007 are the hardest requirements here** and are deliberately phrased to resist a shallow implementation: proving authorization precedes retrieval cannot be done by inspecting a response, because a correct refusal and a refusal issued after an unauthorized read look identical from outside.
