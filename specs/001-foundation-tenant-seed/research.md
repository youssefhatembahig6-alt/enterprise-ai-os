# Phase 0 Research: Foundation — Monorepo, Local Environment & Deterministic Two-Tenant Dataset

**Date**: 2026-08-01 | **Plan**: [plan.md](./plan.md)

Every unknown carried into this feature concerns one question: *what makes generated data
bit-for-bit reproducible across machines, operating systems, and time?* The findings below resolve
each one. Conventional choices (FastAPI, SQLAlchemy, Alembic, Celery) came from the project owner
and are recorded without re-litigation.

---

## R1. Deterministic identifier strategy

**Decision**: UUIDv5 derived from a fixed root namespace plus a stable natural-key URN.

```text
NAMESPACE_ROOT = uuid5(NAMESPACE_DNS, "eaios.local")
NAMESPACE_DATASET = uuid5(NAMESPACE_ROOT, f"seed:{ROOT_SEED}")
id = uuid5(NAMESPACE_DATASET, f"{entity_type}:{company_slug}:{natural_key}")
```

Example: `uuid5(NAMESPACE_DATASET, "user:niletech:employee-0042")`.

**Rationale**: This was the single largest open risk to FR-011 ("identical identifiers"). UUIDv5 is a
pure function of its inputs — same seed and same natural key produce the same UUID on every machine,
in any language, in any insertion order, with no coordination and no database round-trip. Because IDs
are computed *before* insertion, the generator can build the entire object graph in memory and insert
in any order (or in parallel) without changing a single identifier. Natural keys also make the data
debuggable: a failing test can name the exact entity that broke.

**Alternatives considered**:

- *Sequential integers / `BIGSERIAL`* — deterministic only if insertion order is deterministic. That
  makes every future parallelization or reordering a silent data-changing event, and it couples ID
  stability to code that has nothing to do with identity. Rejected.
- *Random UUIDv4 with a seeded RNG* — reproducible only if every `uuid4()` call happens in exactly the
  same order across the whole program. Any refactor that moves a call reshuffles every subsequent ID.
  Rejected as far too fragile.
- *Content-addressed hashes of the full row* — stable, but any field edit changes the ID and therefore
  every foreign key pointing at it. Rejected.

**Consequence**: `packages/core/ids.py` is the only place UUIDs are created for seeded data. A unit
test asserts a frozen set of known ID values, so an accidental change to the namespace or key format
fails immediately rather than silently producing a "different but valid" dataset.

---

## R2. Pinned reference date and the forbidden clock

**Decision**: `REFERENCE_DATE = 2026-06-30` (UTC), stored in the dataset manifest. All generated
temporal data derives from it. Wall-clock access is structurally prevented in the generator.

**Rationale**: FR-012 forbids clock dependence. Choosing 2026-06-30 — the last day of a month and a
quarter — means the blueprint's flagship demo ("generate last month's sales report" → June) works
against a completed month with a full quarter behind it, and year-over-year comparison reaches back
to a complete 2024-07 baseline. Derived windows:

| Window | Range |
|--------|-------|
| Full history (orders, invoices, expenses, leave, reviews, training) | 2024-07-01 → 2026-06-30 |
| Attendance (capped, FR-020a) | 2026-01-01 → 2026-06-30 |
| "Last month" for the demo | 2026-06-01 → 2026-06-30 |

**Enforcement**: `packages/core/clock.py` exposes only `reference_date()` and offset helpers. A lint
rule plus a unit test ban `datetime.now`, `datetime.utcnow`, `date.today`, and `time.time` inside
`scripts/seed/` and `packages/core/`. This is cheaper than discovering the leak through a failed
fingerprint comparison months later.

**Alternatives considered**: generating relative to "now" with a frozen-clock test fixture — makes the
dataset a function of when it was seeded, so two developers seeding on different days get different
data. Directly contradicts SC-002. Rejected.

---

## R3. Seeded random generation and sub-seed derivation

**Decision**: One `ROOT_SEED` (default `20260630`). Every generator receives a **derived sub-seed**,
never the root:

```text
sub_seed = int.from_bytes(sha256(f"{ROOT_SEED}:{generator_name}:{company_slug}").digest()[:8])
```

Each generator instantiates its own `random.Random(sub_seed)` and its own `Faker` with that seed and
a pinned locale list. No module-level global RNG is used anywhere.

**Rationale**: A single shared RNG makes every generator's output depend on the execution order of
every other generator — adding one employee upstream shifts every downstream value. Derived sub-seeds
make each generator independently reproducible, so generators can be added, reordered, or run in
parallel without disturbing existing data. This directly protects SC-002 against ordinary future
refactoring.

**Faker specifics**: pin `Faker` to an exact version and an explicit locale list (`en_US` plus a
curated Egyptian/Emirati name pool). Faker's word lists change between releases, so the version pin is
load-bearing, not hygiene — an unpinned minor upgrade would silently change every generated name.

