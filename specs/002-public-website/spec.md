# Feature Specification: NileTech Public Website

**Feature Branch**: `002-public-website`

**Created**: 2026-08-02

**Status**: Complete

**Evidence**: CI run [31443872819](https://github.com/youssefhatembahig6-alt/enterprise-ai-os/actions/runs/31443872819) at commit `429fdcba8b22d10e356874f0fff1995a83a36145` — API conclusion `success`, 7/7 jobs green, 86 successful steps, 3 conditional log-dump skips, 0 failures. All 139 tasks and all nine checklists are closed. The public site's end-to-end, accessibility, responsive, and metadata sweeps pass in that run at all three viewport widths.

**Input**: User description: "Build the complete public website for the fictional company NileTech Solutions. The company website is a mandatory product component. Create these pages: Home, About, Services, Products, Leadership, Careers, Individual vacancy page, News, Individual news article page, Contact, Not Found, Server Error. Present NileTech as a believable software and business-automation company operating in Cairo, Alexandria, and Dubai. Requirements: Professional enterprise visual identity; Responsive desktop, tablet, and mobile design; Accessible navigation; Header and footer; Company hero section; Services and products; Generated leadership profiles; Generated vacancies; Generated news; Office information; Contact form validation; Loading, empty, error, and success states; Search-engine metadata; Login button leading to the private employee portal; Public APIs must expose only approved public data; Anonymous visitors must never access private portal routes or APIs."

## Context

This feature builds the **first of the two mandatory product surfaces** named in the project
constitution. Feature 001 generated the content it renders — services, product offerings,
leadership profiles, news items, vacancies, and office information — and classified every item
as `PUBLIC`. Nothing has ever displayed that content. This feature does.

It is a **read-only public surface with one write path** (the contact form). It does not
deliver authentication, the employee portal, retrieval, or agents. Those remain on feature
001's carry-forward list and are **not** addressed here — see Scope Boundaries.

## Clarifications

### Session 2026-08-02

Reviewed against `docs/Enterprise_AI_OS_EDITED.html`. The blueprint names the public site as
*Home, About, Services, Products, Leadership, Careers, News, Contact* — the same eight this
specification carries. The four supporting pages (vacancy detail, article detail, Not Found,
Server Error) are additions, not substitutions, and **no clarification below reduces the page
set**. The blueprint is silent on accessibility, responsive behaviour, search-engine metadata,
and the contact form, so the constitution governs those and the decisions below fill the gaps
it leaves open.

- Q: Does this feature build a NileTech-only site, or one serving either tenant by address? → A: NileTech-only. Public endpoints hard-scope to NileTech; Delta Retail's public content is never served and the isolation tests assert exactly that.
- Q: Where does the login control lead while the employee portal does not exist? → A: To the reserved portal address, which returns a designed "sign-in not yet available" page. The route exists and refuses anonymous access now, so the FR-046 boundary is testable before the portal is built; the portal replaces the page's contents later.
- Q: What happens to an accepted contact submission? → A: Stored as a tenant-scoped record and audited. No outbound delivery of any kind — no email, no queue, no notification.
- Q: Which accessibility conformance level must the site meet? → A: WCAG 2.2 Level AA, verified by automated checks on every page plus a keyboard-only pass.
- Q: Which viewport widths must the responsive requirement be verified at? → A: 360px (mobile), 768px (tablet), and 1280px (desktop) as the tested widths, with no horizontal page scrolling at any width from 320px upward.

### Session 2026-08-02 — checklist remediation

Eight requirements-quality checklists were generated after planning and found one conflict, one
contradiction with the existing system, and several unquantified terms. Resolved here before
implementation. **No requirement was removed or narrowed**, and the page set is unchanged.

- **Conflict fixed (FR-006a)** — FR-005 required a hero stating what the company does while FR-006 forbade hard-coded company content, and the dataset carries no positioning field. Record content and interface copy are now distinguished, with interface copy forbidden from stating any fact the dataset could contradict.
- **Contradiction with feature 001 fixed (FR-047a)** — FR-047 would have required refusing the health endpoints and the dataset manifest, which that feature serves anonymously by design and which the status route depends on. The endpoint surface is now classified into public, operational, and non-public sets.
- **Untestable requirement fixed (FR-025)** — the four-state rule demanded a loading state on server-rendered pages, where one can never appear. States are now required per content region according to what can actually occur.
- **Criterion strengthened (SC-005)** — a clean automated run read as established WCAG 2.2 AA conformance, which FR-053 explicitly says it is not. Both the automated checks and the keyboard traversal are now required.
- **Verification path stated (SC-007)** — proving "exactly one stored record" is impossible through the public surface because FR-023b forbids a read path; the criterion now names privileged database access as the method.
- **Routes enumerated (FR-001a)** — the reserved portal address and the diagnostic status route were introduced by the plan without appearing in the specification's page inventory.
- **Privacy gap closed (FR-024a, FR-024b, FR-024c)** — the form collects a name and an email address from the public with no stated notice, retention period, or prohibition on logging them.
- **Thresholds quantified (FR-019, FR-022, FR-027a)** — field lengths, the duplicate-suppression window, the loading-state delay, and the load timeout were all directional rather than measurable.

### Session 2026-08-05 — remaining checklist items

The four checklist items left open through implementation and seven convergence passes. Each was
a genuine specification gap rather than an implementation defect, so none could be closed by
`/speckit-implement`. **No requirement is removed or narrowed below.**

- Q: What abuse protection should the anonymous surface require? → A: Per-IP bounds on the two paths that *write* — contact submissions and audited refusals — with public reads left unlimited because they have no side effects.
- Q: How must the site handle generated content at the low extreme — a one-word summary, an empty biography? → A: Render short content as-is; render a defined fallback for an empty or whitespace-only field, never a blank region. No dataset change.
- Q: What happens when a leadership profile references an employee record that cannot be resolved? → A: The profile is omitted from the public response and the condition is recorded, naming the profile rather than the person. It fails closed.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A Prospective Client Evaluates NileTech (Priority: P1)

A visitor who has never heard of NileTech arrives at the site, understands within seconds what
the company does, browses its services and product offerings, sees where it operates, and
leaves with a clear impression of a real software and business-automation firm.

**Why this priority**: This is the site's reason to exist and the constitution's mandatory
public surface. Every other journey below is reachable only through the navigation this story
establishes. It is also the demo's opening move — the first thing a reviewer sees.

**Independent Test**: With the seeded environment running, open the site root and complete the
journey Home → Services → Products → About without leaving the site or encountering a dead end.
Every item shown traces to a generated record. Delivers value alone: a complete company
brochure, even before careers, news, or contact exist.

**Acceptance Scenarios**:

1. **Given** a visitor on any device, **When** they open the site root, **Then** the home page presents the company name, a hero statement describing what NileTech does, and entry points to services, products, and contact.
2. **Given** the seeded dataset, **When** the visitor opens Services, **Then** every generated service is listed with its name and summary, in the generator's display order, and none is a placeholder.
3. **Given** the seeded dataset, **When** the visitor opens Products, **Then** every generated public product offering is listed — and **no** item from the internal sellable product catalog appears.
4. **Given** the visitor is on any page, **When** they use the header navigation, **Then** every page named in this specification is reachable, and the current page is indicated.
5. **Given** the About page, **When** the visitor reads it, **Then** the three offices — Cairo, Alexandria, Dubai — are named with their country, and they match the offices in the generated data.

---

### User Story 2 - A Candidate Finds And Opens A Role (Priority: P2)

A job seeker opens Careers, scans the open positions, filters to the office or team that
interests them, opens a single vacancy, and reads its full description with department and
location.

**Why this priority**: Careers is the highest-intent journey on a corporate site and the one
with real depth in the generated data — eleven open vacancies across departments and offices.
It also introduces the list-plus-detail pattern that News reuses.

**Independent Test**: Open Careers, confirm the count matches the open vacancies in the
dataset, filter by office, open one vacancy, and confirm its department and location match that
record. Delivers value alone as a working jobs board.

**Acceptance Scenarios**:

1. **Given** the seeded dataset, **When** the visitor opens Careers, **Then** every vacancy marked open is listed with its title, department, and office, and closed vacancies are absent.
2. **Given** the Careers list, **When** the visitor filters by office or department, **Then** only matching vacancies remain and the applied filter is visible and removable.
3. **Given** a vacancy in the list, **When** the visitor opens it, **Then** a dedicated page shows its title, department, office, posting date, and full description.
4. **Given** a vacancy address that does not exist, **When** the visitor opens it, **Then** the Not Found page is shown with a route back to Careers — not a blank screen or a raw error.
5. **Given** a filter that matches nothing, **When** it is applied, **Then** an empty state explains that no roles match and offers to clear the filter.

---

### User Story 3 - A Visitor Reads Company News (Priority: P3)

A visitor opens News, sees announcements in reverse-chronological order, and opens one to read
it in full.

**Why this priority**: News is what makes a company look active rather than dormant, and the
dataset carries eleven dated items spanning the history window. Lower than Careers because it
reuses the same list-plus-detail pattern and carries less visitor intent.

**Independent Test**: Open News, confirm ordering is newest-first and matches the dataset, open
an article, and confirm its headline, date, and body match that record.

**Acceptance Scenarios**:

1. **Given** the seeded dataset, **When** the visitor opens News, **Then** every generated news item appears with its headline and publication date, newest first.
2. **Given** the News list, **When** the visitor opens an item, **Then** a dedicated page shows the headline, publication date, and full body.
3. **Given** a news address that does not exist, **When** the visitor opens it, **Then** the Not Found page is shown with a route back to News.
4. **Given** more news items than fit comfortably on one screen, **When** the visitor reaches the end of the list, **Then** they can reach the remainder without losing their place.

---

### User Story 4 - A Visitor Makes Contact (Priority: P4)

A visitor opens Contact, finds the office addresses and a general enquiry address, fills in a
message form, is told clearly when something is wrong with what they typed, and receives an
unambiguous confirmation when the message is accepted.

**Why this priority**: Contact is the site's only write path and therefore the only place where
validation, success, and failure states are exercised for real. It is lower than the read
journeys because those must exist before a visitor has a reason to write.

**Independent Test**: Submit the form with missing and malformed fields and confirm each error
is reported against its field; submit a valid message and confirm the success state; confirm
the message is recorded and attributed to NileTech.

**Acceptance Scenarios**:

1. **Given** the Contact page, **When** it loads, **Then** each office is shown with its city, country, and address, and a general enquiry address is present.
2. **Given** the contact form, **When** the visitor submits it with a required field empty, **Then** submission is refused, the specific field is identified, and nothing the visitor typed is lost.
3. **Given** the contact form, **When** the visitor enters a malformed email address, **Then** the error names that field and explains what is expected.
4. **Given** a valid submission, **When** the visitor submits it, **Then** a success state confirms the message was received and the form is cleared or disabled to prevent accidental duplicate submission.
5. **Given** the backend is unreachable, **When** the visitor submits, **Then** an error state explains the message was not sent and invites a retry — the visitor is never told a failed submission succeeded.

---

### User Story 5 - A Visitor Assesses Credibility Through Leadership (Priority: P5)

A visitor opens Leadership and sees the executive team, each with a public title and a short
biography.

**Why this priority**: Leadership is the page that most distinguishes a believable company from
a template, and it is the one that carries the sharpest disclosure risk — every field shown
must be public-appropriate.

**Independent Test**: Open Leadership, confirm each profile corresponds to a real generated
executive of NileTech, and confirm no page field exposes salary, personal contact details, or
any other non-public attribute.

**Acceptance Scenarios**:

1. **Given** the seeded dataset, **When** the visitor opens Leadership, **Then** every generated leadership profile is shown with the person's name, public title, and biography, in display order.
2. **Given** a leadership profile, **When** its content is inspected, **Then** it exposes only public-appropriate fields — no salary, no personal contact details, no employment record, no internal identifier.
3. **Given** a profile with no photograph in the dataset, **When** the page renders, **Then** a designed placeholder appears rather than a broken image or an empty gap.

---

### User Story 6 - An Employee Reaches The Portal Entry Point (Priority: P6)

An employee visiting the public site finds an unambiguous way through to the private employee
portal, while an anonymous visitor who tries to reach private routes or private data directly
is refused.

**Why this priority**: The entry point is a small piece of work, but the boundary it marks is
the constitution's first principle. It is last because the portal it points to does not exist
yet — the boundary must be enforced regardless.

**Independent Test**: Confirm the login control is present and leads to the portal entry; then,
as an anonymous visitor, attempt to reach private routes and non-public data directly and
confirm every attempt is refused rather than partially served.

**Acceptance Scenarios**:

1. **Given** any public page, **When** the visitor looks at the header, **Then** a clearly labelled control leads to the employee portal.
2. **Given** an anonymous visitor, **When** they request any private portal route directly, **Then** they are refused with a designed, informative response — never a blank screen, a partial render, or a raw error.
3. **Given** an anonymous visitor, **When** they request any data endpoint that serves non-public content, **Then** the request is refused, and the refusal is recorded.
4. **Given** the public data endpoints, **When** their responses are inspected, **Then** they contain only `PUBLIC`-classified content and expose no field carrying internal, confidential, or restricted data.
5. **Given** an anonymous visitor, **When** they request public data belonging to the other tenant, **Then** nothing from that tenant is returned through the NileTech site.

---

### Edge Cases

- **Empty content family**: a company with no news, no open vacancies, or no leadership profiles must render a designed empty state on that page, and the navigation entry must remain reachable rather than silently disappearing.
- **Unresolvable leadership profile**: a profile whose linked employee record is missing is omitted from the page and the condition is recorded against the profile, not the person. The remaining profiles still render.
- **Content the data cannot supply**: leadership photographs are not generated. Any visual element with no backing data needs a designed fallback rather than a gap or a broken asset.
- **Unknown detail address**: an address for a vacancy or article that does not exist, or that exists only for the other tenant, resolves to Not Found — not to an empty detail page.
- **Closed vacancy reached directly**: a vacancy that is no longer open must not appear as though applications are welcome.
- **Backend unavailable or slow**: every page that loads content must show a loading state while waiting and an error state on failure, and must never present a permanently empty page as though the content genuinely does not exist.
- **Partial failure**: when one section of a page fails to load and others succeed, the failure must be visible in that section rather than replacing the whole page.
- **Unexpected server failure**: an unhandled failure resolves to the Server Error page, which must not expose stack traces, internal hostnames, query text, or identifiers.
- **Very short or empty generated text**: a one-word summary or a single-sentence biography must render as written. A field that is empty or whitespace-only must show its defined fallback rather than leaving a gap that reads as a broken card.
- **Very long generated text**: generated biographies, descriptions, and headlines vary in length; layouts must not overflow, clip meaning, or break at any supported viewport width.
- **Names with non-Latin characters or unusual casing**: generated Egyptian and Emirati names must render correctly everywhere they appear.
- **Deep link into a filtered list**: a shared address that includes a filter must reproduce the same filtered view for the next visitor.
- **Repeated form submission**: submitting the contact form twice in quick succession must not create two records from one visitor intent.
- **Sustained automated traffic**: a script submitting the contact form repeatedly, or probing non-public addresses in a loop, must be bounded rather than allowed to grow the stored record set or the audit trail without limit. Ordinary browsing and search-engine crawling of public pages must be unaffected.
- **Abusive or oversized form input**: input beyond the accepted length, or containing markup, must be rejected or neutralized, and must never be reflected back to another visitor as active content.
- **Search-engine and social preview requests**: a crawler requesting any page must receive complete, accurate metadata for that specific page rather than the same generic values everywhere.

## Requirements *(mandatory)*

### Functional Requirements

**Site structure and navigation**

- **FR-001**: The site MUST provide all twelve named **public pages**: Home, About, Services, Products, Leadership, Careers, individual vacancy, News, individual news article, Contact, Not Found, and Server Error.
- **FR-001a**: The site MUST additionally serve two **non-content routes**, which are not public pages and are excluded from the sitemap, from the per-page metadata audit (FR-039), and from the site navigation:
  - the reserved employee-portal address (FR-049a);
  - a diagnostic status route carrying the environment status view from feature 001, which demonstrates that feature's FR-002 and FR-003.
  They are enumerated here so neither is introduced by an implementation choice, and so page-level checks have an unambiguous population.
- **FR-002**: Every page MUST render a shared header and footer. The header MUST contain the company identity, primary navigation, and the portal entry control; the footer MUST contain office locations, a general enquiry address, and secondary navigation.
- **FR-003**: Navigation MUST indicate the visitor's current location, and every browsable page named in FR-001 MUST be reachable from the header or footer within one interaction from any other page.
- **FR-004**: Every page MUST have a stable, human-readable address. Detail pages for vacancies and news items MUST use an address derived from their content rather than an opaque internal identifier, and that address MUST remain the same across seed runs.
- **FR-005**: The home page MUST include a hero section stating what the company does, and MUST summarize services, products, recent news, and current openings with links to their full pages.

**Content sourcing**

- **FR-006**: All company **record content** displayed on the site MUST come from the generated dataset. No service, product, profile, vacancy, news item, office, or address may be hard-coded in the presentation layer.
- **FR-006a**: **Interface copy is not record content** and is exempt from FR-006. Interface copy means navigation labels, button text, section headings, empty- and error-state wording, and the company positioning statement in the hero. The distinction is required because the dataset carries no positioning or tagline field — `companies` holds name, domain, status, and currency only — so FR-005's hero could not otherwise be satisfied without contradicting FR-006. Interface copy MUST NOT state any fact about the company that the dataset could contradict: no headcount, no client names, no figures, no office list.
- **FR-006b**: Every generated record the site displays MUST be rendered from the dataset at request time rather than copied into the presentation layer at build time, so a reseed is immediately visible.
- **FR-007**: The site MUST display only content classified `PUBLIC`. Content at any other classification MUST NOT be rendered, referenced, or retrievable through any address the site uses.
- **FR-008**: Where the dataset marks ordering, the site MUST honour it. News MUST appear newest-first by publication date; services, products, and leadership profiles MUST appear in their generated display order.
- **FR-008a**: The site MUST render generated content at any length the dataset produces. Content that is short but present — a one-word service summary, a single-sentence biography — MUST render as written; it is legitimate data, not an error. A field that is **empty or whitespace-only** MUST render a defined fallback in its place rather than a blank region, and MUST NOT collapse or misalign the layout around it. This is a presentation rule, not a data rule: the generator is not constrained, and no record is hidden because a field is short (which would contradict FR-011 and FR-013's requirement to list *every* record).
- **FR-009**: The site MUST display only content belonging to NileTech Solutions. No content belonging to the second tenant may appear on any page or in any response, under any address.
- **FR-009a**: The public endpoints MUST be **hard-scoped to NileTech**. The tenant MUST NOT be selectable by the caller — not by hostname, path, parameter, header, or body — so no request an anonymous visitor can construct causes the second tenant's content to be served. Delta Retail's `PUBLIC` content exists in the dataset solely as material for the isolation checks in FR-052.

**Page content**

- **FR-010**: The About page MUST describe the company and list every generated office with its city, country, and address, identifying the headquarters.
- **FR-011**: The Services page MUST list every generated service with its name, summary, and full description.
- **FR-012**: The Products page MUST list every generated public product offering with its name, tagline, and description, and MUST NOT display the internal sellable product catalog, its prices, or its tiers.
- **FR-013**: The Leadership page MUST list every generated leadership profile with the person's name, public title, and biography, and MUST expose no other attribute of that person.
- **FR-013a**: A leadership profile whose linked employee record cannot be resolved MUST be **omitted** from the public response, and the condition MUST be recorded so it is discoverable. The record MUST identify the *profile*, never the person — FR-013 forbids exposing any other attribute of that individual, and an identifier written into a diagnostic record is still an exposure. Omission rather than partial rendering is required because a profile displayed with a fallback where a real name belongs is worse than one absent: it presents fabricated content as company record content, which FR-006 prohibits. One unresolvable profile MUST NOT remove the Leadership page or its other profiles (FR-030).
- **FR-014**: The Careers page MUST list every open vacancy with its title, department, and office, and MUST allow filtering by office and by department.
- **FR-015**: Each vacancy MUST have its own page showing title, department, office, posting date, and full description.
- **FR-016**: The News page MUST list every generated news item with its headline and publication date, and MUST allow the visitor to reach every item when the list exceeds one screen.
- **FR-017**: Each news item MUST have its own page showing headline, publication date, and full body.
- **FR-018**: The Contact page MUST show every office with city, country, and address, plus a general enquiry address, alongside the enquiry form.

**Contact form**

- **FR-019**: The contact form MUST collect, at minimum, the sender's name, email address, subject, and message, bounded as follows so the limits are testable rather than implied: name 1–120 characters, email 3–254, subject 1–150, message 1–4000. A field consisting only of whitespace MUST be treated as empty.
- **FR-020**: The form MUST validate input before submission and again on the server. Client-side validation is a convenience; the server-side check is the control, and MUST NOT be bypassable by submitting directly.
- **FR-021**: Validation failures MUST identify the specific field at fault and state what is expected, MUST preserve everything the visitor already typed, and MUST be conveyed to assistive technology as well as visually.
- **FR-022**: A successful submission MUST be acknowledged with an explicit success state and MUST prevent an accidental duplicate submission of the same message. An identical submission arriving within **10 minutes** MUST be reported as success without creating a second record — the visitor's intent was satisfied by the first. A permanent uniqueness rule MUST NOT be used, because it would silently reject a genuine later enquiry that happened to repeat a short message.
- **FR-023**: Each accepted submission MUST be recorded as a tenant-scoped record carrying the company identifier, and MUST write an audit entry, consistent with the project's audit-by-default principle.
- **FR-023a**: An accepted submission MUST NOT be delivered anywhere — no email, no queued job, no notification, no external call. Storage plus the audit entry is the whole behaviour. Delivering a message on a visitor's behalf is a send action, which the constitution's approval principle gates, and no approver exists on a public site.
- **FR-023b**: Stored submissions MUST NOT be readable through any public endpoint or page. They are written by anonymous visitors and read only through a future authenticated surface.
- **FR-024**: Submitted content MUST be treated as untrusted: it MUST be length-bounded, MUST be stored without executing or interpreting any markup it contains, and MUST never be rendered as active content anywhere in the system.
- **FR-024a**: The contact form MUST display, at the point of collection, what the submitted data is used for and how long it is kept. The site collects a name and an email address from members of the public; collecting personal data without saying so is not acceptable merely because the company is fictional.
- **FR-024b**: Contact submissions MUST be retained for **90 days** and then deleted. The retention period MUST be stated in the notice required by FR-024a.
- **FR-024c**: Submitted personal data — sender name, email address, and message body — MUST NOT be written to application logs, at any level. Log entries about a submission MUST identify it by its stored record only.
- **FR-024d**: Contact submissions MUST be rate-limited per client address to **5 accepted submissions per hour**. A request beyond the limit MUST be refused with a designed, informative response that does not disclose the limit's internals, MUST NOT create a stored record, and MUST NOT be reported to the visitor as success. The bound exists because the form is an unauthenticated write path: FR-022's duplicate suppression stops one message repeating, and nothing else stops a script writing an unbounded number of different ones.

**Interface states**

- **FR-025**: Every **content region** MUST implement the states that can actually occur for it, and each MUST be visually distinct and announced to assistive technology:
  - A **server-rendered** region arrives with its content and has no loading state. It MUST implement **populated**, **empty**, and **error**.
  - A **client-fetched** region — the careers filter and the contact form are the only ones in this feature — MUST additionally implement **loading**.
  This distinction is required rather than cosmetic: demanding a loading state on a server-rendered page produces one that can never appear, which satisfies the words while verifying nothing.
- **FR-026**: An empty state MUST explain what is absent and offer a next action; it MUST NOT be an unexplained blank region.
- **FR-027**: An error state MUST explain that content could not be loaded and offer a manual retry, and MUST NOT expose internal failure detail. Retry MUST be visitor-initiated rather than automatic, so a failing dependency is not amplified by the site.
- **FR-027a**: A client-fetched region MUST show its loading state only after **150ms**, so a fast response does not produce a visible flash, and MUST become an error state after **10 seconds** without a response. Both thresholds exist so SC-014's prohibition on an indefinite loading state has a bound to test against.
- **FR-028**: The Not Found page MUST explain that the address does not exist and offer navigation back into the site.
- **FR-029**: The Server Error page MUST explain that something went wrong, MUST offer a route onward, and MUST NOT disclose stack traces, internal hostnames, connection strings, query text, or internal identifiers.
- **FR-030**: When one section of a page fails while others succeed, the failure MUST be contained to that section rather than replacing the entire page.

**Presentation and accessibility**

- **FR-031**: The site MUST present a consistent, professional enterprise visual identity — a defined type scale, colour palette, spacing system, and component styling applied uniformly across all pages.
- **FR-032**: Every page MUST be usable at three verified widths — **360px (mobile), 768px (tablet), and 1280px (desktop)** — with no clipped content and no overlapping elements at any of them. No page body may scroll horizontally at **any** width from 320px upward; the three verified widths are where layout is asserted, not the only widths that must work.
- **FR-033**: Every interactive element MUST be reachable and operable by keyboard alone, in a logical order, with a visible focus indicator.
- **FR-034**: The site MUST use semantic structure — landmark regions, a single main heading per page, correctly nested headings, labelled form controls, and descriptive link text.
- **FR-035**: Text and interactive elements MUST meet the WCAG 2.2 Level AA contrast minimums against their backgrounds in every state, including hover, focus, and error.
- **FR-036**: Every image MUST carry an appropriate text alternative, and decorative images MUST be marked as such.
- **FR-037**: Navigation MUST be operable by touch, pointer, and keyboard, and the mobile navigation MUST be dismissible and MUST trap focus only while open.
- **FR-038**: Dynamic changes — validation errors, successful submission, filter results, loading completion — MUST be announced to assistive technology rather than being conveyed by visual change alone.

**Search-engine metadata**

- **FR-039**: Every page MUST carry a page-specific title and description; no two distinct pages may share generic placeholder metadata.
- **FR-040**: Every page MUST carry social-preview metadata sufficient to render a titled, described preview when shared.
- **FR-041**: Detail pages MUST derive their metadata from the specific record they display.
- **FR-042**: The site MUST declare a canonical address per page and MUST publish a machine-readable index of its public pages for crawlers.
- **FR-043**: Addresses that do not exist MUST be reported as not found to crawlers, so unknown addresses are not indexed as valid content.

**Public boundary**

- **FR-044**: The public data endpoints serving this site MUST expose only `PUBLIC`-classified content of the NileTech tenant. Every field in every response MUST be an approved public field; internal identifiers of people, internal classifications, and audit metadata MUST NOT appear.
- **FR-045**: The set of approved public fields MUST be explicitly declared, so an added field is an explicit decision rather than an accidental disclosure through a widened response.
- **FR-046**: Anonymous requests to any private portal route MUST be refused with a designed response, and MUST NOT return partial content, internal redirects that leak structure, or raw errors.
- **FR-047**: Anonymous requests to any non-public data endpoint MUST be refused, and each refusal MUST write an audit entry recording what was attempted.
- **FR-047a**: The endpoint surface MUST be classified explicitly into three sets, because "non-public" is otherwise undefined and FR-051's check would have no population to test:
  - **Public** — the `/public/*` endpoints serving this site's content.
  - **Operational** — the health endpoints and the dataset manifest. These are anonymous **by design** and predate this feature: they carry liveness and provenance, never tenant-owned business data, and the status route depends on them. They are exempt from FR-047 and MUST remain free of business data.
  - **Non-public** — everything else. Refused anonymously per FR-047.
  Adding an endpoint to the operational set is an explicit change to this list, never a default.
- **FR-047b**: Auditing a refusal (FR-047) MUST be bounded per client address to **60 audit entries per hour**. Beyond that, further refusals from the same address within the window MUST still be refused and MUST be recorded as a **single coalesced entry** stating the count, rather than one entry each. This is not a relaxation of FR-047: every refusal remains refused and remains represented in the audit trail. The bound exists because FR-047 makes an anonymous request write a row, so an unauthenticated caller can otherwise grow `audit_logs` without limit — and burying real signal in that volume defeats the purpose the audit trail serves.
- **FR-048**: The public site MUST NOT require, accept, or store any visitor credential. It has no sign-in of its own; the portal entry control is a link to the portal, not an authentication surface.
- **FR-049**: The portal entry control MUST be present on every page and MUST lead to the reserved employee-portal address.
- **FR-049a**: That address MUST exist and MUST respond to anonymous visitors with a designed "sign-in not yet available" page explaining that the portal is not open yet and offering a route back into the public site. It MUST NOT present a credential field, MUST NOT return a raw error or blank screen, and MUST NOT reveal any portal structure beyond its own existence. When the portal is built, it replaces this page's contents without changing the address.

**Verification**

- **FR-050**: An automated check MUST confirm that every response from the public endpoints contains only approved public fields and no content above `PUBLIC` classification.
- **FR-051**: An automated check MUST confirm that anonymous access to private routes and non-public endpoints is refused, in every case, with zero successful accesses.
- **FR-052**: An automated check MUST confirm that no content belonging to the second tenant appears in any public response, including by searching for that tenant's distinctive marker phrases.
- **FR-053**: The site MUST conform to **WCAG 2.2 Level AA**. Automated accessibility checks MUST run against every page in continuous integration and MUST report zero violations. Automated checks do not cover every AA criterion, so a keyboard-only pass over each page MUST also be part of acceptance — a suite that only runs the automatable subset would report conformance it has not established.
- **FR-054**: An automated check MUST confirm every page renders its loading, empty, and error states, so a state that exists only in principle is detectable.
- **FR-055**: These checks MUST run in continuous integration on every change and MUST block the change when any of them fails.

### Key Entities

Every content entity below is generated by feature 001 and consumed read-only here. Only the
contact submission is new.

- **Service**: A service offering shown publicly — name, summary, full description, display order.
- **Public Product**: A product offering presented publicly — name, tagline, description, display order. Distinct from the internal sellable product catalog, which is never shown.
- **Leadership Profile**: A public profile of a company executive — the person's name, public title, biography, display order, and an optional photograph reference. Corresponds to a real generated executive.
- **News Item**: A dated public announcement — headline, body, publication date.
- **Vacancy**: An open position — title, description, posting date, open/closed state, owning department, and office.
- **Office**: A physical site — city, country, address, headquarters flag.
- **Contact Submission** *(new)*: A message from a public visitor — sender name, email address, subject, message body, submission timestamp, and the owning company. Tenant-scoped like every other record.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A first-time visitor can state what NileTech does, name at least two of its services, and find where it has offices, within 60 seconds of arriving, without using site search.
- **SC-002**: All twelve pages are reachable and render without error, with 100% of displayed company content traceable to a generated record and zero placeholder or lorem-ipsum text.
- **SC-003**: A candidate can go from the site root to the full description of a specific open role in three interactions or fewer.
- **SC-004**: Every page renders correctly at 360px, 768px, and 1280px with zero clipped text and zero overlapping elements, and no page body scrolls horizontally at any width from 320px upward.
- **SC-005**: Every page passes the automated WCAG 2.2 Level AA checks with zero violations **and** passes the keyboard-only traversal in FR-053. Neither alone establishes conformance — automation covers only part of AA — so both are required for this criterion to be met.
- **SC-006**: 100% of contact submissions with invalid input are refused with a field-specific message, and 0% of invalid submissions are accepted by the server when client-side validation is bypassed.
- **SC-007**: A valid contact submission produces a visible success confirmation and exactly one stored record — duplicate submission of the same message produces no second record, and zero messages are delivered anywhere. Because FR-023b forbids a public read path for submissions, this criterion is verified through **privileged database access in the test suite**, not through the public surface.
- **SC-008**: Anonymous access to private portal routes and non-public data endpoints is refused in 100% of attempts, with zero partial responses and zero raw errors.
- **SC-009**: Public endpoint responses contain zero fields outside the declared approved-public set and zero content above `PUBLIC` classification.
- **SC-010**: Cross-tenant probes against the public site return zero results from the second tenant, in every populated store.
- **SC-011**: Every page carries a unique, page-specific title and description, and detail pages derive theirs from the record displayed — zero pages share generic placeholder metadata.
- **SC-012**: Every content-loading page demonstrably renders all four states (loading, populated, empty, error), verified by automated test rather than by inspection.
- **SC-013**: The Server Error and Not Found pages disclose zero internal identifiers, hostnames, stack traces, or query text.
- **SC-014**: The site's main content becomes visible to a visitor on a typical connection within 3 seconds, and no page presents an indefinite loading state without either resolving or showing an error.
- **SC-015**: All of the above checks run automatically on every change and block the change on failure.
- **SC-016**: The anonymous write paths are bounded and the bounds are demonstrated: a client exceeding FR-024d's submission limit creates zero further stored records, and a client exceeding FR-047b's audit limit still has every request refused while producing one coalesced audit entry rather than one per request. Public reads are unaffected at any rate.

## Scope Boundaries

**In scope**: the twelve public pages, their content sourced from the generated dataset, the
contact form and its stored submissions, the public data endpoints that serve the site, the
public-boundary enforcement in FR-044 through FR-049, and the automated verification in FR-050
through FR-055.

**Out of scope** — these remain on feature 001's carry-forward list and are **not** delivered
here:

- Authentication, the login flow, and the request-time authorization policy engine (001 decision D1). This feature adds a link to the portal, not a way in.
- The private employee portal itself — the second mandatory surface.
- Chunking, embedding, and indexing of the seeded documents, and the semantic cross-tenant leak test that becomes possible once the vector store holds content (001 decision D2).
- Binary document formats (001 decision D3) and the synthetic code repository (001 decision D4).
- A public site for the second tenant. Its public content exists in the dataset and is used here only as isolation-test material.
- Any content-management capability. Site content changes only by regenerating the dataset.
- Outbound email. See Assumptions.

## Assumptions

**Content and data**

- The site renders the **NileTech** tenant only, and the tenant is fixed rather than resolved from the request (FR-009a). The second tenant's public content exists in the dataset and is used here solely as material for cross-tenant isolation tests.
- All content comes from feature 001's dataset at its committed seed, so the site's content is deterministic and its pages are reproducible across environments.
- Leadership photographs are **not** generated by feature 001. Profiles render with a designed placeholder rather than a photograph, and this feature introduces no image assets.
- News items and vacancies carry no human-readable slug in the dataset. A stable, content-derived address is derived for each, and that derivation must itself be deterministic so links do not move between seed runs.
- All content is in English. Generated names reflect the Egypt and UAE setting and must render correctly, but the site is not translated or localized.
- Content is read-only. There is no editorial workflow, no draft state, and no scheduled publication.

**Behaviour**

- Contact submissions are **stored and audited, never delivered** (FR-023a). No mail infrastructure exists, and sending on a visitor's behalf is a send action the constitution's approval principle gates — with no approver on a public site. Submissions are recorded for a future authenticated surface to read.
- The contact form is the only write path on the public site. Every other interaction is a read.
- The site is public and unauthenticated by design; it holds no session and sets no identifying cookie.
- Search-engine metadata is generated per page from the record displayed. Neither analytics nor third-party tracking is introduced.

**Boundary**

- The employee portal does not exist yet. The portal entry control points at its reserved address, which serves a designed "sign-in not yet available" page and refuses anonymous access (FR-049a). Reserving the address now means the FR-046 boundary is enforced and tested before the portal exists, rather than arriving with it.
- Public endpoints serve only approved public fields, declared explicitly rather than derived by omission, so a later schema change cannot widen a response by accident.

**Inherited constraints** *(from the project constitution and blueprint — not decisions made by this specification)*

- The public website is a mandatory surface and must not expose any internal data.
- No frontend feature is complete without responsive layout, accessibility, and loading, empty, error, and access-denied states.
- Every endpoint defines typed request and response models, validated before business logic.
- Every tenant-owned artifact carries and is filtered by its company identifier.
- Consequential operations write audit records.
- The whole system runs under Docker Compose from a single documented command.

## Resolved Decisions

The five decisions that materially affected scope or the security boundary were settled in the
2026-08-02 clarification session recorded above: tenant scope (FR-009a), portal entry behaviour
(FR-049a), contact submission handling (FR-023a, FR-023b), accessibility conformance (FR-053),
and the verified responsive widths (FR-032). No open questions remain.
