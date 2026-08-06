"""Shared pytest fixtures.

Determinism note: the environment is normalised here so a developer's local
timezone or locale cannot change a test outcome. Generation code must not read
these anyway (FR-012), but a test that passes only in one timezone is worse than
no test at all.

Host note: the suite runs on the host machine while the stores run in Compose, so
store hostnames default to `localhost` unless the caller has already set them (CI
runs inside the network and sets its own). Unit tests never connect, so this is
harmless for them.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Compose publishes these on the host, so tests reach the stores through localhost.
_STORE_HOST_DEFAULTS = {
    "POSTGRES_HOST": "localhost",
    "REDIS_HOST": "localhost",
    "QDRANT_HOST": "localhost",
    "MINIO_ENDPOINT": "localhost:9000",
}

#: `uv run` resolves first-party packages through pytest's pythonpath, but a
#: subprocess needs it spelled out.
SEED_PYTHONPATH = os.pathsep.join(
    str(REPO_ROOT / part) for part in ("packages/core/src", "scripts/seed/src")
)

# Applied at *import* time, not in the fixture below, and that ordering is the whole
# point. `eaios_core.settings.get_settings` is `lru_cache`d, and importing
# `eaios_worker.celery_app` — which `tests/security/test_job_tenancy.py` does at
# module level — calls it during collection. A fixture runs too late: by then the
# cache already holds the in-container hostnames from `.env`, every store lookup
# resolves `minio`/`postgres` from the host and fails, and the affected tests skip
# themselves with "database unavailable". Sixty-nine security tests were skipping
# for exactly this reason while the suite reported success.
#
# conftest.py is imported before any test module, so setting them here means the
# first `get_settings()` call — whoever makes it — sees the host-side values.
for _key, _value in _STORE_HOST_DEFAULTS.items():
    os.environ.setdefault(_key, _value)


@pytest.fixture(autouse=True, scope="session")
def _pinned_environment() -> Iterator[None]:
    keys = ("TZ", "LANG", "LC_ALL", "PYTHONHASHSEED", *_STORE_HOST_DEFAULTS)
    previous = {key: os.environ.get(key) for key in keys}

    os.environ["TZ"] = "UTC"
    os.environ["LANG"] = "C.UTF-8"
    os.environ["LC_ALL"] = "C.UTF-8"
    for key, value in _STORE_HOST_DEFAULTS.items():
        os.environ.setdefault(key, value)

    # Discard anything cached during collection under different values. The
    # module-level block above should make this a no-op; keeping it means a future
    # import-time `get_settings()` cannot silently reintroduce the problem.
    from eaios_core.settings import get_settings

    get_settings.cache_clear()

    yield

    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def run_seed_cli(*args: str, timeout: int = 900) -> subprocess.CompletedProcess[str]:
    """Invoke `eaios-seed` as a subprocess and return the completed process.

    Invoked as ``python -m`` rather than through the console script: Windows
    Application Control commonly blocks the ``.exe`` shims inside a virtualenv
    while allowing the interpreter, and CI must behave the same way locally.
    """
    env = {**os.environ, "PYTHONPATH": SEED_PYTHONPATH, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, "-m", "eaios_seed.cli", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
        env=env,
    )


@pytest.fixture(scope="session")
def seed_cli():  # type: ignore[no-untyped-def]
    """Expose :func:`run_seed_cli` to tests that drive the generator."""
    return run_seed_cli


@pytest.fixture(scope="module")
def client():  # type: ignore[no-untyped-def]
    """The API, in-process, with its real middleware and exception handlers.

    Defined here rather than in a helper module the tests import, because importing a
    fixture and then naming it as a parameter is a redefinition — ruff's F811 flags it
    on every test in every file that does it, which is forty-odd warnings saying
    nothing. A conftest fixture is found by name with no import at all.

    In-process rather than over HTTP to the container: these suites check *decisions*,
    and the same ASGI app gives identical middleware, handlers, and routing without a
    rebuild between every change. The deployed path is covered by Playwright.
    """
    from fastapi.testclient import TestClient

    from eaios_api.main import create_app

    from .security.auth_helpers import credentials_are_provisioned

    if not credentials_are_provisioned():
        # Provision rather than skip, because "no credentials" is the *normal* state
        # partway through a suite run: `test_migrations`, `test_seed_refusal`, and
        # `test_runtime_table_integration` all reset the environment, and reset
        # truncates `user_credentials` with every other runtime table. All three sort
        # before `test_session_expiry`, so a full integration pass used to skip every
        # authentication test and still report success.
        #
        # Skipping was the wrong shape of answer to a recoverable condition. The
        # recovery is one documented command and it is what a developer would run.
        result = run_seed_cli("credentials")
        if result.returncode != 0 or not credentials_are_provisioned():
            pytest.skip(
                "could not provision credentials; run `make up && make seed`"
                f" (exit {result.returncode})"
            )

    with TestClient(create_app(), raise_server_exceptions=False) as session:
        yield session


#: Used only when the environment is empty and the suite has to choose for itself.
#: `smoke` because provisioning from nothing should be fast; a developer who wants
#: the full dataset seeds it themselves and the suite then follows.
#:
#: Overridable with `EAIOS_TEST_PROFILE=full`. `tests/e2e/test_clean_startup.py`
#: runs `docker compose down -v`, so a whole-suite run always ends up back at the
#: fallback — without this, the SC-005 assertions could only ever be exercised by
#: CI's dedicated full-profile job, never locally.
FALLBACK_PROFILE = os.environ.get("EAIOS_TEST_PROFILE", "smoke")


def environment_profile(default: str = FALLBACK_PROFILE) -> str:
    """The profile the live environment was actually seeded with.

    The suite used to pass ``--profile smoke`` unconditionally while the CLI — and
    therefore `make seed`, the documented command — defaults to ``full``. Against a
    full environment that made every reseed a silent downgrade, and it made
    `test_reset_and_reseed_reproduce_the_same_fingerprint` fail with "generation is
    not deterministic (SC-002)": an accusation levelled at the generator for what
    was really the test changing profiles underneath itself.

    Reading the manifest is the same thing `verify` does, and for the same reason —
    the environment knows what it is, and a flag that disagrees with it is a lie
    the tooling should not have to honour.
    """
    from sqlalchemy import text

    from eaios_core.db import create_owner_engine

    try:
        engine = create_owner_engine()
        with engine.connect() as conn:
            row = conn.execute(text("SELECT profile FROM dataset_manifest LIMIT 1")).first()
    except Exception:  # pragma: no cover - environment guard
        return default
    return str(row[0]) if row and row[0] else default


#: When set, a skipped test fails the run. Intended for CI, where every dependency this
#: suite guards against is guaranteed present.
#:
#: The environment guards throughout these files — "API is not running", "environment not
#: seeded", "Docker unavailable" — are right for a laptop and dangerous in CI, because a
#: step that skips every test in a file reports green. That is not hypothetical here:
#: `tests/e2e/test_clean_startup.py` runs `docker compose down -v`, and it sorts first, so
#: `test_credentials_lifecycle.py` met an unseeded database and skipped itself — the
#: entire authentication lifecycle suite, passing while checking nothing.
_NO_SKIPS = os.environ.get("EAIOS_NO_SKIPS") == "1"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(  # type: ignore[no-untyped-def]
    item: pytest.Item, call: pytest.CallInfo[None]
):
    """Turn a skip into a failure when `EAIOS_NO_SKIPS=1`.

    Applied at report time rather than by patching `pytest.skip`, so it catches every
    form: the function call, `pytest.mark.skipif`, and a fixture that skips during setup.
    `xfail` is deliberately untouched — it records a known failure rather than an absence
    of evidence.
    """
    outcome = yield
    if not _NO_SKIPS:
        return

    report = outcome.get_result()
    if report.outcome != "skipped" or hasattr(report, "wasxfail"):
        return

    # A skip report's `longrepr` is `(path, lineno, reason)`; a failure's is text.
    reason = report.longrepr[2] if isinstance(report.longrepr, tuple) else report.longrepr
    report.outcome = "failed"
    report.longrepr = (
        "skipped under EAIOS_NO_SKIPS=1 — in CI every dependency is present, so a skip"
        f" is an unchecked requirement rather than a passing one: {reason}"
    )
