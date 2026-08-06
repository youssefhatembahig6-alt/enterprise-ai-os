# Tenant Isolation Requirements Quality Checklist: Foundation

**Purpose**: Validate that tenant-isolation requirements are complete, unambiguous, measurable, and internally consistent — the project's headline security claim and Constitution Principle I (NON-NEGOTIABLE)
**Created**: 2026-08-01
**Feature**: [spec.md](../spec.md)
**Depth**: Formal gate (pre-implementation)

**Note**: These items test the **requirements**, not the isolation itself. Each asks whether something
is adequately *specified*, not whether it holds at runtime.

## Requirement Completeness

- [x] CHK001 **RESOLVED 2026-08-01** — FR-009d added. Is Row-Level Security required anywhere in the spec, or does it appear only in the constitution and the plan — leaving an implementer who reads the spec alone free to omit it? [Gap, Spec §FR-009, Constitution §I]
- [x] CHK002 **RESOLVED 2026-08-01** — FR-009d specifies fail-closed. Are requirements defined for what happens when the tenant context is absent at query time — fail closed or fail open? The direction is a security decision and is currently unstated [Gap, Spec §FR-009]
- [x] CHK003 Are requirements specified constraining tenant leakage through **log output**, given logs will carry request and data context? [Gap, Coverage, Spec §FR-043]
- [x] CHK004 Are requirements defined for tenant isolation in database dumps, backups, and exports? [Gap, Coverage]
- [x] CHK005 Are requirements specified for whether error responses may reveal the *existence* of another tenant's resource — the 404-versus-403 distinction? [Gap, Edge Case]
- [x] CHK006 Is tenant offboarding or deletion addressed, or explicitly recorded as out of scope? [Gap, Coverage]
- [x] CHK007 Are requirements defined for isolation of background-job payloads and queue contents, beyond the job record carrying a company identifier? [Coverage, Spec §FR-042]
- [x] CHK008 Are requirements specified for the seed process itself operating across both tenants without creating a cross-tenant path? [Gap, Spec §FR-014]

## Requirement Clarity

- [x] CHK009 Is the global-entity allowlist required to be enforced in code as a closed set, or is documenting it sufficient? FR-009a names the four entities but not the enforcement mechanism [Clarity, Spec §FR-009a]
- [x] CHK010 Does "across every populated store" leave the vector-store leg of the probe vacuous under decision D2, and is that intended or an oversight? [Ambiguity, Spec §FR-045 vs §D2]
- [x] CHK011 Is "namespaced" defined precisely enough to be checkable for both storage keys and cache keys, or does it rely on shared intuition? [Clarity, Spec §FR-039, §FR-040]
- [x] CHK012 Are tenant identifiers required to be non-enumerable, or is a predictable slug such as `niletech` acceptable? The spec takes no position [Gap, Assumption, Spec §FR-024a]
- [x] CHK013 Is "distinctive marker phrases" quantified enough that a reviewer could reject an insufficiently distinctive phrase? [Measurability, Spec §FR-023]

## Requirement Consistency

- [x] CHK014 **RESOLVED 2026-08-01** — FR-024a now defers to the FR-009a allowlist. Do FR-024a and FR-009a agree? FR-024a says the companies share "nothing except the global permission catalog", while FR-009a places three further entities outside tenant scope [Consistency, Spec §FR-024a vs §FR-009a]
- [x] CHK015 Are the four stores named consistently across the isolation, health-check, and verification requirements? [Consistency, Spec §FR-003 vs §FR-039–§FR-042 vs §FR-044]
- [x] CHK016 Do the vector-store requirements remain consistent with decision D2's deferral, or does FR-041 imply content that will not exist? [Consistency, Spec §FR-041 vs §D2]
- [x] CHK017 Is the isolation guarantee stated consistently as *structural* in this feature versus *enforced at request time* later, so no reader over-claims what this feature delivers? [Clarity, Spec §US3 vs §D1]

## Acceptance Criteria Quality

- [x] CHK018 Can "an unauthorized-visibility rate of 0%" be computed from a defined denominator, or is the population being measured undefined? [Measurability, Spec §SC-004]
- [x] CHK019 Is the probe's search method specified precisely enough that a passing result is meaningful — exact match, substring, case sensitivity? [Clarity, Spec §FR-045]
- [x] CHK020 Are the isolation acceptance criteria stated so they can fail? A check that can only pass provides no assurance [Measurability, Spec §SC-003, §SC-004]

## Edge Case Coverage

- [x] CHK021 Are requirements defined for a query that supplies a tenant identifier belonging to no company? [Edge Case, Gap]
- [x] CHK022 Are requirements defined for records that legitimately reference a global entity, so the cross-tenant reference check does not produce false positives? [Edge Case, Spec §FR-044]
- [x] CHK023 Is behavior specified when a storage key or cache key is constructed without a tenant prefix — rejected at construction, or detected later by audit? [Edge Case, Gap, Spec §FR-039, §FR-040]
- [x] CHK024 Are requirements defined for the case where both companies legitimately generate identical content, so that content similarity is never mistaken for a leak? [Edge Case, Gap, Spec §US3 AS2]

## Notes

- Tenant isolation is the one area where a missing requirement is not a documentation defect but a security defect, so `[Gap]` items here carry more weight than in the other checklists.
- **CHK001 is the most consequential item.** Row-Level Security is mandated by a NON-NEGOTIABLE constitution principle and is designed into the plan, yet no functional requirement in the spec demands it. The requirement chain has a hole in the middle.
- **CHK014 is a confirmed inconsistency**, not a suspicion — FR-024a's "nothing except the permission catalog" is contradicted by FR-009a's four-entity allowlist.
- CHK003, CHK004, and CHK005 cover isolation channels the spec never considers: logs, backups, and error-message inference. All three are real leak paths in production systems.


## Closure record

All 24 items closed 2026-08-06. Two needed no change: FR-044 already enforced the allowlist as a
closed set in both directions (CHK009), and FR-023a had quantified the marker phrases earlier the
same day (CHK013). The requirement closing each of the rest is named in [spec.md](../spec.md) under
*Clarifications → Session 2026-08-06 — isolation checklist remediation*.

The note above was right that CHK003, CHK004, and CHK005 name real leak paths the spec never
considered. FR-045c is the one to re-read: every isolation check must be demonstrably able to fail,
or SC-004's 0% is a number a suite that examined nothing would also report.
