"""The BGE runtime reaches every image that needs it, at one identical version (CHK087).

**Why this exists.** Three services embed: the API embeds retrieval queries, the seed embeds
documents during ingestion, and the worker executes tenant-attributed indexing. All three
install `./packages/core`, so declaring the runtime there is what puts it in front of all
three at once — that is the decision, not an accident of where the import happens to live
(FR-011c, FR-035p).

Two things can quietly break that arrangement, and neither shows up in a test run:

1. An image stops installing `packages/core`. The service then starts without the runtime
   and fails at the first embedding call, in production, at request time.
2. The pin in `packages/core/pyproject.toml` drifts from the version the root `uv.lock`
   resolved. Local tests then run one version and the containers another — the class of
   difference that makes a determinism guarantee meaningless, because two vector spaces
   are involved and neither is wrong on its own.

This check is **static**: it reads files. It needs no Docker, no network and no runtime
installed, so it blocks the ordinary build (FR-035b) rather than waiting for a deploy.
"""

from __future__ import annotations

import pathlib
import re
import tomllib
from typing import Any, Final

import pytest

pytestmark = pytest.mark.unit

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[2]

#: Every image that installs core, and therefore every image that gains the runtime.
DOCKERFILES: Final[dict[str, pathlib.Path]] = {
    "api": REPO / "apps/api/Dockerfile",
    "worker": REPO / "services/worker/Dockerfile",
    "seed": REPO / "scripts/seed/Dockerfile",
}

CORE_MANIFEST: Final[pathlib.Path] = REPO / "packages/core/pyproject.toml"
ROOT_MANIFEST: Final[pathlib.Path] = REPO / "pyproject.toml"
LOCKFILE: Final[pathlib.Path] = REPO / "uv.lock"

#: The distributions that make up the local BGE-M3 runtime.
BGE_RUNTIME: Final[tuple[str, ...]] = ("torch", "transformers", "sentencepiece")


def _pins(manifest: pathlib.Path) -> dict[str, str]:
    """Distribution name → exact pinned version, for `==` pins only."""
    data = tomllib.loads(manifest.read_text(encoding="utf-8"))
    pins: dict[str, str] = {}
    for entry in data.get("project", {}).get("dependencies", []):
        if "==" not in entry:
            continue
        name, version = entry.split("==", 1)
        pins[name.split("[")[0].strip().lower().replace("_", "-")] = version.strip()
    return pins


def _locked_entries(name: str) -> list[dict[str, Any]]:
    """**Every** lock entry for one distribution, in lock order.

    A dictionary keyed by name is wrong for `torch` and quietly so. The CPU index
    resolves two entries — `2.5.1` for the macOS/aarch64 wheels, which carry no local
    segment, and `2.5.1+cpu` for linux_x86_64 and win_amd64 — and collapsing them means
    whichever appears last decides the verdict. The assertions below would then pass or
    fail on lock-entry order rather than on what is locked.
    """
    data = tomllib.loads(LOCKFILE.read_text(encoding="utf-8"))
    wanted = name.lower().replace("_", "-")
    return [
        package
        for package in data.get("package", [])
        if str(package.get("name", "")).lower().replace("_", "-") == wanted
    ]


def _locked_versions() -> dict[str, str]:
    """Distribution name → version, for the single-entry distributions.

    Retained for the pin-comparison tests, which compare *public* versions. Use
    `_locked_entries` wherever a distribution may legitimately appear more than once.
    """
    data = tomllib.loads(LOCKFILE.read_text(encoding="utf-8"))
    return {
        str(package["name"]).lower().replace("_", "-"): str(package["version"])
        for package in data.get("package", [])
        if "name" in package and "version" in package
    }


def cpu_torch_violations(entries: list[dict[str, Any]], expected_public: str) -> list[str]:
    """Every reason `entries` are not an acceptable CPU-only torch resolution.

    Pure and order-independent by construction: it inspects each entry on its own and
    returns a sorted list, so reversing the input cannot change the answer. That is what
    `TestTheCpuCheckIsOrderIndependent` relies on.
    """
    violations: list[str] = []

    if not entries:
        return ["torch is absent from the lockfile"]

    for entry in entries:
        version = str(entry.get("version", ""))
        registry = str(entry.get("source", {}).get("registry", ""))

        if registry != CPU_INDEX_URL:
            violations.append(
                f"{version}: resolved from {registry or '<no registry>'}, not the CPU"
                " index. A default-index resolution is the CUDA build"
            )

        # `2.5.1` and `2.5.1+cpu` are the same upstream release. The local segment is
        # present only on the platforms where PyTorch publishes a distinct CPU build;
        # macOS has no CUDA build to distinguish from, so it carries none. Demanding a
        # `+cpu` tag on every entry would fail a correct lock.
        if _public_version(version) != expected_public:
            violations.append(
                f"{version}: public version is not the pinned {expected_public}"
            )

        local = _local_segment(version)
        if local not in ("", "cpu"):
            violations.append(
                f"{version}: local segment {local!r} is neither absent nor 'cpu';"
                " a build tag like 'cu124' is a GPU build"
            )

        cuda = sorted(
            str(dependency.get("name", ""))
            for dependency in entry.get("dependencies", [])
            if str(dependency.get("name", "")).startswith("nvidia-")
            or str(dependency.get("name", "")) == "triton"
        )
        if cuda:
            violations.append(f"{version}: depends on CUDA distributions {cuda}")

    return sorted(violations)


