# Quickstart: NileTech Public Website

How to run the site and prove it works. Scenarios map to the spec's user stories and to the
verification requirements FR-050 through FR-055.

## Prerequisites

The website renders feature 001's seeded content, so the environment must be up **and seeded**.
Nothing here generates content.

```bash
make up
```

```bash
make seed
```

`make seed` uses the `full` profile by default — 200 employees, 6 services, 4 public products,
6 leadership profiles, 11 news items, 11 open vacancies, 3 offices. The `smoke` profile scales
those down and will make several counts below smaller; the assertions in the test suite read the
manifest rather than hard-coding numbers.

Confirm the data is there before blaming the site:

```bash
make verify
```

## Running

```bash
make up
```

The site is served by the `web` service. The API it reads is the existing `api` service — no new
container is introduced.

| Surface | Address |
|---|---|
| Public website | http://localhost:3000 |
| Public API | http://localhost:8000/public/… |
| API schema | http://localhost:8000/docs |
| Status shell (diagnostic, not a public page) | http://localhost:3000/status |

## Scenario 1 — The client journey (US1)

Open http://localhost:3000 and walk Home → Services → Products → About.

**Expect**: a hero stating what NileTech does; every service and product offering from the
dataset, in display order; the three offices — Cairo, Alexandria, Dubai — with their countries;
no placeholder or lorem text anywhere.

**Cross-check** that what you see is what the database holds:

```bash
curl -s http://localhost:8000/public/services | head -40
```

## Scenario 2 — Careers, filters, and detail (US2)

Open http://localhost:3000/careers.

**Expect**: only open vacancies, each with title, department, and office. Filter by office —
the applied filter is visible and removable, and the address carries it so the view is
shareable. Open one vacancy for its full description.

**Empty state**: combine filters that match nothing (an office and a department that never pair).
Expect an explanation and a way to clear the filter — not a blank region and not a silently
unfiltered list.

**Not Found**: open `/careers/does-not-exist`. Expect the Not Found page with a route back to
Careers, and a not-found status to a crawler:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/careers/does-not-exist
```

## Scenario 3 — News (US3)

Open http://localhost:3000/news. Expect newest-first ordering and every generated item reachable.
Open one for the full body. `/news/does-not-exist` behaves like the vacancy case above.

## Scenario 4 — Contact form (US4)

Open http://localhost:3000/contact.

1. Submit with an empty required field → refused, the field is named, nothing you typed is lost.
2. Enter a malformed email → the error names that field and says what is expected.
3. Submit a valid message → an explicit success state, and the form will not resubmit by accident.

**Prove the server is the control, not the browser** (FR-020) — bypass the interface entirely:

```bash
curl -s -X POST http://localhost:8000/public/contact -H 'content-type: application/json' -d '{"sender_name":"","sender_email":"not-an-email","subject":"","message":""}'
```

Expect `422` with field-addressed errors. A `202` here would mean client-side validation was the
only control.

**Prove nothing is delivered and nothing is publicly readable** (FR-023a, FR-023b): there is no
public read route for submissions. Confirm the row landed by looking at the database directly:

```bash
docker compose -f infrastructure/docker-compose.yml exec postgres psql -U eaios_owner -d eaios -c "SELECT sender_email, subject, submitted_at FROM contact_submissions ORDER BY submitted_at DESC LIMIT 5;"
```

## Scenario 5 — Leadership (US5)

Open http://localhost:3000/leadership. Expect every profile with name, public title, and
biography, and a designed placeholder where a photograph would be — feature 001 generates no
images.

**The disclosure check**: confirm no internal identifier of a real employee is in the payload.

```bash
curl -s http://localhost:8000/public/leadership | grep -c "user_id" || echo "0 — correct"
```

## Scenario 6 — The anonymous boundary (US6)

The portal entry control is in the header of every page. Following it reaches `/portal`, which
serves a designed "sign-in not yet available" page — no credential field, no raw error.

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/portal
```

**Non-public data must be refused.** The manifest endpoint is provenance rather than tenant data,
but any endpoint outside the declared public surface must not serve an anonymous caller:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/internal/documents
```

**Cross-tenant.** Delta Retail's marker phrase must appear in nothing the public site serves:

```bash
curl -s http://localhost:8000/public/news http://localhost:8000/public/services | grep -c "QUIXOTIC-BASALT-MANIFEST" || echo "0 — correct"
```

**Tenant is not selectable.** None of these may return Delta content:

```bash
curl -s -H 'X-Company: delta-retail' "http://localhost:8000/public/services?company=delta-retail" | grep -c "QUIXOTIC" || echo "0 — correct"
```

## Automated verification

```bash
make test
```

The checks specific to this feature:

| Command | Covers |
|---|---|
| `pnpm --filter @eaios/web test` | Component tests: states, form validation, navigation |
| `pnpm --filter @eaios/web e2e` | Playwright: navigation, 360/768/1280px, axe (WCAG 2.2 AA), keyboard-only pass |
| `uv run pytest tests/security/test_public_field_allowlist.py` | FR-044, FR-045, FR-050 |
| `uv run pytest tests/security/test_anonymous_refusal.py` | FR-046, FR-047, FR-051 |
| `uv run pytest tests/security/test_public_site_isolation.py` | FR-009a, FR-052 |
| `uv run pytest tests/integration/test_contact_submission.py` | FR-019–FR-024 |

## Confirming feature 001 still holds

This feature adds a table, which touches three of feature 001's guarantees (data-model §3). After
any work here, confirm none of them moved:

```bash
make verify
```

```bash
uv run pytest tests/e2e -m e2e
```

The dataset fingerprint must be unchanged. If submitting the contact form changes it, the new
table was not excluded from the fingerprint and `verify` will say so.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Pages render empty states everywhere | Environment is up but not seeded — run `make seed` |
| Site loads but every section shows an error | The `api` service is unreachable; check `make ps` and http://localhost:8000/health/ready |
| `verify` fails after using the contact form | `contact_submissions` is not excluded from the fingerprint (research R8) |
| `seed` refuses an apparently empty environment | A contact submission was written before seeding; run `make reset` |
| Counts smaller than this guide states | The environment holds the `smoke` profile — reseed with `--profile full` |
