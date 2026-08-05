#!/usr/bin/env bash
# Block until every Compose service with a healthcheck reports healthy.
#
# `make up` promises a *ready* system, not a started one (spec FR-002, SC-001).
# Returning before the stores are accepting connections would push the failure
# into the next command, where it is harder to interpret.

set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-infrastructure/docker-compose.yml}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-300}"
POLL_SECONDS=3

services=$(docker compose -f "$COMPOSE_FILE" ps --services --filter "status=running")

# An empty service list must not read as success. Without this, running the script
# against a stopped stack reports "All services healthy" because the loop below has
# nothing to iterate over — the same false-ready failure this script exists to
# prevent, one level up.
if [[ -z "${services// /}" ]]; then
    echo "ERROR: no services are running. Start the stack first (make up)." >&2
    exit 1
fi

# One-shot containers are expected to run to completion and exit 0. Everything
# else exiting during the wait is a failure, not a pass.
ONE_SHOT="minio-init seed"

deadline=$(( SECONDS + TIMEOUT_SECONDS ))
while (( SECONDS < deadline )); do
    pending=()
    for service in $services; do
        cid=$(docker compose -f "$COMPOSE_FILE" ps -q "$service" 2>/dev/null || true)
        [[ -z "$cid" ]] && continue

        # Check liveness BEFORE health. A container that exits keeps reporting its
        # last health status, so a health-only check happily reports a dead service
        # as healthy — which is how `make up` once printed "Ready." while the API
        # had already crashed on startup.
        running=$(docker inspect -f '{{.State.Running}}' "$cid" 2>/dev/null || echo "false")
        exit_code=$(docker inspect -f '{{.State.ExitCode}}' "$cid" 2>/dev/null || echo "1")

        if [[ "$running" != "true" ]]; then
            if [[ " $ONE_SHOT " == *" $service "* && "$exit_code" == "0" ]]; then
                continue  # completed its job and exited cleanly
            fi
            echo "ERROR: service '$service' exited with code $exit_code while starting." >&2
            docker compose -f "$COMPOSE_FILE" logs --tail 40 "$service" >&2
            exit 1
        fi

        # Services without a healthcheck report "<no value>"; treat those as ready
        # once running rather than waiting forever on a check that will never come.
        state=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$cid" 2>/dev/null || echo "unknown")

        case "$state" in
            healthy|none) ;;
            unhealthy)
                echo "ERROR: service '$service' is unhealthy." >&2
                docker compose -f "$COMPOSE_FILE" logs --tail 40 "$service" >&2
                exit 1
                ;;
            *) pending+=("$service") ;;
        esac
    done

    if (( ${#pending[@]} == 0 )); then
        echo "All services healthy."
        exit 0
    fi

    echo "  waiting on: ${pending[*]}"
    sleep "$POLL_SECONDS"
done

echo "ERROR: timed out after ${TIMEOUT_SECONDS}s waiting for: ${pending[*]}" >&2
docker compose -f "$COMPOSE_FILE" ps >&2
exit 1
