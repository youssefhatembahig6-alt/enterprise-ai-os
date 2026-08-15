"""The real benchmark target resolves its imports from anywhere (FR-011c, FR-035f, SC-018).

**What the earlier version of this file got wrong, and why it matters.** It rebuilt the
import path itself — parsed the parts out of the Makefile, joined them with `os.pathsep`,
resolved them absolute — and then asserted that *its own* construction worked. It did. The
Makefile's construction did not: the parts were joined with `:` on a platform whose
separator is `;`, and they were relative so the target only ran from the repository root.
Every assertion passed while the target was broken on the reference machine.

So this file does not build a path. It **runs the target** and reports what the target
does. Three properties follow:

* The child starts in a temporary directory **outside the repository**, so a cwd
  assumption fails rather than passing by luck.
* Inherited `PYTHONPATH` is **stripped**, so an ambient value cannot rescue it.
* Where `make` is unavailable — the `windows-latest` runner has none — the same
  `benchmarks/run_phase0.py` the target invokes is executed directly. One path
  construction, exercised by both callers; no test-only semantics.

The child is stopped at **preflight**. That is the deepest point reachable without a
seeded stack, and it is far enough: preflight runs after every first-party import has
resolved, so reaching it proves the import path works. It is also the shallowest point
that loads no weights.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
from typing import Final

import pytest

pytestmark = pytest.mark.unit

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[2]
MAKEFILE: Final[pathlib.Path] = REPO / "Makefile"
LAUNCHER: Final[pathlib.Path] = REPO / "benchmarks" / "run_phase0.py"
TARGET: Final[str] = "benchmark-phase0"

#: `benchmarks/phase0/__main__.py` returns this when preflight refuses. Reaching it means
#: every first-party import resolved and the stack was then found absent — which is the
#: expected state here, since these tests start nothing.
EXIT_PREFLIGHT_FAILED: Final[int] = 2

#: What the benchmark imports. Both are the canonical modules FR-035p forbids duplicating.
REQUIRED_IMPORTS: Final[tuple[str, ...]] = (
    "eaios_core.chunking",
    "eaios_core.embedding.bge_m3",
)


def _scrubbed_environment() -> dict[str, str]:
    """The caller's environment with every ambient import hint removed.

    **Preflight is forced to refuse.** This file proves the *import path* resolves, and it
    reaches preflight to prove it. What it must never do is proceed *past* preflight — on
    a developer machine with the stack up and weights provisioned, that would build a
    preview index and take a real measurement from inside a unit test. It did exactly that
    once: three stray run records and a manifest, written by `pytest tests/unit`.

    `PHASE0_POSTGRES_PORT` points the child at a closed port, so preflight refuses on
    every machine for the same reason. The result is deterministic whether or not the
    developer happens to have `make up` running.
    """
    environment = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    environment["PYTHONIOENCODING"] = "utf-8"
    # Weights are absent here and must never be fetched to make a test pass.
    environment["HF_HUB_OFFLINE"] = "1"
    environment["TRANSFORMERS_OFFLINE"] = "1"
    # Closed port: preflight fails first, before any index, any weight load, any sample.
    environment["PHASE0_POSTGRES_PORT"] = "1"
    return environment


def _run_target(*, cwd: pathlib.Path) -> subprocess.CompletedProcess[str]:
    """Run the real target from `cwd`, preferring `make` and falling back to the launcher.

    The fallback is not a second implementation: `make` invokes exactly this script with
    exactly these arguments, so both routes exercise the same path construction.
    """
    make = shutil.which("make")
    command = [make, "-f", str(MAKEFILE), TARGET] if make else [sys.executable, str(LAUNCHER)]
    return subprocess.run(
        command,
        cwd=str(cwd),
        env=_scrubbed_environment(),
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )


class TestTheTargetIsWiredToTheLauncher:
    """The declarative half — that the two callers really are the same code path."""

    def test_the_launcher_exists(self) -> None:
        assert LAUNCHER.is_file(), f"missing {LAUNCHER.relative_to(REPO)}"

    def test_the_target_invokes_the_launcher(self) -> None:
        recipe = MAKEFILE.read_text(encoding="utf-8")
        assert "benchmarks/run_phase0.py" in recipe, (
            "the Make target no longer invokes the launcher, so this file and the target"
            " would be exercising different path constructions — the failure mode that"
            " let a broken target pass a green test"
        )

    def test_the_target_does_not_build_its_own_path(self) -> None:
        recipe = MAKEFILE.read_text(encoding="utf-8")
        assert "BENCH_PYTHONPATH" not in recipe, (
            "the Makefile builds an import path again; there must be exactly one"
        )

    def test_the_launcher_runs_the_module_entry_point(self) -> None:
        from benchmarks.run_phase0 import ENTRY_MODULE

        assert ENTRY_MODULE == "benchmarks.phase0", (
            "the entry point must stay `python -m benchmarks.phase0`, so preflight is"
            f" always the first call: {ENTRY_MODULE}"
        )
        assert (REPO / "benchmarks" / "phase0" / "__main__.py").is_file()

    def test_the_launcher_uses_the_platform_separator(self) -> None:
        """The defect that made the old target unusable on Windows."""
        from benchmarks.run_phase0 import build_environment

        value = build_environment({})["PYTHONPATH"]
        assert os.pathsep in value, f"import path is not {os.pathsep!r}-joined: {value!r}"
        parts = value.split(os.pathsep)
        assert len(parts) == 5, f"expected five roots, got {len(parts)}: {parts}"

    def test_every_root_is_absolute_and_exists(self) -> None:
        from benchmarks.run_phase0 import import_roots

        for path in import_roots():
            assert path.is_absolute(), f"{path} is relative; it would follow the caller's cwd"
            assert path.exists(), f"{path} does not exist"

    def test_the_launcher_replaces_rather_than_extends_pythonpath(self) -> None:
        from benchmarks.run_phase0 import build_environment

        polluted = build_environment({"PYTHONPATH": "/somewhere/else"})
        assert "/somewhere/else" not in polluted["PYTHONPATH"], (
            "an inherited PYTHONPATH survived into the child, which is the ambient"
            " dependence this launcher exists to remove"
        )


class TestTheTargetRunsFromOutsideTheRepository:
    """The executable half — what actually happens when someone runs it."""

    @pytest.fixture(scope="class")
    def outside(self) -> pathlib.Path:
        with tempfile.TemporaryDirectory() as elsewhere:
            yield pathlib.Path(elsewhere)

    def test_it_reaches_preflight_from_outside_the_repository(self, outside: pathlib.Path) -> None:
        result = _run_target(cwd=outside)
        combined = result.stdout + result.stderr

        assert "ModuleNotFoundError" not in combined, (
            "the target could not resolve its own modules from outside the repository.\n"
            f"cwd: {outside}\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "preflight failed" in combined, (
            "the target did not reach preflight, so the import path did not resolve.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_it_stops_at_preflight_rather_than_loading_weights(self, outside: pathlib.Path) -> None:
        result = _run_target(cwd=outside)
        assert result.returncode == EXIT_PREFLIGHT_FAILED, (
            f"expected exit {EXIT_PREFLIGHT_FAILED} (preflight refused), got"
            f" {result.returncode}. Anything else means it either failed earlier — an"
            " import — or proceeded past the gate.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "no BGE-M3 weights" not in result.stderr, (
            "the embedder was constructed; preflight must refuse before that"
        )

    def test_it_takes_no_measurement(self, outside: pathlib.Path) -> None:
        """A unit test must not become a benchmark run.

        Guards the regression directly: with the stack up and weights provisioned, this
        file once ran three real measurements and wrote three run records.
        """
        result = _run_target(cwd=outside)
        combined = result.stdout + result.stderr
        assert "recorded " not in combined, (
            "the child wrote a run record, so it proceeded past preflight and measured"
            f" something:\n{combined}"
        )
        assert "p95=" not in combined, "the child reported a measured figure"

    def test_it_reaches_preflight_from_inside_the_repository_too(self) -> None:
        result = _run_target(cwd=REPO)
        assert result.returncode == EXIT_PREFLIGHT_FAILED, (
            f"exit {result.returncode} from inside the repository.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


class TestTheImportsResolveUnderTheTargetsOwnPath:
    """Imports checked through the launcher's environment, not one this file invents."""

    @staticmethod
    def _child(code: str, *, cwd: pathlib.Path) -> subprocess.CompletedProcess[str]:
        from benchmarks.run_phase0 import build_environment

        environment = build_environment(_scrubbed_environment())
        return subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(cwd),
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )

    @pytest.mark.parametrize("module", REQUIRED_IMPORTS)
    def test_the_module_imports_from_outside_the_repository(self, module: str) -> None:
        with tempfile.TemporaryDirectory() as elsewhere:
            result = self._child(f"import {module}", cwd=pathlib.Path(elsewhere))
        assert result.returncode == 0, (
            f"`{module}` does not import under the target's own path.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_without_that_path_the_import_fails(self) -> None:
        """Falsification: if it imports anyway, this file measures an installed copy."""
        with tempfile.TemporaryDirectory() as elsewhere:
            result = subprocess.run(
                [sys.executable, "-c", "import eaios_core.chunking"],
                cwd=elsewhere,
                env=_scrubbed_environment(),
                capture_output=True,
                text=True,
                check=False,
                timeout=120,
            )
        assert result.returncode != 0, (
            "`eaios_core` imported with no PYTHONPATH from outside the repository, so"
            " these tests are checking an installed copy rather than the checkout"
        )


class TestTheRuntimeIsReachableAndItsAbsenceIsDetectable:
    """T008 attacks the *manifest*; this attacks the *runtime*, without uninstalling it."""

    @staticmethod
    def _blocker_directory(stack: tempfile.TemporaryDirectory[str]) -> pathlib.Path:
        """A directory whose `sitecustomize.py` hides the model runtime from the child.

        Hiding rather than uninstalling: a falsification that mutates the developer's
        environment is one nobody will run twice, and one that fails half-applied leaves
        the machine broken.
        """
        directory = pathlib.Path(stack.name)
        (directory / "sitecustomize.py").write_text(
            "import sys\n"
            "class _Block:\n"
            "    def find_spec(self, name, path=None, target=None):\n"
            "        if name.split('.')[0] in {'torch', 'transformers'}:\n"
            "            raise ModuleNotFoundError(name)\n"
            "        return None\n"
            "sys.meta_path.insert(0, _Block())\n",
            encoding="utf-8",
        )
        return directory

    def test_the_runtime_is_installed(self) -> None:
        from benchmarks.run_phase0 import build_environment

        with tempfile.TemporaryDirectory() as elsewhere:
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from eaios_core.embedding import bge_m3;"
                    " missing = bge_m3.missing_runtime();"
                    " raise SystemExit('missing: ' + ','.join(missing) if missing else 0)",
                ],
                cwd=elsewhere,
                env=build_environment(_scrubbed_environment()),
                capture_output=True,
                text=True,
                check=False,
                timeout=300,
            )
        assert result.returncode == 0, (
            "the pinned BGE-M3 runtime is not installed, so the benchmark cannot embed."
            f" Declared in packages/core/pyproject.toml; install with `uv sync`.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_hiding_the_runtime_is_detected(self) -> None:
        """The falsifiable half. Without this the assertion above can never fail."""
        from benchmarks.run_phase0 import build_environment

        with tempfile.TemporaryDirectory() as blocker_dir:
            stack = tempfile.TemporaryDirectory()
            stack.name = blocker_dir  # type: ignore[misc]
            blocker = self._blocker_directory(stack)

            environment = build_environment(_scrubbed_environment())
            environment["PYTHONPATH"] = str(blocker) + os.pathsep + environment["PYTHONPATH"]

            with tempfile.TemporaryDirectory() as elsewhere:
                result = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        "from eaios_core.embedding import bge_m3;"
                        " missing = bge_m3.missing_runtime();"
                        " raise SystemExit('missing: ' + ','.join(missing) if missing else 0)",
                    ],
                    cwd=elsewhere,
                    env=environment,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=300,
                )

        assert result.returncode != 0, (
            "the runtime was hidden from the child and `missing_runtime()` still reported"
            " nothing missing, so that check cannot detect an unprovisioned machine"
        )
        assert "torch" in (result.stdout + result.stderr), (
            "the absence was detected but not named; 'the benchmark cannot embed' and"
            f" 'torch is not installed' are different messages: {result.stdout}{result.stderr}"
        )
