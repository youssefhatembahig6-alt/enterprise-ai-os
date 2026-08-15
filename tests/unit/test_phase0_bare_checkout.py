"""The canonical chunker and embedder run on a bare checkout (FR-011c, FR-035p, SC-057).

**What "bare checkout" buys.** Phase 0 has a circularity problem if the chunker and the
embedder need a running stack: the preview benchmark builds the index it measures, so
anything it imports must load before any store exists. Keeping these two modules free of
store clients is what lets §0G build a temporary index using them, instead of §0C needing
§0G to exist first.

It also buys the ordinary CI property. Chunk determinism and embedding identity are
checkable with no Docker, no network and no weights (FR-035b), which is why those checks
block the build rather than living in the controlled lane that never blocks anything.

**Model-runtime imports are permitted; network access is not.** `torch` and `transformers`
are exactly what these modules exist to wrap. What they may not do is *reach* — no HTTP
client, no socket, no Hub API. The distinction is the whole point of FR-011f: acquiring
weights is provisioning, and using them is not.

The scan reads the AST rather than importing, so it **fails on the first forbidden import
statement** rather than at whatever runtime moment the module would first be exercised.
"""

from __future__ import annotations

import ast
import pathlib
from typing import Final

import pytest

pytestmark = pytest.mark.unit

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[2]

#: The modules that must stay bare. §0E onward — preflight, the preview-index builder, the
#: benchmarks themselves — legitimately reach the stack, and are deliberately absent here.
BARE_ROOTS: Final[tuple[pathlib.Path, ...]] = (
    REPO / "packages/core/src/eaios_core/chunking",
    REPO / "packages/core/src/eaios_core/embedding",
)

#: Benchmark modules belonging to §0A–§0D. Named individually rather than by directory,
#: because the same directory holds §0F–§0H modules that must reach the stores.
BARE_BENCHMARK_MODULES: Final[tuple[pathlib.Path, ...]] = (
    REPO / "benchmarks/phase0/config.py",
    REPO / "benchmarks/phase0/measure.py",
    REPO / "benchmarks/phase0/results.py",
    REPO / "benchmarks/phase0/server_provisioning.py",
)

#: Application store clients. Importing any of these means the module cannot load before
#: the stack does.
STORE_CLIENTS: Final[frozenset[str]] = frozenset(
    {
        "psycopg",
        "psycopg2",
        "sqlalchemy",
        "alembic",
        "asyncpg",
        "minio",
        "boto3",
        "botocore",
        "qdrant_client",
        "redis",
        "celery",
        "docker",
        "kombu",
    }
)

#: Anything that can open an outbound connection or fetch a model.
NETWORK_CLIENTS: Final[frozenset[str]] = frozenset(
    {
        "socket",
        "http",
        "urllib",
        "urllib3",
        "requests",
        "httpx",
        "aiohttp",
        "ftplib",
        "telnetlib",
        "smtplib",
        "huggingface_hub",
        "datasets",
    }
)

#: Permitted: this is the runtime these modules exist to wrap.
PERMITTED_MODEL_RUNTIME: Final[frozenset[str]] = frozenset(
    {"torch", "transformers", "tokenizers", "sentencepiece", "numpy", "safetensors"}
)


def _modules_under(root: pathlib.Path) -> list[pathlib.Path]:
    if root.is_file():
        return [root]
    return sorted(root.rglob("*.py")) if root.is_dir() else []


def _all_bare_modules() -> list[pathlib.Path]:
    found: list[pathlib.Path] = []
    for root in BARE_ROOTS:
        found.extend(_modules_under(root))
    for module in BARE_BENCHMARK_MODULES:
        found.extend(_modules_under(module))
    return found


