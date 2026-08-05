# Quickstart & Validation Guide: Foundation

**Date**: 2026-08-01 | **Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md)

How to bring the environment up and how to prove it satisfies the specification. Every scenario below
maps to numbered requirements and success criteria, and each is automated — the manual steps exist so
a human can reproduce what CI does.

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Docker Desktop (or Docker Engine + Compose v2) | 24+ | Allocate ≥ 8 GB RAM — four stateful stores plus three application services |
| `make` | any | **Not bundled with Git Bash** — install with `winget install ezwinports.make`, or use the raw `docker compose` equivalents |
| Git | 2.40+ | `core.autocrlf` must **not** be `true` — see the Windows note below |

Nothing else. Python, Node, and every dependency live inside containers, so a clean machine needs no
language toolchain to run the stack.

> **Windows note (load-bearing, not cosmetic)**: the repository ships a `.gitattributes` with
> `* text eol=lf`. If Git rewrites checked-out files to CRLF, generated documents differ by bytes and
> the fingerprint check fails with a confusing whole-dataset mismatch. Verify with
> `git config core.autocrlf` — it must be `false` or `input`.

---

## The two commands

```bash
make up
```

Builds images, starts all 9 Compose services, runs migrations to head, and blocks until `/health/ready`
reports all five dependencies up — the four stores plus the background worker. This is the single
documented startup command required by FR-002.

```bash
make reset
```

Destroys all state in every store and regenerates the full dataset (FR-004, FR-014a). Prompts for
confirmation; refuses if the target is not local.

Supporting targets: `make down` (stop, keep volumes) · `make seed` (seed only, refuses if non-empty)
· `make verify` (fingerprint + integrity) · `make test` (full suite).

---

## Scenario 1 — Clean checkout to healthy stack

**Validates**: US1 · FR-002, FR-003 · SC-001

```bash
git clone <repo> && cd Grad_Project
cp infrastructure/.env.example .env
make up
```

Expected: all 9 Compose services reach healthy (`minio-init` and `seed` are one-shot containers and exit); total elapsed under 15 minutes on a first run (image pulls
dominate; subsequent runs are ~60 seconds).

```bash
curl -s localhost:8000/health/ready | jq
```

```json
{
  "status": "ready",
  "dependencies": [
    { "name": "postgres", "status": "up", "latency_ms": 3 },
    { "name": "redis",    "status": "up", "latency_ms": 1 },
    { "name": "qdrant",   "status": "up", "latency_ms": 7 },
    { "name": "minio",    "status": "up", "latency_ms": 4 }
  ]
}
```

**Negative check** — stop one dependency and confirm the failure is *named*, not hidden behind a
boolean:

```bash
docker compose stop qdrant && curl -s -o /dev/null -w '%{http_code}\n' localhost:8000/health/ready
```

Expected `503`, with `qdrant` reported `down` and the other three still `up`. Restart with
`docker compose start qdrant`.

The web status shell at `http://localhost:3000/status` renders the same per-dependency view. It is a status
page only — there is no product UI in this feature (decision D1).

---

## Scenario 2 — Deterministic seed

**Validates**: US2 · FR-011 – FR-017 · SC-002, SC-008

```bash
make seed
eaios-seed fingerprint          # or: docker compose run --rm seed fingerprint
```

Record the `root_fingerprint`. Then prove reproducibility from empty:

```bash
make reset            # destroy everything and regenerate
eaios-seed fingerprint
```

**Expected**: byte-identical `root_fingerprint`. A second team member on a different OS, running the
same commands, must produce the same value — that comparison is what SC-002 actually asserts, and CI
runs it across a Linux/macOS/Windows matrix.

**Refusal check** (FR-014) — run the seed against the now-populated environment:

```bash
make seed
```

Expected: exit code `2`, nothing modified, and a message naming `make reset` as the intended path.
Confirm nothing changed by re-running `eaios-seed fingerprint` and comparing.

**Interrupted-run check** (FR-014b/c): kill the seed midway (`Ctrl-C` during document upload), then:

```bash
eaios-seed verify
```

Expected: exit `3`, reported as *incomplete environment* because `completed_at` is null — not as a
fingerprint mismatch, and never as success.

---

## Scenario 3 — Tenant isolation

**Validates**: US3 · FR-009a, FR-024, FR-024a, FR-039 – FR-045 · SC-003, SC-004

```bash
make verify
```

Expected output includes:

```text
✓ tenant columns        27/27 tables carry non-null company_id
✓ global allowlist      4/4 exactly (permissions, platform_administrators,
                          alembic_version, dataset_manifest)
✓ cross-tenant refs     0 foreign keys cross a company boundary
✓ storage namespacing   183/183 objects under a company prefix
```

**Cross-store probe** — search for a Delta Retail marker phrase in NileTech's scope:

```bash
pytest tests/security/test_cross_tenant_probe.py -v
```

The probe searches every populated store for Delta's distinctive marker phrases while scoped to
NileTech, and the reverse. Expected: zero results in both directions.

> The Qdrant leg of this probe currently asserts the collection is present, correctly configured with
> a `company_id` payload index, and **empty** — because decision D2 defers indexing. The semantic
> version of this probe (similarity search returning nothing across tenants) is a required acceptance
> test of the ingestion feature, recorded in the spec's carry-forward list.

