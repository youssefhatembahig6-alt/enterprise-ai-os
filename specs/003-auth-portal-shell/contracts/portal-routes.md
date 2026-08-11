# Contract: Employee Portal Routes and States

**App**: `apps/web` | **Feature**: `003-auth-portal-shell`

The portal replaces the holding page at `/portal` **without changing that address**
(FR-027, spec 002 FR-049a). Every header link on the public site already points there.

---

## 1. Route inventory

Added to `apps/web/lib/pages.ts` so the existing sweeps pick them up. That module is the
single inventory feature 002 built precisely so a new page cannot be missed by the
accessibility, keyboard, responsive, and metadata suites — a route added anywhere else is
a route those suites never visit.

| Path | Rendering | Auth | Purpose |
|------|-----------|------|---------|
| `/portal` | server | anonymous | Sign-in. Replaces the holding page. Redirects to `/portal/home` when a live session exists. |
| `/portal/home` | server | required | Landing: greeting, session state, role-aware navigation. |
| `/portal/profile` | server | required | My HR Profile (FR-023). The complete page. |
| `/portal/team` | server | `hr:read_team` | Direct reports list (FR-024). |
| `/portal/team/[userId]` | server | `hr:read_team` | One direct report's profile. The same address refuses for anyone outside the reporting line. |
| `/portal/denied` | server | required | The designed access-denied state (FR-029). |

**Non-content routes** — excluded from the sitemap and marked `noindex`, joining the
existing `NON_CONTENT_ROUTES` set. The portal is not public content and must not appear in
`sitemap.ts`, which a test asserts.

**No AI Assistant placeholder.** The brief permits one "only if the approved Feature 003
spec requires it". It does not — RAG, chat, and the assistant are named out of scope and
carried to feature 004. A navigation entry to a page that does nothing would also violate
FR-028's own principle: an entry point to something the user cannot use.

---

## 2. Route handlers (the same-origin boundary)

Browser JavaScript never holds the token (research R3). These handlers are the only place
it is set or cleared.

| Route | Method | Does |
|-------|--------|------|
| `/portal/api/login` | POST | Forwards to `POST /auth/login`; on success sets `eaios_session` (`httpOnly`, `Secure`, `SameSite=Strict`, `Path=/`, `Max-Age` = 8h) and a readable `eaios_csrf` cookie; returns only `{ ok: true }` — never the token. |
| `/portal/api/logout` | POST | Requires the `X-CSRF-Token` header to match `eaios_csrf`; forwards to `POST /auth/logout`; clears both cookies **regardless of the API's answer**, so a failed server call cannot leave the browser holding a credential. |

Server components call the API directly with the cookie read through `next/headers`
`cookies()` and forwarded on the `Authorization` header. A `fetch` from a server component
does not inherit the browser's cookie jar; forgetting this produces a portal that renders
signed-out on the server and signed-in in the browser.

---

## 3. Required states

Constitution *Frontend completeness* and FR-029. Every portal surface implements every
one of these states **that it can reach**, and `apps/web/tests/portal-states.test.tsx`
holds the evidence — a missing state fails a test rather than being noticed in review.

**The rule, stated precisely.** The original wording asked for a literal cross-product of
every surface against every state. Nine of those thirty-five cells cannot exist: the
denied page reads nothing, so it has no populated or empty result; the home page's only
read is `/me`, which no authenticated caller can be forbidden from; a profile resolves,
is refused, or is absent, so there is no empty profile. Satisfying them would have meant
giving pages fetches they do not need. What is required instead, and enforced:

1. **Every reachable route-specific state is tested** on the route that renders it.
2. **Shared boundaries are tested once**, and proven to cover their child routes — the
   `(authed)` shell for unauthenticated and expired, `(authed)/loading.tsx` for loading,
   and `portal/error.tsx` for the routes with no error state of their own. Nesting is
   asserted against the route tree, so a route added outside a boundary fails.
3. **Unreachable cells are classified explicitly, with a stated reason** in the suite, and
   the suite fails if any route or state is left unclassified.