def _imports(path: pathlib.Path) -> list[tuple[str, int]]:
    """Every imported top-level module name, with the line it appears on."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((alias.name.split(".")[0], node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.append((node.module.split(".")[0], node.lineno))
    return found


class TestTheScanHasSubjects:
    """A boundary test that scans nothing passes exactly like a correct one."""

    def test_the_bare_roots_exist(self) -> None:
        missing = [str(root.relative_to(REPO)) for root in BARE_ROOTS if not root.is_dir()]
        assert missing == [], f"missing directories to scan: {missing}"

    def test_the_scan_finds_modules(self) -> None:
        modules = _all_bare_modules()
        assert len(modules) >= 5, (
            f"only {len(modules)} module(s) found; the assertions below would be checking"
            " an almost-empty set"
        )

    def test_the_scan_finds_the_permitted_runtime_somewhere(self) -> None:
        """If nothing imports torch, the permit is untested and so is the prohibition."""
        names = {name for path in _all_bare_modules() for name, _ in _imports(path)}
        assert names & PERMITTED_MODEL_RUNTIME, (
            "no scanned module imports the model runtime at all, so this file cannot"
            f" distinguish permitted from forbidden: {sorted(names)}"
        )

    def test_the_two_prohibition_sets_are_disjoint_from_the_permit(self) -> None:
        overlap = (STORE_CLIENTS | NETWORK_CLIENTS) & PERMITTED_MODEL_RUNTIME
        assert overlap == set(), f"a name is both permitted and forbidden: {overlap}"


class TestNoStoreClientIsImported:
    def test_no_bare_module_imports_a_store_client(self) -> None:
        offenders = [
            f"{path.relative_to(REPO)}:{line} imports `{name}`"
            for path in _all_bare_modules()
            for name, line in _imports(path)
            if name in STORE_CLIENTS
        ]
        assert offenders == [], (
            "a canonical Phase 0 module imports an application store client. The preview"
            " benchmark builds the index it measures, so these modules must load before"
            " any store exists:\n  " + "\n  ".join(offenders)
        )


class TestNoNetworkClientIsImported:
    def test_no_bare_module_imports_a_network_client(self) -> None:
        offenders = [
            f"{path.relative_to(REPO)}:{line} imports `{name}`"
            for path in _all_bare_modules()
            for name, line in _imports(path)
            if name in NETWORK_CLIENTS
        ]
        assert offenders == [], (
            "a canonical Phase 0 module imports a network client. Weight acquisition is"
            " provisioning; embedding is not, and a retrieval path that can reach the"
            " network is one that can leak a query and stall on a timeout"
            " (FR-011c, FR-011f):\n  " + "\n  ".join(offenders)
        )


class TestTheModelRuntimeIsPermitted:
    def test_importing_torch_is_not_an_offence(self) -> None:
        assert not (PERMITTED_MODEL_RUNTIME & (STORE_CLIENTS | NETWORK_CLIENTS))

    def test_the_embedder_does_import_the_runtime(self) -> None:
        source = REPO / "packages/core/src/eaios_core/embedding/bge_m3.py"
        names = {name for name, _ in _imports(source)}
        assert names & PERMITTED_MODEL_RUNTIME, (
            "the embedder no longer imports a model runtime at all; either it stopped"
            f" embedding or this scan stopped seeing lazy imports: {sorted(names)}"
        )


class TestTheCheckWouldCatchTheRealCase:
    """Falsification against a planted import, so a passing run means something."""

    def test_a_planted_store_import_is_detected(self, tmp_path: pathlib.Path) -> None:
        planted = tmp_path / "planted.py"
        planted.write_text(
            "from qdrant_client import QdrantClient\nimport minio\n", encoding="utf-8"
        )
        names = {name for name, _ in _imports(planted)}
        assert names & STORE_CLIENTS == {"qdrant_client", "minio"}

    def test_a_planted_network_import_is_detected(self, tmp_path: pathlib.Path) -> None:
        planted = tmp_path / "planted.py"
        planted.write_text("import requests\nimport huggingface_hub\n", encoding="utf-8")
        names = {name for name, _ in _imports(planted)}
        assert names & NETWORK_CLIENTS == {"requests", "huggingface_hub"}

    def test_a_lazy_import_inside_a_function_is_still_seen(self, tmp_path: pathlib.Path) -> None:
        """The scan walks the whole tree, so hiding an import in a function does not help."""
        planted = tmp_path / "planted.py"
        planted.write_text(
            "def load():\n    import requests\n    return requests\n", encoding="utf-8"
        )
        assert {name for name, _ in _imports(planted)} & NETWORK_CLIENTS == {"requests"}
