"""`users.password_hash` exists and is never used (spec 003, plan deviation D1).

Feature 001 added the column "so the auth feature does not need a migration to start
using it". Feature 003 does not use it: the credential lives in its own table, with its
own lifecycle — the generator writes users, a later command writes credentials, and a
reset clears both independently. A password hash is also a company-owned artifact, so
it belongs behind RLS rather than on a row every part of the system reads.

Dropping the column would be tidier and is rejected for a stated reason: the generator
writes ``"password_hash": None`` into every user row, that key is part of the hashed
row, and removing it moves **both** committed fingerprints — which SC-014 forbids.

So the column stays, permanently unused, looking exactly like the place a password is
kept. That is a trap for the next person who greps for one, and a comment is not a
control. This file is the control: the moment application code touches it, this fails.

Parsed rather than grepped. The docstrings and comments across this codebase mention
`password_hash` constantly, and a text search would drown in them.
"""

from __future__ import annotations

import ast
import pathlib
import re

import pytest

pytestmark = pytest.mark.security

REPO = pathlib.Path(__file__).resolve().parents[2]

#: Application source only. The model definition legitimately *declares* the column,
#: the migration legitimately creates it, and tests legitimately assert about it — what
#: must not happen is code reading or writing it at runtime.
SOURCE_ROOTS = (
    REPO / "apps/api/src/eaios_api",
    REPO / "services/worker/src/eaios_worker",
    REPO / "packages/core/src/eaios_core",
)

#: The three places the column is allowed to appear, each for a stated reason.
ALLOWED = {
    # Declares the column. Removing the declaration is what would move the fingerprint.
    REPO / "packages/core/src/eaios_core/models/organization.py",
}

COLUMN = "password_hash"


def _python_files() -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for root in SOURCE_ROOTS:
        if root.is_dir():
            files.extend(p for p in root.rglob("*.py") if p not in ALLOWED)
    return sorted(files)


#: The model whose column is forbidden. `UserCredential.password_hash` is the one the
#: system actually uses and must be reachable; only `User.password_hash` is the trap.
FORBIDDEN_OWNER = "User"

#: Matches the `users` table in raw SQL without also matching `user_credentials`.
_USERS_TABLE = re.compile(r"\busers\b", re.IGNORECASE)
_SQL_VERBS = ("SELECT", "UPDATE", "INSERT")


