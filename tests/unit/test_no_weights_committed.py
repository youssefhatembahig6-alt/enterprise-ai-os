"""No model weight file is tracked by git (FR-011g, CHK072).

**Why this exists.** Two licences meet here and only one of them is permissive. BGE-M3 is
MIT, so committing it would be legal and merely wasteful. Qwen2.5-3B-Instruct is the Qwen
RESEARCH LICENSE, whose §3 permits redistribution only with the agreement attached, an
attribution notice, and modified files marked — none of which a `git add` does. A weight
file committed by accident is therefore a licence violation that looks exactly like a large
diff, and it survives in history after the file is deleted.

`.gitignore` prevents the accident. This test proves the prevention worked, which is not
the same claim: `git add -f` bypasses the ignore file, and so does a pattern that was added
after the file was already tracked.

The scan reads `git ls-files`, not the working tree. An ignored file sitting in the working
directory is exactly the intended state — the point is that it never became *tracked*.
"""

from __future__ import annotations

import pathlib
import subprocess
from typing import Final

import pytest

pytestmark = pytest.mark.unit

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[2]

#: Extensions that only ever hold model weights. `.bin` is the loose one — it is also a
#: plausible extension for unrelated binary fixtures — which is why the failure message
#: names the file rather than asserting a bare count.
WEIGHT_SUFFIXES: Final[frozenset[str]] = frozenset(
    {".gguf", ".safetensors", ".bin", ".pt", ".pth", ".onnx", ".onnx_data", ".h5", ".ckpt"}
)

#: Directories that hold weights by convention, **anchored to the repository root**.
#: Unanchored would be wrong in both directions: it would flag every file under
#: `packages/core/src/eaios_core/models/`, which is the ORM package, and it would teach
#: `.gitignore` to swallow new files there.
WEIGHT_DIRECTORIES: Final[frozenset[str]] = frozenset({"models"})


def _tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def _looks_like_weights(path: str) -> bool:
    pure = pathlib.PurePosixPath(path)
    if pure.parts and pure.parts[0] in WEIGHT_DIRECTORIES:
        return True
    return pure.suffix.lower() in WEIGHT_SUFFIXES


class TestTheScanHasSubjects:
    """A scan that reads no files passes exactly like a correct one."""

    def test_git_reports_tracked_files(self) -> None:
        tracked = _tracked_files()
        assert len(tracked) > 50, (
            "`git ls-files` returned almost nothing, so this test would pass over an"
            f" empty set rather than over the repository: {len(tracked)} paths"
        )

    def test_the_predicate_recognises_a_weight_path(self) -> None:
        """Falsification: the detector must fire on the paths it exists to catch."""
        for candidate in (
            "models/bge-m3/pytorch_model.bin",
            "qwen2.5-3b-instruct-q4_k_m.gguf",
            "packages/core/model.safetensors",
        ):
            assert _looks_like_weights(candidate), f"detector missed {candidate}"

    def test_the_predicate_leaves_ordinary_files_alone(self) -> None:
        for candidate in (
            "packages/core/src/eaios_core/ids.py",
            "docs/models.md",
            "Makefile",
            # The ORM package. An unanchored `models` rule flags all eleven of these,
            # and the matching `.gitignore` rule would hide the next one added.
            "packages/core/src/eaios_core/models/hr.py",
        ):
            assert not _looks_like_weights(candidate), f"detector fired on {candidate}"


class TestNoWeightsAreTracked:
    def test_no_tracked_file_is_a_model_weight(self) -> None:
        offenders = sorted(path for path in _tracked_files() if _looks_like_weights(path))
        assert offenders == [], (
            "model weight files are tracked by git. The Qwen licence permits"
            " redistribution only with the agreement attached (§3), and git history keeps"
            " them after deletion, so this needs a history rewrite rather than a commit:\n  "
            + "\n  ".join(offenders)
        )


class TestGitignoreCarriesThePatterns:
    """The test above proves the current state; these prove the guard that keeps it."""

    @pytest.mark.parametrize("pattern", ["/models/", "*.gguf", "*.safetensors", "*.bin"])
    def test_the_pattern_is_present(self, pattern: str) -> None:
        text = (REPO / ".gitignore").read_text(encoding="utf-8")
        assert pattern in text.split(), (
            f"`.gitignore` no longer excludes `{pattern}`; the next weight download lands"
            " in `git status` as an untracked file waiting to be added by a wildcard"
        )