**RLS enforcement** (Constitution Principle I):

```bash
pytest tests/security/test_rls.py -v
```

Covers three cases: as `eaios_app` with `app.company_id` set to NileTech, Delta rows are invisible;
with it set to Delta, NileTech rows are invisible; **with the session variable unset, zero rows are
returned** — the system fails closed rather than open.

---

## Scenario 4 — Data coherence

**Validates**: US4 · FR-033 – FR-038 · SC-005, SC-006, SC-007

```bash
pytest tests/integration/test_coherence.py tests/integration/test_org_hierarchy.py -v
```

| Check | Expectation |
|-------|-------------|
| Leave policy `stated_values` vs. `leave_balances.entitlement_days` | Agreement for every user, per country and employment type |
| `invoice.amount` = `order.total` = Σ `line_total` | Exact at 2 decimal places, every order |
| `monthly_revenue` vs. aggregation over `orders` | Identical |
| Org hierarchy | Exactly one manager-less user per company; no cycles; department heads belong to their department |
| Date windows | No child predates its parent; all dates within 2024-07-01 → 2026-06-30 |
| Referential integrity | Zero orphans |

Spot-check the coherence property that matters most for later grounded answers — the policy and the
records must state the same number:

```bash
docker compose exec postgres psql -U eaios_owner -d eaios -c \
  "SELECT p.stated_values->'annual_leave_days' AS policy,
          (SELECT DISTINCT entitlement_days FROM leave_balances lb
             JOIN users u ON u.id = lb.user_id
            WHERE u.country = 'EG' AND lb.leave_type = 'ANNUAL') AS records
     FROM policy_documents p WHERE p.policy_type = 'LEAVE' LIMIT 1;"
```

Expected: the policy's `EG` value and the records' value are the same number.

---

## Scenario 5 — Personas and scenario readiness

**Validates**: US5 · FR-025b, FR-025c, FR-028a, FR-047a · SC-011, SC-013, SC-014

```bash
pytest tests/security/test_scenario_readiness.py tests/security/test_public_content.py -v
```

Confirms all ten personas resolve with their documented company, department, role, country, and
manager, and that all eight blueprint access-control scenarios have the records needed to express
them once enforcement lands.

Persona reference (stable across every seed run — acceptance tests and the demo script cite these by
name):

| `persona_key` | Company | Department | Role |
|---|---|---|---|
| `employee.engineering` | NileTech | Engineering | Employee |
| `manager.engineering` | NileTech | Engineering | Manager (≥3 reports) |
| `employee.sales` | NileTech | Sales | Employee |
| `hr.generalist` | NileTech | HR | HR |
| `finance.analyst` | NileTech | Finance | Finance |
| `legal.counsel` | NileTech | Legal | Legal (ACL on the contract pair) |
| `auditor.readonly` | NileTech | Operations | Auditor |
| `admin.company` | NileTech | Executive Management | Company Admin |
| `comms.sender` | NileTech | Customer Support | Employee + `communications:send` |
| `employee.delta` | Delta Retail | Sales | Employee |

The contract-comparison pair (FR-028a) is verifiable directly:

```bash
docker compose exec postgres psql -U eaios_owner -d eaios -c \
  "SELECT counterparty_name, notice_period_days, liability_cap_amount, payment_terms
     FROM contracts WHERE contract_type = 'CUSTOMER' ORDER BY counterparty_name LIMIT 2;"
```

Expected: 30 vs. 90 day notice, 50,000 vs. NULL liability cap, identical NET_30 payment terms — the
same shape of answer the blueprint's contract-comparison demo produces.

**Public-content safety** (SC-011): the scan asserts no `PUBLIC` row contains salary figures, contract
terms, internal financial values, or non-executive contact details.

---

## Full validation

```bash
make test
```

Runs unit → integration → security → e2e in that order. This is exactly what CI runs on every change
(FR-047, SC-012), against a freshly seeded environment.

Expected summary:

```text
unit         ok    ids, fingerprint, keys, clock, document bytes, no-wallclock scan
integration  ok    migrations up/down, seed end-to-end, coherence, hierarchy, dates
security     ok    tenant columns, allowlist, cross-tenant refs, RLS, probe,
                   public content, scenario readiness
e2e          ok    clean-checkout → up → seed → verify → determinism (2 runs)
```

Any failure blocks the change. A fingerprint mismatch names the diverging entity families rather than
reporting a single opaque digest difference — see [`contracts/seed-cli.md`](./contracts/seed-cli.md).

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Fingerprint differs only on Windows | CRLF line endings in templates or output | `git config core.autocrlf false`, re-clone, `make reset` |
| `make seed` exits `2` unexpectedly | Environment already seeded | `make reset`, or `make verify` if you meant to check it |
| `verify` reports "environment incomplete" | A previous seed was interrupted | `make reset` |
| `/health/ready` returns 503 on `minio` | Bucket bootstrap has not finished | Wait for the `minio-init` service to exit `0`, then retry |
| Seed exceeds the 10-minute budget | Attendance volume, usually | Confirm the 6-month cap (FR-020a) is applied; use `--profile smoke` for iteration |
| Port already in use | Local PostgreSQL or Redis running | Change the host port in `.env`; container ports are fixed |
