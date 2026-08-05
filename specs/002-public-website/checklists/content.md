# Content Quality Checklist: NileTech Public Website

**Purpose**: Validate that requirements governing displayed content — its source, ordering, and integrity — are complete and unambiguous
**Created**: 2026-08-02
**Feature**: [spec.md](../spec.md)

## Requirement Consistency

- [x] CHK001 Do §FR-005 and §FR-006 conflict? The hero must state "what the company does", while all company content must come from the generated dataset — but the `companies` table carries only name, domain, status, and currency, with no positioning or tagline field. [Conflict, Spec §FR-005 vs §FR-006]
- [x] CHK002 Is the boundary between "company content" (dataset-sourced) and "interface copy" (navigation labels, button text, empty-state wording) defined, so §FR-006's prohibition is applicable? [Ambiguity, Spec §FR-006]
- [x] CHK003 Are the About page's descriptive passages classified as company content or interface copy? [Clarity, Spec §FR-006, §FR-010]

## Requirement Completeness

- [x] CHK004 Is a tie-break specified for news items sharing a publication date, or is ordering left database-dependent? [Gap, Spec §FR-008]
- [x] CHK005 Are truncation requirements defined for long generated descriptions and biographies on list pages — length, boundary, and whether an affordance to read more is required? [Gap, Spec §FR-008, Edge Cases]
- [x] CHK006 Are requirements specified for how the general enquiry address is composed, given the dataset supplies a company domain rather than an address? [Gap, Spec §FR-018]
- [x] CHK007 Are requirements defined for rendering generated body text that contains paragraph breaks, lists, or other structure? [Gap, Spec §FR-017]
- [x] CHK008 Is the source of each leadership profile's display name specified — the profile record or the linked employee record? [Clarity, Spec §FR-013]

## Measurability

- [x] CHK009 Can SC-002's "zero placeholder or lorem-ipsum text" be checked automatically, and is the detection method or word list defined? [Measurability, Spec §SC-002]
- [x] CHK010 Is "non-placeholder content" (§US1/AC2) defined by a testable property rather than by inspection? [Measurability, Spec §US1]
- [x] CHK011 Can §FR-006's prohibition on hard-coded content be verified, or does it rely on reviewer judgement? [Measurability, Spec §FR-006]

## Edge Case Coverage

- [x] CHK012 Are requirements defined for names containing non-Latin characters, diacritics, or unusual casing beyond "must render correctly"? [Clarity, Edge Cases]
- [x] CHK013 Are requirements specified for content whose length is at the low extreme — a one-word service summary or an empty biography? [Coverage, Gap]
- [x] CHK014 Is behaviour defined when a leadership profile references an employee record that cannot be resolved? [Coverage, Gap, Spec §FR-013]

## Dependencies & Assumptions

- [x] CHK015 Is the assumption that feature 001's dataset supplies every field the site needs validated field-by-field, or asserted generally? [Assumption, Spec §Assumptions]
- [x] CHK016 Is the dependency on the `full` seed profile stated in the spec, given persona and volume differences between profiles? [Gap, Assumption]

## Notes

- **CHK001 is the highest-value item here.** It is a genuine conflict, not a wording issue: the hero copy has no dataset source, so either §FR-006 needs an explicit carve-out for company positioning copy, or feature 001's dataset needs a field it does not have. Resolving it during planning is far cheaper than discovering it while building the home page.
- CHK002 determines how many other items are even answerable — without the content/copy boundary, §FR-006 cannot be applied consistently.
