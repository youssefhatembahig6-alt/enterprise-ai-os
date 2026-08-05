# Contract: Seed CLI (`eaios-seed`)

**Package**: `scripts/seed` · **Entry point**: `eaios-seed` · **Plan**: [../plan.md](../plan.md)

The command-line surface of the deterministic generator. This is a contract: exit codes, output
shape, and refusal behavior are relied on by CI, by the `make` targets, and by the e2e tests, so
changing any of them is a breaking change.

## Global options

| Option | Default | Notes |
|--------|---------|-------|
| `--seed <str>` | `20260630` | Root seed (R3). Changing it produces a different but equally valid dataset. |
| `--reference-date <date>` | `2026-06-30` | Pinned generation date (R2). |
| `--profile <name>` | `full` | `full` (spec volumes, FR-020b) or `smoke` (~2% volume, for fast CI). |
| `--json` | off | Emit machine-readable output on stdout; human summary goes to stderr. |
| `--log-level <level>` | `info` | Structured JSON logs to stderr. |

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | Unexpected error (bug, unreachable dependency after retries) |
| `2` | **Refused** — precondition not met (e.g. `seed` against a non-empty environment) |
| `3` | **Verification failed** — fingerprint mismatch, integrity violation, or incomplete dataset |
| `4` | Confirmation required but not supplied (`reset` without `--yes`) |

Exit code `2` is deliberately distinct from `1`: a refusal is a correct, expected outcome, and CI
must be able to distinguish "the tool protected the environment" from "the tool broke."

---

## `eaios-seed seed`

Populates an empty environment end to end (FR-013).

**Preconditions**: All four stores must be empty. Emptiness means: no rows in any application table,
no objects under the bucket prefix, no non-system Qdrant collections carrying points, and no keys
under the application's Redis namespace. Migrations must be at head.

**Refusal** (FR-014): if any store holds data, exit `2` without writing anything:

```text
REFUSED: environment is not empty.
  postgres: 41,882 rows across 27 tables
  minio:    183 objects under s3://eaios/
To destroy and regenerate, run:  make reset
```

**Order of operations** (R7 — a crash must always leave a detectably incomplete environment):

1. Open a single transaction; write the manifest row with `completed_at = NULL`.
2. Insert all relational data (global tables first, then per company).
3. Upload generated documents to object storage; record `content_sha256` per file.
4. Provision Qdrant collections and the `company_id` payload index — created empty (D2).
5. Compute per-family and root fingerprints.
6. Write `entity_counts`, `family_digests`, `root_fingerprint`, and **`completed_at` last**; commit.
7. Write `SEED` audit entries for both companies (FR-043).

**Output** (`--json`) conforms to [`dataset-manifest.schema.json`](./dataset-manifest.schema.json).

**Guarantee**: two `seed` runs with the same `--seed` and `--reference-date`, against empty
environments, produce identical `root_fingerprint` values on any OS (FR-011, SC-002).

---

## `eaios-seed reset`

Destroys all data in every store and regenerates from empty (FR-004, FR-014a).

**This is the only destructive command in the feature.** Per Constitution Principle VII it never runs
implicitly and never as a side effect of `seed`.

**Safety gates**, all required:

1. `--yes` must be passed, or exit `4`.
2. The resolved database host must be `localhost`, `127.0.0.1`, or a Compose service name. Anything
   else exits `2` regardless of `--yes`.
3. An environment variable `EAIOS_ENV` set to anything other than `local` causes exit `2`.

**Behavior**: prints what it is about to destroy (per-store counts) → truncates all application
tables → empties the bucket prefix → deletes and recreates Qdrant collections → flushes the Redis
namespace → re-runs migrations to head → invokes `seed`. Writes a `RESET` audit entry.

```text
$ eaios-seed reset --yes
About to destroy:
  postgres: 41,882 rows   minio: 183 objects   qdrant: 4 collections   redis: 0 keys
Target: postgres://eaios_owner@postgres:5432/eaios   (local)
Resetting... done in 4m12s
root_fingerprint: 9f2c...a71b   (matches expected)
```

---

## `eaios-seed verify`

Recomputes the fingerprint from the live environment and compares it to the manifest (FR-017).
Read-only; safe to run at any time and in CI.

**Checks**, each reported independently:

| Check | Fails with |
|-------|-----------|
| Manifest exists and `completed_at` is set | exit `3` — "environment incomplete" |
| Recomputed root fingerprint matches stored | exit `3` — plus the **names of the diverging families** |
| Every non-allowlisted table has non-null `company_id` | exit `3` |
| No foreign key crosses tenants | exit `3` |
| Realized counts within ±10% of the profile targets | exit `3` |
| Object-storage contents match `documents.content_sha256` | exit `3` |

Per-family reporting is the point: "fingerprint mismatch" alone is nearly undebuggable across ~27
tables, so the failure output names which families drifted.

```text
$ eaios-seed verify
✓ manifest complete            ✓ tenant columns (27/27 tables)
✗ fingerprint mismatch
    niletech.orders      expected 3a91... got 7c02...
    niletech.invoices    expected 88be... got 1d44...
  25 other families match.
exit 3
```

---

## `eaios-seed fingerprint`

Prints the recomputed root fingerprint (and per-family digests with `--json`) without comparing.
Used by the determinism e2e test to compare two independent runs. Exit `0` unless the environment is
unreadable.

---

## Determinism contract

The generator must satisfy all of the following. Each has a test.

| Invariant | Test |
|-----------|------|
| Same seed + same reference date ⇒ identical fingerprint | `tests/e2e/test_determinism.py` |
| Identical across Linux, macOS, Windows | CI matrix |
| Independent of machine timezone and locale | `tests/unit/test_clock.py`, container `LANG=C.UTF-8` |
| Independent of insertion and row-retrieval order | `tests/unit/test_fingerprint.py` |
| Generated files byte-identical (LF, UTF-8, no BOM) | `tests/unit/test_document_bytes.py` |
| No wall-clock call in generator code | `tests/unit/test_no_wallclock.py` (AST scan) |
| Frozen known-ID fixtures unchanged | `tests/unit/test_ids.py` |
