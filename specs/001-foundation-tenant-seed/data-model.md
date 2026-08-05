# Phase 1 Data Model: Foundation — Two-Tenant Deterministic Dataset

**Date**: 2026-08-01 | **Plan**: [plan.md](./plan.md) | **Research**: [research.md](./research.md)

## Conventions applied to every table

| Rule | Detail | Source |
|------|--------|--------|
| Primary key | `id UUID PRIMARY KEY` — UUIDv5, derived per R1, never database-generated | FR-011, R1 |
| Tenancy | `company_id UUID NOT NULL REFERENCES companies(id)` on every table **except** the four global-allowlist tables | FR-009, FR-009a |
| RLS | Every tenant-owned table: `ENABLE` + `FORCE ROW LEVEL SECURITY`, policy `company_id = current_setting('app.company_id', true)::uuid` | Constitution I, R6 |
| Timestamps | `created_at`, `updated_at` — set explicitly from the reference clock, never `now()` | FR-012, R2, R5 |
| Money | `NUMERIC(14,2)` + `currency CHAR(3)`; never floating point | FR-038 |
| Dates | `DATE` for business dates, `TIMESTAMPTZ` for events; all derived from `REFERENCE_DATE` | FR-037, R2 |
| Composite uniqueness | Every table has a natural-key unique constraint matching its ID derivation, so a duplicate is a database error rather than a silent second row | R1 |
| Deletion | No hard deletes in seeded data; nothing in this feature deletes rows | — |

**Classification enum** (FR-010a) — PostgreSQL enum `classification_level`:
`PUBLIC` · `INTERNAL` · `CONFIDENTIAL` · `RESTRICTED`

---

## 1. Global entities (the closed allowlist — FR-009a)

These four have **no** `company_id`. Anything else lacking one is an audit violation, and any of these
*gaining* one is equally a violation (FR-044).

### `permissions`
| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID PK | Derived from `permission:{code}` — no company in the key |
| `code` | TEXT UNIQUE NOT NULL | `documents:read`, `hr:read_self`, `hr:read_team`, `hr:read_all`, `hr:update`, `sales:read`, `finance:read`, `contracts:read`, `documents:upload`, `documents:delete`, `reports:generate`, `users:manage`, `roles:manage`, `actions:approve`, `audit:read`, `communications:draft`, `communications:send` |
| `description` | TEXT NOT NULL | |

Shared identically by both companies (FR-009b). 17 rows.

### `platform_administrators`
| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID PK | |
| `email` | TEXT UNIQUE NOT NULL | |
| `display_name` | TEXT NOT NULL | |
| `is_active` | BOOLEAN NOT NULL | |

Deliberately a separate table from `users` rather than a nullable `company_id` on `users` (FR-009c).
A nullable tenant column on the main user table is precisely the hole every later query would have to
remember to close; a separate table makes "no user is tenant-less" enforceable by `NOT NULL`. 1 row.

### `alembic_version`
Alembic-managed. Excluded from the fingerprint (R5).

### `dataset_manifest`
| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID PK | Singleton row |
| `root_seed` | TEXT NOT NULL | |
| `reference_date` | DATE NOT NULL | `2026-06-30` |
| `generator_version` | TEXT NOT NULL | |
| `entity_counts` | JSONB NOT NULL | Realized per-family counts (FR-016, FR-020b) |
| `family_digests` | JSONB NOT NULL | Per-family digest map (R5) |
| `root_fingerprint` | TEXT NOT NULL | |
| `started_at` | TIMESTAMPTZ NOT NULL | |
| `completed_at` | TIMESTAMPTZ NULL | **Written last.** NULL ⇒ incomplete (FR-014b, R7) |

---

## 2. Organization

### `companies`
`id` · `slug` (UNIQUE: `niletech`, `delta-retail`) · `name` · `domain` · `status` · `reporting_currency` · `created_at`

Self-referential `company_id`: a company row's tenant is itself, keeping the audit rule uniform.

### `offices`
`id` · `company_id` · `code` · `city` · `country` (ISO-2: `EG`, `AE`) · `address` · `is_headquarters`

NileTech: Cairo (HQ), Alexandria, Dubai. Delta Retail: 2 offices. Unique on `(company_id, code)`.

### `departments`
`id` · `company_id` · `name` · `head_user_id` (FK `users`, nullable during load) · `office_id`

NileTech (8): Engineering, HR, Sales, Finance, Legal, Customer Support, Operations, Executive
Management. Delta Retail (5): HR, Sales, Finance, Operations, Executive Management — no Engineering,
no Legal, documented as intentional (FR-022).

`head_user_id` is nullable **only** to break the circular dependency between departments and users
during insertion; a post-load constraint check asserts every department has a head, and the head
belongs to that department (FR-034).

