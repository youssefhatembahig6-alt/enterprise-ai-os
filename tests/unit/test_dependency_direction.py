"""Dependency direction between workspace members (spec 001 FR-001a).

The rule, and the reason it is written down rather than assumed:

* ``packages/*`` MUST NOT import from ``apps/*``, ``services/*``, or ``scripts/*``
* ``apps/*``, ``services/*``, and ``scripts/*`` MAY import from ``packages/*`` but
  MUST NOT import from one another
* code needed by two members moves **down** into ``packages/``, never sideways

This existed as folklore until it was needed. During feature 002 the seed loader
had to clear Redis keys that the API writes, and nothing stated that
``scripts/seed`` may not import from ``apps/api``. The key pattern was moved into
``packages/core`` because that seemed right — a judgement call that happened to
match the rule nobody had written. The next feature adds a second application and a
second API surface, which is when an unwritten layering rule usually breaks.

**Scope.** Source directories only. Tests are deliberately exempt: this file
imports from `eaios_seed` and `eaios_api` in the same breath, and a test suite that
could not reach across the layers it verifies would be useless.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

pytestmark = pytest.mark.unit

REPO = pathlib.Path(__file__).resolve().parents[2]

#: Import root → the workspace member that owns it.
MEMBERS: dict[str, str] = {
    "eaios_core": "packages/core",
    "eaios_api": "apps/api",
    "eaios_worker": "services/worker",
    "eaios_seed": "scripts/seed",
}

#: What each member is allowed to import. `packages/core` sits at the bottom and
#: depends on nothing internal; everything else may reach down to it and nowhere
#: else. Written as an allowlist rather than a denylist so a new member added later
#: is a violation until somebody states where it sits.
ALLOWED: dict[str, set[str]] = {
    "eaios_core": set(),
    "eaios_api": {"eaios_core"},
    "eaios_worker": {"eaios_core"},
    "eaios_seed": {"eaios_core"},
}

SOURCE_ROOTS = {
    "eaios_core": REPO / "packages/core/src/eaios_core",
    "eaios_api": REPO / "apps/api/src/eaios_api",
    "eaios_worker": REPO / "services/worker/src/eaios_worker",
    "eaios_seed": REPO / "scripts/seed/src/eaios_seed",
}


def _imported_members(path: pathlib.Path) -> set[str]:
    """Every workspace member this file imports, by static analysis.

    Parsed rather than grepped: a comment or a docstring mentioning `eaios_api` is
    not an import, and this check exists precisely to avoid the false positives that
    ad-hoc pattern matching produced elsewhere in this project.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(
                alias.name.split(".")[0]
                for alias in node.names
                if alias.name.split(".")[0] in MEMBERS
            )
        # `level > 0` is a relative import, which cannot leave its own package.
        elif (
            isinstance(node, ast.ImportFrom)
            and node.level == 0
            and node.module
            and node.module.split(".")[0] in MEMBERS
        ):
            found.add(node.module.split(".")[0])
    return found


def _violations() -> list[str]:
    out: list[str] = []
    for member, root in SOURCE_ROOTS.items():
        for path in sorted(root.rglob("*.py")):
            for imported in _imported_members(path):
                if imported == member:
                    continue
                if imported not in ALLOWED[member]:
                    out.append(f"{path.relative_to(REPO)} imports {imported}")
    return out


class TestTheScanHasSubjects:
    """A layering check that reads no files passes exactly like a clean codebase."""

    def test_every_source_root_exists(self) -> None:
        missing = [name for name, root in SOURCE_ROOTS.items() if not root.is_dir()]
        assert missing == [], f"source roots not found: {missing}"

    def test_the_scan_reads_a_real_number_of_files(self) -> None:
        counted = sum(len(list(root.rglob("*.py"))) for root in SOURCE_ROOTS.values())
        assert counted > 40, f"only {counted} source files found; the scan is not reaching the code"

    def test_the_parser_recognises_an_import(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            probe = pathlib.Path(tmp) / "probe.py"
            probe.write_text(
                "# a comment mentioning eaios_api must not count\n"
                '"""nor a docstring naming eaios_worker"""\n'
                "from eaios_core.keys import cache_key\n"
                "import eaios_seed.cli\n",
                encoding="utf-8",
            )
            found = _imported_members(probe)

        assert found == {"eaios_core", "eaios_seed"}, (
            f"parser found {found}; comments and docstrings must not count as imports"
        )


class TestDependencyDirection:
    def test_no_backwards_imports_exist(self) -> None:
        found = _violations()
        assert found == [], (
            "dependency direction violated (FR-001a) — shared code moves down into"
            " packages/, never sideways:\n  " + "\n  ".join(found)
        )

    def test_core_depends_on_no_other_member(self) -> None:
        """Stated separately because it is the load-bearing half. `packages/core` is
        imported by every other member; a dependency out of it would make the graph
        cyclic and the package unusable on its own."""
        root = SOURCE_ROOTS["eaios_core"]
        reaching_out = [
            f"{path.relative_to(REPO)} -> {sorted(_imported_members(path) - {'eaios_core'})}"
            for path in sorted(root.rglob("*.py"))
            if _imported_members(path) - {"eaios_core"}
        ]
        assert reaching_out == [], "packages/core reaches upward:\n  " + "\n  ".join(reaching_out)

    def test_applications_do_not_import_each_other(self) -> None:
        """The case the rule was written for: the seed needing something the API
        also uses. The answer is `packages/core`, not a sideways import."""
        siblings = {"eaios_api", "eaios_worker", "eaios_seed"}
        out: list[str] = []
        for member in siblings:
            for path in sorted(SOURCE_ROOTS[member].rglob("*.py")):
                crossing = _imported_members(path) & (siblings - {member})
                if crossing:
                    out.append(f"{path.relative_to(REPO)} imports {sorted(crossing)}")
        assert out == [], "sibling members import each other:\n  " + "\n  ".join(out)
