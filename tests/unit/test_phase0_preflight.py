"""Preflight runs first, and a failed preflight stops everything (FR-001, FR-035a, SC-018).

Two properties, and the second is the one that is easy to get wrong.

**Every prerequisite is checked, and a missing one is named.** "Preflight failed" sends
someone hunting. "active profile is `smoke`, expected `full`" does not.

**Preflight runs *before* anything it is checking for.** This is an ordering property, and
ordering properties decay silently. If the embedder is imported at module scope, it is
constructed before `main()` runs at all — and then preflight's report arrives after the
2 GB load it was supposed to gate, after the Qdrant client is built, and after the failure
it existed to prevent has already happened. The benchmark still *fails*, but it fails with a
`FileNotFoundError` from inside a model loader instead of "weights absent, see
docs/models.md", and it fails a minute later.

The evaluation lane already works this way — its harness entry point calls preflight first —
so this is the same discipline applied to the benchmark lane.

Everything here is **network-free**: the environment is injected, so a check of the checking
logic never needs the stack it checks for.
"""

from __future__ import annotations

import dataclasses
import hashlib
import pathlib
import sys

import pytest

from benchmarks.phase0 import preflight
from benchmarks.phase0.preflight import Environment, PreflightReport, run

pytestmark = pytest.mark.unit

#: The pinned values, so a satisfied fake matches what preflight demands.
GOOD_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"
GOOD_CHECKSUM = "b5e0ce3470abf5ef3831aa1bd5553b486803e83251590ab7ff35a117cf6aad38"


@dataclasses.dataclass(frozen=True)
class FakeEnvironment:
    """A fully prepared environment, with any single prerequisite withholdable."""

    postgres_reachable: bool = True
    minio_reachable: bool = True
    qdrant_reachable: bool = True
    active_profile: str = "full"
    text_document_count: int = 105
    code_document_count: int = 0
    unreadable_objects: tuple[str, ...] = ()
    weights_revision: str | None = GOOD_REVISION
    weights_checksum: str | None = GOOD_CHECKSUM

    def observe(self) -> dict[str, object]:
        return dataclasses.asdict(self)


def _environment(**withheld: object) -> Environment:
    return FakeEnvironment(**withheld)  # type: ignore[arg-type]


#: Each case: the field that breaks, and the substring the failure must name.
BROKEN: tuple[tuple[dict[str, object], str], ...] = (
    ({"postgres_reachable": False}, "postgres"),
    ({"minio_reachable": False}, "minio"),
    ({"qdrant_reachable": False}, "qdrant"),
    ({"active_profile": "smoke"}, "profile"),
    ({"text_document_count": 104}, "105"),
    ({"text_document_count": 0}, "105"),
    ({"code_document_count": 12}, "code"),
    ({"unreadable_objects": ("documents/a.txt",)}, "readable"),
    ({"weights_revision": None}, "revision"),
    ({"weights_revision": "0" * 40}, "revision"),
    ({"weights_checksum": None}, "checksum"),
    ({"weights_checksum": "f" * 64}, "checksum"),
)


@dataclasses.dataclass(frozen=True)
class _FixedObservation:
    """Hands preflight an observation that has already been made.

    Lets the weights assertions above reach `preflight.run` without observing twice —
    and without a second trip through the store boundaries this test deliberately owns.
    """

    observed: dict[str, object]

    def observe(self) -> dict[str, object]:
        return dict(self.observed)


class TestTheSatisfiedCase:
    """Without this, a preflight that refuses everything would pass the rest of the file."""

    def test_a_prepared_environment_passes(self) -> None:
        report = run(_environment())
        assert report.ok is True, f"a prepared environment failed preflight: {report.describe()}"
        assert report.failures == ()

    def test_it_checks_something(self) -> None:
        assert len(run(_environment()).checks) >= 7, (
            "preflight ran fewer than seven checks; FR-035a names more than that, so"
            " something is not being verified"
        )


