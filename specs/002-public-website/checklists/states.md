# Interface States Checklist: NileTech Public Website

**Purpose**: Validate that loading, empty, and error state requirements are complete, quantified, and distinguishable from one another
**Created**: 2026-08-02
**Feature**: [spec.md](../spec.md)

## Loading States

- [x] CHK001 Is a delay threshold specified before a loading state appears, so a fast response does not produce a visible flash? [Gap, Spec §FR-025]
- [x] CHK002 Is a timeout specified after which an in-flight load becomes an error state? §SC-014 forbids an indefinite loading state but names no bound. [Gap, Measurability, Spec §FR-025, §SC-014]
- [x] CHK003 Are loading-state requirements reconciled with server rendering, where content arrives with the document and no client loading state exists? [Consistency, Spec §FR-025 vs plan]
- [x] CHK004 Is the loading state's announcement to assistive technology specified, distinct from its visual form? [Clarity, Spec §FR-025, §FR-038]

## Empty States

- [x] CHK005 Are the conditions that produce an empty state enumerated — no records, a filter matching nothing, or an unseeded environment — and are they required to be distinguishable? [Clarity, Spec §FR-026]
- [x] CHK006 Is the "next action" an empty state must offer (§FR-026) specified per page, or left to the implementer? [Clarity, Spec §FR-026]
- [x] CHK007 Are requirements defined for an entirely unseeded environment, where every page is simultaneously empty — is that an empty state or an error? [Gap, Coverage]
- [x] CHK008 Is the empty state for a filtered list required to differ from the empty state for an unfiltered one? [Gap, Spec §FR-026, §US2]

## Error States

- [x] CHK009 Are retry requirements quantified — how many attempts, and whether retry is manual or automatic? [Gap, Spec §FR-027]
- [x] CHK010 Is the boundary of a "section" defined for §FR-030's partial-failure containment? [Ambiguity, Spec §FR-030]
- [x] CHK011 Are requirements specified for a page where every section fails independently — does that remain a set of section errors or become a page error? [Coverage, Gap, Spec §FR-030]
- [x] CHK012 Is the distinction between the in-page error state (§FR-027) and the Server Error page (§FR-029) defined by which conditions trigger each? [Clarity, Spec §FR-027, §FR-029]
- [x] CHK013 Are requirements defined for what an error state may reveal about the failure, given §FR-027 forbids internal detail without saying what is permitted? [Clarity, Spec §FR-027]

## Consistency & Coverage

- [x] CHK014 Does §FR-025's "every page that loads content" have a defined membership, given the Not Found and Server Error pages load none? [Clarity, Spec §FR-025]
- [x] CHK015 Are the four states required to be mutually exclusive, or may a page show a populated section beside an error section? [Consistency, Spec §FR-025, §FR-030]
- [x] CHK016 Is the success state — required for the contact form by §FR-022 — part of the four-state model, or a fifth state outside it? [Consistency, Spec §FR-025, §FR-022]

## Acceptance Criteria Quality

- [x] CHK017 Does §FR-054 specify how a loading or error state is to be induced for verification, or only that it must be verified? [Measurability, Spec §FR-054]
- [x] CHK018 Is §SC-012's "verified by automated test rather than by inspection" bound to a page list, so a page added later is not silently unverified? [Traceability, Spec §SC-012]

## Notes

- **CHK003 is a consequence of the framework decision and should be settled before implementation.** The plan renders pages on the server, so most pages never show a client-side loading state at all. §FR-025 requires all four states on every content page. Either the requirement is scoped to client-fetched regions — the careers filter and the contact form — or server-rendered pages need a stated exemption. As written, an implementer could satisfy the letter by adding loading states that never appear.
- CHK016 notes that the user's original request named four states plus success, while §FR-025 defines four; the success state currently lives only in the contact-form requirements.
- CHK002 and CHK009 are the quantification gaps: "no indefinite loading" and "offer a retry" are both directions rather than thresholds.
