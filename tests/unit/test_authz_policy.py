"""Structural guarantees of the policy engine (spec 003 FR-012, FR-014).

Three claims that no behavioural test can make, because each is about what the code
*is* rather than what it returns:

* the engine never consults a role name (FR-014);
* every ``Condition`` member has a branch, so a new one cannot silently behave like an
  existing one;
* the engine is pure — it imports nothing that could perform I/O.

Parsed rather than grepped. A comment or docstring mentioning `role_names` is not a
read of it, and this project has already been misled twice by ad-hoc pattern matching
reporting things that were not there.
"""

from __future__ import annotations

import ast
import pathlib
from typing import ClassVar

import pytest

from eaios_core.authz import Action, Condition, ResourceKind
from eaios_core.authz.rules import POLICIES

pytestmark = pytest.mark.unit

ENGINE = pathlib.Path(__file__).resolve().parents[2] / "packages/core/src/eaios_core/authz"

#: The modules that make the decision. `context.py` is excluded because it *defines*
#: `role_names`; the rule is that nothing which decides may read it.
DECIDING_MODULES = ("policy.py", "rules.py", "sensitivity.py")


def _module_paths() -> list[pathlib.Path]:
    return sorted(ENGINE / name for name in DECIDING_MODULES)


def _tree(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


class TestTheScanHasSubjects:
    """A structural check that reads no files passes exactly like clean code."""

    def test_every_deciding_module_exists(self) -> None:
        missing = [path.name for path in _module_paths() if not path.is_file()]
        assert missing == [], f"deciding modules not found: {missing}"

    def test_the_parser_reaches_real_code(self) -> None:
        nodes = sum(len(list(ast.walk(_tree(path)))) for path in _module_paths())
        assert nodes > 200, f"only {nodes} AST nodes; the scan is not reaching the engine"


class TestPermissionCodesNeverRoleNames:
    """FR-014: code checks permission codes, never role names.

    A check written against a role name is a defect even when it produces the correct
    answer, because it breaks the moment roles are recomposed — and roles are data a
    tenant administrator edits.
    """

    def test_no_deciding_module_reads_role_names(self) -> None:
        offenders: list[str] = []
        for path in _module_paths():
            for node in ast.walk(_tree(path)):
                if isinstance(node, ast.Attribute) and node.attr == "role_names":
                    offenders.append(f"{path.name}:{node.lineno}")
        assert offenders == [], (
            "the policy engine reads role_names — FR-014 requires permission codes:\n  "
            + "\n  ".join(offenders)
        )

    def test_the_scan_would_catch_a_read(self) -> None:
        """Falsification. Without this, the assertion above passes for a scanner that
        finds nothing because it is looking for the wrong node type."""
        probe = ast.parse("if subject.role_names: pass\n# role_names in a comment\n")
        found = [
            node
            for node in ast.walk(probe)
            if isinstance(node, ast.Attribute) and node.attr == "role_names"
        ]
        assert len(found) == 1, "the scanner does not detect an attribute read"

    def test_every_rule_names_a_seeded_permission(self) -> None:
        """The engine invents no codes. A code that exists only in `rules.py` would be
        a permission nobody can ever be granted, and the denial would look like policy
        rather than a typo."""
        from eaios_seed.generators.organization import PERMISSIONS

        used = {
            rule.permission
            for policy in POLICIES.values()
            for rule in policy.rules
            if rule.permission is not None
        }
        assert used, "no rule requires a permission code at all"
        unknown = sorted(used - set(PERMISSIONS))
        assert unknown == [], f"codes not in the seeded catalog: {unknown}"


class TestEveryConditionHasABranch:
    """`_condition_holds` has no trailing `return` — a member with no branch falls out
    as `None` and denies, which is the safe direction but a silent one. This is what
    makes it loud."""

    def test_each_member_is_named_in_the_function(self) -> None:
        source = (ENGINE / "policy.py").read_text(encoding="utf-8")
        function = next(
            node
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.FunctionDef) and node.name == "_condition_holds"
        )
        compared = {
            node.attr
            for node in ast.walk(function)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "Condition"
        }
        missing = sorted(member.name for member in Condition if member.name not in compared)
        assert missing == [], (
            f"Condition members with no branch in _condition_holds: {missing}."
            " They would fall through and deny, which is safe but silent."
        )


class TestTheEngineIsPure:
    """No I/O, no clock, no randomness. Purity is what makes every ordering and
    default-deny test runnable with nothing started."""

    FORBIDDEN: ClassVar[set[str]] = {
        "sqlalchemy",
        "redis",
        "httpx",
        "requests",
        "fastapi",
        "qdrant_client",
        "minio",
        "random",
        "secrets",
        "time",
        "datetime",
        "os",
    }

    def test_no_deciding_module_imports_io_or_a_clock(self) -> None:
        offenders: list[str] = []
        for path in sorted(ENGINE.glob("*.py")):
            for node in ast.walk(_tree(path)):
                if isinstance(node, ast.Import):
                    roots = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    roots = [node.module.split(".")[0]]
                else:
                    continue
                offenders.extend(
                    f"{path.name}:{node.lineno} imports {root}"
                    for root in roots
                    if root in self.FORBIDDEN
                )
        assert offenders == [], (
            "the policy engine reached for I/O or a clock:\n  " + "\n  ".join(offenders)
        )


class TestTheRulesTableIsComplete:
    def test_every_kind_has_a_read_rule(self) -> None:
        missing = [kind for kind in ResourceKind if (kind, Action.READ) not in POLICIES]
        assert missing == [], f"kinds with no READ policy: {missing}"

    def test_no_policy_is_empty(self) -> None:
        """An empty rule tuple denies everything, which is safe but is almost certainly
        a half-finished entry rather than a decision."""
        empty = [kind for (kind, _), policy in POLICIES.items() if not policy.rules]
        assert empty == [], f"policies with no rules: {empty}"
