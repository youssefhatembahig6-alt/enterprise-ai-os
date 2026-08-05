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

## `make reset`

Destructive. It removes every row, object, vector, and cache entry.

```bash
docker compose -f infrastructure/docker-compose.yml --env-file .env \
  run --rm --no-deps -T seed reset --yes
```

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
