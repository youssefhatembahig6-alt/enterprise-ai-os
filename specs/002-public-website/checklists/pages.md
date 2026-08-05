# Page Completeness Checklist: NileTech Public Website

**Purpose**: Validate that page-level requirements are complete, unambiguous, and internally consistent before implementation
**Created**: 2026-08-02
**Feature**: [spec.md](../spec.md)

## Requirement Completeness

- [x] CHK001 Are the number and selection criteria for each summary block on the home page specified — how many services, products, news items, and vacancies appear? [Gap, Spec §FR-005]
- [x] CHK002 Is the ordering of primary navigation items defined, or left to the implementer? [Gap, Spec §FR-002]
- [x] CHK003 Are requirements defined for what the footer's "secondary navigation" contains, as distinct from the header's primary navigation? [Clarity, Spec §FR-002]
- [x] CHK004 Is a page-level requirement stated for the About page's narrative content, or only for its office list? [Completeness, Spec §FR-010]
- [x] CHK005 Are requirements defined for how a visitor moves between a detail page and its list — a back affordance, breadcrumbs, or neither? [Gap, Spec §FR-015, §FR-017]
- [x] CHK006 Is pagination or progressive disclosure for the news list specified with a concrete mechanism, or only as "can reach every item"? [Clarity, Spec §FR-016]

## Requirement Consistency

- [x] CHK007 Does the spec's twelve-page list (§FR-001) reconcile with the routes the plan introduces — `/portal` and `/status` are addressed in the plan but neither appears in the spec's page inventory? [Conflict, Spec §FR-001 vs plan routes.md]
- [x] CHK008 Is `/status` declared anywhere in the spec as an addressable route, given the plan migrates the feature 001 status shell there? [Gap, Spec §FR-001]
- [x] CHK009 Are the reserved portal page's content requirements stated once, or split between the spec (§FR-049a) and the plan in a way that could drift? [Consistency, Spec §FR-049a]
- [x] CHK010 Do the navigation requirements (§FR-003, "every browsable page reachable within one interaction") hold for detail pages, which are reachable only through their list? [Conflict, Spec §FR-003]

## Scenario Coverage

- [x] CHK011 Are requirements defined for the home page when one of its summary sources is empty — no open vacancies, or no news? [Coverage, Edge Case, Spec §FR-005]
- [x] CHK012 Are requirements specified for a vacancy that is open at list time but closed by the time its detail page is requested? [Coverage, Gap]
- [x] CHK013 Are requirements defined for what a crawler receives at `/portal` and `/status` — indexed, excluded, or unspecified? [Gap, Spec §FR-042]

## Acceptance Criteria Quality

- [x] CHK014 Can "understands within seconds what the company does" (§US1) be objectively evaluated, or does SC-001's 60-second criterion supersede it? [Measurability, Spec §US1, §SC-001]
- [x] CHK015 Is SC-002's "100% of displayed company content traceable to a generated record" verifiable by an automated check, and is the checking method specified? [Measurability, Spec §SC-002]
- [x] CHK016 Is SC-003's "three interactions or fewer" defined precisely enough to count — does applying a filter count as an interaction? [Clarity, Spec §SC-003]

## Notes

- CHK007 and CHK008 are the same underlying issue seen from two directions: the plan introduces routes the specification does not enumerate. Resolve by amending §FR-001 to distinguish *public content pages* from *non-content routes*, rather than by removing the routes.
- CHK014 flags narrative language in a user story that a success criterion already quantifies; the risk is a reviewer testing the looser statement.
