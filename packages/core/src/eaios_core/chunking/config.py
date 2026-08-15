"""Chunker configuration, and the hash that makes a change to it detectable (FR-007a/b).

Every field here is part of chunk identity. That is the point: two chunks with the same
text but different configuration are **not** the same chunk, because the procedures that
produced them differ, and an index holding both would be holding two chunk generations it
cannot tell apart.

`chunker_config_hash` is what an index records so a later run can notice the change and
re-ingest rather than mix (contracts IC §2).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from typing import Final

__all__ = ["DEFAULT_CONFIG", "ChunkerConfig"]

#: Bumped whenever boundary placement changes. Changing it moves every chunk identifier in
#: the corpus, which is the intended cost of changing how documents are cut.
CHUNKER_VERSION: Final[str] = "chunker@v1"

#: The pinned embedding tokenizer, revision included. `docs/models.md` records the same
#: revision; `benchmarks/phase0/preflight.py` verifies the weights match it before any
#: measurement. Including the revision means a tokenizer upgrade cannot silently reuse
#: identifiers computed under the old one.
BGE_M3_TOKENIZER_IDENTITY: Final[str] = "bge-m3@5617a9f61b028005a4858fdac845db406aefb181"


@dataclasses.dataclass(frozen=True, slots=True)
class ChunkerConfig:
    """Settled chunking parameters (FR-007a, research R21).

    Attributes:
        chunker_version: Boundary-placement version.
        strategy: Boundary strategy. ``structure-first`` splits on document structure
            before sentence boundaries.
        max_tokens: Maximum tokens per chunk, counted by `tokenizer_identity`.
        overlap_tokens: Maximum overlap between neighbours, as complete trailing
            sentences where possible.
        tokenizer_identity: The tokenizer the two bounds are expressed in.
    """

    chunker_version: str = CHUNKER_VERSION
    strategy: str = "structure-first"
    #: 400 is chosen against the *generation* budget, not retrieval alone: FR-028b2 allows
    #: 400 tokens per passage, so a chunk that fits here also fits a passage slot without
    #: trimming in the common case, making trimming the exception (research R21).
    max_tokens: int = 400
    #: One to three sentences of ordinary prose. The sentence answering a question is
    #: often the one right after a heading, and a boundary placed just before it would
    #: leave that sentence without its context in either neighbour.
    overlap_tokens: int = 50
    tokenizer_identity: str = BGE_M3_TOKENIZER_IDENTITY

    def __post_init__(self) -> None:
        if self.max_tokens <= 0:
            raise ValueError(f"max_tokens must be positive, got {self.max_tokens}")
        if self.overlap_tokens < 0:
            raise ValueError(f"overlap_tokens must not be negative, got {self.overlap_tokens}")
        if self.overlap_tokens >= self.max_tokens:
            raise ValueError(
                f"overlap_tokens ({self.overlap_tokens}) must be smaller than max_tokens"
                f" ({self.max_tokens}); an overlap at or above the budget cannot terminate"
            )

    @property
    def chunker_config_hash(self) -> str:
        """SHA-256 over every field, as sorted JSON.

        Sorted keys rather than field order, so the hash cannot change because someone
        reordered the dataclass — which would re-ingest the corpus for a cosmetic edit.
        """
        payload = json.dumps(dataclasses.asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


#: The settled configuration. Chunking anywhere in the system starts from this.
DEFAULT_CONFIG: Final[ChunkerConfig] = ChunkerConfig()