**Alternatives considered**: `numpy.random.Generator` (adds a heavy dependency for no benefit here);
one global seeded RNG (rejected above).

---

## R4. Byte-identical document generation

**Decision**: Documents are rendered from Jinja2 templates to UTF-8 text with `newline="\n"` forced at
every write, no BOM, no trailing whitespace, and a fixed template-variable ordering. Decimal values
are quantized to two places before rendering. No generation timestamp appears in any document body.

**Rationale**: FR-032 requires byte-identical files. On Windows — the team's primary OS — Python's
default text mode translates `\n` to `\r\n`, so the same generator produces different bytes on
different machines and the fingerprint diverges immediately. Three controls close this:

1. Every file write passes `newline="\n"` explicitly (or writes bytes directly).
2. `.gitattributes` sets `* text eol=lf` so checked-in templates are identical everywhere.
3. A unit test renders a fixture document and asserts an exact SHA-256, so a regression is caught at
   the file level rather than surfacing as an unexplained whole-dataset fingerprint mismatch.

Locale is pinned to `C`/`en_US.UTF-8` inside the containers so number and date formatting cannot vary.

**Alternatives considered**: PDF/DOCX generation — rejected by confirmed decision D3. Worth recording
*why* it is genuinely harder: both formats embed creation timestamps and document IDs by default, so
byte-identical output requires post-processing every file to strip or freeze metadata. That work
belongs with the ingestion feature that actually needs binary parsing.

---

## R5. Dataset fingerprint algorithm

**Decision**: A two-level digest — per-entity-family, then a root.

1. Serialize each row to canonical JSON: keys sorted, UUIDs as lowercase hyphenated strings, dates as
   ISO-8601, decimals as fixed-scale strings, `null` explicit.
2. `SHA-256` each row → hex digest.
3. Sort the row digests lexicographically (making the family digest **order-independent**), join with
   `\n`, hash → family digest.
4. Files: `SHA-256` of raw bytes, paired with the storage key, sorted by key, hashed → files digest.
5. Root: hash the sorted `family:digest` lines plus the files digest.

**Rationale**: Sorting row digests before combining is what satisfies FR-015a's order-independence
requirement — two runs that insert in different orders but produce identical content must match.
Per-family digests matter for diagnosis: when a run diverges, the report names *which family* drifted
instead of just reporting "fingerprint mismatch."

**Exclusion list** (documented per FR-015a, deliberately minimal):

| Excluded | Why |
|----------|-----|
| The `dataset_manifest` row itself | Contains the fingerprint — including it would be self-referential |
| `alembic_version` | Migration bookkeeping, not dataset content |
| Physical/system columns (`ctid`, OIDs) | Not logical content |

Notably **not** excluded: `created_at` / `updated_at`. Rather than exempting them, the generator sets
them explicitly from the reference clock, so they are deterministic and can be verified like any other
field. Excluding them would have left a real class of non-determinism untested.

---

## R6. Row-Level Security with no authentication layer yet

**Decision**: Two database roles and a session GUC.

- `eaios_owner` — owns the schema, runs migrations and the seed. Table owners bypass RLS unless
  `FORCE ROW LEVEL SECURITY` is set, which is exactly the behavior the seed needs.
- `eaios_app` — non-owner role used by the API and worker. RLS is enforced.
- Policy on every tenant-owned table:
  `USING (company_id = current_setting('app.company_id', true)::uuid)`.
- `packages/core/db` provides a context manager that sets `app.company_id` for the session and clears
  it on exit; with no GUC set, the app role sees **zero rows** — failing closed.

**Rationale**: Constitution Principle I mandates RLS, but decision D1 defers authentication, so there
is no authenticated principal to derive the tenant from yet. Binding policies to a session variable
decouples the two: RLS is real and testable now, and the next feature simply sets the GUC from the
verified JWT claim instead of from a test fixture. Failing closed on an unset GUC means a future code
path that forgets to set the tenant returns nothing rather than everything — the correct direction for
a security default.

**Alternatives considered**:

- *Defer RLS to the ingestion/auth feature* — rejected: Principle I is NON-NEGOTIABLE and explicitly
  not eligible for the Complexity Tracking escape hatch. Retrofitting also means revisiting every
  table after queries already exist.
- *Separate database or schema per tenant* — stronger isolation, but it breaks the blueprint's shared
  `permissions` catalog, complicates migrations (N schemas to keep in step), and does not match the
  documented `company_id`-column architecture. Rejected.

---

## R7. Seed refusal, reset, and partial-run detection

**Decision**: `seed` performs a pre-flight emptiness check across all four stores and aborts with exit
code `2` and a message naming `make reset` if anything is present. Relational writes run inside a
single transaction. The `completed_at` field of the dataset manifest is written **last**, in that same
transaction. `verify` treats a manifest without `completed_at` as an incomplete environment.

