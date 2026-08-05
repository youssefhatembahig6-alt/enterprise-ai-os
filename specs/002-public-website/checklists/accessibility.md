# Accessibility Checklist: NileTech Public Website

**Purpose**: Validate that accessibility requirements are specific, complete, and verifiable rather than asserted by reference to a standard
**Created**: 2026-08-02
**Feature**: [spec.md](../spec.md)

## Requirement Completeness

- [x] CHK001 Is a skip-to-content mechanism required? The plan places one in the root layout, but no requirement demands it. [Gap, Spec §FR-034 vs plan]
- [x] CHK002 Is a document language declaration required for each page? [Gap, Spec §FR-034]
- [x] CHK003 Are reduced-motion requirements specified for any animation or transition the design introduces? [Gap, Coverage]
- [x] CHK004 Are requirements defined for programmatic association between a validation message and its field, as distinct from the message being announced? [Clarity, Spec §FR-021, §FR-038]
- [x] CHK005 Are requirements specified for the accessible name of the portal entry control, given "Login" alone may not convey its destination? [Gap, Spec §FR-049]
- [x] CHK006 Are heading-level requirements defined for repeated page sections, or only "correctly nested"? [Clarity, Spec §FR-034]
- [x] CHK007 Are requirements defined for how the current-page indicator (§FR-003) is conveyed non-visually? [Gap, Spec §FR-003, §FR-034]

## Requirement Clarity

- [x] CHK008 Is "announced to assistive technology" (§FR-038) specified precisely enough to be implemented consistently — politeness level, and whether announcement is required for every listed change? [Ambiguity, Spec §FR-038]
- [x] CHK009 Is "a visible focus indicator" (§FR-033) quantified against the WCAG 2.2 focus-appearance criterion, or left to judgement? [Clarity, Spec §FR-033]
- [x] CHK010 Is "descriptive link text" (§FR-034) defined by a testable property? [Measurability, Spec §FR-034]
- [x] CHK011 Is the meaning of "traps focus only while open" (§FR-037) specified for the dismissal path — where focus returns? [Gap, Spec §FR-037]

## Coverage

- [x] CHK012 Does the accessibility requirement set cover the Not Found and Server Error pages, which are reachable but absent from most page enumerations? [Coverage, Spec §FR-053]
- [x] CHK013 Are the criteria the keyboard-only pass must establish enumerated, or is the pass described only as existing? [Clarity, Spec §FR-053]
- [x] CHK014 Are requirements defined for the careers filter controls specifically — labelling, and announcement of result counts after filtering? [Gap, Spec §FR-014, §FR-038]

## Consistency

- [x] CHK015 Do §FR-035 (contrast in hover, focus, and error states) and the design-token approach in the plan agree on where contrast is guaranteed — per token pair, or per rendered component? [Consistency, Spec §FR-035]
- [x] CHK016 Is §SC-005 ("zero violations") reconciled with §FR-053's acknowledgement that automation covers only part of AA — could a page pass SC-005 while failing AA? [Conflict, Spec §SC-005 vs §FR-053]

## Notes

- **CHK016 is worth resolving before implementation.** §FR-053 correctly states that automated checks cover a subset of AA, but §SC-005 is phrased as though a clean automated run establishes conformance. As written, the success criterion is satisfiable without the standard being met.
- CHK001 is the recurring pattern from feature 001: the plan supplies something no requirement asks for, so nothing will notice if it is dropped.
