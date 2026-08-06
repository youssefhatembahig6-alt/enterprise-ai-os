"""Every import a package makes is declared in that package's own manifest.

**Why this exists.** The Docker images install each workspace member from its *own*
`pyproject.toml` — `apps/api/pyproject.toml`, `packages/core/pyproject.toml`, and so on.
The root `pyproject.toml` is only the developer environment: it is what `uv sync`
resolves, what the tests import through, and what every local check runs against.

So a dependency added to the root and not to the member that ships it is invisible
locally and fatal in the container. Feature 003 did exactly that: `PyJWT` and
`argon2-cffi` went into the root, all 1,300-odd tests passed, `ruff` and `mypy` passed,
and the API container then died on startup with `ModuleNotFoundError: No module named
'jwt'`. Nothing between the code being written and the container being rebuilt could
have noticed — the in-process test client imports from the developer environment, where
the module was present.

This is the check that notices. It reads what each member imports and compares it
against what that member declares, following `eaios-core` where a member depends on it.
"""

from __future__ import annotations

import ast
import pathlib
import tomllib
from typing import Final

import pytest

pytestmark = pytest.mark.unit

REPO = pathlib.Path(__file__).resolve().parents[2]

#: Member name → (manifest, source root).
MEMBERS: Final[dict[str, tuple[pathlib.Path, pathlib.Path]]] = {
    "eaios-core": (
        REPO / "packages/core/pyproject.toml",
        REPO / "packages/core/src/eaios_core",
    ),
    "eaios-api": (
        REPO / "apps/api/pyproject.toml",
        REPO / "apps/api/src/eaios_api",
    ),
    "eaios-worker": (
        REPO / "services/worker/pyproject.toml",
        REPO / "services/worker/src/eaios_worker",
    ),
    "eaios-seed": (
        REPO / "scripts/seed/pyproject.toml",
        REPO / "scripts/seed/src/eaios_seed",
    ),
}

#: Import root → the distribution that provides it, where the two differ.
DISTRIBUTION_OF: Final[dict[str, str]] = {
    "jwt": "pyjwt",
    "argon2": "argon2-cffi",
    "sqlalchemy": "sqlalchemy",
    "psycopg": "psycopg",
    "pydantic_settings": "pydantic-settings",
    "qdrant_client": "qdrant-client",
    "dateutil": "python-dateutil",
    "yaml": "pyyaml",
    "faker": "faker",
    "jinja2": "jinja2",
}

#: First-party roots, resolved through the member graph rather than a distribution.
FIRST_PARTY: Final[dict[str, str]] = {
    "eaios_core": "eaios-core",
    "eaios_api": "eaios-api",
    "eaios_worker": "eaios-worker",
    "eaios_seed": "eaios-seed",
}


def _stdlib() -> frozenset[str]:
    import sys

    return frozenset(sys.stdlib_module_names)


def _declared(manifest: pathlib.Path) -> set[str]:
    """Distribution names this manifest declares, normalised and version-stripped."""
    data = tomllib.loads(manifest.read_text(encoding="utf-8"))
    names: set[str] = set()
    for entry in data.get("project", {}).get("dependencies", []):
        # "fastapi==0.115.6" -> "fastapi"; "celery[redis]==5.4.0" -> "celery"
        name = entry.split("==")[0].split(">=")[0].split("[")[0].strip()
        names.add(name.lower().replace("_", "-"))
    return names


def _available(member: str, seen: frozenset[str] = frozenset()) -> set[str]:
    """Everything a member can import, following first-party dependencies."""
    if member in seen:
        return set()
    manifest, _ = MEMBERS[member]
    declared = _declared(manifest)
    available = set(declared)
    for name in declared:
        if name in MEMBERS:
            available |= _available(name, seen | {member})
    return available


