# Public Data Exposure Checklist: NileTech Public Website

**Purpose**: Validate that requirements governing which data leaves the system are declared, bounded, and impossible to widen silently
**Created**: 2026-08-02
**Feature**: [spec.md](../spec.md)

## Requirement Completeness

- [x] CHK001 Does the spec name where the approved-public field set is declared, or only that it must be declared somewhere? [Clarity, Spec §FR-045]
- [x] CHK002 Are requirements defined for API error response bodies, given §FR-029 constrains only the Server Error *page*? [Gap, Spec §FR-029, §FR-044]
- [x] CHK003 Are logging requirements specified so that contact-form content — a name and email address — does not reach application logs? [Gap, Spec §FR-023, §FR-024]
- [x] CHK004 Are retention requirements defined for stored contact submissions? [Gap, Coverage]
- [x] CHK005 Are requirements specified for what the response to a duplicate submission reveals, given it must report success without creating a record? [Clarity, Spec §FR-022]
- [x] CHK006 Is a requirement stated that no public response may contain a database identifier, or is that only a contract-level rule? [Gap, Spec §FR-044 vs contracts]

## Requirement Clarity

- [x] CHK007 Is "approved public field" defined by an enumeration, or by the property of being non-sensitive? [Ambiguity, Spec §FR-044, §FR-045]
- [x] CHK008 Is the direction of the allowlist check specified — must an *extra* field fail, not only a missing one? [Clarity, Spec §FR-050]
- [x] CHK009 Are requirements defined for fields reached through a join, such as the employee display name behind a leadership profile? [Gap, Spec §FR-013, §FR-044]
- [x] CHK010 Is "no field carrying internal, confidential, or restricted data" (§FR-044) checkable, given classification is a property of rows rather than of response fields? [Measurability, Spec §FR-044]

## Scenario Coverage

- [x] CHK011 Are requirements defined for what happens if a seeded record's classification is not `PUBLIC` but it belongs to a family the site displays? [Coverage, Gap, Spec §FR-007]
- [x] CHK012 Are requirements specified for a public endpoint returning content sourced from a row that was reclassified after seeding? [Coverage, Gap]
- [x] CHK013 Is the cross-tenant check's method defined — marker-phrase search only, or also structural assertions about tenant selection? [Clarity, Spec §FR-052]

## Consistency

- [x] CHK014 Do §FR-007 (display only `PUBLIC` content) and §FR-044 (expose only `PUBLIC` content) state the same rule for two layers, and is one derivable from the other? [Consistency, Spec §FR-007, §FR-044]
- [x] CHK015 Is §FR-023b (submissions not publicly readable) enforced by a stated structural absence of a read route, or by a filter that could later be relaxed? [Clarity, Spec §FR-023b]

## Acceptance Criteria Quality

- [x] CHK016 Does §SC-009's "zero fields outside the declared set" identify the authoritative declaration the check compares against? [Traceability, Spec §SC-009]
- [x] CHK017 Is a requirement stated that the allowlist test must cover every public endpoint, so an endpoint added later is not silently unchecked? [Gap, Spec §FR-050]

## Notes

- CHK003 and CHK004 are the privacy gap in this feature. The site collects a name and an email address from members of the public, and no requirement addresses how long that is kept or where it may be written. Both are cheap to specify now and expensive to retrofit.
- CHK008 captures the distinction the plan's research R6 relies on: an allowlist that only detects *missing* fields fails open exactly as an exclusion list would.
- CHK017 is the pattern that matters most over time — the check must be bound to the endpoint set, not to a list someone maintains by hand.
