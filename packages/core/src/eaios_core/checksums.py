"""File checksums, with no dependency on what is being checksummed.

**Why this is its own module.** `sha256_of` used to live in `eaios_core.embedding.bge_m3`,
which meant that anything wanting to hash a file had to import the embedder. Phase 0's
preflight did exactly that — it hashes the weight file to verify the pin — so preflight
imported the embedder module *while checking whether the embedder may be constructed*.
That inverted the ordering preflight exists to enforce.

Hashing a file has nothing to do with embedding. Separating them removes the inversion
structurally rather than by remembering not to do it.

Nothing here imports anything outside the standard library.
"""

from __future__ import annotations

import hashlib
import pathlib
from typing import Final

__all__ = ["BLOCK_SIZE", "sha256_of"]

#: Read size. The BGE-M3 weight file is 2.2 GB; reading it whole would cost more memory
#: than the process that is about to load the model.
BLOCK_SIZE: Final[int] = 1024 * 1024


def sha256_of(path: pathlib.Path) -> str:
    """Streaming SHA-256 of a file.

    Args:
        path: File to hash.

    Returns:
        Lowercase hex digest.
    """
    digest = hashlib.sha256()
    with pathlib.Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(BLOCK_SIZE), b""):
            digest.update(block)
    return digest.hexdigest()