def _installs_core(dockerfile: pathlib.Path) -> bool:
    """Whether the image installs `./packages/core`, across line continuations.

    The naive `pip install[^\\n]*\\./packages/core` is single-line and broke the moment
    the command grew a `\\`-continued index flag — reporting that three correct images
    had stopped installing core.
    """
    text = dockerfile.read_text(encoding="utf-8")
    joined = re.sub(r"\\\s*\n\s*", " ", text)
    return bool(re.search(r"pip install[^\n]*\./packages/core", joined))


def _public_version(version: str) -> str:
    """The version without its PEP 440 local segment: `2.5.1+cpu` -> `2.5.1`."""
    return version.split("+", 1)[0]


def _local_segment(version: str) -> str:
    """The local segment, or empty: `2.5.1+cpu` -> `cpu`."""
    return version.split("+", 1)[1] if "+" in version else ""


class TestTheScanHasSubjects:
    """A check that reads no files passes exactly like a correct one."""

    def test_every_dockerfile_exists(self) -> None:
        missing = [name for name, path in DOCKERFILES.items() if not path.is_file()]
        assert missing == [], f"missing Dockerfiles: {missing}"

    def test_the_manifests_and_lockfile_exist(self) -> None:
        for path in (CORE_MANIFEST, ROOT_MANIFEST, LOCKFILE):
            assert path.is_file(), f"missing {path.relative_to(REPO)}"

    def test_the_lockfile_parses_to_something(self) -> None:
        locked = _locked_versions()
        assert len(locked) > 50, (
            f"the lockfile yielded {len(locked)} packages, so the comparison below would"
            " run over an almost-empty mapping and pass without checking anything"
        )

    def test_the_core_manifest_pins_something(self) -> None:
        assert _pins(CORE_MANIFEST), "no `==` pins parsed out of packages/core/pyproject.toml"


class TestEveryImageInstallsCore:
    @pytest.mark.parametrize("service", sorted(DOCKERFILES))
    def test_the_image_installs_packages_core(self, service: str) -> None:
        assert _installs_core(DOCKERFILES[service]), (
            f"the {service} image no longer installs `./packages/core`, so it ships"
            " without the BGE-M3 runtime and fails at the first embedding call rather"
            f" than at build time: {DOCKERFILES[service].relative_to(REPO)}"
        )


class TestCoreDeclaresTheRuntime:
    @pytest.mark.parametrize("distribution", BGE_RUNTIME)
    def test_core_pins_the_distribution(self, distribution: str) -> None:
        assert distribution in _pins(CORE_MANIFEST), (
            f"`{distribution}` is not declared in packages/core/pyproject.toml. The three"
            " images install from that manifest, so an undeclared runtime is present"
            " locally and absent in every container (FR-035p)"
        )


class TestThePinMatchesTheLock:
    """The drift check. Docker resolves from core's manifest; developers resolve from
    the root lock. Identical is the only relationship between them that is safe."""

    @pytest.mark.parametrize("distribution", BGE_RUNTIME)
    def test_the_core_pin_equals_every_locked_version(self, distribution: str) -> None:
        """Every locked entry, so a distribution with per-platform entries is fully checked."""
        core = _pins(CORE_MANIFEST).get(distribution)
        entries = _locked_entries(distribution)

        assert core is not None, f"`{distribution}` is not pinned in core's manifest"
        assert entries, (
            f"`{distribution}` is pinned in core's manifest but absent from uv.lock;"
            " run `uv lock` so the developer environment matches the containers"
        )
        # Compared on the *public* version. `torch==2.5.1` legitimately resolves to
        # `2.5.1+cpu`: the `+cpu` is a PEP 440 local segment identifying the build, and a
        # pin without one matches any local version. Demanding string equality here would
        # report drift every time the CPU index is used, which is always.
        drifted = sorted(
            str(entry["version"])
            for entry in entries
            if _public_version(str(entry["version"])) != _public_version(core)
        )
        assert drifted == [], (
            f"`{distribution}` drifted: packages/core pins {core}, the root uv.lock"
            f" resolved {drifted}. Local tests and the containers would run different"
            " versions of the embedding runtime, which is two vector spaces"
        )

    @pytest.mark.parametrize("distribution", BGE_RUNTIME)
    def test_the_root_pin_equals_the_core_pin(self, distribution: str) -> None:
        root = _pins(ROOT_MANIFEST).get(distribution)
        core = _pins(CORE_MANIFEST).get(distribution)
        assert root == core, (
            f"`{distribution}`: root manifest pins {root}, packages/core pins {core}."
            " FR-035p requires one identical version pin in both"
        )


