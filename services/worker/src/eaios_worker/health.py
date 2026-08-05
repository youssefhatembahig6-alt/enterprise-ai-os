"""Worker-side liveness check, used by the container healthcheck.

Named in the plan's project structure and missing until now — the Compose
healthcheck instead shelled out to `celery -A ... inspect ping -d celery@$HOSTNAME`,
which put the probe's logic in a YAML string where nothing could test it.

This is deliberately *not* the same question `eaios_core.clients.stores.check_worker`
answers, and the difference matters:

* `check_worker` asks "is **any** worker draining the queue?" — that is what the API
  reports on `/health/ready`, because an operator wants to know whether background
  work moves at all.
* `worker_ping` asks "is **this** container's worker alive?" — that is what Compose
  must restart on. A broadcast ping would answer yes while a second replica carried
  the load and this one was wedged, and the restart would never fire.

Run as ``python -m eaios_worker.health``: exit 0 when alive, 1 otherwise.
"""

from __future__ import annotations

import socket
import sys

from eaios_core.settings import get_settings

__all__ = ["main", "worker_ping"]


def node_name(hostname: str | None = None) -> str:
    """The Celery node name for this container, matching the worker's default."""
    return f"celery@{hostname or socket.gethostname()}"


def worker_ping(timeout: float | None = None) -> bool:
    """True when *this* container's worker answers a targeted ping."""
    from .celery_app import celery_app

    budget = timeout if timeout is not None else get_settings().health_timeout_seconds
    try:
        replies = celery_app.control.ping(destination=[node_name()], timeout=budget, limit=1)
    except Exception:
        # A broker that cannot be reached means this worker is not doing work,
        # which is the same operational answer as a worker that never replied.
        return False
    return bool(replies)


def main() -> None:
    alive = worker_ping()
    if not alive:
        # Written straight to stderr rather than through structlog: Docker surfaces
        # a failing healthcheck's output verbatim, and a JSON envelope would bury
        # the one line an operator reads in `docker inspect`.
        sys.stderr.write(f"{node_name()} did not answer a ping\n")
    raise SystemExit(0 if alive else 1)


if __name__ == "__main__":
    main()
