"""Cross-platform launcher for the Phase 0 benchmark (FR-035b, FR-035f, SC-018).

**Why a launcher and not a Makefile recipe.** The recipe used to export the import path
inline, and it was wrong in two ways at once:

* It joined the parts with `:`. On Windows `os.pathsep` is `;`, so the whole value
  collapsed into a single bogus entry and `eaios_core` was not resolvable at all.
* The parts were relative, so the target only worked when the caller happened to be
  standing in the repository root — the exact cwd assumption it claimed not to have.

Both are removed here by construction. The repository root is derived from **this file's
own location**, so it is correct from any working directory on any platform, and the parts
are joined with `os.pathsep` so they are correct on both.

**Why the test runs this and not a copy of it.** A test that rebuilds the import path
verifies the path it built, not the one the target exports — which is how the two defects
above survived a passing test. There is one path-construction in the repository and both
the Make target and the test go through it.

`PYTHONPATH` is **replaced**, never extended. An inherited value is exactly the ambient
dependence this exists to eliminate.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
from typing import Final

__all__ = ["ENTRY_MODULE", "build_environment", "import_roots", "main", "repository_root"]

#: The entry point. `__main__.py` under this module calls preflight first.
ENTRY_MODULE: Final[str] = "benchmarks.phase0"

#: First-party source roots, relative to the repository root. The repository root itself
#: is last so `benchmarks` resolves without relying on cwd being on `sys.path`.
IMPORT_ROOTS: Final[tuple[str, ...]] = (
    "packages/core/src",
    "apps/api/src",
    "services/worker/src",
    "scripts/seed/src",
    ".",
)


def repository_root() -> pathlib.Path:
    """The repository root, derived from this file rather than from the caller's cwd."""
    return pathlib.Path(__file__).resolve().parents[1]


def import_roots() -> list[pathlib.Path]:
    """Absolute import roots, in the checked-in order."""
    root = repository_root()
    return [(root / part).resolve() for part in IMPORT_ROOTS]


def build_environment(base: dict[str, str] | None = None) -> dict[str, str]:
    """The child environment: an absolute, platform-correct, non-inherited `PYTHONPATH`."""
    environment = dict(os.environ if base is None else base)
    environment["PYTHONPATH"] = os.pathsep.join(str(path) for path in import_roots())
    environment.setdefault("PYTHONIOENCODING", "utf-8")
    return environment


def main(argv: list[str] | None = None) -> int:
    """Run `python -m benchmarks.phase0` with the resolved import path."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    missing = [str(path) for path in import_roots() if not path.exists()]
    if missing:
        print(
            "the checked-in import roots do not exist; this launcher is not inside the"
            f" repository it expects: {missing}",
            file=sys.stderr,
        )
        return 2

    completed = subprocess.run(
        [sys.executable, "-m", ENTRY_MODULE, *arguments],
        env=build_environment(),
        # The repository root, so relative paths inside the benchmark resolve the same way
        # regardless of where the operator invoked the target from.
        cwd=str(repository_root()),
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())
