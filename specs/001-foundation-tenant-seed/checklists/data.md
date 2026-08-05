# Data Requirements Quality Checklist: Foundation

**Purpose**: Validate that requirements covering synthetic-data completeness, database integrity, and seed reproducibility are complete, unambiguous, measurable, and internally consistent — before implementation begins
**Created**: 2026-08-01
**Feature**: [spec.md](../spec.md)
**Depth**: Formal gate (pre-implementation)

**Note**: These items test the **requirements**, not the generated data. Each asks whether something
is adequately *written down*, not whether it works.

## Synthetic-Data Completeness

- [x] CHK001 **RESOLVED 2026-08-01** — FR-030 now covers both companies. Do the public-content requirements and the volume table agree on whether Delta Retail has public content? FR-030 mandates it "for NileTech" only, while the volume table allocates 20 public items to Delta Retail [Conflict, Spec §FR-030 vs §FR-020b]
- [ ] CHK002 Is "plausible for a company of this type and size rather than uniform" expressed as a checkable rule, or does acceptance depend on a reviewer's judgment? [Ambiguity, Spec §FR-020]
- [ ] CHK003 Are the number, form, and placement of Delta Retail marker phrases specified, or only their existence? [Gap, Spec §FR-023]
- [ ] CHK004 Are salary band names and value ranges defined anywhere, given salary is the payload behind the flagship denial scenario? [Gap, Spec §FR-026, §FR-047a]
- [ ] CHK005 Is the set of distinct job titles specified, or is only the existence of a `job_title` attribute required? [Gap, Spec §FR-026]
- [ ] CHK006 Is "non-placeholder content" defined with acceptance criteria, or is it an unfalsifiable claim about prose quality? [Measurability, Spec §US5 AS1]
- [ ] CHK007 Are the entity families that Delta Retail must populate enumerated, given FR-022 requires it be "complete enough to exercise every entity family used in isolation tests"? [Ambiguity, Spec §FR-022]
- [ ] CHK008 Are Delta Retail's five departments stated as a requirement, or only as an assumption — and is an assumption an acceptable source for a countable acceptance criterion? [Consistency, Spec §Assumptions vs §FR-021]
- [ ] CHK009 Is currency scope defined as per-company or per-office, given NileTech operates across Egypt and the UAE? [Ambiguity, Spec §FR-038 vs §Assumptions]
- [ ] CHK010 Are requirements defined for how many of each classification level must exist per company beyond the extremes named in FR-010c? [Coverage, Spec §FR-010c]
- [ ] CHK011 Are requirements specified for the content and structure of the synthetic code repository referenced in the source blueprint but absent from this spec? [Gap]
- [ ] CHK012 Are requirements defined for generated data volumes under the reduced CI profile, or does the profile exist only in the plan and CLI contract? [Gap, Spec §FR-020b]

## Database Integrity

- [ ] CHK013 Are deletion and cascade semantics specified for any relationship, or is deletion simply undefined? [Gap, Spec §FR-033]
- [ ] CHK014 Is there a requirement that migration downgrades are exercised, or only that migrations are "reversible"? [Clarity, Spec §FR-007]
- [ ] CHK015 Is it specified which invariants must be enforced by database constraints versus which may be enforced only by tests — given that FR-034's acyclicity cannot be a simple constraint? [Gap, Spec §FR-034]
- [ ] CHK016 Are requirements defined for transiently nullable columns needed to break circular insertion dependencies, and for the post-load check that closes them? [Gap, Spec §FR-034]
- [ ] CHK017 Is audit-log immutability stated as a requirement in the spec, or does it exist only in the constitution and data model? [Gap, Spec §FR-043, Constitution §X]
- [ ] CHK018 Are requirements defined for how the classification enum may evolve without invalidating existing data? [Gap, Spec §FR-010a]
- [ ] CHK019 Does the spec require foreign keys to be declared, or would enforcement purely by test satisfy "zero orphaned references"? [Clarity, Spec §FR-033]
- [ ] CHK020 Are index or query-performance requirements specified, given SC-008 imposes a seed-time budget over ~40,000 rows? [Gap, Spec §SC-008]
- [ ] CHK021 Are uniqueness rules specified for every entity, or only for those where a natural key happens to be obvious? [Coverage, Spec §FR-033]
- [ ] CHK022 Are requirements defined for numeric precision and rounding, given FR-038 requires arithmetic consistency across derived totals? [Clarity, Spec §FR-038]

## Seed Reproducibility

- [x] CHK023 **RESOLVED 2026-08-01** — FR-012c added. Does the spec state whether the seed value is fixed and committed or operator-supplied? FR-011 guarantees reproducibility "given the same fixed seed value" without ever requiring the value be fixed [Gap, Spec §FR-011]
- [x] CHK024 **RESOLVED 2026-08-01** — FR-017a added. Is there a requirement to pin a known-good fingerprint in version control? Without one, FR-017's verification only proves the dataset matches its own manifest — a code change that alters generation produces a new dataset and a new manifest that agree perfectly [Gap, Spec §FR-017]
- [ ] CHK025 Do the ±10% volume tolerance and the exact-determinism guarantee conflict, or is the tolerance scoped to profile targets rather than run-to-run variance? The spec does not say which [Ambiguity, Spec §FR-020b vs §FR-011]
- [x] CHK026 **RESOLVED 2026-08-01** — FR-012b added. Are dependency version-pinning requirements specified, given that generated names and text depend on library data that changes between releases? [Gap, Spec §FR-011]
- [x] CHK027 **RESOLVED 2026-08-01** — FR-012a added. Are the encoding, newline, and locale controls that make byte-identical output achievable stated as requirements, or only as plan-level design decisions? [Gap, Spec §FR-032]
- [ ] CHK028 Is it defined when a generator-version bump is required, so that a legitimate dataset change is distinguishable from an accidental one? [Gap, Spec §FR-016]
- [ ] CHK029 Are requirements defined for changing the pinned reference date, and for what that change invalidates? [Gap, Spec §FR-012]
- [ ] CHK030 Is the fingerprint exclusion list constrained by a stated principle, so that a future over-broad exclusion cannot silently weaken the determinism guarantee? [Clarity, Spec §FR-015a]
- [x] CHK031 **RESOLVED 2026-08-01** — FR-047b added. Are requirements defined for verifying determinism across operating systems, or does SC-002's cross-machine claim rest on an untested assumption? [Gap, Spec §SC-002]
- [ ] CHK032 Are requirements specified for how generated identifiers remain stable when generator code is refactored or reordered? [Gap, Spec §FR-011]

## Notes

- `[Gap]` — the requirement appears to be **missing**; resolve by adding a requirement or explicitly recording it as out of scope.
- `[Conflict]` — two parts of the spec disagree; one must change. **CHK001 is a confirmed conflict**, not a suspicion.
- `[Ambiguity]` — reads as testable but is not objectively measurable as written.
- CHK024, CHK026, CHK027, and CHK031 form a cluster: the spec asserts reproducibility as an outcome but does not require the controls that produce it. Each is currently carried by the plan alone, which means an implementer who reads only the spec could satisfy every requirement and still ship a non-deterministic generator.
