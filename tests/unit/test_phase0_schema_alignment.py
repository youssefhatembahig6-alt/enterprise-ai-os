"""The benchmark addresses the schema that exists (D2, D3).

**What this exists to prevent.** `benchmarks/phase0/live_environment.py` was written against
an assumed schema and shipped green: it queried a `corpus` column that does not exist, read
`object_key` where the column is `storage_key`, addressed a `documents` bucket where the
bucket is `eaios`, and selected `allowed_roles` from a table that has no such column. Every
unit test passed, because every test injected a fake environment. The harness could not run
at all.

The behavioural proof lives in `tests/integration/test_live_environment.py`, which needs the
stack. This file is the part that does not: a **static scan**, so a reintroduced name fails
the ordinary build rather than waiting for someone to have Docker running.

Names are checked as *identifiers in SQL and bucket arguments*, not as substrings of prose —
a comment explaining why `object_key` was wrong must not fail the check that keeps it wrong.
"""

from __future__ import annotations

import ast
import pathlib
import re
from typing import Final

import pytest

pytestmark = pytest.mark.unit

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[2]
LIVE: Final[pathlib.Path] = REPO / "benchmarks/phase0/live_environment.py"

#: Names retired **as SQL columns**. Each maps to what is real.
#:
#: Scoped to SQL literals on purpose. `allowed_roles` is a legitimate *payload* key — the
#: preview index must carry it (FR-010) — and `corpus` is a legitimate English word that
#: appears in diagnostic labels like "corpus query". What must never come back is either
#: one used as a column in a statement, which is what actually failed.
RETIRED_SQL_COLUMNS: Final[dict[str, str]] = {
    "corpus": "count(*) FROM documents, and the `code` Qdrant collection for emptiness",
    "allowed_roles": "document_acl.principal_id where permission allows read",
}

#: Retired everywhere: there is no context in which this name is correct.
RETIRED_ANYWHERE: Final[dict[str, str]] = {"object_key": "storage_key"}

#: A literal that is a SQL statement rather than a label or a payload key.
_SQL: Final[re.Pattern[str]] = re.compile(r"\bSELECT\b|\bFROM\b|\bJOIN\b|\bWHERE\b", re.IGNORECASE)


def _string_literals(path: pathlib.Path) -> list[str]:
    """Every string literal in the module — where SQL and bucket names actually live.

    The AST rather than a text grep, so prose in comments and docstrings explaining the
    old names cannot trip the check that retires them.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    literals: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            literals.append(node.value)
    # Docstrings are Constant nodes too; drop the ones attached to a definition.
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                docstrings.add(doc)
    return [literal for literal in literals if literal not in docstrings]


class TestTheScanHasSubjects:
    def test_the_module_exists(self) -> None:
        assert LIVE.is_file(), f"missing {LIVE.relative_to(REPO)}"

    def test_it_contains_sql(self) -> None:
        literals = " ".join(_string_literals(LIVE)).lower()
        assert "select" in literals, (
            "no SQL literal found, so the assertions below would scan nothing"
        )

    def test_the_docstring_filter_keeps_real_literals(self) -> None:
        """Guard on the guard: dropping docstrings must not drop the SQL with them."""
        literals = _string_literals(LIVE)
        assert any("storage_key" in literal for literal in literals), (
            "the literal filter removed the SQL as well as the docstrings"
        )


class TestNoRetiredSchemaNameSurvives:
    @pytest.mark.parametrize("retired", sorted(RETIRED_SQL_COLUMNS))
    def test_the_column_appears_in_no_sql_statement(self, retired: str) -> None:
        offenders = [
            " ".join(literal.split())[:140]
            for literal in _string_literals(LIVE)
            # Word-boundary, so `document_type` does not match `corpus`; SQL-scoped, so a
            # payload key or a diagnostic label is not a false positive.
            if _SQL.search(literal) and re.search(rf"\b{re.escape(retired)}\b", literal)
        ]
        assert offenders == [], (
            f"`{retired}` is not a column in this schema — use"
            f" {RETIRED_SQL_COLUMNS[retired]} instead. Found in:\n  " + "\n  ".join(offenders)
        )

    @pytest.mark.parametrize("retired", sorted(RETIRED_ANYWHERE))
    def test_the_name_appears_in_no_string_literal(self, retired: str) -> None:
        offenders = [
            " ".join(literal.split())[:140]
            for literal in _string_literals(LIVE)
            if re.search(rf"\b{re.escape(retired)}\b", literal)
        ]
        assert offenders == [], (
            f"`{retired}` does not exist anywhere in this schema — use"
            f" {RETIRED_ANYWHERE[retired]}. Found in:\n  " + "\n  ".join(offenders)
        )

    def test_the_sql_filter_actually_recognises_sql(self) -> None:
        """Guard on the scoping: if nothing is classified as SQL, the check is vacuous."""
        statements = [literal for literal in _string_literals(LIVE) if _SQL.search(literal)]
        assert len(statements) >= 3, (
            f"only {len(statements)} literal(s) look like SQL, so the column check above"
            " is scanning almost nothing"
        )

    def test_the_payload_key_is_still_present(self) -> None:
        """`allowed_roles` must survive as a payload key — retiring it entirely would
        strip an authorization attribute the preview index is required to carry."""
        literals = _string_literals(LIVE)
        assert any(literal == "allowed_roles" for literal in literals), (
            "the `allowed_roles` payload key is gone; FR-010 requires every chunk to"
            " carry it"
        )


class TestTheBucketIsConfiguredNotHardcoded:
    def test_no_literal_documents_bucket(self) -> None:
        offenders = [
            literal
            for literal in _string_literals(LIVE)
            if literal == "documents"
        ]
        assert offenders == [], (
            "a literal 'documents' bucket name survives; the bucket is configured"
            " (`eaios` in this environment) and must be read from settings"
        )

    def test_the_bucket_comes_from_settings(self) -> None:
        source = LIVE.read_text(encoding="utf-8")
        assert "minio.bucket" in source or "settings" in source, (
            "the module does not read the bucket from configuration"
        )


class TestTheRealColumnNamesArePresent:
    """The other half — retiring a name means nothing if nothing replaced it."""

    @pytest.mark.parametrize("expected", ["storage_key", "document_acl", "principal_id"])
    def test_the_real_name_is_used(self, expected: str) -> None:
        literals = " ".join(_string_literals(LIVE))
        assert expected in literals, (
            f"`{expected}` is not referenced anywhere; the retired name was removed"
            " without being replaced"
        )


class TestNoSilentFallbacks:
    """D3: a failed probe must be a named failure, never a plausible zero."""

    def test_no_bare_except_returns_a_success_shaped_value(self) -> None:
        tree = ast.parse(LIVE.read_text(encoding="utf-8"), filename=str(LIVE))
        offenders: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            for statement in ast.walk(node):
                if not isinstance(statement, ast.Return) or statement.value is None:
                    continue
                value = statement.value
                empty = (
                    isinstance(value, ast.Constant)
                    and value.value in (0, False, "", None)
                ) or (isinstance(value, ast.Tuple | ast.List | ast.Dict) and not value.elts
                      if isinstance(value, ast.Tuple | ast.List) else False)
                if empty:
                    offenders.append(f"line {statement.lineno}: returns {ast.unparse(value)}")
        assert offenders == [], (
            "an exception handler returns a success-shaped empty value. That is how four"
            " SQL errors became 'found 0 text documents' — a verification failure wearing"
            " the costume of a verified result:\n  " + "\n  ".join(offenders)
        )
