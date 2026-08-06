# Running the stack without `make`

`make` is not bundled with Git Bash on Windows. Either install it —

```bash
winget install ezwinports.make
```

— or use the equivalents below. They are exactly what the Makefile targets run.

Every command assumes you are at the repository root and have a `.env`:

```bash
cp infrastructure/.env.example .env
```

## Setting the compose file once

```bash
export COMPOSE_FILE=infrastructure/docker-compose.yml
export COMPOSE_ENV_FILE=.env
```

In PowerShell:

```powershell
$env:COMPOSE_FILE = "infrastructure/docker-compose.yml"
```

## `make up`

```bash
docker compose -f infrastructure/docker-compose.yml --env-file .env up -d --build
bash infrastructure/wait-for-healthy.sh
docker compose -f infrastructure/docker-compose.yml --env-file .env run --rm --no-deps -T api alembic upgrade head
```

Then check it:

```bash
curl -s localhost:8000/health/ready
```

## `make down` / `make clean`

```bash
# stop, keep data
docker compose -f infrastructure/docker-compose.yml --env-file .env down

# stop and DELETE all volumes
docker compose -f infrastructure/docker-compose.yml --env-file .env down -v
```

## `make seed` / `make verify` / `make fingerprint`

The generator runs in the `seed` service, which lives in the `tools` profile so it does not
start with the stack.

```bash
SEED="docker compose -f infrastructure/docker-compose.yml --env-file .env run --rm --no-deps -T seed"

$SEED seed
$SEED verify
$SEED fingerprint
```

## `make credentials`

Establishes sign-in credentials for every active seeded user. **Run it after `make
seed`, and again after `make reset`.**

```bash
docker compose -f infrastructure/docker-compose.yml --env-file .env \
  run --rm --no-deps -T seed credentials
```

The full order from a clean checkout is therefore three commands, not two:

```bash
make up && make seed && make credentials
```

The generator deliberately leaves `password_hash` unset (spec 003 FR-002a), so a freshly
seeded environment has a complete dataset and **nobody who can sign in**. That
separation is what keeps the dataset fingerprint stable: it is computed from the
in-process generated rows, not from the database, so a credential written afterwards
cannot move it. Hashing inside the seed would have needed a fixed salt — weakening the
hash by construction — and would have invalidated both committed fingerprints.

The command prints the password it used. It refuses to run unless `ENVIRONMENT=local`;
these are deliberately weak, shared, local-only placeholders for a demonstration
dataset, and there is no environment other than `local` where writing them would be
anything but a mistake.

Sign in at <http://localhost:3000/portal> with any seeded address — `make docs`
regenerates `docs/personas.md`, which lists them.

## `make reset`

Destructive. It removes every row, object, vector, and cache entry.

```bash
docker compose -f infrastructure/docker-compose.yml --env-file .env \
  run --rm --no-deps -T seed reset --yes
```

**Reset also clears credentials**, because they are runtime state like every other
non-generated row. Re-provision afterwards or nobody can sign in:

```bash
make reset && make credentials
```

The reset output says so too — a reset that silently leaves the portal unusable is the
kind of correct-but-invisible consequence this project keeps finding.

## `make test`

The test suite runs on the host, not in a container.

```bash
uv sync

uv run python -m pytest tests/unit        -m unit
uv run python -m pytest tests/integration -m integration
uv run python -m pytest tests/security    -m security
uv run python -m pytest tests/e2e         -m e2e
```

> **Windows:** invoke pytest as `python -m pytest`, not `pytest`. Application Control policies
> commonly block the console-script `.exe` shims inside a virtualenv while allowing the
> interpreter itself. The same applies to `ruff` and `mypy`.

## `make lint`

```bash
uv run python -m ruff check .
uv run python -m mypy packages/core/src apps/api/src services/worker/src
```

## PowerShell gotchas

Two aliases and one policy trip people up on Windows. None of them mean anything is broken.

**`curl` is not curl.** In PowerShell it aliases `Invoke-WebRequest`, which has no `-s` flag —
so `curl -s localhost:8000/health/ready` hangs prompting for `Uri:`. Press `Ctrl+C` and use:

```powershell
irm http://localhost:8000/health/ready | ConvertTo-Json   # Invoke-RestMethod, parses JSON
curl.exe -s http://localhost:8000/health/ready            # the real curl, alias bypassed
```

**Console-script shims are often blocked.** Windows Application Control commonly blocks the
`.exe` shims inside a virtualenv (`pytest.exe`, `ruff.exe`, `mypy.exe`) while allowing the
interpreter itself. Run modules instead:

```powershell
uv run python -m pytest tests/unit -m unit
uv run python -m ruff check .
uv run python -m mypy packages/core/src
```

**`&&` does not chain in Windows PowerShell 5.1.** Use `;` or separate lines.

## Useful while debugging

```bash
# what is running, and is it healthy?
docker compose -f infrastructure/docker-compose.yml --env-file .env ps

# follow logs for one service
docker compose -f infrastructure/docker-compose.yml --env-file .env logs -f api

# open a psql shell as the schema owner
docker compose -f infrastructure/docker-compose.yml --env-file .env \
  exec postgres psql -U eaios_owner -d eaios
```

## The employee portal

<http://localhost:3000/portal>. Sign in with any address from
[personas.md](personas.md) and the password `make credentials` printed.

What each persona reaches differs by their permission codes, which is the point:

| Persona | Sees |
|---|---|
| `employee.engineering` | their own HR profile; **no** "My team" entry at all |
| `manager.engineering` | their own profile, plus their direct reports and each report's profile |
| `hr.generalist` | anyone in NileTech, including compensation |
| `employee.delta` | only Delta Retail records — a NileTech identifier is *not found*, never *forbidden* |

Navigation is built from permission codes, never role names, and hiding an entry is
presentation only: the server refuses the address regardless of what was rendered. Try
`/portal/team` as `employee.engineering` to see both halves of that.

## The public website

The NileTech public site is served by the `web` service at **http://localhost:3000**
(feature 002). It is a production Next.js build rather than a dev server: dev mode
compiles each route on its first request, which would put a multi-second delay in front
of the first visitor to every page.

```bash
docker compose -f infrastructure/docker-compose.yml --env-file .env up -d --build web
```

The environment status view from feature 001 moved to **http://localhost:3000/status**.
It is a diagnostic route, not a public page.
