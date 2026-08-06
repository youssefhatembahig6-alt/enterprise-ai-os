# Contract: Authorization Policy Engine

**Package**: `eaios_core.authz` | **Feature**: `003-auth-portal-shell`

The deterministic decision point Constitution Principle II (NON-NEGOTIABLE) requires. This
document is the contract; `specs/003-auth-portal-shell/data-model.md` §3 carries the type
shapes.

---

## 1. The one entry point

```python
def evaluate(
    subject: AccessContext,
    action: Action,
    resource: ResourceDescriptor,
) -> Decision: ...
```

**Pure.** No database, no cache, no HTTP, no clock, no randomness, no environment. Given
the same three arguments it returns the same `Decision` on every machine, every run. The
module imports nothing from `apps/`, `services/`, or `scripts/` — enforced by
`tests/unit/test_dependency_direction.py`, which walks the AST rather than grepping.

**No model may call it, influence it, or be called by it.** This feature introduces no
model at all; the boundary is stated now so it exists before one arrives (FR-012).

---

## 2. Guarantees

| # | Guarantee | Proven by |
|---|-----------|-----------|
| G1 | Layers evaluate in the order tenant → RBAC → ABAC → ACL → classification, and the first refusal short-circuits | A parametrised test constructs a descriptor failing *several* layers at once and asserts the reported `layer` and `reason` are the earliest one |
| G2 | A missing required attribute denies | Each nullable attribute dropped in turn from an otherwise-allowing descriptor; every one must yield `CONTEXT_INCOMPLETE` |
| G3 | Permission codes only, never role names | A test asserts the engine module's AST contains no read of `subject.role_names` |
| G4 | A layer-1 refusal is reported as absence, not denial | `Decision.tenant_absent` is true only when layer 1 fired, and the router maps it to 404 (FR-021, FR-030) |
| G5 | `audit_required` is computed in one place | `sensitivity.is_sensitive` is the only definition; a test asserts no router computes it independently |
| G6 | The same inputs give the same answer | Repeated evaluation over a fixed matrix of subjects × resources produces byte-identical decisions |

---

## 3. Required permission codes

The `(ResourceKind, Action) → permission code` table, in one module (`authz.rules`) so it
is reviewable as a unit. Codes come from the seeded catalog
(`scripts/seed/src/eaios_seed/generators/organization.py:39`) — the engine invents none.

| Resource kind | Action | Required code | Additional condition (layer 3) |
|---------------|--------|---------------|-------------------------------|
| `HR_PROFILE` (self) | `READ` | `hr:read_self` | `resource.owner_id == subject.user_id` |
| `HR_PROFILE` (report) | `READ` | `hr:read_team` | `subject.manages(resource.owner_id)` |
| `HR_PROFILE` (any) | `READ` | `hr:read_all` | none |
| `HR_COMPENSATION` | `READ` | `hr:read_all` | none |
| `DIRECT_REPORTS` | `READ` | `hr:read_team` | none |
| `ACCESS_CONTEXT` | `READ` | — | `resource.owner_id == subject.user_id` |
| `SESSION` | `READ` | — | `resource.owner_id == subject.user_id` |
| `AUDIT_LOG` | `READ` | `audit:read` | none |

The three `HR_PROFILE` rows are alternatives evaluated in that order: the first whose code
the caller holds *and* whose condition passes decides. Holding none of them denies with
`PERMISSION_MISSING`; holding a code but failing its condition denies with
`NOT_IN_REPORTING_LINE`. The two are separate reason codes because they answer different
questions for whoever reads the audit trail.

**Compensation is `hr:read_all`, not `hr:read_team`.** That is FR-025: a manager reading
their own direct report is refused. It is the blueprint's flagship denial and it is a rule
here, not an omission from a response model.

---

## 4. The caller's obligations

The engine cannot enforce these — they are the API layer's part of the contract, and each
is checked by a test that would fail if the layer skipped it.

1. **Build the descriptor from access attributes only.** A `ResourceDescriptor` is
   populated by a query selecting `company_id`, `owner_id`, `department_id`,
   `manager_id`, and `classification`. It must never be populated by a query that also
   selects a protected payload column — that would read the data before deciding
   (FR-015).
2. **Do not read the payload before `Decision.allowed`.** The recorded-SQL harness asserts
   this in both directions: nothing on the denied path, and the expected statement on the
   allowed path.
3. **Map the decision to a status without reinterpreting it.** `tenant_absent` → 404,
   any other denial → 403, allow → 200. The router chooses no status of its own.
4. **Write the audit entry when `audit_required`.** With actor, tenant, action, resource
   type and id, decision, `reason`, and timestamp — and with no credential or token
   (FR-017, FR-018).
5. **Bind `app.company_id` from `subject.company_id`** before any tenant-owned query, and
   from nothing else (FR-010, research R13).

---

## 5. Declared for feature 004, unimplemented here

Present so the boundary does not need redesign, and unimplemented so nothing claims a
capability it does not have:

- `authz.filters.qdrant_filter(subject) -> Mapping[str, object]` — the payload filter
  (`company_id`, `department_id`, `country`, `classification`, `allowed_roles`,
  `owner_id`) Principle III requires at search time. Unit-tested against an access context;
  **no Qdrant client is imported and no search runs** — the collections hold nothing
  (feature 001 decision D2).
- `AccessContext.permission_fingerprint` — the cache-key component
  `eaios_core.keys.cache_key` has required since feature 001 and nothing has ever produced.
- `ResourceDescriptor.classification` and `.acl_grants` — the two fields a document
  decision needs, already carried and already evaluated by layers 4 and 5.

**Not declared**: tool contracts (Principle VI). A tool declaration includes an approval
classification, and this feature has no write path to classify. Inventing the declaration
before the first tool exists would produce a shape fitted to nothing.
