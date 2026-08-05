# Phase 0 Research: NileTech Public Website

Decisions taken before design, with the alternatives that were rejected and why. Each entry is
referenced from `plan.md` or `data-model.md`.

---

## R1 — Frontend framework: Next.js 15 (App Router)

**Decision**: Replace the Vite SPA in `apps/web` with Next.js 15 using the App Router, rendering
public pages on the server.

**Rationale**: Three of this feature's requirement groups land almost exactly on Next's built-in
surface, and hand-rolling them on the existing stack would mean rebuilding what it already does:

- FR-039–FR-041 (per-page and per-record title, description, social preview) map to the Metadata API and `generateMetadata`.
- FR-042 (canonical address, machine-readable page index) maps to `sitemap.ts` and `robots.ts`.
- FR-043 (unknown addresses reported as not found to crawlers) is what `notFound()` does — a client-rendered SPA returns 200 with an empty shell to a crawler no matter what the user sees.

Server rendering also removes the loading-then-content flash that a client-fetching SPA shows on
every page, which is the difference between meeting SC-014's 3-second budget and merely
appearing to.

**Alternatives considered**:

- **React Router v7 in framework mode** — genuinely modern, server-rendering, and Vite-native, so it would preserve the existing toolchain and Vitest setup. Rejected because its metadata story is a `meta` export per route that we would extend by hand into canonicals, social previews, and a sitemap — reimplementing R1's whole rationale. The toolchain saving is real but smaller than the reimplementation cost.
- **Keep the Vite SPA and pre-render at build time** — bakes the dataset into the build, so a reseed silently leaves the site describing the previous dataset. That is the exact class of staleness feature 001 spent five convergence passes eliminating.
- **Astro** — excellent for content sites, but the contact form and the careers filter are interactive, and the project's other surface (the employee portal) is an application. Two frameworks for two surfaces is a cost with no offsetting benefit here.

**Consequence**: `apps/web` changes shape. `vite.config.ts`, `index.html`, and `main.tsx` go;
Vitest stays for component tests and gains Playwright alongside it for end-to-end. The Dockerfile
and the Compose healthcheck both change (R3).

---

## R2 — The feature 001 status shell moves to `/status`

**Decision**: Migrate `StatusPage.tsx` and its 13 tests into the new app at `/status` rather than
deleting them with the SPA.

