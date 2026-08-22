"""The existing API is the only verifier of browser session tokens (FR-028, FR-029, Principle II).

A browser JWT is a claim about a person, and it is worth exactly as much as the secret that
signs it. Every additional process holding that secret is another place it can leak from,
and — worse — another place that can be *wrong* about what the token means. Two verifiers
drift: one honours `nbf`, the other forgets; one checks the audience, the other accepts any.
The drift is silent until it is an incident, so the rule is not "verify carefully
everywhere", it is **verify in one place**.

`apps/api` is that place. This file fixes the boundary for the two services that exist
today — the Celery **worker** and the **seed** CLI — and T114 extends it to the generation
boundary in Phase 4.

**Static and behavioural, because either alone is defeatable.** A static scan proves no
JWT machinery is *present*; it cannot prove the code does not accept a token by some other
name. A behavioural check proves a token-bearing call is *refused*; it cannot prove the
capability was never built, only that this one path declines. Both are here.

**What "rejects a token-bearing request" means for a process with no HTTP surface.** Neither
service listens on a socket, so the request that reaches them is a Celery task invocation
or a command line. The behavioural tests use those: a task called with a token argument and
a CLI invoked with a token option must both be refused by construction — not ignored, not
silently dropped, but an error. Ignoring is the dangerous outcome, because a caller who
believes a token was honoured will send one.

**Non-vacuity is proven, not assumed.** The scanners run against `apps/api` too, where they
must *find* the verifier they are looking for. A detector that finds nothing anywhere would
pass this file with the boundary wide open.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Final

import pytest
from typer.testing import CliRunner, Result

pytestmark = pytest.mark.security

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

#: The boundaries that exist now. Phase 4 adds the generation service (T114).
GUARDED_PACKAGES: Final[dict[str, Path]] = {
    "worker": REPO_ROOT / "services" / "worker" / "src" / "eaios_worker",
    "seed": REPO_ROOT / "scripts" / "seed" / "src" / "eaios_seed",
}

#: Where verification is allowed to live, and where the scanners must find it.
THE_ONE_VERIFIER: Final[Path] = REPO_ROOT / "apps" / "api" / "src" / "eaios_api"

#: Libraries that decode or verify a JWT. Import of any is the capability itself.
JWT_LIBRARIES: Final[frozenset[str]] = frozenset(
    {"jwt", "jose", "authlib", "python_jose", "pyjwt", "joserfc"}
)

#: Names a signing secret hides behind. Matched case-insensitively on identifiers and
#: string literals alike, because a settings key is as dangerous as a variable.
SECRET_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(jwt[_-]?secret|secret[_-]?key|signing[_-]?key|access[_-]?token[_-]?secret|jwt[_-]?"
    r"algorithm|hs256|rs256)",
    re.IGNORECASE,
)

#: Function names that decode a token. `verify_access_token` is the API's own verifier,
#: named explicitly so importing it into a worker is caught.
DECODER_NAMES: Final[frozenset[str]] = frozenset(
    {"decode", "verify_access_token", "verify_jwt", "decode_token", "verify_token"}
)


def _python_files(package: Path) -> list[Path]:
    return sorted(package.rglob("*.py"))


def _imported_modules(tree: ast.AST) -> set[str]:
    """Top-level module names imported anywhere in a file, absolute imports only."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module.split(".")[0])
    return found


