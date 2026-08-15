"""Token counting, behind an interface (FR-007a).

The chunker's budget is expressed in **BGE-M3 tokens**, but the chunker itself must not
depend on 2 GB of weights being present. Two consequences follow, and both are deliberate:

* The tokenizer is **injected**, so the unit tests stay pure and in-memory and the
  benchmark passes the real one.
* The tokenizer's **identity** is part of chunk identity (FR-007b), so a chunk produced
  under a stand-in can never be mistaken for one produced under BGE-M3. The two get
  different identifiers even when the text is identical, which is exactly the confusion
  that would otherwise be undetectable.

`load_bge_m3` reads **local files only**. It never contacts the network — not to resolve a
revision, not to check a cache. An embedding path that reaches the network at request time
is the defect `tests/security/test_no_download_at_request_time.py` exists to catch
(FR-011c, FR-011f).
"""

from __future__ import annotations

import pathlib
import re
from typing import Final, Protocol, runtime_checkable

__all__ = ["FixedVocabularyTokenizer", "Tokenizer", "load_bge_m3"]


@runtime_checkable
class Tokenizer(Protocol):
    """What the chunker needs from a tokenizer: a count and a name."""

    @property
    def identity(self) -> str:
        """Stable name of this tokenizer, recorded in every chunk identifier."""

    def count(self, text: str) -> int:
        """Number of tokens `text` occupies."""


#: Word-ish runs and individual punctuation marks. ASCII classes are spelled out rather
#: than using `\w`, because `\w` is Unicode-aware and its behaviour would then depend on
#: the interpreter's Unicode data — a determinism leak across Python versions (FR-007).
_PIECE: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9]+|[^\sA-Za-z0-9]")

#: How many characters of a word-ish run map to one subword piece. BGE-M3 uses
#: SentencePiece over XLM-RoBERTa's vocabulary, which splits long words into several
#: pieces; this reproduces that shape without reproducing that vocabulary.
_CHARS_PER_PIECE: Final[int] = 5


class FixedVocabularyTokenizer:
    """A deterministic stand-in for BGE-M3's tokenizer.

    It is **not** an approximation of BGE-M3's vocabulary and does not pretend to be. It
    exists so boundary logic can be tested without weights, and it is honest about that
    through its identity string: a chunk counted with this tokenizer carries an identifier
    that no BGE-M3-counted chunk can collide with.

    Determinism is the whole contract. No locale, no hash iteration, no Unicode-category
    lookups — the same string counts the same on every machine and every Python build.
    """

    __slots__ = ("_identity",)

    def __init__(self, identity: str = "fixed-vocabulary-tokenizer@v1") -> None:
        self._identity = identity

    @property
    def identity(self) -> str:
        return self._identity

    def count(self, text: str) -> int:
        total = 0
        for piece in _PIECE.findall(text):
            total += 1 + (len(piece) - 1) // _CHARS_PER_PIECE
        return total


class _HuggingFaceTokenizer:
    """The real BGE-M3 tokenizer, loaded from a local directory."""

    __slots__ = ("_identity", "_tokenizer")

    def __init__(self, tokenizer: object, identity: str) -> None:
        self._tokenizer = tokenizer
        self._identity = identity

    @property
    def identity(self) -> str:
        return self._identity

    def count(self, text: str) -> int:
        # `add_special_tokens=False` because the chunker measures content, not the two
        # sentinel tokens the encoder adds around it. Counting them would shrink every
        # chunk by two tokens for no reason a reader could infer.
        return len(self._tokenizer.encode(text, add_special_tokens=False))  # type: ignore[attr-defined]


def load_bge_m3(weights_directory: pathlib.Path, identity: str) -> Tokenizer:
    """Load the pinned BGE-M3 tokenizer from `weights_directory`.

    Raises:
        FileNotFoundError: the directory does not hold a tokenizer. Raised rather than
            downloading, because acquisition is a provisioning activity and a download
            here would be a network call on the retrieval path (FR-011c, FR-011f).
        ModuleNotFoundError: the pinned runtime is not installed.
    """
    directory = pathlib.Path(weights_directory)
    if (
        not (directory / "tokenizer.json").is_file()
        and not (directory / "sentencepiece.bpe.model").is_file()
    ):
        raise FileNotFoundError(
            f"no BGE-M3 tokenizer in {directory}. Weight acquisition is a provisioning"
            " step — see the download command in docs/models.md. This function will not"
            " fetch it, because that would put a network call on the retrieval path"
        )

    # Imported here, not at module scope: the chunker must import on a bare checkout
    # with no model runtime installed (tests/unit/test_phase0_bare_checkout.py).
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(str(directory), local_files_only=True)
    return _HuggingFaceTokenizer(tokenizer, identity)
