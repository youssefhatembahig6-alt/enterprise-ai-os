# Route Security Checklist: NileTech Public Website

**Purpose**: Validate that requirements governing which routes an anonymous visitor may reach are complete, enumerable, and testable
**Created**: 2026-08-02
**Feature**: [spec.md](../spec.md)

## Requirement Clarity

- [x] CHK001 Is the set of "private portal routes" (§FR-046) enumerable today? The portal does not exist, so the refusal requirement has no defined subject beyond `/portal` itself. [Ambiguity, Spec §FR-046]
- [x] CHK002 Is the set of "non-public data endpoints" (§FR-047) enumerated, or inferred as the complement of the public surface? [Clarity, Spec §FR-047]
- [x] CHK003 Is `/dataset/manifest` — served anonymously today by feature 001 and consumed by the status shell — classified as public or non-public? [Conflict, Spec §FR-047 vs feature 001]
- [x] CHK004 Are the health endpoints classified, given they are anonymous by design and reveal per-dependency infrastructure state? [Gap, Spec §FR-047]
- [x] CHK005 Is `/status` classified as a public page, a diagnostic route, or a private route? It reads two anonymous endpoints and appears in no spec requirement. [Gap, Conflict]

## Requirement Completeness

- [x] CHK006 Are requirements defined for what a refusal returns — a designed page for route requests and a structured response for data requests, or one form for both? [Clarity, Spec §FR-046, §FR-047]
- [x] CHK007 Are rate-limiting or abuse-protection requirements specified for the anonymous surface? [Gap, Coverage]
- [x] CHK008 Are requirements defined for HTTP methods other than the ones each public endpoint declares? [Gap, Coverage]
- [x] CHK009 Is a requirement stated that the reserved portal address must not change when the portal is built, or is that only a plan note? [Gap, Spec §FR-049a vs plan]
- [x] CHK010 Are requirements defined for what the refusal audit entry records — and explicitly what it must not record, such as request bodies? [Clarity, Spec §FR-047]

## Scenario Coverage

- [x] CHK011 Are requirements defined for a request to a private route that arrives with a credential, given the site accepts none (§FR-048)? [Coverage, Gap]
- [x] CHK012 Are requirements specified for a public endpoint reached with an unexpected header or parameter attempting tenant selection? [Coverage, Spec §FR-009a]
- [x] CHK013 Is the behaviour of the reserved portal page specified for a crawler, as distinct from a visitor? [Gap, Spec §FR-042, §FR-049a]

## Acceptance Criteria Quality

- [x] CHK014 Does §FR-051 define the population of routes the check must cover, so the check cannot pass by testing an empty or partial set? [Measurability, Spec §FR-051]
- [x] CHK015 Is §SC-008's "100% of attempts" anchored to an enumerated attempt list, or to whatever the test happens to try? [Measurability, Spec §SC-008]
- [x] CHK016 Is a requirement stated that the refusal test set must be non-empty, so a vacuous pass is impossible? [Gap, Spec §FR-051]

## Notes

- **CHK003 is a real conflict with the existing system.** Feature 001 exposes `/dataset/manifest` anonymously and the status page reads it. §FR-047 as written would require refusing it. Either the manifest is declared public (with a stated rationale — it carries provenance, not tenant data), or feature 001's endpoint and its status page must change. This needs a decision, not an implementation choice.
- CHK001 and CHK014/CHK016 are the same risk from two ends: a refusal requirement whose subject set is undefined produces a test that passes because it has nothing to check — the exact failure mode feature 001 encountered repeatedly.