**Rationale**: This resolves the spec's former "idempotent **or** refuse" ambiguity (clarification Q5).
Full idempotency across ~25 entity families and four heterogeneous stores would require upsert logic
and reconciliation for every family — substantial code whose failure mode is a subtly half-merged
dataset. Refuse-plus-explicit-reset is a few dozen lines, has one obvious correct behavior, and is
trivially testable.

MinIO and Qdrant are not transactional. The completion marker covers them: content may exist after a
crash, but without `completed_at` the environment is unambiguously "incomplete", and `verify` reports
object-store contents that disagree with the manifest.

**Ordering**: relational rows first, then object storage, then the manifest's completion marker. A
crash therefore always leaves an environment that reads as incomplete, never as complete-but-wrong.

---

## R8. Monorepo tooling across Python and TypeScript

**Decision**: `uv` workspace for Python (members: `packages/core`, `apps/api`, `services/worker`,
`scripts/seed`) with a single committed `uv.lock`; `pnpm` workspaces for TypeScript (`apps/web`,
`packages/ui`, `packages/contracts`); `make` as the one entry point the team actually types.

**Rationale**: The two ecosystems need separate tools, but the team needs one interface. A short
Makefile wrapping both keeps the spec's "one documented command" promise honest (FR-002). A single
committed lockfile per ecosystem is also part of reproducibility — an unpinned transitive dependency
that changes Faker or the JSON serializer would change generated content.

**Alternatives considered**: Nx or Turborepo (heavy for a five-person student team, and neither
manages Python); Poetry (slower, and its workspace support is weaker than uv's); a single `pip` +
`requirements.txt` (no lockfile guarantees for transitive dependencies — unacceptable given R3's
version-pinning requirement).

---

## R9. Health checks and structured logging

**Decision**: Two endpoints — `GET /health/live` (process is up, no dependencies touched) and
`GET /health/ready` (checks PostgreSQL, Redis, Qdrant, and MinIO concurrently with a per-dependency
timeout, returning a per-dependency status object). `/health/ready` returns `200` only when all four
are reachable, `503` otherwise, with the failing dependency named in the body.

Logging is `structlog` emitting JSON, with `request_id` and — once authentication exists —
`company_id` bound to the context. Log output is one line per event, so it stays greppable in
`docker compose logs`.

**Rationale**: FR-003 requires per-dependency reporting so a partially started environment is
immediately visible, which a single boolean cannot provide. Splitting liveness from readiness prevents
Compose from restart-looping the API while a slower dependency is still warming up. Binding
`company_id` into the log context now means the audit and observability story does not need
retrofitting when the tenant becomes known per request.

---

## R10. Qdrant, MinIO, and Redis provisioning while empty

**Decision**:

- **Qdrant** — create one collection per tenant-scoped content type with the vector configuration
  fixed now, plus a **payload index on `company_id`**. Collections are created empty (D2).
- **MinIO** — one bucket, keys namespaced `{company_slug}/{classification}/{document_type}/{filename}`
  (FR-039). Bucket policy denies anonymous access; a per-company prefix convention is documented and
  asserted by tests.
- **Redis** — no cached values yet, but `packages/core/keys.py` ships the cache-key builder in the
  final format (`{company_slug}:{permission_fingerprint}:{normalized_question}:{data_version}`) with
  unit tests proving two companies can never collide.

**Rationale**: Provisioning the *shape* now costs almost nothing and makes decision D2's deferral
safe: the ingestion feature adds content to a store that already filters correctly, rather than
adding both content and filtering at once. Creating the `company_id` payload index up front matters
particularly — adding it later to a populated collection is a reindex.

**Consequence for testing**: the cross-tenant vector probe in this feature asserts the collection is
present, correctly configured, and **empty**. The semantic version of that probe is already recorded
in the spec as a required acceptance test of the ingestion feature, so the gap is tracked rather than
forgotten.

---

## Summary of decisions

| # | Area | Decision |
|---|------|----------|
| R1 | Identifiers | UUIDv5 from root namespace + natural-key URN |
| R2 | Time | Pinned `REFERENCE_DATE = 2026-06-30`; wall-clock access banned by lint + test |
| R3 | Randomness | Root seed → per-generator derived sub-seeds; pinned Faker version and locale |
| R4 | Documents | Jinja2 → UTF-8, forced LF, quantized decimals, byte-exact fixture test |
| R5 | Fingerprint | Canonical JSON → sorted per-row digests → per-family → root; minimal exclusions |
| R6 | RLS | `eaios_owner` / `eaios_app` roles + `app.company_id` session GUC; fails closed |
| R7 | Seed safety | Refuse on non-empty (exit 2); explicit reset; completion marker written last |
| R8 | Tooling | uv workspace + pnpm workspaces, unified behind `make` |
| R9 | Ops | Split liveness/readiness with per-dependency status; structlog JSON |
| R10 | Stores | Qdrant collections + `company_id` payload index (empty); MinIO key namespacing; Redis key builder |

**All NEEDS CLARIFICATION items are resolved.** No unknowns carry into Phase 1.
