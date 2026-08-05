"""Static guard: generation code may not read the wall clock (spec FR-012).

test_clock.py proves the pinned clock behaves. This test proves nobody bypassed it.
A single stray `datetime.now()` inside a generator would make the dataset depend on
when it was seeded, and the symptom — a fingerprint that differs by machine and by
day — is genuinely hard to trace back to its cause. Catching it statically is much
cheaper than catching it empirically.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]

# Directories where wall-clock access is forbidden outright.
GUARDED_ROOTS = [
    REPO_ROOT / "packages" / "core" / "src" / "eaios_core",
    REPO_ROOT / "scripts" / "seed" / "src" / "eaios_seed",
]

# The clock module is the one sanctioned place that may name these symbols, and
# the manifest records genuine run metadata (started_at/completed_at) which is
# deliberately excluded from the fingerprint.
EXEMPT_FILES = {"clock.py", "manifest.py"}

BANNED_ATTRIBUTES = {
    ("datetime", "now"),
    ("datetime", "utcnow"),
    ("datetime", "today"),
    ("date", "today"),
    ("time", "time"),
    ("time", "time_ns"),
    ("time", "monotonic"),
}
BANNED_NAMES = {"utcnow"}


def _python_files() -> list[Path]:
    files: list[Path] = []
    for root in GUARDED_ROOTS:
        if root.exists():
            files.extend(p for p in root.rglob("*.py") if p.name not in EXEMPT_FILES)
    return sorted(files)


def _violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            owner = node.value
            if isinstance(owner, ast.Name) and (owner.id, node.attr) in BANNED_ATTRIBUTES:
                found.append(f"{path.name}:{node.lineno} {owner.id}.{node.attr}()")
            elif isinstance(owner, ast.Attribute) and (owner.attr, node.attr) in BANNED_ATTRIBUTES:
                found.append(f"{path.name}:{node.lineno} {owner.attr}.{node.attr}()")
        elif isinstance(node, ast.Name) and node.id in BANNED_NAMES:
            found.append(f"{path.name}:{node.lineno} {node.id}")
    return found


def test_guarded_roots_exist() -> None:
    """A silent pass because the paths moved would defeat the whole test."""
    assert _python_files(), "no Python files found under the guarded roots"


def test_no_wall_clock_access_in_generation_code() -> None:
    violations = [v for path in _python_files() for v in _violations(path)]
    assert not violations, (
        "Wall-clock access found in determinism-critical code. Use "
        "eaios_core.clock.reference_date() instead:\n  " + "\n  ".join(violations)
    )


def test_no_naive_utcnow_import() -> None:
    offenders: list[str] = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "time":
                for alias in node.names:
                    if alias.name in {"time", "monotonic", "time_ns"}:
                        offenders.append(f"{path.name}:{node.lineno} from time import {alias.name}")
    assert not offenders, "\n  ".join(offenders)
