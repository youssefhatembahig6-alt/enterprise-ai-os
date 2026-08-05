# Forms Checklist: NileTech Public Website

**Purpose**: Validate that contact-form requirements are complete, quantified, and cover failure and abuse paths
**Created**: 2026-08-02
**Feature**: [spec.md](../spec.md)

## Requirement Clarity

- [x] CHK001 Are field length bounds stated in the specification, or only that input must be "length-bounded"? [Measurability, Spec §FR-024]
- [x] CHK002 Is the duplicate-suppression window quantified, or described only as preventing "accidental duplicate submission"? [Clarity, Spec §FR-022]
- [x] CHK003 Is "the form is cleared or disabled" (§US4/AC4) a choice left to the implementer, and are both outcomes acceptable? [Ambiguity, Spec §US4]
- [x] CHK004 Is the email validation rule specified — format-checked, deliverability-checked, or neither? [Clarity, Spec §FR-019]
- [x] CHK005 Is "treated as untrusted" (§FR-024) expressed as concrete obligations, or as a principle? [Clarity, Spec §FR-024]

## Requirement Completeness

- [x] CHK006 Is a privacy notice or consent statement required at the point of collection, given the form gathers personal data from the public? [Gap, Coverage]
- [x] CHK007 Are anti-abuse requirements specified — rate limiting, volume caps, or bot mitigation — distinct from input length bounds? [Gap, Spec §Edge Cases]
- [x] CHK008 Are requirements defined for whether the success state survives navigation or reload? [Gap, Spec §FR-022]
- [x] CHK009 Are requirements specified for the form's behaviour while a submission is in flight? [Gap, Spec §FR-025]
- [x] CHK010 Is a required-field indicator requirement stated, so a visitor knows before submitting? [Gap, Spec §FR-019, §FR-021]
- [x] CHK011 Are requirements defined for how many validation errors are reported at once — the first, or all? [Gap, Spec §FR-021]

## Scenario Coverage

- [x] CHK012 Are requirements defined for a submission that passes client-side rules but is refused by the server? [Coverage, Spec §FR-020]
- [x] CHK013 Are requirements specified for a submission that is accepted but whose audit write fails? [Coverage, Gap, Spec §FR-023]
- [x] CHK014 Is behaviour defined for a submission arriving while the database is unavailable, as distinct from the backend being unreachable? [Coverage, Spec §US4]
- [x] CHK015 Are requirements defined for input that is valid but semantically empty — whitespace only? [Coverage, Gap]

## Consistency

- [x] CHK016 Do §FR-022 (prevent accidental duplicate submission) and the duplicate-suppression behaviour agree on what the visitor is told when a duplicate is detected? [Consistency, Spec §FR-022 vs contracts]
- [x] CHK017 Is §FR-020's "not bypassable by submitting directly" reconciled with §FR-021's requirement that errors be conveyed to assistive technology — do both apply to server-returned errors? [Consistency, Spec §FR-020, §FR-021]

## Acceptance Criteria Quality

- [x] CHK018 Is §SC-006's "0% of invalid submissions accepted when client-side validation is bypassed" backed by a defined set of invalid inputs? [Measurability, Spec §SC-006]
- [x] CHK019 Can §SC-007's "exactly one stored record" be checked without a public read path for submissions? [Measurability, Conflict, Spec §SC-007 vs §FR-023b]

## Notes

- **CHK019 is a genuine tension.** §FR-023b forbids reading submissions publicly, and §SC-007 requires proving exactly one record exists. The verification path must therefore be privileged — direct database access in the test — and the spec should say so rather than leaving a criterion that appears unverifiable.
- CHK006 and CHK007 are the two substantive gaps: a public form collecting personal data with no consent requirement and no abuse protection. Neither is exotic; both are standard for the surface type.
- CHK013 asks a question the audit-by-default principle makes sharp: if the audit write fails, was the submission accepted?
