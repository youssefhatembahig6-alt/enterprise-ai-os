"""The pinned local BGE-M3 embedder (FR-011, FR-011b, FR-011c, FR-011f).

**Local only.** There is no network path in this module. Weights are read from a directory
that provisioning put there; if they are absent the constructor raises, and it raises
`FileNotFoundError` rather than reaching for the Hub. That is deliberate and it is tested:
`transformers` downloads missing models by default, so "no download at request time" is a
property this file has to assert rather than one it inherits.

**Identity travels with the vectors.** Cosine distance between two embedding models is a
number with no interpretation, so an index built under one revision and queried under
another does not degrade — it returns confident nonsense. `declared_identity()` is what an
index and every evaluation run record so that mixing becomes detectable instead of silent.

**The runtime is imported lazily**, inside the constructor. Importing torch at module scope
would pull the whole runtime into every process that touches `eaios_core` — including the
ones that never embed — and would break the bare-checkout boundary that
`tests/unit/test_phase0_bare_checkout.py` enforces.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import pathlib
from typing import Final, Protocol

from ..checksums import sha256_of

__all__ = [
    "EMBEDDING_DIMENSION",
    "MODEL_REPOSITORY",
    "PINNED_REVISION",
    "WEIGHT_SHA256",
    "BgeM3Embedder",
    "EmbeddingIdentity",
    "declared_identity",
    "missing_runtime",
]

#: Recorded in `docs/models.md`, verified against the authoritative model card.
#: `tests/unit/test_embedding_identity.py` fails if these drift apart.
MODEL_REPOSITORY: Final[str] = "BAAI/bge-m3"
PINNED_REVISION: Final[str] = "5617a9f61b028005a4858fdac845db406aefb181"
WEIGHT_SHA256: Final[str] = "b5e0ce3470abf5ef3831aa1bd5553b486803e83251590ab7ff35a117cf6aad38"

#: Fixed by the vector store's existing collections, not chosen here (FR-011).
EMBEDDING_DIMENSION: Final[int] = 1024

#: The distributions the embedder needs at load time.
_RUNTIME: Final[tuple[str, ...]] = ("torch", "transformers")

#: Files that indicate a real BGE-M3 checkout rather than an empty directory.
_WEIGHT_FILENAMES: Final[tuple[str, ...]] = ("pytorch_model.bin", "model.safetensors")


@dataclasses.dataclass(frozen=True, slots=True)
class EmbeddingIdentity:
    """Which model produced a vector. Recorded beside every index and every run."""

    model: str
    revision: str
    weight_checksum: str
    dimension: int


def declared_identity() -> EmbeddingIdentity:
    """The pinned identity, without loading anything.

    Callable while writing a manifest, long before weights are read — which is why the
    preview-index builder can record what it is about to use before it uses it.
    """
    return EmbeddingIdentity(
        model=MODEL_REPOSITORY,
        revision=PINNED_REVISION,
        weight_checksum=WEIGHT_SHA256,
        dimension=EMBEDDING_DIMENSION,
    )


#: Offline switches for the model libraries. `local_files_only=True` governs the *lookup*;
#: these govern the *client*, which otherwise resolves and probes before the flag is read.
OFFLINE_ENVIRONMENT: Final[dict[str, str]] = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
}


def _enforce_offline() -> None:
    """Put the model libraries in offline mode before they are imported.

    Set unconditionally rather than with `setdefault`: a caller who exported
    `HF_HUB_OFFLINE=0` would otherwise re-enable exactly the behaviour FR-011f forbids,
    and the embedding path is not a place to honour that preference.
    """
    import os

    os.environ.update(OFFLINE_ENVIRONMENT)


def missing_runtime() -> list[str]:
    """Which pinned runtime distributions are not importable.

    Reported by name rather than as a bare boolean, because "the benchmark cannot embed"
    and "torch is not installed" are different messages to receive at 2am.
    """
    return [name for name in _RUNTIME if importlib.util.find_spec(name) is None]


class _Backend(Protocol):
    """The minimum the embedder needs from a loaded model."""

    def encode(self, texts: list[str]) -> list[list[float]]: ...


class BgeM3Embedder:
    """Embeds text with the pinned BGE-M3 revision, from local weights only."""

    __slots__ = ("_backend", "_identity")

    def __init__(
        self,
        weights_directory: pathlib.Path,
        *,
        verify_checksum: bool = True,
    ) -> None:
        """Load the pinned model from `weights_directory`.

        Args:
            weights_directory: Directory provisioning downloaded the weights into.
            verify_checksum: Hash the weight file and compare with `WEIGHT_SHA256`.
                Defaults to on. An unverified download is a guess about what will run
                (FR-011f), and the cost is one pass over the file at startup.

        Raises:
            FileNotFoundError: No weights there. Raised rather than downloading them —
                acquisition is a provisioning step, and fetching here would put a network
                call on the retrieval path.
            ModuleNotFoundError: The pinned runtime is not installed.
            ValueError: The weight file's checksum is not the pinned one.
        """
        directory = pathlib.Path(weights_directory)
        weight_file = self._locate_weights(directory)

        absent = missing_runtime()
        if absent:
            raise ModuleNotFoundError(
                f"the pinned BGE-M3 runtime is not installed: {', '.join(absent)}."
                " It is declared in packages/core/pyproject.toml and the root manifest;"
                " install with `uv sync`"
            )

        if verify_checksum:
            actual = sha256_of(weight_file)
            if actual != WEIGHT_SHA256:
                raise ValueError(
                    f"{weight_file} has checksum {actual}, not the pinned"
                    f" {WEIGHT_SHA256}. These are different weights, so any vector"
                    " produced here would not be comparable with the index"
                )

        # Defence in depth alongside `local_files_only=True`. That flag governs the
        # lookup; these govern the client, which will otherwise fall back to a hub
        # request when a local file is missing rather than failing on the spot. On the
        # retrieval path such a fallback is a query leaving the machine and a network
        # timeout standing between a user and their answer (FR-011c, FR-011f).
        _enforce_offline()

        # Imported here, never at module scope. See the module docstring.
        import torch
        from transformers import AutoModel, AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(str(directory), local_files_only=True)
        model = AutoModel.from_pretrained(str(directory), local_files_only=True)
        model.eval()

        self._backend: _Backend = _TorchBackend(torch, tokenizer, model)
        self._identity = declared_identity()

    @staticmethod
    def _locate_weights(directory: pathlib.Path) -> pathlib.Path:
        for name in _WEIGHT_FILENAMES:
            candidate = directory / name
            if candidate.is_file():
                return candidate
        raise FileNotFoundError(
            f"no BGE-M3 weights in {directory}. Weight acquisition is a provisioning"
            " step, not something an inference request performs — see the download and"
            " checksum commands in docs/models.md. This constructor will not fetch them,"
            " because that would put an outbound call on the retrieval path (FR-011f)"
        )

    @classmethod
    def from_backend(cls, backend: _Backend, *, identity: EmbeddingIdentity) -> BgeM3Embedder:
        """Wrap an already-loaded backend.

        Exists so the request path can be exercised without weights — the tests that prove
        no socket is opened need a real `embed_query` call, and loading 2 GB to make that
        call would put the check out of reach of ordinary CI (FR-035b).
        """
        instance = object.__new__(cls)
        instance._backend = backend
        instance._identity = identity
        return instance

    @property
    def identity(self) -> EmbeddingIdentity:
        """Which model these vectors came from."""
        return self._identity

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed passages for indexing."""
        vectors = self._backend.encode(list(texts))
        self._check_shape(vectors)
        return vectors

    def embed_query(self, text: str) -> list[float]:
        """Embed one query for retrieval."""
        return self.embed_documents([text])[0]

    def _check_shape(self, vectors: list[list[float]]) -> None:
        wrong = [len(v) for v in vectors if len(v) != self._identity.dimension]
        if wrong:
            raise ValueError(
                f"embedder produced {wrong[0]}-dimension vectors, expected"
                f" {self._identity.dimension}. The collection is provisioned at"
                " 1024 and would reject or silently mis-rank these"
            )


class _TorchBackend:
    """CLS pooling with L2 normalization — BGE-M3's dense retrieval representation."""

    __slots__ = ("_model", "_titles", "_tokenizer", "_torch")

    def __init__(self, torch_module: object, tokenizer: object, model: object) -> None:
        self._torch = torch_module
        self._tokenizer = tokenizer
        self._model = model

    def encode(self, texts: list[str]) -> list[list[float]]:
        torch = self._torch
        batch = self._tokenizer(  # type: ignore[operator]
            texts, padding=True, truncation=True, max_length=8192, return_tensors="pt"
        )
        with torch.no_grad():  # type: ignore[attr-defined]
            output = self._model(**batch)  # type: ignore[operator]
        # BGE-M3's dense vector is the CLS token, normalized. Mean pooling would produce
        # a different vector space — one the index was not built in.
        dense = output.last_hidden_state[:, 0]
        normalized = torch.nn.functional.normalize(dense, p=2, dim=1)  # type: ignore[attr-defined]
        return [row.tolist() for row in normalized]
