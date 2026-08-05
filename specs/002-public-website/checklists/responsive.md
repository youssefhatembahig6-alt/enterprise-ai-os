# Responsive Design Checklist: NileTech Public Website

**Purpose**: Validate that responsive requirements are quantified, complete, and verifiable
**Created**: 2026-08-02
**Feature**: [spec.md](../spec.md)

## Requirement Clarity

- [x] CHK001 Are the three verified widths (360/768/1280px) declared as *test* widths or as *breakpoints*, and is the distinction stated? [Clarity, Spec §FR-032]
- [x] CHK002 Is the width at which navigation collapses to its mobile form specified, or left to the implementer? [Gap, Spec §FR-037]
- [x] CHK003 Is an upper bound defined — does the layout constrain its maximum content width above 1280px, or stretch indefinitely? [Gap, Spec §FR-032]
- [x] CHK004 Is "no clipped content" defined precisely enough to distinguish deliberate truncation with an ellipsis from accidental overflow? [Ambiguity, Spec §FR-032]

## Requirement Completeness

- [x] CHK005 Are minimum touch-target size requirements specified for interactive elements at mobile widths? [Gap, Spec §FR-037]
- [x] CHK006 Are reflow requirements defined for browser zoom up to 400%, which WCAG 2.2 AA requires and which the 320px floor does not by itself satisfy? [Gap, Spec §FR-032, §FR-053]
- [x] CHK007 Are requirements defined for landscape orientation on short viewports, where vertical space rather than width is the constraint? [Gap, Coverage]
- [x] CHK008 Are responsive requirements specified for tabular or grid content — services, products, vacancies — at the narrowest width? [Gap, Spec §FR-032]
- [x] CHK009 Are requirements defined for the leadership placeholder's sizing behaviour across widths? [Gap, Spec §US5]

## Consistency

- [x] CHK010 Do §FR-032 (three verified widths) and §SC-004 (same three widths) state identical thresholds and identical pass conditions? [Consistency, Spec §FR-032, §SC-004]
- [x] CHK011 Are the responsive requirements consistent with §FR-037's touch/pointer/keyboard operability, or could a layout satisfy one and violate the other? [Consistency, Spec §FR-032, §FR-037]

## Acceptance Criteria Quality

- [x] CHK012 Is "no page body scrolls horizontally at any width from 320px upward" testable as stated — is it sampled at intervals, or asserted continuously? [Measurability, Spec §FR-032]
- [x] CHK013 Can "zero overlapping elements" be detected automatically, and is the detection method specified? [Measurability, Spec §SC-004]
- [x] CHK014 Are the pages subject to responsive verification enumerated, or is "every page" intended to include `/portal` and `/status`? [Coverage, Spec §SC-004]

## Notes

- CHK006 is a compliance interaction, not a layout preference: the spec commits to WCAG 2.2 AA (§FR-053), whose reflow criterion is not satisfied by a 320px floor alone. Left unstated, it will be discovered by the axe run rather than by design.
- CHK005 is the same shape — target size is an AA criterion in WCAG 2.2 that the responsive requirements do not currently mention.