class TestEachMissingPrerequisiteFails:
    @pytest.mark.parametrize(
        ("broken", "named"),
        BROKEN,
        ids=[f"{next(iter(b))}={next(iter(b.values()))}" for b, _ in BROKEN],
    )
    def test_it_fails(self, broken: dict[str, object], named: str) -> None:
        assert run(_environment(**broken)).ok is False, f"preflight passed with {broken}"

    @pytest.mark.parametrize(
        ("broken", "named"),
        BROKEN,
        ids=[f"{next(iter(b))}={next(iter(b.values()))}" for b, _ in BROKEN],
    )
    def test_the_failure_names_the_prerequisite(
        self, broken: dict[str, object], named: str
    ) -> None:
        description = run(_environment(**broken)).describe().lower()
        assert named in description, (
            f"breaking {broken} produced a message that does not name `{named}`, so it"
            f" sends the reader hunting: {description}"
        )

    def test_one_break_does_not_cascade(self) -> None:
        """A report that blames everything cannot be acted on."""
        report = run(_environment(active_profile="smoke"))
        assert len(report.failures) == 1, (
            f"one broken prerequisite produced {len(report.failures)} failures: {report.describe()}"
        )


class TestTheExitCode:
    def test_a_failed_preflight_exits_nonzero(self) -> None:
        assert run(_environment(qdrant_reachable=False)).exit_code != 0

    def test_a_passed_preflight_exits_zero(self) -> None:
        assert run(_environment()).exit_code == 0