**Rationale**: That page is not decoration. It is how feature 001 demonstrates FR-002 (the whole
stack starts) and FR-003 (per-dependency health, including the background worker added in that
feature's Phase 11). Its tests cover the loading, ready, degraded, empty, and error states, and
one of them asserts that a 503 from `/health/ready` is rendered rather than thrown away. Deleting
the SPA without moving it would retire that coverage silently — which is precisely the failure
mode feature 001 kept finding.

**Alternatives considered**:

- **Delete it** — the site is the product surface now. Rejected: it would remove passing coverage of another feature's requirements, and nothing else exercises the degraded-readiness path in a browser.
- **Keep a second Vite app for it** — two frontend toolchains to maintain for one diagnostic page.

**Consequence**: `/status` is not in the site navigation and is excluded from the sitemap. It is
a diagnostic route, not a public page, and it must not appear in FR-039's per-page metadata audit
as though it were one.

---

## R3 — Container and healthcheck changes

**Decision**: The `web` service builds Next.js and serves it; its Compose healthcheck probes the
site root instead of the Vite dev server.

**Rationale**: The existing healthcheck (added as feature 001's T154) fetches `http://127.0.0.1:5173`
and passes on any OK response. Next serves on 3000 by default. Left unchanged, the healthcheck
would fail permanently — or worse, if the port were reused, would pass while serving the old
bundle.

**Consequence**: `WEB_HOST_PORT` and the healthcheck command change together, and
`infrastructure/.env.example` documents the new default. `docs/running.md` needs the new URL.

---

## R4 — Styling: design tokens + CSS Modules in `packages/ui`

**Decision**: A token layer (`tokens.css`, CSS custom properties for the type scale, palette,
spacing, and radii) plus CSS Modules for component styles, both living in `packages/ui`.

**Rationale**: FR-031 asks for a *defined* type scale, palette, and spacing system applied
uniformly — that is a token problem, and tokens make FR-035's contrast requirement checkable at
the palette level rather than one component at a time. CSS Modules keep component styles scoped
without adding a build plugin to a workspace that already pins its toolchain exactly (feature
001's FR-012b).

**Alternatives considered**:

- **Tailwind** — faster to build consistently, and its defaults are decent. Rejected because the tokens would then live in a Tailwind config that `packages/ui` consumers must also configure, which couples every future surface to that choice; and because "professional enterprise visual identity" is a design decision better expressed as named tokens than as utility strings scattered through markup.
- **CSS-in-JS** — runtime cost on a server-rendered content site, for styling that never changes at runtime.

**Amended during implementation**: the components ship a single `components.css` of
token-driven, prefixed classes rather than one CSS Module per component. Modules inside a
transpiled workspace package need additional Next configuration and buy nothing at this scale —
the package has one consumer, the class names are namespaced, and every value still comes from
`tokens.css`. The property this decision actually wanted — no hard-coded colour or spacing
outside the token layer — is unaffected. Revisit if a second consumer appears and the classes
start colliding.

---

## R5 — Deterministic slugs for detail pages (FR-004)

**Decision**: Derive each vacancy and news slug in the API from the record's own text plus a
short digest of its natural key: `information-security-analyst-cairo-7f3a2c`.

**Rationale**: FR-004 requires human-readable addresses that are stable across seed runs. The
dataset carries no slug column, and the identifiers it does carry are UUIDs. Deriving from title
alone is not enough — feature 001 generates repeated vacancy titles across offices, and the
generator appends a numeric suffix to collided emails, so collisions are known to occur. The
digest suffix makes the address unique without making it opaque, and because feature 001 derives
identifiers deterministically from natural keys, the same slug comes back from every seed run.

**Alternatives considered**:

- **UUID in the address** — stable and unique, but FR-004 explicitly rejects opaque identifiers, and it wastes the SEO value of a descriptive URL.
- **Title-only slug with a collision counter** — the counter depends on iteration order, so two environments could assign `-2` to different records. That is the kind of order dependence feature 001's determinism work exists to prevent.
- **Add a slug column to the dataset** — cleaner, but it changes feature 001's generated content, which moves both committed fingerprints and requires a generator version bump for a presentation concern.

**Consequence**: slug derivation lives in `apps/api/src/eaios_api/public/slugs.py` and is unit
tested for stability and collision behaviour. The frontend never constructs a slug; it uses the
one the API returns.

---

## R6 — Public responses are built from a declared allowlist

**Decision**: Every public endpoint returns a hand-written Pydantic model listing exactly the
fields it exposes. No ORM row is serialized directly, and no internal serializer is shared with
a future authenticated endpoint. The allowlist is documented in `contracts/public-fields.md` and
asserted by a test that compares response keys to it.

**Rationale**: FR-045 requires an added field to be an explicit decision. The common failure is
the opposite shape — serialize the model, exclude what looks sensitive — because that fails
*open*: a column added later appears in the response until someone notices. An allowlist fails
closed. This matters more than usual here because the same database holds RESTRICTED payroll
records and a second tenant.

**Consequence**: `LeadershipProfileOut` exposes name, public title, biography, and display order
— and deliberately **not** `user_id`, which is an internal identifier of a real employee row.
The test asserting response keys is the control; the model is just how it is expressed.

---

## R7 — No Redis caching of public pages

**Decision**: Serve public pages from live queries. Do not cache them in Redis in this feature.

**Rationale**: The content is a few dozen rows behind an index; the 3-second budget in SC-014 is
not under threat. Adding a cache would add a tenant-namespaced key discipline, an invalidation
path on reseed, and a class of "stale after reset" bug — for a page that reads six rows.

**Alternatives considered**: Next's own request-level caching is used for deduplication within a
single render pass, which is free and needs no invalidation. Cross-request caching is deliberately
not enabled, so a reseed is immediately visible.

**Revisit when**: page latency is actually measured above budget, or the dataset grows an order
of magnitude.

---

## R8 — `contact_submissions` is excluded from the dataset fingerprint

**Decision**: Add the new table to the fingerprint's exclusion list, to `reset_all`'s truncation
set, and to the seed's emptiness pre-flight.

**Rationale**: This is the one place where this feature can break feature 001's guarantees, and
all three follow from the same fact — the table holds *runtime* data, not generated data.

- **Fingerprint**: FR-015a of feature 001 says the fingerprint covers generated content and excludes what legitimately varies between environments. A submitted message is exactly that. If it were included, submitting the contact form would change the dataset fingerprint and fail `verify`.
- **Reset**: `reset_all` must truncate it, or a reset would leave visitor messages behind while claiming to have destroyed all state.
- **Seed pre-flight**: `inspect_stores` iterates `INSERT_ORDER`, which lists only seeded tables. A submission written before seeding would leave the environment non-empty in a way the pre-flight cannot see, so `seed` would proceed against a dirty database. The pre-flight must count this table too.

**Consequence**: three small edits in `scripts/seed`, each with a test. The exclusion is recorded
in `docs/determinism.md`, which FR-015a requires to document the exclusion list and its rationale.

---

## R9 — Accessibility verification: automated plus keyboard

**Decision**: `@axe-core/playwright` against every page at WCAG 2.2 A and AA tags, in CI, plus a
scripted keyboard-only traversal of each page asserting focus order, focus visibility, and that
the mobile navigation returns focus on dismissal.

**Rationale**: FR-053 states the reason plainly — automated tooling covers a subset of AA, so a
suite running only that subset reports conformance it has not established. The keyboard pass is
the cheapest high-value complement: it catches focus traps, invisible focus, and unreachable
controls, which together account for most real keyboard failures and none of which axe detects
reliably.

**Alternatives considered**: axe alone (rejected above); a full manual audit per release
(valuable, but not something CI can block a merge on).

---

## R10 — Contact form: server-side validation, no delivery, duplicate suppression by content

**Decision**: Validate with a Pydantic model on the server (the control) and mirror the rules in
the browser (the convenience). Accept, store, audit, and return. Suppress duplicates by hashing
the submission content and rejecting an identical hash from the same tenant within a short window.

**Rationale**: FR-020 makes the server the control explicitly, so the browser rules exist only to
tell the visitor sooner. FR-023a forbids delivery, which removes the whole approval-gate question
(Constitution VII) — there is no outward action to gate. The edge case in the spec is a visitor
double-submitting one intent, which a content hash addresses without a session, a cookie, or a
token on an anonymous surface.

**Alternatives considered**:

- **Idempotency key from the client** — requires the client to be trusted to vary it, and an anonymous form has no session to anchor it to.
- **Rate limit by IP** — blunt, punishes shared networks, and does not actually address the double-submit case it would be introduced for. Worth revisiting as abuse protection, which is a different problem.

---

## R11 — Testing the anonymous boundary

**Decision**: Three pytest modules in `tests/security/`, written before the endpoints:

1. **Field allowlist** — every public response's keys equal the declared set, and no response contains any value drawn from a non-`PUBLIC` row.
2. **Anonymous refusal** — every private route and non-public endpoint refuses an anonymous request, with an audit entry written per refusal, and a companion assertion that the refusal list is non-empty so the test cannot pass by having nothing to check.
3. **Cross-tenant** — Delta Retail's marker phrases appear in zero public responses, and no caller-supplied hostname, path, parameter, header, or body causes Delta content to be served.

**Rationale**: Constitution VIII requires these to be written first. The anti-vacuity assertion in
(2) is a direct lesson from feature 001, where a security suite silently skipped 69 tests and
reported success.
