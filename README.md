# Enterprise AI Operating System

A tenant-isolated, permission-aware AI platform over private company knowledge.

**Features 001-003 are complete**: the monorepo and one-command local environment, a
deterministic generator for two isolated synthetic companies, the public website, and an
authenticated employee portal with request-time authorization. Verified by CI run
[31443872819](https://github.com/youssefhatembahig6-alt/enterprise-ai-os/actions/runs/31443872819)
at commit `429fdcb` — 7/7 jobs green. **Feature 004 has not started**; document ingestion,
embeddings, RAG, chat streaming, agents, and write actions with their approval gate are
all out of scope so far.

- **Blueprint** (what we are building): [`docs/Enterprise_AI_OS_EDITED.html`](docs/Enterprise_AI_OS_EDITED.html)
- **Engineering rules** (how we build it): [`.specify/memory/constitution.md`](.specify/memory/constitution.md)
- **Completed features**: [`001-foundation-tenant-seed`](specs/001-foundation-tenant-seed/) ·
  [`002-public-website`](specs/002-public-website/) ·
  [`003-auth-portal-shell`](specs/003-auth-portal-shell/)
- **Documentation index**: [`docs/README.md`](docs/README.md)

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Docker Desktop (or Engine + Compose v2) | 24+ | Allocate ≥ 8 GB RAM |
| `make` | any | **Not bundled with Git Bash.** Windows: `winget install ezwinports.make`, or use the raw `docker compose` commands in [docs/running.md](docs/running.md) |
| Git | 2.40+ | See the Windows note below |

Python and Node live inside containers — a clean machine needs no language toolchain to run
the stack. They are only required to run the test suite locally.

> **Windows: check this before anything else.**
>
> ```bash
> git config core.autocrlf
> ```
>
> It must be `false` or `input`. The repository ships `.gitattributes` with `* text eol=lf`
> because generated documents must be byte-identical across machines. If Git rewrites files
> to CRLF on checkout, the dataset fingerprint diverges and the failure looks like a
> mysterious whole-dataset mismatch rather than a line-ending problem.

## Getting it running

```bash
make up && make seed && make credentials
```

`make up` builds and starts all nine Compose services, applies migrations, and blocks
until every dependency reports healthy. `make seed` generates the deterministic dataset.

`make credentials` is the third step and it is not optional if you want the portal: the
generator deliberately leaves `password_hash` unset (spec 003 FR-002a), so a seeded
environment has a complete dataset and nobody who can sign in. Separating the two is
what keeps the dataset fingerprint stable — it is computed from the generated rows, not
from the database, so a credential written afterwards cannot move it.

The command prints the password it used, and refuses to run unless `ENVIRONMENT=local`.

- Public website — <http://localhost:3000>
- Employee portal — <http://localhost:3000/portal> (any seeded address; see
  `docs/personas.md`)
- API — <http://localhost:8000/docs>

```bash
make reset
```

Destroys every row, object, vector, and cache entry in the local environment and regenerates
the full dataset. Requires typed confirmation and refuses to run outside a local environment.
**Follow it with `make credentials`** — reset clears those too.

Supporting targets: `make down` · `make clean` · `make seed` · `make credentials` ·
`make verify` · `make test` · `make lint`. Run `make` with no arguments for the full list.

## Layout

```text
apps/api          FastAPI service. Modules: health (liveness, readiness), public
                  (anonymous website content), auth (sign-in, sign-out, session),
                  authz (the five-layer policy engine and its audit trail),
                  me (current user, access context, own HR profile, direct reports),
                  hr (a report's profile, and compensation behind its own permission)
apps/web          Next.js site: the eight public content pages, a diagnostic status
                  route, and the authenticated portal at /portal — sign-in, home,
                  own HR profile, team, a report's profile, and access-denied
packages/core     Shared domain: models, deterministic IDs, fingerprinting, tenant keys,
                  password hashing, and the authorization policy types
packages/ui       Shared React primitives and state patterns (empty, error,
                  access-denied, session-expired, skeleton)
packages/contracts Generated TypeScript API types, checked against the live schema
services/worker   Celery worker (tenant-attributed jobs)
scripts/seed      Deterministic synthetic-enterprise generator, plus `credentials`
infrastructure    Docker Compose, Postgres roles, MinIO and Qdrant bootstrap
tests             unit · integration · security · e2e
```

## Running the tests

The stores are only needed for the integration, security, and e2e lanes.

```bash
uv sync
uv run python -m pytest tests/unit -m unit
```

**Windows notes** (see [docs/running.md](docs/running.md) for the full list):

- Invoke tools as modules — `python -m pytest`, `python -m ruff` — because Application
  Control commonly blocks the console-script `.exe` shims inside a virtualenv.
- `curl` in PowerShell is an alias for `Invoke-WebRequest` and does not accept `-s`. Use
  `irm http://localhost:8000/health/ready` or `curl.exe`.

## Two things that are easy to get wrong

**Never read the wall clock in generation code.** All dates derive from a pinned reference
date (`2026-06-30`). A single `datetime.now()` makes the dataset depend on *when* it was
seeded, so two developers get different data. `tests/unit/test_no_wallclock.py` enforces this
statically.

**Never build a storage or cache key by hand.** Use `eaios_core.keys`. The builders refuse to
produce a key without a tenant prefix, which is what makes a cross-tenant collision
impossible to construct rather than merely detectable afterwards.