class TestPreflightRunsBeforeAnythingItGates:
    """The ordering property. This is what T025 falsifies."""

    EMBEDDER = "eaios_core.embedding.bge_m3"

    @pytest.fixture
    def unimported(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Start from a state where the embedder has genuinely not been imported."""
        for name in list(sys.modules):
            if name.startswith("eaios_core.embedding"):
                monkeypatch.delitem(sys.modules, name, raising=False)

    def test_the_entry_point_imports_nothing_heavy_at_module_scope(self) -> None:
        """A module-scope import is constructed before `main()` is ever entered."""
        import ast
        import pathlib

        source = pathlib.Path("benchmarks/phase0/__main__.py").resolve()
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        top_level = [node for node in tree.body if isinstance(node, ast.Import | ast.ImportFrom)]
        offenders = [
            name
            for node in top_level
            for name in (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
            )
            if name.startswith(("eaios_core.embedding", "qdrant_client", "torch", "transformers"))
        ]
        assert offenders == [], (
            "the benchmark entry point imports these at module scope, so they load"
            f" before preflight can refuse: {offenders}"
        )

    def test_a_failing_preflight_prevents_the_embedder_from_being_imported(
        self, unimported: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from benchmarks.phase0 import __main__ as entry

        monkeypatch.setattr(
            entry, "gather_environment", lambda _settings: _environment(qdrant_reachable=False)
        )
        exit_code = entry.main([])

        assert exit_code != 0, "a failing preflight did not stop the benchmark"
        assert self.EMBEDDER not in sys.modules, (
            "the embedder was imported despite preflight failing. Preflight ran after the"
            " thing it gates, so its refusal arrived too late to prevent anything"
        )

    def test_a_failing_preflight_prevents_a_qdrant_client(
        self, unimported: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from benchmarks.phase0 import __main__ as entry

        created: list[str] = []
        monkeypatch.setattr(
            entry, "gather_environment", lambda _s: _environment(minio_reachable=False)
        )
        monkeypatch.setattr(entry, "build_preview_index", lambda *a, **k: created.append("qdrant"))

        assert entry.main([]) != 0
        assert created == [], "a Qdrant collection was built despite preflight failing"

    def test_the_real_weights_probe_does_not_import_the_embedder(
        self, unimported: None, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The assertion the fake cannot make, without requiring a stack.

        `FakeEnvironment.observe()` returns a static dict, so it structurally cannot
        import anything — which is how a real preflight that *did* import the embedder
        went unnoticed. `LiveEnvironment._weights_checksum` hashes the weight file, and
        it used to reach `eaios_core.embedding.bge_m3` for the hashing helper: preflight
        importing the very module whose fate it decides.

        **Why this owns its boundaries.** An earlier version called the whole of
        `observe()` and passed only because the author's Docker stack happened to be
        running. Since the D3 fix an unreachable store *raises* rather than returning
        zeros, so on CI — which has no stack in the unit lane — it failed on both
        platforms. Skipping would have been worse: the assertion would then be silently
        unproven in exactly the environment that is supposed to prove it.

        So the three store probes are replaced with deterministic in-memory answers and
        the **weights path is left entirely real** — real files, real `pathlib`, real
        streaming SHA-256. That is the branch that used to pull the embedder in, and it
        is the branch under test. Nothing here opens a socket.
        """
        import socket

        from benchmarks.phase0.config import MeasurementConfig
        from benchmarks.phase0.live_environment import LiveEnvironment

        weights = tmp_path / "weights"
        weights.mkdir()
        body = b"not real weights, just bytes to hash"
        (weights / "pytorch_model.bin").write_bytes(body)
        (weights / ".revision").write_text("0" * 40, encoding="utf-8")

        # Any outbound attempt is recorded and refused, so "no store was contacted" is
        # measured rather than asserted from reading the code.
        attempts: list[str] = []

        def refuse(*args: object, **kwargs: object) -> object:
            attempts.append(repr(args))
            raise AssertionError("the weights probe attempted a network connection")

        monkeypatch.setattr(socket, "create_connection", refuse)
        monkeypatch.setattr(socket, "getaddrinfo", refuse)
        monkeypatch.setattr(socket.socket, "connect", refuse, raising=False)

        environment = LiveEnvironment(MeasurementConfig(weights_directory=weights))

        # Only the external store boundaries are replaced. Everything about weights —
        # locating the file, reading the marker, hashing the bytes — runs for real.
        monkeypatch.setattr(type(environment), "_probe_postgres", lambda self, e: True)
        monkeypatch.setattr(type(environment), "_probe_minio", lambda self, e: True)
        monkeypatch.setattr(type(environment), "_probe_qdrant", lambda self, e: True)
        monkeypatch.setattr(type(environment), "_active_profile", lambda self, e: "full")
        monkeypatch.setattr(type(environment), "_text_document_count", lambda self, e: 105)
        monkeypatch.setattr(type(environment), "_code_collection_points", lambda self, e: 0)
        monkeypatch.setattr(type(environment), "_unreadable_objects", lambda self, e: ())

        observed = environment.observe()

        expected = hashlib.sha256(body).hexdigest()
        assert observed["weights_checksum"] == expected, (
            "the real weights branch did not run; the checksum is not the one this test"
            " wrote to disk"
        )
        assert observed["weights_revision"] == "0" * 40, "the revision marker was not read"
        assert attempts == [], f"a network connection was attempted: {attempts}"

        # Far enough to have verified provenance: preflight can now judge the weights.
        report = run(_FixedObservation(observed))
        assert any(check.name == "BGE weights checksum" for check in report.checks), (
            "preflight did not reach the weights checks, so provenance was never verified"
        )

        assert self.EMBEDDER not in sys.modules, (
            "the real preflight probe imported the embedder module. Preflight decides"
            " whether the embedder may be constructed; importing it to make that decision"
            " inverts the ordering (T022)"
        )

    def test_the_checksum_helper_lives_outside_the_embedding_package(self) -> None:
        """Structural guard, so the import cannot creep back in unnoticed."""
        import ast

        source = pathlib.Path("benchmarks/phase0/live_environment.py").resolve()
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        offenders = [
            f"line {node.lineno}: {node.module}"
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and (node.module or "").startswith("eaios_core.embedding")
        ]
        assert offenders == [], (
            "the live environment imports the embedding package again; preflight runs"
            f" through this module: {offenders}"
        )

    def test_preflight_is_the_first_call_in_main(self) -> None:
        """Static backstop: whatever `main` does first, it is preflight."""
        import ast
        import pathlib

        source = pathlib.Path("benchmarks/phase0/__main__.py").resolve()
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        main_function = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "main"
        )
        called: list[str] = []
        for node in ast.walk(main_function):
            if isinstance(node, ast.Call):
                target = node.func
                name = (
                    target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
                )
                if name:
                    called.append(name)

        gating = [n for n in called if n in {"gather_environment", "run_preflight", "run"}]
        assert gating, f"`main` calls no preflight function at all: {called}"


