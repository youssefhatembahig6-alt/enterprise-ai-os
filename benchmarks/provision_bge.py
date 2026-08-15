"""Provision and verify the pinned BGE-M3 weights (FR-011f, FR-011g).

**Why a checked-in helper rather than three shell commands.** The documented process used
to be `huggingface-cli download`, then `sha256sum`, then — nothing. The revision was never
recorded anywhere the benchmark could read, so preflight demanded a `.revision` marker that
no step in the repository created. A convention invented by the consumer and written by
nobody: correct weights on disk, matching checksum, and preflight refusing anyway.

This helper closes that loop. It verifies the checksum **before** writing the marker, so the
marker's existence means the bytes were checked — not that a download once started. And it
writes **atomically**, because a marker half-written by an interrupted run is worse than no
marker: it asserts a verification that did not finish.

**Verify-only is the default posture for already-provisioned weights.** `--verify-only`
never touches the network, so re-establishing the marker on a machine that already has the
files costs nothing and risks nothing.

Cross-platform by construction: `pathlib`, `hashlib`, `os.replace`. No shell, no
`sha256sum`, no `huggingface-cli` on PATH, and no dependence on the layout of Hugging
Face's cache — the revision is recorded because this script writes it, not because it was
excavated from somewhere undocumented.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
from typing import Final

REPO_ROOT: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages/core/src"))

from eaios_core.checksums import sha256_of  # noqa: E402

__all__ = ["MARKER_NAME", "main", "provision", "verify_only", "write_revision_marker"]

#: From `docs/models.md`, verified against the authoritative model card.
REPOSITORY: Final[str] = "BAAI/bge-m3"
REVISION: Final[str] = "5617a9f61b028005a4858fdac845db406aefb181"
WEIGHT_FILENAME: Final[str] = "pytorch_model.bin"
WEIGHT_SHA256: Final[str] = "b5e0ce3470abf5ef3831aa1bd5553b486803e83251590ab7ff35a117cf6aad38"
WEIGHT_SIZE_BYTES: Final[int] = 2_271_145_830

#: Everything the chunker's tokenizer and the embedder need. Deliberately not the whole
#: repository: the ONNX and Colbert artefacts are megabytes this feature never loads.
REQUIRED_FILES: Final[tuple[str, ...]] = (
    WEIGHT_FILENAME,
    "config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "sentencepiece.bpe.model",
    "special_tokens_map.json",
)

#: Read by `LiveEnvironment._weights_revision`. Ignored by git (`.gitignore` `/models/`).
MARKER_NAME: Final[str] = ".revision"

DEFAULT_DIRECTORY: Final[pathlib.Path] = REPO_ROOT / "models" / "bge-m3"


class ProvisioningError(RuntimeError):
    """The weights are not the pinned ones, or are not all there."""


def write_revision_marker(directory: pathlib.Path, revision: str = REVISION) -> pathlib.Path:
    """Record the verified revision, atomically.

    Written to a temporary file in the same directory and then `os.replace`d, which is
    atomic on both POSIX and Windows. A reader therefore sees either no marker or a
    complete one — never a truncated revision that would compare unequal and send someone
    hunting for a corruption that is really an interrupted write.
    """
    directory = pathlib.Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    marker = directory / MARKER_NAME
    temporary = directory / f"{MARKER_NAME}.{os.getpid()}.tmp"
    temporary.write_text(revision + "\n", encoding="utf-8")
    os.replace(temporary, marker)
    return marker


def verify_only(directory: pathlib.Path) -> str:
    """Check what is already on disk and write the marker. No network access.

    Returns:
        The verified SHA-256 of the weight file.

    Raises:
        ProvisioningError: A required file is missing, or the checksum does not match the
            pin. An unverified download is a guess about what will run (FR-011f).
    """
    directory = pathlib.Path(directory)

    missing = [name for name in REQUIRED_FILES if not (directory / name).is_file()]
    if missing:
        raise ProvisioningError(
            f"{directory} is missing {missing}. Run this helper without --verify-only to"
            " download them, or see docs/models.md"
        )

    weight = directory / WEIGHT_FILENAME
    size = weight.stat().st_size
    if size != WEIGHT_SIZE_BYTES:
        raise ProvisioningError(
            f"{weight} is {size} bytes, expected {WEIGHT_SIZE_BYTES}. A partial download"
            " hashes to something plausible and is not the pinned model"
        )

    actual = sha256_of(weight)
    if actual != WEIGHT_SHA256:
        raise ProvisioningError(
            f"{weight} has checksum {actual}, not the pinned {WEIGHT_SHA256}. These are"
            " different weights, so any vector produced from them would not be comparable"
            " with an index built from the pinned ones"
        )

    write_revision_marker(directory)
    return actual


def provision(directory: pathlib.Path) -> str:
    """Download the pinned files if absent, then verify and record.

    Downloading is a **provisioning** activity and lives here, deliberately away from
    every request path (FR-011f). Already-present files are not re-fetched.
    """
    directory = pathlib.Path(directory)
    if any(not (directory / name).is_file() for name in REQUIRED_FILES):
        from huggingface_hub import snapshot_download

        snapshot_download(
            repo_id=REPOSITORY,
            revision=REVISION,
            local_dir=str(directory),
            allow_patterns=list(REQUIRED_FILES),
        )
    return verify_only(directory)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="provision_bge",
        description="Provision and verify the pinned BGE-M3 weights, then record the revision.",
    )
    parser.add_argument(
        "--directory",
        type=pathlib.Path,
        default=DEFAULT_DIRECTORY,
        help=f"where the weights live (default: {DEFAULT_DIRECTORY})",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="check and record what is already on disk; never touch the network",
    )
    arguments = parser.parse_args(argv)

    try:
        checksum = (
            verify_only(arguments.directory)
            if arguments.verify_only
            else provision(arguments.directory)
        )
    except ProvisioningError as failure:
        print(f"provisioning failed: {failure}", file=sys.stderr)
        return 1

    print(f"repository : {REPOSITORY}")
    print(f"revision   : {REVISION}")
    print(f"checksum   : {checksum}")
    print(f"directory  : {arguments.directory}")
    print(f"marker     : {arguments.directory / MARKER_NAME}")
    return 0


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())