def _imported_names(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            found |= {alias.asname or alias.name for alias in node.names}
    return found


def _called_attributes(tree: ast.AST) -> set[str]:
    """Attribute names in call position — `jwt.decode(...)` yields `decode`."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            target = node.func
            if isinstance(target, ast.Attribute):
                found.add(target.attr)
            elif isinstance(target, ast.Name):
                found.add(target.id)
    return found


def _secret_hits(source: str) -> set[str]:
    return {match.group(0) for match in SECRET_PATTERN.finditer(source)}


class TestTheScannersSeeRealCode:
    """Vacuity guards. Each runs first against the package that *does* verify."""

    def test_the_guarded_packages_contain_files(self) -> None:
        for name, package in GUARDED_PACKAGES.items():
            assert package.is_dir(), f"{name} package not found at {package}"
            assert _python_files(package), f"no Python files scanned in {name}"

    def test_the_import_scanner_finds_the_api_s_jwt_library(self) -> None:
        found: set[str] = set()
        for path in _python_files(THE_ONE_VERIFIER):
            found |= _imported_modules(ast.parse(path.read_text(encoding="utf-8")))
        assert found & JWT_LIBRARIES, (
            "the import scanner found no JWT library in the one package that must have"
            " one, so its silence about the worker and the seed means nothing"
        )

    def test_the_secret_scanner_finds_the_api_s_signing_key(self) -> None:
        hits: set[str] = set()
        for path in _python_files(THE_ONE_VERIFIER):
            hits |= _secret_hits(path.read_text(encoding="utf-8"))
        assert hits, "the secret scanner matched nothing in the API; its pattern is dead"

    def test_the_decoder_scanner_finds_the_api_s_decode_call(self) -> None:
        found: set[str] = set()
        for path in _python_files(THE_ONE_VERIFIER):
            found |= _called_attributes(ast.parse(path.read_text(encoding="utf-8")))
        assert found & DECODER_NAMES, "the decoder scanner found no decode call in the API"


class TestNoGuardedServiceImportsJwtMachinery:
    @pytest.mark.parametrize("service", sorted(GUARDED_PACKAGES))
    def test_it_imports_no_jwt_library(self, service: str) -> None:
        offenders: list[str] = []
        for path in _python_files(GUARDED_PACKAGES[service]):
            for module in _imported_modules(ast.parse(path.read_text(encoding="utf-8"))):
                if module in JWT_LIBRARIES:
                    offenders.append(f"{path.relative_to(REPO_ROOT)}: {module}")
        assert offenders == [], (
            f"the {service} imports JWT machinery: {offenders}. Holding the capability is"
            " holding the signing secret, and a second verifier drifts from the first"
        )

    @pytest.mark.parametrize("service", sorted(GUARDED_PACKAGES))
    def test_it_does_not_import_the_api_s_verifier(self, service: str) -> None:
        """The subtler route: reuse rather than reimplementation. It shares the drift
        problem's smaller half and all of the secret-distribution problem."""
        offenders: list[str] = []
        for path in _python_files(GUARDED_PACKAGES[service]):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            if "eaios_api" in _imported_modules(tree):
                offenders.append(f"{path.relative_to(REPO_ROOT)}: eaios_api")
            for name in _imported_names(tree) & DECODER_NAMES:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {name}")
        assert offenders == [], f"the {service} imports the API's verifier: {offenders}"

    @pytest.mark.parametrize("service", sorted(GUARDED_PACKAGES))
    def test_it_does_not_declare_a_jwt_dependency(self, service: str) -> None:
        """Ahead of the import: a declared dependency is the capability provisioned."""
        manifest = GUARDED_PACKAGES[service].parents[1] / "pyproject.toml"
        assert manifest.is_file(), f"no pyproject.toml for {service} at {manifest}"
        declared = manifest.read_text(encoding="utf-8").lower()
        for library in ("pyjwt", "python-jose", "authlib", "joserfc", "eaios-api"):
            assert library not in declared, (
                f"the {service} declares `{library}`, which provisions token verification"
                f" into a process that must never perform it"
            )


class TestNoGuardedServiceHoldsASigningKey:
    @pytest.mark.parametrize("service", sorted(GUARDED_PACKAGES))
    def test_it_references_no_signing_secret(self, service: str) -> None:
        offenders: list[str] = []
        for path in _python_files(GUARDED_PACKAGES[service]):
            hits = _secret_hits(path.read_text(encoding="utf-8"))
            if hits:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {sorted(hits)}")
        assert offenders == [], (
            f"the {service} references a signing secret: {offenders}. A process that can"
            " sign a token can mint one, which is worse than verifying one"
        )

    @pytest.mark.parametrize("service", sorted(GUARDED_PACKAGES))
    def test_it_defines_no_token_decoding_path(self, service: str) -> None:
        offenders: list[str] = []
        for path in _python_files(GUARDED_PACKAGES[service]):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    lowered = node.name.lower()
                    if "token" in lowered and (
                        "verify" in lowered or "decode" in lowered or "auth" in lowered
                    ):
                        offenders.append(f"{path.relative_to(REPO_ROOT)}: {node.name}")
        assert offenders == [], f"the {service} defines a token-decoding path: {offenders}"


class TestTheWorkerRejectsATokenBearingTask:
    """Behavioural. A Celery invocation is the request that reaches a worker."""

    def test_no_task_accepts_a_token_argument(self) -> None:
        """Statically over signatures — the argument a caller would use to pass one."""
        offenders: list[str] = []
        for path in _python_files(GUARDED_PACKAGES["worker"]):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                arguments = node.args
                names = [
                    argument.arg
                    for argument in (
                        *arguments.posonlyargs,
                        *arguments.args,
                        *arguments.kwonlyargs,
                    )
                ]
                for name in names:
                    if any(word in name.lower() for word in ("token", "jwt", "bearer")):
                        offenders.append(f"{path.relative_to(REPO_ROOT)}: {node.name}({name})")
        assert offenders == [], f"a worker task accepts a token: {offenders}"

    def test_calling_a_task_with_a_token_is_refused(self) -> None:
        """Not ignored — refused. A caller whose token was silently dropped believes it
        was honoured and keeps sending it."""
        from eaios_worker.tasks.retention import purge_expired_submissions

        with pytest.raises(TypeError):
            purge_expired_submissions(company_slug="niletech", access_token="anything")

    def test_the_same_call_without_a_token_is_accepted_by_the_signature(self) -> None:
        """Vacuity guard: the refusal above must be about the token, not about the call
        being malformed in some way that would reject everything."""
        import inspect

        from eaios_worker.tasks.retention import purge_expired_submissions

        signature = inspect.signature(purge_expired_submissions)
        signature.bind(company_slug="niletech")

        with pytest.raises(TypeError):
            signature.bind(company_slug="niletech", access_token="anything")


class TestTheSeedCliRejectsATokenBearingInvocation:
    """Behavioural. A command line is the request that reaches the seed."""

    @staticmethod
    def _run(*arguments: str) -> Result:
        """In-process through Typer's own runner.

        A subprocess would be closer to a real invocation but would depend on the seed
        package being installed into whatever interpreter runs the tests — and a failure
        to import is indistinguishable, from the outside, from a refusal. That would make
        the assertion below pass for the wrong reason.
        """
        from eaios_seed.cli import app

        return CliRunner().invoke(app, list(arguments))

    def test_a_token_option_is_not_accepted(self) -> None:
        result = self._run("verify", "--access-token", "eyJhbGciOiJIUzI1NiJ9.e30.x")
        assert result.exit_code != 0, (
            "the seed CLI accepted a token-bearing option. Even unused, an accepted"
            " option tells the caller the token was received and may be honoured"
        )
        assert "no such option" in result.output.lower(), (
            f"the CLI failed, but not because it refused the token:\n{result.output}"
        )

    def test_the_refusal_is_about_the_option_and_not_the_command(self) -> None:
        """Vacuity guard: the parser must distinguish a declared option from an undeclared
        one, or the refusal above would be what this CLI says to everything.

        `--seed` is declared and takes a value; supplying none fails at parse time with a
        different message and without running the command, which is exactly the contrast
        needed and costs no database connection.
        """
        result = self._run("verify", "--seed")
        assert result.exit_code != 0
        assert "no such option" not in result.output.lower(), (
            "a declared option was also reported as unknown, so the assertion above"
            f" cannot tell a refused token from ordinary parser noise:\n{result.output}"
        )

    def test_no_command_declares_a_token_option(self) -> None:
        source = (GUARDED_PACKAGES["seed"] / "cli.py").read_text(encoding="utf-8")
        for option in ("--access-token", "--token", "--jwt", "--bearer"):
            assert option not in source, f"the seed CLI declares `{option}`"
