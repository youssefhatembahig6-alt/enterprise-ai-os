"""Every dependency is pinned exactly (spec FR-012b, FR-011).

Generated names, words, and prose come from library data that changes between
releases. `faker>=33.3.0` instead of `faker==33.3.0` would keep resolving to a
newer release over time, silently producing a different dataset and invalidating
the committed fingerprints — with nothing in the failure pointing at the cause.

The requirement held when this was written; nothing enforced it. That is the whole
category of defect this feature keeps rediscovering, so it is enforced here.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]

PYPROJECTS = (
    "pyproject.toml",
    "packages/core/pyproject.toml",
    "apps/api/pyproject.toml",
    "services/worker/pyproject.toml",
    "scripts/seed/pyproject.toml",
)

#: One per ecosystem (FR-012b, plan R8). Without a committed lockfile, pinning the
#: direct dependencies still leaves every transitive one free to move.
LOCKFILES = ("uv.lock", "pnpm-lock.yaml")

#: First-party workspace members carry no version specifier; they are resolved from
#: the workspace, not from an index, so there is no release that could drift.
FIRST_PARTY = frozenset({"eaios-core", "eaios-api", "eaios-worker", "eaios-seed"})

#: Anything that lets the resolved version move.
LOOSE_OPERATORS = (">=", ">", "<=", "<", "~=", "!=", "^", "*")


def _requirements(path: Path) -> list[str]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    project = data.get("project", {})
    requirements: list[str] = list(project.get("dependencies", []))
    for group in project.get("optional-dependencies", {}).values():
        requirements.extend(group)
    for group in data.get("dependency-groups", {}).values():
        requirements.extend(item for item in group if isinstance(item, str))
    return requirements


def _name(requirement: str) -> str:
    for operator in ("==", *LOOSE_OPERATORS, ";", "@"):
        if operator in requirement:
            requirement = requirement.split(operator)[0]
    return requirement.strip().split("[")[0].strip().lower()


class TestEveryPyprojectExists:
    @pytest.mark.parametrize("relative", PYPROJECTS)
    def test_file_is_present(self, relative: str) -> None:
        """A renamed or moved manifest would otherwise silently drop out of the
        checks below, leaving its dependencies unexamined."""
        assert (REPO_ROOT / relative).is_file(), f"missing {relative}"


class TestExactPins:
    @pytest.mark.parametrize("relative", PYPROJECTS)
    def test_no_dependency_uses_a_loose_specifier(self, relative: str) -> None:
        offenders = [
            requirement
            for requirement in _requirements(REPO_ROOT / relative)
            if _name(requirement) not in FIRST_PARTY
            and any(operator in requirement for operator in LOOSE_OPERATORS)
        ]
        assert offenders == [], (
            f"{relative} has unpinned dependencies {offenders}; FR-012b requires an "
            "exact pin because library data changes between releases and would "
            "change the generated dataset"
        )

    @pytest.mark.parametrize("relative", PYPROJECTS)
    def test_every_third_party_dependency_carries_a_version(self, relative: str) -> None:
        """An unversioned dependency is looser than a loose specifier, not tighter."""
        offenders = [
            requirement
            for requirement in _requirements(REPO_ROOT / relative)
            if _name(requirement) not in FIRST_PARTY and "==" not in requirement
        ]
        assert offenders == [], f"{relative} has unversioned dependencies {offenders}"

    def test_the_generator_libraries_are_pinned_by_name(self) -> None:
        """Named explicitly because these are the ones whose output *is* the
        dataset — a check that happened to stop covering them would still pass the
        generic assertions above if they were removed from the file entirely."""
        requirements = _requirements(REPO_ROOT / "pyproject.toml")
        pinned = {_name(item): item for item in requirements}
        for library in ("faker", "sqlalchemy", "pydantic"):
            assert library in pinned, f"{library} is not declared at the workspace root"
            assert "==" in pinned[library], f"{library} is not pinned exactly"


class TestCommittedLockfiles:
    @pytest.mark.parametrize("relative", LOCKFILES)
    def test_lockfile_is_committed(self, relative: str) -> None:
        path = REPO_ROOT / relative
        assert path.is_file(), (
            f"{relative} is missing; FR-012b requires a committed lockfile per "
            "ecosystem so transitive dependencies cannot drift either"
        )

    @pytest.mark.parametrize("relative", LOCKFILES)
    def test_lockfile_is_not_a_stub(self, relative: str) -> None:
        """An empty or near-empty lockfile satisfies "exists" while locking
        nothing."""
        assert (REPO_ROOT / relative).stat().st_size > 1024


class TestTheCheckCanFail:
    """A pinning check that cannot detect a loose pin is worse than none, because
    it reads as coverage."""

    @pytest.mark.parametrize(
        "requirement", ["faker>=33.3.0", "pydantic~=2.10", "celery[redis]>5.0", "structlog"]
    )
    def test_loose_specifiers_are_recognised(self, requirement: str) -> None:
        loose = any(operator in requirement for operator in LOOSE_OPERATORS)
        unversioned = "==" not in requirement
        assert loose or unversioned

    @pytest.mark.parametrize("requirement", ["faker==33.3.0", "celery[redis]==5.4.0"])
    def test_exact_pins_are_accepted(self, requirement: str) -> None:
        assert not any(operator in requirement for operator in LOOSE_OPERATORS)
        assert "==" in requirement

    def test_first_party_packages_are_exempt_but_still_recognised(self) -> None:
        assert _name("eaios-core") in FIRST_PARTY
        assert _name("celery[redis]==5.4.0") == "celery"