class TestASatisfiedPreflightPermitsExactlyOneConstruction:
    """Not zero — a preflight that always refuses is useless. Not two — a second
    construction means the first was wasted, which on a 2 GB model is a minute."""

    def test_the_embedder_is_constructed_once(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
    ) -> None:
        from benchmarks.phase0 import __main__ as entry
        from benchmarks.phase0.results import Outcome, RowResult

        constructions: list[str] = []
        rows = (
            RowResult(name="preview", outcome=Outcome.NOT_RUN),
            RowResult(name="first_token", outcome=Outcome.NOT_RUN),
        )

        monkeypatch.setenv("PHASE0_RESULTS_DIR", str(tmp_path / "results"))
        monkeypatch.setattr(entry, "gather_environment", lambda _s: _environment())
        monkeypatch.setattr(
            entry, "load_embedder", lambda *a, **k: constructions.append("embedder") or object()
        )
        monkeypatch.setattr(entry, "build_preview_index", lambda *a, **k: None)
        monkeypatch.setattr(entry, "measure", lambda *a, **k: rows)

        entry.main([])
        assert constructions == ["embedder"], (
            f"expected exactly one embedder construction, got {len(constructions)}"
        )

    def test_an_unmeasured_row_does_not_exit_zero(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
    ) -> None:
        """A caller reading only the exit code must not read absence as success."""
        from benchmarks.phase0 import __main__ as entry
        from benchmarks.phase0.results import Outcome, RowResult

        monkeypatch.setenv("PHASE0_RESULTS_DIR", str(tmp_path / "results"))
        monkeypatch.setattr(entry, "gather_environment", lambda _s: _environment())
        monkeypatch.setattr(entry, "load_embedder", lambda *a, **k: object())
        monkeypatch.setattr(entry, "build_preview_index", lambda *a, **k: None)
        monkeypatch.setattr(
            entry,
            "measure",
            lambda *a, **k: (
                RowResult(name="preview", outcome=Outcome.NOT_RUN),
                RowResult(name="first_token", outcome=Outcome.NOT_RUN),
            ),
        )
        assert entry.main([]) != 0


class TestTheReportIsAValue:
    def test_the_report_is_frozen(self) -> None:
        report = run(_environment())
        assert isinstance(report, PreflightReport)
        # `checks` is the field; `ok` is derived from it. Assigning to a property would
        # raise TypeError from the slots machinery, which is not the immutability claim.
        with pytest.raises(dataclasses.FrozenInstanceError):
            report.checks = ()  # type: ignore[misc]

    def test_the_derived_verdict_cannot_be_overridden(self) -> None:
        """`ok` is computed from `checks`; nothing may pin it to a different answer.

        The exception type is Python's business, not this project's — a frozen slots
        dataclass raises `TypeError` from its generated `__setattr__` here rather than
        the `AttributeError` a plain property would. What matters is that it refuses.
        """
        report = run(_environment())
        with pytest.raises((AttributeError, TypeError)):
            report.ok = False  # type: ignore[misc]
        assert report.ok is True

    def test_the_module_exposes_its_pins(self) -> None:
        assert preflight.EXPECTED_DOCUMENT_COUNT == 105
        assert preflight.EXPECTED_PROFILE == "full"
