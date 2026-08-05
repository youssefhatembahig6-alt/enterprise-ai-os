# Determinism

The dataset must be identical on every machine and every run (spec FR-011, SC-002). This is
what makes a bug reproducible, a demo re-runnable, and an evaluation metric comparable
between weeks. Everything below exists to protect that property.

## The four anchors

| Anchor | Value | Defined in |
|---|---|---|
| Root seed | `20260630` | `eaios_core.constants.ROOT_SEED` |
| Reference date | `2026-06-30` | `eaios_core.constants.REFERENCE_DATE` |
| Identifier scheme | UUIDv5 from a natural-key URN | `eaios_core.ids` |
| Byte controls | UTF-8, LF, no BOM, fixed decimal scale | `.gitattributes`, container locale |

Changing any of these produces a *different but equally valid* dataset. That is a deliberate
act: it invalidates the committed fingerprint and every frozen identifier fixture. Bump
`GENERATOR_VERSION` when you do it, so a deliberate change is distinguishable from an
accidental one.

The reference date is the last day of a month **and** a quarter, so the blueprint's flagship
demo — "generate last month's sales report" — lands on a complete June with a full quarter
behind it, and year-over-year comparison reaches a complete 2024-07 baseline.

## What is banned in generation code

`packages/core` and `scripts/seed` may not call `datetime.now`, `datetime.utcnow`,
`date.today`, or `time.time`. `tests/unit/test_no_wallclock.py` walks the AST of every file
in those trees and fails if any appear. `clock.py` and `manifest.py` are the only exemptions:
the first *is* the sanctioned time source, the second records genuine run metadata that is
excluded from the fingerprint.

A single stray wall-clock call makes the dataset a function of *when* it was seeded. The
symptom — a fingerprint that differs by machine and by day — is unpleasant to trace back to
its cause, so it is caught statically instead.

## Randomness

One root seed, from which every generator derives its own sub-seed:

```text
sub_seed = sha256(f"{ROOT_SEED}:{generator_name}:{company_slug}")[:8]
```

Each generator gets its own `random.Random` and its own `Faker`. A single shared RNG would
make every generator's output depend on the execution order of every other one — adding an
employee upstream would shift every downstream value, and any future reordering would look
like a determinism bug.

Faker is pinned to an exact version. Its word and name lists change between releases, so that
pin is load-bearing rather than hygiene.

## What the fingerprint excludes

Deliberately minimal (FR-015a) — an over-broad exclusion silently weakens the guarantee:

| Excluded | Why |
|---|---|
| `dataset_manifest` | Contains the fingerprint; including it would be self-referential |
| `alembic_version` | Migration bookkeeping, not dataset content |
| `contact_submissions` | Written at runtime by visitors to the public site (feature 002), never by the generator. Including it would make submitting the contact form change the fingerprint and fail `verify` — reporting a legitimate user action as a determinism defect |

`contact_submissions` is the only exclusion that is *tenant-owned data*, which makes it the
one worth watching. Excluding a table from the fingerprint means nothing verifies its
contents, so the exclusion is only safe because the generator never writes there. Two
companion changes keep that honest: `reset_all` truncates it, and the seed's emptiness
pre-flight counts it. Without the second, a submission written before seeding would leave the
environment non-empty in a way the pre-flight could not see, and `seed` would proceed against
a dirty database — exactly the state FR-014 exists to refuse.

Note what is **not** excluded: `created_at` and `updated_at`. Rather than exempting them, the
generator sets them explicitly from the reference clock, so they are deterministic and get
verified like any other field. Excluding them would have left a real class of
non-determinism untested.

The digest is order-independent by construction: row digests are sorted before being
combined, so two runs that insert in different orders but produce the same content still
match.

## Cross-platform verification

The full seed needs Docker, and GitHub's Windows runners cannot run Linux containers, so a
genuinely cross-OS *stack* run is not available. The parts that actually vary by platform are
pure Python — line endings, text encoding, locale-sensitive formatting, ordering, path
handling — and `eaios_core.selfcheck` digests exactly those. CI computes it on Ubuntu and
Windows and fails if the two disagree.

```bash
PYTHONPATH=packages/core/src uv run python -m eaios_core.selfcheck
```

Until this job existed, the fingerprint was computed on one platform only, so SC-002's
cross-machine claim rested on a comparison that never happened.

## Windows

`.gitattributes` sets `* text eol=lf`. If `core.autocrlf` is `true`, Git rewrites files on
checkout, generated documents differ by bytes, and the fingerprint diverges for reasons that
look nothing like line endings. CI checks this explicitly on the Windows runner before
anything else runs.

## Tenant identifiers are predictable, and that is accepted

**Decision (2026-08-01):** company slugs are the human-readable `niletech` and
`delta-retail`, and they appear in object-storage keys and cache keys.

They are therefore guessable. This is accepted for this project, for two reasons. The slugs
are not a secret and grant nothing on their own — every access path is gated by the tenant
predicate in the RLS policy and by application-level filtering, neither of which consults a
key string. And readable keys make the isolation tests, the audit output, and the defense
demo dramatically easier to follow: `niletech/RESTRICTED/POLICY/payroll-2026.md` states its
own tenant and sensitivity at a glance.

The trade-off is enumerability: someone who can already list a bucket learns that two tenants
exist and what they are called. Given a synthetic demo dataset with no real personal data,
that is not worth opaque identifiers.

If this system were ever to hold real customer data, revisit it — opaque per-tenant
identifiers with a slug used only for display would be the change, and it touches
`eaios_core.keys` and the storage layout, not the policy model.

*(Resolves converge finding F15 / checklists/isolation.md CHK012.)*