### `roles`
`id` · `company_id` · `name` · `description` — 7 per company: Company Admin, Employee, Manager, HR,
Finance, Legal, Auditor. Unique `(company_id, name)`.

Delta Retail has no Legal *department* but still carries the Legal *role* row, unassigned — role
catalogs stay uniform so later authorization code has no per-tenant special cases.

### `role_permissions`
`role_id` → `roles` · `permission_id` → `permissions` (global) · `company_id` (denormalized for RLS)

The join carries `company_id` even though it is derivable, so RLS applies without a subquery.

### `users`
| Field | Type | Notes |
|-------|------|-------|
| `id` · `company_id` | UUID | |
| `department_id` | UUID NOT NULL | |
| `manager_id` | UUID NULL | NULL only for the single top-level executive (FR-034) |
| `office_id` | UUID NOT NULL | |
| `email` | TEXT | Unique per company |
| `full_name` · `country` · `employment_type` · `is_active` | | `employment_type`: `FULL_TIME`, `PART_TIME`, `CONTRACT` |
| `password_hash` | TEXT NULL | Column exists; unused until D1's auth feature |
| `is_persona` · `persona_key` | BOOLEAN / TEXT NULL | Marks the fixed persona set (FR-025b); `persona_key` unique per company |

**Invariants** (enforced by constraint where possible, by test otherwise):
- Exactly one row per company with `manager_id IS NULL`.
- `manager_id` resolves within the same company — cross-tenant manager is impossible.
- No cycles in the manager chain (verified by recursive CTE in the integrity check).
- `department_id` and `office_id` belong to the same company.

### `user_roles`
`user_id` · `role_id` · `company_id`. Exactly one primary role per user, plus Manager where the user
has direct reports (FR-025a). A check confirms every user with direct reports holds Manager.

### Persona set (FR-025b)
Ten fixed `persona_key` values with stable IDs, documented in `quickstart.md`:

| `persona_key` | Company | Dept | Role | Purpose |
|---|---|---|---|---|
| `employee.engineering` | NileTech | Engineering | Employee | Own leave balance; general policy read |
| `manager.engineering` | NileTech | Engineering | Manager | ≥3 direct reports |
| `employee.sales` | NileTech | Sales | Employee | Out-of-scope target for the Engineering manager |
| `hr.generalist` | NileTech | HR | HR | Company-wide HR access; payroll |
| `finance.analyst` | NileTech | Finance | Finance | Financial reads |
| `legal.counsel` | NileTech | Legal | Legal | Explicit ACL on the restricted contract pair |
| `auditor.readonly` | NileTech | Operations | Auditor | Audit-log reads |
| `admin.company` | NileTech | Executive Management | Company Admin | User/role management |
| `comms.sender` | NileTech | Customer Support | Employee | Holds `communications:send` |
| `employee.delta` | Delta Retail | Sales | Employee | Cross-tenant probe origin |

---

## 3. HR

### `employee_profiles`
`id` · `company_id` · `user_id` (UNIQUE) · `job_title` · `salary_band` · `salary_amount` · `currency` ·
`hire_date` · `employment_type`

`salary_amount` is the payload behind the blueprint's "another employee's salary → deny" test.
Classification `RESTRICTED` at the document level; the column itself is protected by RLS plus the
authorization work in the next feature.

### `leave_balances`
`id` · `company_id` · `user_id` · `leave_type` · `year` · `entitlement_days` · `used_days` ·
`remaining_days`

**Coherence rule (FR-035)**: `entitlement_days` must equal the value stated in that company's leave
policy document for the user's `country` and `employment_type`. A dedicated coherence test asserts
this across all users — this is the check that keeps the "21 days" answer consistent between the
policy PDF and the HR record.

`remaining_days = entitlement_days - used_days` enforced by a check constraint.

### `leave_requests`
`id` · `company_id` · `user_id` · `approver_id` · `leave_type` · `start_date` · `end_date` · `status`
(`PENDING`/`APPROVED`/`REJECTED`/`CANCELLED`) · `days_count` · `submitted_at`

Invariants: `end_date >= start_date`; `start_date >= user.hire_date` (FR-037); approver is the user's
manager and in the same company; dates within the 24-month window.

### `attendance_records`
`id` · `company_id` · `user_id` · `work_date` · `status` (`PRESENT`/`REMOTE`/`LEAVE`/`HOLIDAY`) ·
`hours_worked`

Unique `(user_id, work_date)`. Restricted to 2026-01-01 → 2026-06-30 (FR-020a). Weekend and public
holiday patterns come from a committed per-country table (`EG`/`AE` weekend = Fri–Sat), so no
impossible working days are generated and no external calendar service is consulted.