def _imported(root: pathlib.Path) -> dict[str, str]:
    """Third-party import root → the file and line that first imports it."""
    stdlib = _stdlib()
    found: dict[str, str] = {}

    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                roots = [node.module.split(".")[0]]
            else:
                continue
            for name in roots:
                if name in stdlib or name.startswith("_"):
                    continue
                found.setdefault(name, f"{path.relative_to(REPO)}:{node.lineno}")
    return found


def _distribution(import_root: str) -> str:
    if import_root in FIRST_PARTY:
        return FIRST_PARTY[import_root]
    return DISTRIBUTION_OF.get(import_root, import_root.lower().replace("_", "-"))


class TestTheScanHasSubjects:
    """A check that reads no manifests passes exactly like a correct one."""

    def test_every_manifest_and_source_root_exists(self) -> None:
        missing = [
            f"{name}: {p}"
            for name, (manifest, src) in MEMBERS.items()
            for p in (manifest, src)
            if not p.exists()
        ]
        assert missing == [], f"missing: {missing}"

    def test_every_member_declares_something(self) -> None:
        empty = [name for name in MEMBERS if not _declared(MEMBERS[name][0])]
        assert empty == [], f"members with no declared dependencies: {empty}"

    def test_every_member_imports_something_third_party(self) -> None:
        bare = [name for name, (_, src) in MEMBERS.items() if not _imported(src)]
        assert bare == [], f"members whose import scan found nothing: {bare}"


class TestEveryImportIsDeclared:
    @pytest.mark.parametrize("member", sorted(MEMBERS))
    def test_the_member_declares_what_it_imports(self, member: str) -> None:
        _, source = MEMBERS[member]
        available = _available(member)

        undeclared = [
            f"{_distribution(root)} (imported as `{root}` at {where})"
            for root, where in sorted(_imported(source).items())
            if _distribution(root) not in available
        ]

        assert undeclared == [], (
            f"`{member}` imports packages its own pyproject.toml does not declare.\n"
            "The Docker image installs from that manifest, not from the root one, so"
            " this fails at container startup and nowhere earlier:\n  "
            + "\n  ".join(undeclared)
        )


class TestTheCheckWouldCatchTheRealCase:
    """Falsification against the actual bug, not a synthetic one.

    `jwt` is imported by `apps/api/src/eaios_api/auth/tokens.py`. Removing `pyjwt` from
    the API's manifest must make the check above fail — if it does not, the check would
    not have caught the failure that motivated it.
    """

    def test_removing_a_real_dependency_is_detected(self) -> None:
        manifest, source = MEMBERS["eaios-api"]
        available = _available("eaios-api") - {"pyjwt"}

        undeclared = [
            root
            for root in _imported(source)
            if _distribution(root) not in available
        ]
        assert "jwt" in undeclared, (
            "dropping pyjwt from the API manifest was not detected; this check would"
            " not have caught the ModuleNotFoundError that motivated it"
        )
        assert manifest.is_file()

    def test_the_import_scan_finds_jwt(self) -> None:
        _, source = MEMBERS["eaios-api"]
        assert "jwt" in _imported(source), "the API no longer imports jwt at all"

    def test_the_import_scan_finds_argon2_in_core(self) -> None:
        _, source = MEMBERS["eaios-core"]
        assert "argon2" in _imported(source), "core no longer imports argon2"


class TestTheRootManifestAgrees:
    """The root is the developer environment. It should be a superset of what the
    members need, or `uv sync` produces a environment the containers do not match — and
    every local test then runs against different versions than production."""

    def test_the_root_declares_everything_the_members_do(self) -> None:
        root_declared = _declared(REPO / "pyproject.toml")
        missing: list[str] = []
        for name in MEMBERS:
            for dependency in _declared(MEMBERS[name][0]):
                if dependency in MEMBERS:
                    continue  # first-party, resolved by path locally
                if dependency not in root_declared:
                    missing.append(f"{dependency} (declared by {name})")
        assert missing == [], (
            "the root manifest is missing dependencies its members declare, so the"
            " developer environment differs from the containers:\n  "
            + "\n  ".join(sorted(set(missing)))
        )