def _label(path: pathlib.Path) -> str:
    """Repo-relative when it can be, absolute otherwise.

    The falsification probes live in the system temp directory, and a bare
    `relative_to` raises there — turning the control that proves the scanner works into
    an error about paths.
    """
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def _references(path: pathlib.Path) -> list[str]:
    """References to **`users`**`.password_hash` specifically.

    The distinction is the whole test. `UserCredential.password_hash` is the column the
    system uses on every sign-in, and `resolved.password_hash` carries its value —
    both are correct and both must stay. Only the column on `users` is the one that
    exists solely so nothing uses it.

    A first version matched the attribute name alone and reported five violations in
    `auth/router.py`, every one of them the credential table doing its job. A check
    that cannot tell the intended use from the forbidden one is a check that gets
    switched off.

    Both syntactic forms are covered: `User.password_hash` is the ORM read, and a
    hand-written `SELECT password_hash FROM users` is the raw-SQL one that an
    attribute scan alone would miss entirely.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and node.attr == COLUMN
            and isinstance(node.value, ast.Name)
            and node.value.id == FORBIDDEN_OWNER
        ):
            found.append(
                f"{_label(path)}:{node.lineno} {FORBIDDEN_OWNER}.{COLUMN}"
            )
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            # A docstring is a Constant too, and every module here discusses the column
            # at length. Only SQL that names the column *and* the `users` table counts.
            text = node.value
            if (
                COLUMN in text
                and any(verb in text.upper() for verb in _SQL_VERBS)
                and _USERS_TABLE.search(text)
            ):
                found.append(f"{_label(path)}:{node.lineno} SQL against users")
    return found


class TestTheScanHasSubjects:
    """A scan that reads no files passes exactly like clean code."""

    def test_every_source_root_exists(self) -> None:
        missing = [str(r.relative_to(REPO)) for r in SOURCE_ROOTS if not r.is_dir()]
        assert missing == [], f"source roots not found: {missing}"

    def test_it_reaches_a_real_number_of_files(self) -> None:
        counted = len(_python_files())
        assert counted > 40, f"only {counted} files scanned; the scan is not reaching the code"

    def test_every_allowed_path_exists(self) -> None:
        """An exemption pointing at a moved file exempts nothing and hides that the
        file it was written for is now unguarded."""
        missing = [str(p.relative_to(REPO)) for p in ALLOWED if not p.is_file()]
        assert missing == [], f"exempted files that do not exist: {missing}"

    def test_the_scanner_detects_both_forbidden_forms(self) -> None:
        """Falsification. Without this the assertion below passes for a scanner looking
        for the wrong node types."""
        found = _references(self._probe(
            '"""A docstring mentioning password_hash must not count."""\n'
            "# nor a comment mentioning password_hash\n"
            "x = User.password_hash\n"
            'y = "SELECT password_hash FROM users WHERE id = :u"\n'
        ))
        assert len(found) == 2, (
            f"expected the attribute and the SQL string, found {len(found)}: {found}"
        )

    def test_the_scanner_ignores_the_credential_table(self) -> None:
        """The other half, and the one that matters more.

        A scanner that flagged every `password_hash` would flag the sign-in path — the
        code that is *supposed* to read a hash — and the only way to make it pass would
        be to exempt the file, which would then exempt a real violation too.
        """
        found = _references(self._probe(
            "a = UserCredential.password_hash\n"
            "b = resolved.password_hash\n"
            "c = row.password_hash\n"
            'd = "SELECT password_hash FROM user_credentials WHERE user_id = :u"\n'
        ))
        assert found == [], f"the credential table's own column was flagged: {found}"

    @staticmethod
    def _probe(source: str) -> pathlib.Path:
        import tempfile

        handle = tempfile.NamedTemporaryFile(  # noqa: SIM115 - kept for the test's life
            "w", suffix=".py", delete=False, encoding="utf-8"
        )
        handle.write(source)
        handle.close()
        return pathlib.Path(handle.name)


class TestTheColumnIsNeverUsed:
    def test_no_application_code_reads_or_writes_it(self) -> None:
        offenders = [ref for path in _python_files() for ref in _references(path)]
        assert offenders == [], (
            "application code touches `users.password_hash`, which is permanently"
            " unused by design — the credential lives in `user_credentials`"
            " (plan deviation D1):\n  " + "\n  ".join(offenders)
        )

    def test_the_column_still_exists_in_the_model(self) -> None:
        """The other half. If it were dropped, both committed fingerprints would move
        and SC-014 would fail — so its *presence* is as load-bearing as its disuse."""
        from eaios_core.models import User

        assert hasattr(User, COLUMN), (
            "`users.password_hash` was removed. The generator writes it into every user"
            " row, so dropping it changes the hashed row set and invalidates both"
            " committed fingerprints (SC-014)."
        )

    def test_the_generator_still_writes_it_as_null(self) -> None:
        """FR-002a: "The generator MUST continue to leave `password_hash` unset". Read
        from the generator's source rather than the database, because that is where the
        fingerprint's input comes from."""
        source = (
            REPO / "scripts/seed/src/eaios_seed/generators/organization.py"
        ).read_text(encoding="utf-8")
        assert '"password_hash": None' in source, (
            "the generator no longer writes password_hash as None; the generated row"
            " shape has changed and the committed fingerprints are invalid"
        )


class TestTheCredentialLivesElsewhere:
    def test_the_credential_table_is_the_one_in_use(self) -> None:
        from eaios_core.models import UserCredential

        assert hasattr(UserCredential, COLUMN)
        assert UserCredential.__tablename__ == "user_credentials"

    def test_it_is_tenant_owned(self) -> None:
        """Principle I. A password hash is a company-owned artifact; putting it in a
        global table to make one lookup easier would invert the principle."""
        from eaios_core.models import UserCredential
        from eaios_core.tenancy import is_tenant_scoped

        assert hasattr(UserCredential, "company_id")
        assert is_tenant_scoped("user_credentials")
