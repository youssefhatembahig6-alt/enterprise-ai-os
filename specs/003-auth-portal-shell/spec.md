# Feature Specification: Authentication, Request-Time Authorization, and Employee Portal Shell

**Feature Branch**: `003-auth-portal-shell`

**Created**: 2026-08-05

**Status**: Complete

**Evidence**: CI run [31443872819](https://github.com/youssefhatembahig6-alt/enterprise-ai-os/actions/runs/31443872819) at commit `429fdcba8b22d10e356874f0fff1995a83a36145` — API conclusion `success`, 7/7 jobs green, 86 successful steps, 3 conditional log-dump skips, 0 failures. All 121 tasks and the requirements checklist are closed. FR-037 and SC-012 are met by the `Authentication and authorization` step (128 passed), which is proven to gate the job. See [verification.md](verification.md).

**Input**: User description: "Build Feature 003: Authentication, Request-Time Authorization, and Employee Portal Shell. Implement FastAPI-issued JWT authentication for NileTech and Delta Retail synthetic users. Replace the /portal holding page with a secure login flow and authenticated portal shell. For every protected request, verify token signature, issuer, audience, expiry, active-user status, and tenant membership. Build an immutable server-side access context containing company, user, department, office, country, employment type, manager relationships, roles, and permission codes. Never trust tenant, identity, role, or permission values supplied by request parameters, headers, or bodies. Implement deterministic authorization in this order: tenant boundary, RBAC, ABAC, resource ACL, and classification. Authorization must happen before database reads, document access, vector retrieval, cache reads, or tool execution. Return 401 for missing or invalid identity and 403 for authenticated authorization denials. Audit every allow and denial without recording passwords or tokens. Provide protected current-user and access-context endpoints plus one complete self-service vertical slice: viewing the authenticated employee's own HR profile. Prove manager access to direct reports, denial for unrelated employees, and zero cross-tenant access. The portal must provide login, logout, session expiry, role-aware navigation, responsive accessibility, and designed loading, empty, error, unauthenticated, and access-denied states. Keep the public website, health endpoints, and dataset manifest anonymous. Out of scope: ingestion, chunking, embeddings, Qdrant population, RAG, chat streaming, agents, write actions, and approval workflows. Carry these into Feature 004."

This feature discharges **decision D1**, deferred by feature 001 and named as out of scope by
feature 002. It is the first feature in which the system *enforces* access rather than structuring
data so that access can later be enforced.

## Clarifications

### Session 2026-08-05

Two conflicts between existing governing documents surfaced while writing this specification. Both
are resolved here rather than left for implementation to discover.

- **Constitution Principle II versus spec 001 FR-043a.** Principle II states "Every denial MUST return 403". Spec 001 FR-043a states that a request for another company's resource MUST be answered as not found, never as forbidden. Resolved by FR-030: the tenant boundary is **layer 1 of Principle II's own ordering**, applied before authorization is consulted, so a cross-tenant resource is not *denied* — it is absent. 403 governs layers 2 through 5, which is exactly the distinction the feature brief draws between missing identity (401), authenticated denial (403), and the tenant boundary.
- **Spec 002 FR-048 versus a sign-in form.** FR-048 states the public site "MUST NOT require, accept, or store any visitor credential". Resolved by FR-006: the sign-in surface lives at the reserved portal address, which spec 002 FR-001a already classifies as a *non-content route* outside the public site. The eight public content pages stay credential-free and the check enforcing FR-048 must continue to pass unchanged.

The questions below were raised by `/speckit-clarify` against this specification.

- Q: What must bound repeated sign-in attempts? → A: Both per-account and per-address failure limits, with a temporary lockout. Per-account stops credential stuffing from many addresses; per-address stops spraying across many accounts. The refusal must not reveal which bound was reached.
- Q: How are credentials established, given `users.password_hash` is NULL for all seeded users and `users` is fingerprinted? → A: A separate post-seed provisioning step. The fingerprint is computed from the in-process generated rows, not from the database, so a post-seed write does not move it.
- Q: What makes FR-007's sign-out actually end access? → A: Server-side session records, checked on every protected request. A self-contained credential cannot be withdrawn, so without server state sign-out only deletes the client's copy.
- Q: FR-017 audits every allow and deny; what stops ordinary browsing drowning the trail? → A: Every **denial** is always audited. **Allows** are audited for sensitive resources only, with the sensitive set enumerated in the spec so the rule is testable.
- Q: FR-005 requires expiry but names no duration; what are the numbers? → A: **30 minutes idle** and an **8-hour absolute cap** from sign-in. Two bounds because they cover different risks — an unattended desk, and how long a stolen credential stays useful.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - An Employee Signs In And Sees Their Own Record (Priority: P1)

A NileTech employee opens the portal address, signs in, and reaches a portal that greets them by
name and shows their own HR profile — department, office, manager, employment type, and leave
balance. They sign out and the session ends.

**Why this priority**: This is the vertical slice proving the whole chain: credentials become a
verified identity, identity becomes a server-built access context, and that context governs a real
data read. Every other story depends on it; none can be demonstrated without it.

**Independent Test**: Sign in as a known seeded employee, confirm the portal shows that person's
own profile and nobody else's, sign out, and confirm protected addresses are no longer reachable.

**Acceptance Scenarios**:

1. **Given** valid credentials for an active seeded employee, **When** they sign in, **Then** they reach the portal and see their own name, department, office, and manager.
2. **Given** an authenticated employee, **When** they request their own HR profile, **Then** it returns the fields their permissions allow and no others.
3. **Given** an authenticated employee, **When** they sign out, **Then** the session ends and any subsequent protected request is refused as unauthenticated.
4. **Given** invalid credentials, **When** they are submitted, **Then** sign-in fails with a message that does not reveal whether the account exists.
5. **Given** an expired session, **When** the employee acts, **Then** they are told the session expired and returned to sign-in, rather than shown a generic failure.

---

### User Story 2 - A Manager Sees Their Team And No One Else (Priority: P2)

A manager signs in and can read the HR profiles of the people who report to them. Requesting the
profile of an employee outside their reporting line is refused, and the refusal is recorded.

**Why this priority**: The first requirement that identity alone cannot satisfy — it needs the
manager relationship, an attribute-based decision. It is also the blueprint's flagship
demonstration: the same request succeeds or fails depending on who asks.

**Independent Test**: Sign in as a seeded manager, read a direct report's profile, request an
unrelated employee's profile and confirm refusal, then check the audit trail holds both events.

**Acceptance Scenarios**:

1. **Given** an authenticated manager, **When** they request a direct report's HR profile, **Then** it is returned.
2. **Given** an authenticated manager, **When** they request the profile of an employee in another department who does not report to them, **Then** the request is refused as forbidden.
3. **Given** an authenticated employee with no direct reports, **When** they request a colleague's profile, **Then** the request is refused as forbidden.
4. **Given** any of the above, **When** the audit trail is inspected, **Then** both the allow and the denial appear with actor, tenant, resource, decision, and reason — the allow qualifies because a direct report's HR record belongs to someone other than the requester (FR-017a).
5. **Given** a manager whose reporting line differs in the dataset, **When** they sign in, **Then** their reachable set differs accordingly with no code or role change.

---

### User Story 3 - A Delta Retail User Cannot Reach NileTech Data (Priority: P3)

A user of the second tenant signs in to the same system and reaches only their own company's
records. No address, parameter, or token manipulation returns anything belonging to the other
tenant.

**Why this priority**: Tenant isolation is the constitution's first principle and the project's
central claim. Features 001 and 002 established it structurally and for anonymous callers; this is
the first time an *authenticated* caller could attempt to cross it.

**Independent Test**: Sign in as a Delta Retail user, attempt to read a NileTech record by its
identifier, and confirm the response is indistinguishable from that record not existing.

**Acceptance Scenarios**:

1. **Given** an authenticated Delta Retail user, **When** they request a NileTech record by identifier, **Then** the response reports it as not found, not as forbidden.
2. **Given** an authenticated user, **When** they supply a company identifier in a parameter, header, or body, **Then** it is ignored entirely and the tenant from their verified identity is used.
3. **Given** a session credential issued for one tenant, **When** it is presented to an address serving the other, **Then** the request is refused and the attempt is recorded.
4. **Given** any authenticated session, **When** the audit trail is inspected, **Then** every entry carries the company of the acting user.

---

### User Story 4 - Navigation Shows Only What The User Can Use (Priority: P4)

Signed in, a user sees navigation entries only for areas their permissions allow. An administrator
sees the administration area; an ordinary employee does not see it at all, rather than seeing it
and being refused on arrival.

**Why this priority**: The constitution requires role-aware navigation explicitly — "a user never
sees an entry point to something they cannot use." It is also the difference between a portal that
feels designed and one that feels like a permissions error surface.

**Independent Test**: Sign in as users with different role sets and compare the visible navigation
against each user's permission codes.

**Acceptance Scenarios**:

1. **Given** a user without a permission, **When** the portal renders, **Then** no navigation entry for that area appears in the page at all.
2. **Given** a user with a permission, **When** the portal renders, **Then** the corresponding entry is present and reachable.
3. **Given** a user who reaches a forbidden address directly, **When** the page renders, **Then** they see a designed access-denied state explaining that they lack access — never a blank screen or a raw error.
4. **Given** navigation is hidden for a user, **When** they request that address directly, **Then** the server refuses it regardless of what the interface showed.

---

### Edge Cases

- **A token that is well-formed but not ours**: signed by a different key, or carrying a different issuer or audience, must be refused as unauthenticated even if every other claim looks correct.
- **A token for a user since deactivated**: valid by signature and expiry, presented by a user no longer active, must be refused — active status is checked per request, not at issue time.
- **A token for a user whose department or manager has changed**: authorization uses the current record, not the state captured when the credential was issued.
- **Session expiry mid-task**: the interface must say the session expired rather than showing a generic failure, and must not silently discard the user's place.
- **A session kept alive by continuous use**: activity renews the idle timeout but never extends past the 8-hour cap, at which point the user signs in again.
- **Clock skew**: a credential marginally outside the accepted window must fail closed, not open.
- **Sustained sign-in attempts**: repeated failures against one account, or across many accounts from one address, must be bounded rather than allowed to continue indefinitely. A legitimate user who mistypes a few times must not be locked out for long, and an attacker must not be able to lock out a real user at will.
- **Missing credentials versus wrong credentials**: both refused, and the refusal must not distinguish them — a message revealing which accounts exist is an enumeration surface.
- **A permission granted through two roles**: removing one role must not remove the permission while another still grants it.
- **A user with no roles at all**: must still sign in, reach their own record, and see a portal that explains the absence rather than an empty page.
- **A resource in the other tenant with the same identifier shape**: reported as not found, exactly as an identifier belonging to nobody would be.
- **Sign-in attempted from the public site**: the public pages carry no credential field (spec 002 FR-048); the sign-in surface is the portal address and nothing else.
- **A read that is authorized but not audited**: a user loading their own profile writes no audit entry by design (FR-017a). A denial in the same session writes one. The absence of an allow entry must never be mistaken for the read not happening.
- **Authorization consulted after a read**: any path that reads a record and then decides whether the caller may have it is a defect, even when the answer is the same.

## Requirements *(mandatory)*

### Functional Requirements

**Identity and sessions**

- **FR-001**: The system MUST authenticate a user against credentials held for the seeded synthetic users of **both** tenants, and MUST issue a session credential on success.
- **FR-002**: Stored credentials MUST NOT be recoverable from what is stored. A stored value that can be reversed to the original credential is a defect regardless of how the storage is described.
- **FR-002a**: Credentials MUST be established by a **step separate from the generator**, run after seeding. The generator MUST continue to leave `password_hash` unset, as it does today for all 240 seeded users.

  This preserves determinism without weakening anything. The dataset fingerprint is computed from the **in-process generated rows**, not from the database, so a credential written after seeding does not move it — the committed value stays valid and no fingerprint exclusion is needed. Generating hashes inside the seed would instead require a fixed salt, weakening the hash by construction *and* invalidating the pinned fingerprint.

  The provisioning step MUST be idempotent, MUST NOT write credentials to logs or audit entries (FR-018), and MUST NOT commit any credential in plain text. It MUST be re-runnable after a reset, since a reset restores the generated dataset with `password_hash` unset again.
- **FR-003**: Every protected request MUST verify, before anything else: the session credential's signature, its issuer, its audience, its expiry, that the identified user is **currently active**, and that the user belongs to the tenant the request is served for. Failure of any check MUST be refused as unauthenticated.
- **FR-004**: Active status and tenant membership MUST be evaluated **per request** against current records, not read from the credential's contents. A user deactivated after sign-in MUST lose access on their next request.
- **FR-005**: A session MUST expire after **30 minutes without activity** and, regardless of activity, no later than **8 hours after sign-in**. Both bounds are required and they cover different risks: the idle timeout protects a machine left unattended, and the absolute cap limits how long a stolen credential remains useful — without it, a credential taken from an active session can be kept alive indefinitely simply by using it. Expiry MUST be enforced by the **server**; an interface that hides an expired session without the server refusing it does not satisfy this requirement. The numbers are stated because "MUST expire" is not testable.
- **FR-006**: The sign-in surface MUST live at the reserved portal address (spec 002 FR-049a), not on the public website. Spec 002 FR-048's prohibition on the public site accepting credentials remains in force and its check MUST continue to pass.
- **FR-007**: Signing out MUST end the session such that the previous credential no longer grants access. This MUST be enforced by **server-side session state consulted on every protected request** — a self-contained credential cannot be withdrawn, so without server state "sign out" would only delete the client's copy while the credential stayed valid until expiry, and FR-007 would be false as written. The cost is small because the check already exists: FR-004 requires active status and tenant membership to be read from current records on every request, so session validity joins a lookup that is happening regardless.
- **FR-007a**: Failed sign-in attempts MUST be bounded **both per account and per client address**, and a bound that is reached MUST temporarily refuse further attempts for that account or address. Both dimensions are required: an address-only bound is defeated by distributing attempts across addresses, which is the ordinary shape of credential stuffing, and an account-only bound lets an attacker lock a real user out by failing deliberately against their account. A successful sign-in MUST reset the account's failure count. The refusal MUST NOT reveal which bound was reached, whether the account exists, or how many attempts remain — each of those is an enumeration signal (FR-022). Bound values MUST be stated as numbers so they are testable, and every lockout MUST be audited.

**The access context**

- **FR-008**: For every protected request the system MUST build a server-side **access context** from verified identity only, containing at minimum: company, user identity, department, office, country, employment type, manager relationships in **both** directions (who they report to, and who reports to them), role assignments, and permission codes.
- **FR-009**: The access context MUST be **immutable** once built. Nothing downstream may add a permission, change the tenant, or widen the scope of a request in progress.
- **FR-010**: The system MUST NOT accept a tenant, identity, role, or permission value from any request parameter, header, cookie, or body. Such a value MUST be ignored, and the attempt SHOULD be recorded. This is absolute because a single trusted field is the entire boundary.
- **FR-011**: The access context MUST be inspectable through a protected endpoint, so what the server believes about a caller is observable rather than inferred.

**Authorization**

- **FR-012**: Authorization MUST be decided by deterministic code. No language model may make, influence, soften, or override an authorization decision (Constitution Principle II, NON-NEGOTIABLE). This feature introduces no model; the requirement is stated so the boundary exists before one arrives.
- **FR-013**: Authorization MUST evaluate in this fixed order: **(1) tenant boundary, (2) role-based permission codes, (3) attribute conditions, (4) resource-level access control, (5) classification**. An earlier layer's refusal MUST short-circuit the rest.
- **FR-014**: Code MUST check **permission codes**, never role names. A check written against a role name is a defect even when it produces the correct answer, because it breaks the moment roles are recomposed.
- **FR-015**: Authorization MUST be applied **before** any data is read — before database queries, document retrieval, vector search, cache reads, or tool execution. Retrieving a record and then deciding whether the caller may have it is prohibited, and MUST be detectable by inspecting the request path rather than only the outcome.
- **FR-016**: Cache reads and writes MUST be scoped so a value computed for one user or permission set can never be served to another.
- **FR-017**: Every authorization **denial** MUST write an audit entry carrying actor, tenant, action, resource type and identifier, decision, reason, and timestamp (Constitution Principle X). There is no exemption and no coalescing for denials — they are the security signal.
- **FR-017a**: Authorization **allows** MUST be audited when the resource is **sensitive**, and MUST NOT be audited otherwise. The sensitive set is enumerated here so the rule is testable rather than decided at each call site:
  - any HR record belonging to **someone other than the requesting user**;
  - compensation detail of any kind, including the requester's own;
  - any record classified above the ordinary level;
  - any read of the audit log itself.
  A user reading their **own** non-compensation profile is not audited. The reasoning is the one feature 002 learned the hard way: auditing every read makes a single page view write dozens of rows and buries the entries an auditor actually needs. Principle X's purpose is answering "who saw this?" — a question about sensitive material, not about someone loading their own name.
- **FR-017b**: The enumerated sensitive set MUST be defined in one place and consulted by the authorization decision, not restated at call sites. Adding a resource type MUST be a change to that definition.
- **FR-018**: Audit entries MUST NOT contain credentials, session tokens, or any value from which either could be reconstructed.

**Responses**

- **FR-019**: A request with missing, malformed, expired, or otherwise invalid identity MUST be refused as **unauthenticated**.
- **FR-020**: A request from a verified identity that fails authorization layers 2 through 5 MUST be refused as **forbidden**.
- **FR-021**: A request for a resource belonging to **another tenant** MUST be answered as **not found**, never as forbidden — see FR-030 for why this is not an exception to FR-020.
- **FR-022**: No refusal may disclose internal detail: no stack traces, no query text, no internal identifiers, no indication of whether a resource exists in another tenant, and no distinction between "no such account" and "wrong credentials".

**The vertical slice**

- **FR-023**: An authenticated employee MUST be able to read **their own HR profile**, including at minimum department, office, manager, employment type, and leave balance.
- **FR-024**: A user holding a team-scoped permission MUST be able to read the HR profiles of their **direct reports**, and MUST be refused for employees outside their reporting line.
- **FR-025**: Salary and other compensation detail MUST NOT be readable by a user lacking the permission for it — including a manager reading their own direct report — unless that permission is separately granted. This is the blueprint's flagship denial and MUST be demonstrable.
- **FR-026**: The set of records a user can reach MUST follow from the dataset's relationships, not from anything hard-coded. Changing a reporting line in the data MUST change the reachable set with no code change.

**The portal**

- **FR-027**: The portal MUST provide sign-in, sign-out, and a session-expiry experience, and MUST replace the "sign-in not yet available" page at the reserved address **without changing that address** (spec 002 FR-049a).
- **FR-028**: Navigation MUST be **role-aware**: an entry point to an area the user cannot use MUST NOT be rendered at all. Hiding navigation is a presentation concern and MUST NOT be the only control — the server MUST refuse the address regardless of what was shown (FR-020).
- **FR-029**: Every portal surface MUST implement responsive layout, accessibility, and designed **loading, empty, error, unauthenticated, and access-denied** states. Access-denied MUST be a designed, informative state — never a blank screen, a silent omission, or a raw error (Constitution: Frontend completeness).
- **FR-030**: The tenant boundary is **layer 1 of FR-013**, evaluated before authorization is consulted. A resource in another tenant is therefore **absent**, not denied — which is why FR-021 requires not-found while FR-020 requires forbidden. Constitution Principle II's "every denial returns 403" governs layers 2 through 5; spec 001 FR-043a governs layer 1. Both hold, and the audit entry records the true reason either way.

**Preserving what already works**

- **FR-031**: The public website, the health endpoints, and the dataset manifest MUST remain reachable **anonymously**. Every existing check asserting this MUST continue to pass unchanged.
- **FR-032**: The anonymous refusal behaviour established by spec 002 (FR-047, FR-047a, FR-047b) MUST continue to hold for callers with no identity.

**Verification**

- **FR-033**: An automated check MUST prove a manager can read a direct report and cannot read an unrelated employee, using **seeded users** rather than fixtures invented for the test.
- **FR-034**: An automated check MUST prove **zero** cross-tenant access for an authenticated caller, across every store the system reads at request time.
- **FR-035**: An automated check MUST prove that supplying a tenant, role, or permission value in a request parameter, header, or body changes nothing about what is returned.
- **FR-036**: An automated check MUST prove that authorization precedes retrieval — that a denied request performs **no read** of the protected data. A check that only inspects the response cannot establish this.
- **FR-037**: The authorization checks MUST run in continuous integration and MUST block the change on failure. Unauthorized information leakage MUST measure **zero** (Constitution Principle VIII).
- **FR-038**: Tests for tenant isolation and authorization MUST be written **before** their implementation, per Constitution Principle VIII's strict cycle for these areas.

### Key Entities

- **User** *(existing)*: A seeded person who can sign in. Carries active status, tenant, department, office, country, employment type, and manager. This feature adds the ability to authenticate as one; it does not change the generated data.
- **Credential** *(new)*: The stored, non-recoverable verifier for a user's sign-in. Never returned by any endpoint, never logged, never audited.
- **Session** *(new)*: A time-bounded grant of access to one user, issued at sign-in and ended by sign-out or expiry. Held as **server-side state** so ending it is real (FR-007), carrying at minimum the user, the tenant, when it was issued, when it expires, and whether it has been ended. Never contains the credential.
- **Access Context** *(new, request-scoped)*: The immutable server-built description of who is asking — company, identity, department, office, country, employment type, manager relationships, roles, permissions. Lives for one request and is never persisted.
- **Role**, **Permission**, **Role Permission**, **User Role**, **Resource ACL** *(existing)*: Seeded by feature 001 and read here for the first time. This feature consumes them; it does not reshape them.
- **Audit Log** *(existing)*: Gains authorization allow and deny entries alongside the seed, contact, refusal, and retention entries already written.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A seeded employee can sign in and see their own HR profile within three interactions of arriving at the portal address.
- **SC-002**: 100% of protected addresses refuse an anonymous caller, and 100% refuse a caller whose session has expired — by either bound: 30 minutes idle, or 8 hours from sign-in even while active.
- **SC-002a**: After sign-out, 100% of protected requests presenting the previous credential are refused — demonstrated by replaying that exact credential, not by observing that the interface stopped sending it.
- **SC-003**: A manager can read every one of their direct reports and **zero** employees outside their reporting line.
- **SC-004**: Cross-tenant access attempts by an authenticated user return zero records, in every store read at request time, and are indistinguishable from a request for something that does not exist.
- **SC-005**: Supplying a tenant, role, or permission value in a request changes the response in **zero** cases.
- **SC-006**: 100% of authorization **denials** appear in the audit trail with actor, tenant, resource, decision, and reason. 100% of allows **for sensitive resources** appear; reading one's own non-compensation profile produces **zero** entries. **Zero** audit entries contain a credential or token.
- **SC-007**: Zero denied requests perform a read of the data they were denied, demonstrated by observing the request path rather than only the response.
- **SC-008**: Navigation contains zero entry points to areas the signed-in user lacks permission for, and every hidden area is also refused when requested directly.
- **SC-009**: Every portal surface renders its loading, empty, error, unauthenticated, and access-denied states, verified by automated test rather than by inspection.
- **SC-010**: Every portal page passes the automated WCAG 2.2 Level AA checks with zero violations and a keyboard-only traversal, at the same three viewport widths feature 002 verifies.
- **SC-011**: The public website, health endpoints, and dataset manifest remain anonymously reachable, with every existing check passing unchanged.
- **SC-012**: Unauthorized information leakage measures **zero** across the authorization test suite, and that suite blocks the change on failure.
- **SC-013**: Repeated failed sign-in attempts are bounded in both dimensions: after the stated number of failures a further attempt against that account is refused, and after the stated number from one address a further attempt from that address is refused. Zero refusals disclose which bound was reached or whether the account exists.
- **SC-014**: Establishing credentials leaves the committed dataset fingerprint unchanged, and a reset followed by re-provisioning restores a working sign-in.

## Scope Boundaries

**In scope**: authentication for both tenants' seeded users, the access context, the five-layer
authorization decision, the protected current-user and access-context endpoints, the HR-profile
vertical slice including the manager and cross-tenant cases, the portal shell with sign-in,
sign-out, expiry, role-aware navigation and its required states, and the automated checks proving
all of it.

**Out of scope** — carried into **Feature 004**:

- Document ingestion, chunking, embedding, and vector-store population (feature 001 decision D2).
- Retrieval-augmented generation, chat streaming, and the AI assistant.
- Agents, tool execution, and the orchestrator.
- Any **write** action, and therefore the human-approval gate of Constitution Principle VII. This feature reads only.
- Binary document formats and the synthetic code repository (decisions D3, D4).
- Password reset, self-registration, multi-factor authentication, and account lifecycle management. The users are seeded; there is no signup.

## Assumptions

- **Credentials are synthetic and provisioned separately from the seed** (FR-002a). These are generated users in a demonstration system; no real person is behind any account and there is no registration flow. The generator leaves `password_hash` unset — it does so today — and a distinct post-seed step establishes credentials, which is what keeps the dataset fingerprint stable.
- **Both tenants authenticate through the same system.** Delta Retail exists so cross-tenant isolation can be demonstrated by an authenticated caller, not merely asserted structurally.
- **The dataset already carries everything authorization needs.** Feature 001's FR-047a guarantees the eight blueprint access-control scenarios are expressible — a manager with direct reports, an employee whose salary must be denied, a second department outside a manager's scope, and so on. This feature enforces them; it adds no data.
- **Roles and permissions are read, not authored.** Feature 001 seeds `roles`, `permissions`, `role_permissions`, `user_roles`, and `document_acl`. No interface for editing them is in scope.
- **Reading only.** Every endpoint this feature adds is a read. That is what keeps Principle VII's approval gate out of scope, and it is worth stating because the first write action changes what this feature must satisfy.
- **The audit log is append-only and already enforced** by a database trigger from feature 001. Authorization entries inherit that guarantee.
- **Session mechanism.** Server-side session records, per FR-007. The alternative — a self-contained credential with no server state — was considered and rejected because it cannot satisfy FR-007: sign-out would clear the client and leave the credential valid. A revocation list was also considered and rejected for inverting the safe default, since anything absent from such a list is trusted and losing the store would silently re-validate every signed-out session.

## Dependencies

- **Feature 001** — seeded users, roles, permissions, ACLs, manager relationships, and the append-only audit log. Its dataset fingerprint is computed from generated rows rather than from the database, which is the property FR-002a relies on. Also its FR-043a (cross-tenant answers as not found) and FR-001a (dependency direction), both of which this feature must honour.
- **Feature 002** — the reserved portal address (FR-049a), the design system and state patterns, the anonymous boundary this feature must not weaken (FR-046 through FR-052), and the contract-checking machinery that will now cover a second API surface.
- **The constitution** — Principles I, II, III, VIII, and X apply directly and are cited throughout rather than paraphrased.
