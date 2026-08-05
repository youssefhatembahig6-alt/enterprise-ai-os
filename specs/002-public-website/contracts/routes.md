# Page routes and slug derivation

Satisfies **FR-004** (stable, human-readable addresses), **FR-042** (canonical address and
machine-readable index), and **FR-049** (reserved portal address).

## Public pages

| Address | Page | Source | In sitemap |
|---|---|---|---|
| `/` | Home | company, services, products, recent news, open vacancies | yes |
| `/about` | About | company, offices | yes |
| `/services` | Services | services | yes |
| `/products` | Products | public products | yes |
| `/leadership` | Leadership | leadership profiles | yes |
| `/careers` | Careers | open vacancies (filterable) | yes |
| `/careers/{slug}` | Vacancy detail | one vacancy | yes, one entry per open vacancy |
| `/news` | News | news items | yes |
| `/news/{slug}` | Article detail | one news item | yes, one entry per item |
| `/contact` | Contact | offices, company | yes |

## Non-content routes

| Address | Behaviour | In sitemap |
|---|---|---|
| `/portal` | Reserved. Serves the designed "sign-in not yet available" page to anonymous visitors (FR-049a). No credential field. The portal replaces this page's contents later **without changing the address**. | **no** |
| `/status` | Diagnostic. The migrated feature 001 status shell (research R2). Not in site navigation. | **no** |
| any unknown address | Not Found, reported as not found to crawlers (FR-043) | n/a |
| unhandled failure | Server Error, disclosing nothing internal (FR-029) | n/a |

`/portal` and `/status` are excluded from the sitemap and from the per-page metadata audit that
FR-039 requires, because neither is public content. The audit's page list is derived from the
sitemap, so the exclusion is expressed once.

## Filter addresses

`/careers?office=cairo&department=engineering`

Filters live in the query string so a filtered view is shareable and reproducible, which is the
spec's "deep link into a filtered list" edge case. Unknown filter values yield the empty state
described by FR-026 — not an error, and not a silently unfiltered list, which would show a
visitor more than they asked for and look like the filter had failed open.

## Slug derivation

Deterministic, computed in the API, never constructed by the frontend. See research R5.

```
slug = kebab(title-or-headline) + "-" + first6(sha256(entity + ":" + company_slug + ":" + natural_key))
```

- **kebab**: lowercase; non-alphanumeric runs collapse to a single hyphen; leading and trailing hyphens trimmed; truncated at 60 characters on a word boundary.
- **suffix**: six hex characters from a digest of the record's natural key — the same natural key feature 001 derives the record's UUID from, so the slug is as stable as the identifier.

Examples:

```
information-security-analyst-cairo-7f3a2c
niletech-opens-alexandria-delivery-centre-b41e09
```

**Why the suffix**: feature 001 generates repeated vacancy titles across offices, and its
organization generator appends numeric suffixes to collided emails — so collisions are known to
occur in this dataset, not merely possible. A title-only slug with a positional counter would
depend on iteration order, and two environments could assign the counter differently. The digest
depends only on the record, so it cannot.

**Round-tripping**: the API resolves a slug back to a record by recomputing candidate slugs
within the fixed tenant and matching, rather than by parsing the suffix. A slug for a record in
the other tenant therefore resolves to nothing and yields Not Found — the same outcome as a
slug that never existed, which is the correct one: a public visitor learns nothing about
whether a record exists elsewhere.

## Metadata per address

| Address | Title source | Description source |
|---|---|---|
| `/` | company name + positioning | company summary |
| `/careers/{slug}` | vacancy title + office | first sentences of the description |
| `/news/{slug}` | headline | first sentences of the body |
| others | page name + company name | page-specific summary |

Every address declares a canonical URL. Detail pages derive metadata from the record they
display (FR-041), so no two pages share generic placeholder text (FR-039).