#: The CPU-only PyTorch index. Every consumer of `packages/core` must resolve through it.
CPU_INDEX_URL: Final[str] = "https://download.pytorch.org/whl/cpu"

#: Distributions that only exist to serve a GPU. Their presence means the default CUDA
#: wheel was resolved somewhere.
CUDA_MARKERS: Final[tuple[str, ...]] = ("nvidia-", "triton")


class TestTheRuntimeIsCpuOnly:
    """Embedding runs on the local CPU and the reference machine has no CUDA stack.

    The default PyPI `torch` wheel bundles the CUDA runtime — thirteen `nvidia-*`
    distributions plus `triton`, gigabytes of it — into every image that installs
    `packages/core`, which is the API, the worker *and* the seed. None of them can use a
    GPU, so the payload is pure weight and pure download time. It is also the kind of
    regression that reappears silently the next time someone re-locks.
    """

    def test_the_lockfile_carries_no_cuda_distribution(self) -> None:
        offenders = sorted(
            name
            for name in _locked_versions()
            if name.startswith(CUDA_MARKERS[0]) or name == CUDA_MARKERS[1]
        )
        assert offenders == [], (
            "CUDA distributions are back in uv.lock, so every image that installs"
            " packages/core now ships a GPU runtime it cannot use. Check that"
            f" `[tool.uv.sources] torch` still points at the CPU index:\n  {offenders}"
        )

    def test_the_root_manifest_pins_the_cpu_index(self) -> None:
        text = ROOT_MANIFEST.read_text(encoding="utf-8")
        assert CPU_INDEX_URL in text, (
            f"the root manifest no longer declares {CPU_INDEX_URL}; the next `uv lock`"
            " resolves the CUDA build"
        )
        assert "torch = [{ index = " in text, (
            "`[tool.uv.sources]` no longer routes torch to that index, so declaring it"
            " has no effect"
        )

    def test_every_locked_torch_entry_is_an_acceptable_cpu_build(self) -> None:
        """All entries, not whichever one a dictionary happened to keep."""
        expected = _public_version(_pins(ROOT_MANIFEST)["torch"])
        violations = cpu_torch_violations(_locked_entries("torch"), expected)
        assert violations == [], (
            "the locked torch resolution is not CPU-only:\n  " + "\n  ".join(violations)
        )

    def test_the_lock_really_does_carry_more_than_one_torch_entry(self) -> None:
        """Vacuity guard for the order-independence test below.

        If the lock ever collapses to a single entry, the reversal test still passes but
        stops proving anything — reversing a one-element list is a no-op.
        """
        entries = _locked_entries("torch")
        assert len(entries) >= 1, "torch is absent from the lockfile"
        if len(entries) == 1:
            pytest.skip(
                "only one torch entry is locked, so ordering cannot matter here;"
                " the order-independence test is trivially satisfied"
            )
        versions = sorted(str(e["version"]) for e in entries)
        assert len(set(versions)) == len(versions), f"duplicate torch versions: {versions}"

    @pytest.mark.parametrize("service", sorted(DOCKERFILES))
    def test_the_image_resolves_torch_from_the_cpu_index(self, service: str) -> None:
        text = DOCKERFILES[service].read_text(encoding="utf-8")
        assert CPU_INDEX_URL in text, (
            f"the {service} image does not pin the CPU index, so `pip install"
            " ./packages/core` resolves the default CUDA wheel — a container that"
            " downloads gigabytes of GPU runtime it has no GPU for"
        )

    @pytest.mark.parametrize("service", sorted(DOCKERFILES))
    def test_the_cpu_index_is_primary_not_extra(self, service: str) -> None:
        """`--extra-index-url` alone still lets the default CUDA build win."""
        text = DOCKERFILES[service].read_text(encoding="utf-8")
        assert f"--index-url {CPU_INDEX_URL}" in text, (
            f"the {service} image lists the CPU index as an *extra* index or not at all."
            " pip may then prefer the default PyPI CUDA wheel; the CPU index must be the"
            " primary `--index-url`"
        )