This narrows nothing. Every state below is still required wherever it can occur, and the
classification is what makes a gap visible instead of absorbed into a rectangle that was
never fillable.

| State | Trigger | What the user sees |
|-------|---------|--------------------|
| Loading | server render in flight; client region pending | Skeleton matching the final layout, never a spinner over a blank page |
| Empty | permitted, nothing to show (e.g. a manager with no reports) | An explanation of why it is empty. Distinct from access-denied — "you have no direct reports" is not "you may not see this" |
| Error | the API failed or timed out (10s, matching `lib/api.ts`) | A stated failure with a retry control that is actually wired. `ErrorState.retry` was a prop no caller passed for the whole of feature 002 |
| Unauthenticated | no session, or the session was never established | Return to sign-in with a plain statement. Never a raw 401 |
| **Expired** | session ended by the idle or absolute bound | **Says the session expired**, distinctly from the unauthenticated state. FR-005 and the spec's edge cases both call for this: a generic failure after a 30-minute pause is the difference between a portal that explains itself and one that looks broken |
| Access denied | 403 from the API, or a direct request to a hidden address | A designed page saying access is not held. Never blank, never a raw 403 (FR-029) |
| Success | data present | The page |

**Empty, unauthenticated, expired, and denied are four different states, not one.**
Collapsing any pair is the defect FR-029 exists to prevent. Two such collapses were found
and fixed once the states were tested: the `(authed)` shell caught every identity failure
with a bare `catch` and redirected to the sign-in form, so a dependency outage told a
signed-in person they were signed out; and `/portal` fell through to the form on the same
failure. Both now leave the unexpected case to `portal/error.tsx`, which states that the
portal could not be loaded and claims nothing about the session in either direction.

---

## 4. Role-aware navigation

`PortalNav` renders from `CurrentUser.permissions` — codes, never role names (FR-014).

- An entry for an area the caller lacks the code for is **not rendered at all**. Not
  disabled, not hidden with CSS: absent from the markup. A test asserts the string does
  not appear in the rendered HTML, because `display: none` is still present in the DOM and
  still readable by a screen reader.
- Hiding is presentation only. The server refuses the address regardless of what the
  interface showed (FR-028, SC-008), and a separate test requests each hidden address
  directly and asserts the refusal.
- The permitted case is asserted in the **same test** as the hidden case. Without that,
  a bug that renders no navigation at all passes every hiding assertion.

---

## 5. Accessibility and responsiveness

The bar feature 002 set, applied to the new pages with no exceptions:

- WCAG 2.2 AA, automated checks with **zero** violations, at 360 / 768 / 1280 — the three
  Playwright viewport projects already configured.
- Keyboard-only traversal of sign-in, navigation, and every state above.
- **Focus management on transitions**: after sign-in, focus moves to the portal heading;
  after an expiry redirect, to the expiry message. A route change that leaves focus on a
  detached node strands a keyboard user silently.
- The sign-in form: `<label>` on every control, errors associated with
  `aria-describedby`, and the failure announced in a live region — a message a sighted
  user sees and a screen-reader user does not is not an error message.
- No token, internal identifier, hostname, stack trace, or authorization reason code
  appears in any rendered page or in the DOM (FR-022). A test greps the rendered output.

---

## 6. What must not regress

The public site's guarantees are load-bearing for FR-031, FR-032, and SC-011, and every
existing check must pass **unchanged**:

- The eight public content pages carry no credential field (spec 002 FR-048). The sign-in
  form is at `/portal`, which spec 002 FR-001a already classifies as a non-content route.
- The public API, health endpoints, and dataset manifest stay anonymous.
- The anonymous refusal behaviour (FR-047, FR-047a, FR-047b) is untouched. The new
  `/auth/*`, `/me/*`, and `/hr/*` prefixes are **not** added to `_SERVED_PREFIXES` in
  `refusal_audit.py`: an anonymous request to a protected address is exactly the refusal
  that middleware exists to record.