### `training_records`
`id` · `company_id` · `user_id` · `course_name` · `provider` · `completed_on` · `outcome` · `score`

### `performance_reviews`
`id` · `company_id` · `user_id` · `reviewer_id` · `period_start` · `period_end` · `rating` (1–5) ·
`summary`

Reviewer must be the user's manager, same company. 4 semi-annual cycles across the window.

---

## 4. Sales & Finance

### `customers`
`id` · `company_id` · `name` · `region` · `country` · `account_owner_id` (a Sales user) · `since_date`

Never shared between companies (FR-024a) — the generator uses disjoint name pools per tenant.

### `products`
`id` · `company_id` · `sku` · `name` · `tier` · `unit_price` · `currency` · `is_active`

Unique `(company_id, sku)`. NileTech ≈ 25 software/service SKUs; Delta Retail ≈ 80 retail SKUs.

### `orders` / `order_lines`
**orders**: `id` · `company_id` · `customer_id` · `sales_rep_id` · `order_date` · `region` ·
`status` · `subtotal` · `tax` · `total` · `currency`

**order_lines**: `id` · `company_id` · `order_id` · `product_id` · `quantity` · `unit_price` ·
`line_total`

Invariants: order, customer, rep, and product all share one `company_id`; `line_total = quantity ×
unit_price`; `subtotal = Σ line_total`; `total = subtotal + tax` — all exact at `NUMERIC(14,2)`
(FR-038). `order_date` ≥ `customer.since_date` (FR-037).

Volumes follow a deterministic seasonal curve with per-rep variation (FR-020c), so June-vs-May and
year-over-year questions have a genuine trend rather than noise.

### `invoices`
`id` · `company_id` · `order_id` (UNIQUE) · `invoice_number` · `issue_date` · `due_date` ·
`amount` · `currency` · `status`

`amount` must equal `orders.total` — asserted by the coherence check, not merely by convention.

### `sales_targets`
`id` · `company_id` · `sales_rep_id` · `period_start` · `period_end` · `region` · `target_amount` · `currency`

### `expenses`
`id` · `company_id` · `department_id` · `category` · `expense_date` · `amount` · `currency` ·
`submitted_by_id` · `status`

### `budgets`
`id` · `company_id` · `department_id` · `period_start` · `period_end` · `allocated_amount` · `currency`

Unique `(company_id, department_id, period_start)`.

### `monthly_revenue` (materialized aggregate)
`id` · `company_id` · `year_month` · `region` · `revenue_amount` · `currency` · `order_count`

Recomputed from orders at seed time. Included so the blueprint's SQL-agent scenario has a fast,
pre-aggregated path, and so the coherence check can prove aggregate equals detail.

---

## 5. Legal & Documents

### `documents`
| Field | Type | Notes |
|-------|------|-------|
| `id` · `company_id` | UUID | |
| `department_id` | UUID NULL | Governing department |
| `owner_id` | UUID NOT NULL | Exactly one owner, same company (FR-031a) |
| `title` · `document_type` | TEXT | `POLICY`, `CONTRACT`, `NDA`, `AGREEMENT`, `TEMPLATE`, `REPORT`, `PUBLIC` |
| `storage_key` | TEXT UNIQUE NOT NULL | `{company_slug}/{classification}/{document_type}/{slug}.md` (FR-039) |
| `classification` | `classification_level` NOT NULL | One of four (FR-010b) |
| `country` | CHAR(2) NULL | For country-scoped policies |
| `content_sha256` | TEXT NOT NULL | Byte digest of the stored file (FR-032) |
| `byte_size` | INTEGER NOT NULL | |

**Ownership convention** (FR-031a): policy → head of the governing department; contract → a Legal user,
or the Executive Management head where the company has no Legal department (Delta Retail); departmental
report/expense → that department's head; public content → head of Executive Management;
employee-specific → the employee concerned.

### `document_acl`
`id` · `company_id` · `document_id` · `principal_type` (`USER`/`ROLE`/`DEPARTMENT`) · `principal_id` ·
`permission` (`READ`/`WRITE`)

Carries the explicit grants that satisfy the resource-ACL layer. The `legal.counsel` persona receives
explicit `READ` on both contracts of the comparison pair (FR-028a).

### `contracts`
`id` · `company_id` · `document_id` · `counterparty_name` · `contract_type` · `effective_date` ·
`expiry_date` · `notice_period_days` · `liability_cap_amount` (NULL = uncapped) · `payment_terms` ·
`governing_law`

**The comparison pair (FR-028a)** — two NileTech customer contracts, both `CONFIDENTIAL`, both
ACL-granted to `legal.counsel`, deliberately differing so the blueprint's contract-comparison demo has
a verifiable answer:

| | Contract A | Contract B |
|---|---|---|
| `notice_period_days` | 30 | 90 |
| `liability_cap_amount` | 50,000 | NULL (uncapped) |
| `payment_terms` | NET_30 | NET_30 (deliberately identical) |

### `policy_documents`
`id` · `company_id` · `document_id` · `policy_type` · `version` · `effective_date` ·
`stated_values` (JSONB)

`stated_values` holds the machine-readable form of what the prose asserts — e.g.
`{"annual_leave_days": {"EG": 21, "AE": 22}}`. This is what makes FR-035's coherence check mechanical:
the test compares `stated_values` against `leave_balances` rather than parsing English.

8 policy types per company: handbook, leave, remote work, expense, security, code of conduct, travel,
benefits.

---

## 6. Public content (all `classification = PUBLIC`)

### `services` · `public_products` · `leadership_profiles` · `news_items` · `vacancies`

- **services**: `id` · `company_id` · `name` · `summary` · `description` · `display_order`
- **public_products**: `id` · `company_id` · `name` · `tagline` · `description` · `display_order` — separate from `products` (see spec terminology); marketing content, not the sellable catalog
- **leadership_profiles**: `id` · `company_id` · `user_id` (FK, must be an Executive Management member) · `public_title` · `bio` · `photo_key` — exposes only public-appropriate fields; no salary, no personal contact (FR-030, SC-011)
- **news_items**: `id` · `company_id` · `headline` · `body` · `published_on` (within the window)
- **vacancies**: `id` · `company_id` · `department_id` · `office_id` · `title` · `description` · `posted_on` · `is_open`

A `PUBLIC`-content leakage test scans every row of these five tables for salary figures, contract
terms, internal financial values, and non-executive contact details (SC-011).

---

## 7. Platform

### `audit_logs`
`id` · `company_id` · `actor_user_id` NULL · `actor_type` (`USER`/`SYSTEM`/`SEED`) · `action` ·
`resource_type` · `resource_id` · `decision` (`ALLOW`/`DENY`/`NA`) · `reason` · `sources` (JSONB) ·
`created_at`

Append-only: a trigger rejects `UPDATE` and `DELETE`. The seed writes `SEED` entries for the dataset
it creates and the reset it performs (FR-043).

### `job_records`
`id` · `company_id` · `job_name` · `status` · `scheduled_for` · `started_at` · `finished_at` ·
`error` — carries the tenant of the work performed (FR-042).

---

## Relationship summary

```text
companies ─┬─ offices ─── departments ─── users ─┬─ employee_profiles
           │                    ▲   └──manager_id─┘
           │                    │            ├─ leave_balances / leave_requests
           │                    │            ├─ attendance_records
           │                    │            ├─ training_records
           │                    │            └─ performance_reviews
           ├─ roles ── role_permissions ──► permissions (GLOBAL)
           ├─ customers ─── orders ─── order_lines ──► products
           │                   └─ invoices
           ├─ sales_targets · expenses · budgets · monthly_revenue
           ├─ documents ─┬─ document_acl
           │             ├─ contracts
           │             └─ policy_documents
           ├─ services · public_products · leadership_profiles · news_items · vacancies
           └─ audit_logs · job_records

GLOBAL (no company_id): permissions · platform_administrators · alembic_version · dataset_manifest
```

## Validation checks derived from this model

| Check | Requirement | Where |
|-------|-------------|-------|
| Every non-allowlisted table has non-nullable `company_id` | FR-009, FR-009a | `tests/security/test_tenant_columns.py` |
| No FK crosses tenants | FR-024, FR-024a | `tests/security/test_cross_tenant_refs.py` |
| RLS blocks the other tenant; unset GUC returns zero rows | Constitution I, R6 | `tests/security/test_rls.py` |
| Exactly one manager-less user per company; no cycles | FR-034 | `tests/integration/test_org_hierarchy.py` |
| `leave_balances.entitlement_days` = policy `stated_values` | FR-035 | `tests/integration/test_coherence.py` |
| `invoice.amount` = `order.total` = Σ `line_total` | FR-038 | `tests/integration/test_coherence.py` |
| `monthly_revenue` equals aggregation of `orders` | FR-038 | `tests/integration/test_coherence.py` |
| No child predates its parent | FR-037 | `tests/integration/test_date_windows.py` |
| Public content contains no sensitive values | SC-011 | `tests/security/test_public_content.py` |
| All 8 blueprint scenarios have their records | FR-047a, SC-013 | `tests/security/test_scenario_readiness.py` |
| Fingerprint is stable across two clean runs | FR-011, SC-002 | `tests/e2e/test_determinism.py` |