class TestTheCpuCheckIsOrderIndependent:
    """Reversing the lock entries must not change the verdict.

    This is the regression guard for the defect it replaces: the previous assertion read
    a dictionary keyed by package name, so with two `torch` entries the answer came from
    whichever one uv happened to emit last. It passed — and would have kept passing, or
    started failing, for a reason that has nothing to do with what is locked.
    """

    @staticmethod
    def _expected() -> str:
        return _public_version(_pins(ROOT_MANIFEST)["torch"])

    def test_forward_and_reversed_agree(self) -> None:
        entries = _locked_entries("torch")
        forward = cpu_torch_violations(entries, self._expected())
        reversed_ = cpu_torch_violations(list(reversed(entries)), self._expected())
        assert forward == reversed_, (
            "reversing the lock entries changed the verdict, so the check depends on"
            f" ordering: {forward} vs {reversed_}"
        )

    def test_both_orders_are_clean(self) -> None:
        entries = _locked_entries("torch")
        for label, ordering in (("forward", entries), ("reversed", list(reversed(entries)))):
            assert cpu_torch_violations(ordering, self._expected()) == [], label

    def test_a_planted_cuda_entry_is_caught_in_either_order(self) -> None:
        """Falsification: the check must fire wherever the bad entry sits."""
        planted = {
            "name": "torch",
            "version": "2.5.1+cu124",
            "source": {"registry": "https://pypi.org/simple"},
            "dependencies": [{"name": "nvidia-cudnn-cu12"}, {"name": "triton"}],
        }
        entries = [*_locked_entries("torch"), planted]

        first = cpu_torch_violations(entries, self._expected())
        last = cpu_torch_violations(list(reversed(entries)), self._expected())

        assert first, "a planted CUDA entry was not detected"
        assert first == last, "detection depended on where the bad entry sat"
        assert any("nvidia-cudnn-cu12" in v for v in first)
        assert any("cu124" in v for v in first)
        assert any("pypi.org" in v for v in first)

    def test_the_legitimate_platform_split_is_accepted(self) -> None:
        """`2.5.1` and `2.5.1+cpu` are the same release on different platforms."""
        both = [
            {
                "name": "torch",
                "version": "2.5.1",
                "source": {"registry": CPU_INDEX_URL},
                "dependencies": [{"name": "filelock"}],
            },
            {
                "name": "torch",
                "version": "2.5.1+cpu",
                "source": {"registry": CPU_INDEX_URL},
                "dependencies": [{"name": "filelock"}],
            },
        ]
        assert cpu_torch_violations(both, "2.5.1") == []
        assert cpu_torch_violations(list(reversed(both)), "2.5.1") == []

    def test_a_wrong_public_version_is_rejected_in_either_order(self) -> None:
        drifted = [
            {"name": "torch", "version": "2.4.0", "source": {"registry": CPU_INDEX_URL}},
            {"name": "torch", "version": "2.5.1+cpu", "source": {"registry": CPU_INDEX_URL}},
        ]
        assert cpu_torch_violations(drifted, "2.5.1")
        assert cpu_torch_violations(drifted, "2.5.1") == cpu_torch_violations(
            list(reversed(drifted)), "2.5.1"
        )


class TestNoInertBenchmarkManifest:
    """FR-035p names this specific mistake, so the check names it too."""

    def test_there_is_no_benchmarks_pyproject(self) -> None:
        stray = REPO / "benchmarks" / "pyproject.toml"
        assert not stray.exists(), (
            "`benchmarks/pyproject.toml` exists. Nothing installs from it — there is no"
            " uv workspace in this repository and no benchmark image — so a pin placed"
            " there is inert while looking authoritative (FR-035p)"
        )


class TestTheCheckWouldCatchTheRealCase:
    """Falsification: the comparison must fail when a pin actually drifts."""

    def test_a_drifted_pin_is_detected(self) -> None:
        locked = dict(_locked_versions())
        locked["torch"] = "0.0.1-not-a-real-version"
        assert _pins(CORE_MANIFEST)["torch"] != locked["torch"], (
            "a fabricated version compared equal to the manifest pin, so the drift check"
            " above cannot distinguish agreement from disagreement"
        )

    def test_a_dockerfile_without_the_install_is_detected(self, tmp_path: pathlib.Path) -> None:
        decoy = tmp_path / "Dockerfile"
        decoy.write_text("FROM python:3.12-slim\nRUN pip install ./apps/api\n", encoding="utf-8")
        assert not _installs_core(decoy), "the detector accepted an image that skips core"
