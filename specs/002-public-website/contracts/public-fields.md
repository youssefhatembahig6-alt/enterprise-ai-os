# Approved public fields

Satisfies **FR-045**. This is the declared allowlist: the complete set of fields any public
response may contain. A field not listed here is not public, and adding one is a change to this
document plus a change to the test that reads it — never a side effect of a schema change.

`tests/security/test_public_field_allowlist.py` asserts that every public response's keys equal
the set below. The direction matters: the test fails on an **extra** key, not only a missing one.
A response that serialized a model and excluded what looked sensitive would fail open the moment
a column was added; this fails closed.

## Why this is a separate document

The public surface reads the same database that holds RESTRICTED payroll records, executive
contracts, and a second tenant's data. The distance between "public" and "catastrophic" is one
forgotten exclusion, so the safe shape is to enumerate what goes out rather than what stays in.

## Service — `GET /public/services`

| Field | Source | Notes |
|---|---|---|
| `name` | `services.name` | |
| `summary` | `services.summary` | |
| `description` | `services.description` | |
| `display_order` | `services.display_order` | Drives FR-008 ordering |

**Excluded**: `id`, `company_id`, `created_at`, `updated_at`.

## Public Product — `GET /public/products`

| Field | Source |
|---|---|
| `name` | `public_products.name` |
| `tagline` | `public_products.tagline` |
| `description` | `public_products.description` |
| `display_order` | `public_products.display_order` |

**Excluded**: `id`, `company_id`, timestamps. The internal `products` table is not readable
through any public endpoint — it is a different table and no public route touches it.

## Leadership Profile — `GET /public/leadership`

| Field | Source | Notes |
|---|---|---|
| `full_name` | `users.full_name` via `leadership_profiles.user_id` | The **only** column this surface reads from `users` |
| `public_title` | `leadership_profiles.public_title` | Not the employee's internal job title |
| `bio` | `leadership_profiles.bio` | |
| `display_order` | `leadership_profiles.display_order` | |

**Excluded, and why it matters**: `user_id` is an internal identifier for a real employee row
carrying salary band, hire date, country, manager, and employment type. Exposing it would hand an
anonymous visitor a key into the private data model even though the key alone returns nothing
today. Also excluded: `photo_key` (feature 001 generates no images; the interface uses a
placeholder), `email`, `department`, `country`, and every other `users` column.

## News Item — `GET /public/news`, `GET /public/news/{slug}`

| Field | Source | Notes |
|---|---|---|
| `slug` | derived | Deterministic; see `routes.md` |
| `headline` | `news_items.headline` | |
| `published_on` | `news_items.published_on` | Date only |
| `body` | `news_items.body` | **Detail response only** — the list response omits it |

**Excluded**: `id`, `company_id`, timestamps.

## Vacancy — `GET /public/vacancies`, `GET /public/vacancies/{slug}`

| Field | Source | Notes |
|---|---|---|
| `slug` | derived | |
| `title` | `vacancies.title` | |
| `department` | `departments.name` via `vacancies.department_id` | Name only |
| `office_city` | `offices.city` via `vacancies.office_id` | |
| `office_country` | `offices.country` | |
| `posted_on` | `vacancies.posted_on` | |
| `description` | `vacancies.description` | **Detail response only** |

**Excluded**: `id`, `company_id`, `department_id`, `office_id`, `is_open`. The open flag is a
filter applied server-side, not a field — closed vacancies are absent from the response entirely
(FR-014), so there is no state for a client to misread.

## Office — `GET /public/offices`

| Field | Source |
|---|---|
| `city` | `offices.city` |
| `country` | `offices.country` |
| `address` | `offices.address` |
| `is_headquarters` | `offices.is_headquarters` |

**Excluded**: `id`, `company_id`, `code`.

## Company — `GET /public/company`

| Field | Source | Notes |
|---|---|---|
| `name` | `companies.name` | |
| `domain` | `companies.domain` | Used for the general enquiry address |

**Excluded**: `id`, `company_id`, `slug`, `status`, `reporting_currency`.

## Contact submission — `POST /public/contact`

**Request** (all required): `sender_name`, `sender_email`, `subject`, `message`.

**Response**: `status` only. No echo of the submitted content, no identifier of the stored row.
An anonymous writer receives confirmation, not a handle.

**No read endpoint exists.** FR-023b forbids reading submissions publicly, and the router declares
no such route — the absence is structural rather than a filter that could later be relaxed.

## Global rules

1. No response contains a database identifier of any kind — not `id`, not a foreign key, not the internal `company_id`.
2. No response contains a `classification` value. Everything served is `PUBLIC` by construction; echoing the field would invite a client to reason about levels it should never see.
3. No response contains audit metadata, timestamps of record creation, or generator provenance.
4. No response contains a field sourced from a row whose classification is not `PUBLIC`.
5. The tenant is never named in a request and never varies by request (FR-009a).
