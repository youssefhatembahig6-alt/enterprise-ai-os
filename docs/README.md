# Documentation set

Satisfies **FR-048**. The specification uses the word "documented" in six separate
requirements without ever defining the artifact it refers to, which left all six
unverifiable. This index is that artifact: every such reference resolves to a location here.

| Requirement | What must be documented | Where it lives |
|---|---|---|
| FR-002, FR-004 | Startup and reset commands, with prerequisites | [Root README](../README.md#the-two-commands) |
| FR-005, FR-006 | Environment configuration surface and its defaults | [`infrastructure/.env.example`](../infrastructure/.env.example) — annotated inline |
| FR-012a | Platform-specific setup caveats (Windows line endings) | [Root README](../README.md#prerequisites) and [determinism.md](determinism.md) |
| FR-015a | Fingerprint exclusion list and its rationale | [determinism.md](determinism.md#what-the-fingerprint-excludes) |
| FR-022 | Delta Retail's intentional absences | [dataset.md](dataset.md) |
| FR-025b | Persona reference with company, department, role, country, manager | [personas.md](personas.md) |

Every entry now resolves. `personas.md` and `dataset.md` are **generated** by
`make docs` from `scripts/seed/src/eaios_seed/docgen.py` — edit the generator, never the
output.

They are rendered from the **deterministic generator at the `full` profile**, not from a
live database. That distinction matters twice over. The generator needs no running stack,
so `tests/unit/test_docs_freshness.py` can fail on drift in every run rather than skipping
itself whenever Docker is down. And the profile is stamped in both files because persona
*names* differ between the full and smoke profiles — a reader comparing the persona table
against a smoke-seeded environment will find eight names that look wrong and are not.

This paragraph previously claimed the files were generated from the live database and
therefore "cannot drift". No generator existed at the time. The claim was read as a
guarantee for several review passes while both files carried a stale version stamp and
fingerprint, and it later produced a false alarm in the other direction. An assurance with
nothing behind it is worse than no assurance.

## Other documents

| Document | Purpose |
|---|---|
| [`Enterprise_AI_OS_EDITED.html`](Enterprise_AI_OS_EDITED.html) | The project blueprint — the authority on *what* is being built |
| [`determinism.md`](determinism.md) | How reproducibility is achieved and enforced |
| [`dataset.md`](dataset.md) | The two tenants, their shape, and Delta's intentional absences |
| [`personas.md`](personas.md) | The ten fixed personas and the scenario each serves |
| [`running.md`](running.md) | Running the stack without `make`, plus PowerShell gotchas |
| [`../.specify/memory/constitution.md`](../.specify/memory/constitution.md) | Engineering rules — the authority on *how* |
| [`../specs/001-foundation-tenant-seed/`](../specs/001-foundation-tenant-seed/) | Spec, plan, research, data model, contracts, quickstart, tasks |

## The public website (feature 002)

The NileTech public site runs at **http://localhost:3000** once `make up && make seed`
have finished. It renders feature 001's `PUBLIC` content and holds no content of its own.

| Address | What it is |
|---|---|
| `/` … `/contact` | The eight public pages, plus vacancy and article detail pages |
| `/portal` | Reserved employee-portal address. Serves a designed "sign-in not yet available" page and accepts no credentials — the boundary is enforced before the portal exists |
| `/status` | The feature 001 environment status view. Diagnostic, not a public page: excluded from the sitemap and from indexing |

```bash
make test-site
```

Runs the component tests plus the browser sweeps — accessibility (WCAG 2.2 AA via axe),
the keyboard-only pass, responsive assertions at 360/768/1280, and the metadata audit.
Needs a running, seeded stack; the sweeps assert against real content, and against an
empty site they would pass while checking nothing.

**The site writes one table.** `contact_submissions` holds enquiries from the public
form. It is excluded from the dataset fingerprint, truncated by `reset`, and counted by
the seed's emptiness pre-flight — see [determinism.md](determinism.md) for why all three
are needed.

## Recorded deviations from the plan

| Plan says | What was built | Why |
|---|---|---|
| `packages/contracts/schemas/dataset-manifest.schema.json` | The schema lives only at [`specs/001-foundation-tenant-seed/contracts/dataset-manifest.schema.json`](../specs/001-foundation-tenant-seed/contracts/dataset-manifest.schema.json); the empty package directory was removed | A second copy inside the package would be a third representation of the same contract — the TypeScript side already receives `DatasetManifest` as a generated type from the OpenAPI schema, and `tests/integration/test_manifest_schema.py` validates the emitted manifest against the JSON Schema. Two files with no test asserting they agree drift; one file cannot |

## Keeping this honest

Documentation whose instructions no longer work is a defect, not an inconvenience (FR-048).
The commands in the root README are exercised by `tests/e2e/test_clean_startup.py`, so a
README that drifts from reality fails CI rather than quietly misleading the next person.
