"""Embedding never reaches the network (FR-011c, FR-011f, CHK071).

**The distinction this file enforces.** Weight acquisition is a *provisioning* activity. An
inference request is not. A library that quietly downloads a missing model on first use
turns every cold start into an outbound call — and turns a retrieval path that is supposed
to be local into one that fails when the network does, leaks a query to a third party, and
takes minutes instead of milliseconds the first time anyone asks a question.

`transformers` does exactly this by default. `from_pretrained("BAAI/bge-m3")` will fetch
from the Hub. So "we don't download at request time" is not a property this system gets for
free; it is a property it has to assert and keep asserting.

Three checks, because each catches a different mistake:

1. **Absent weights raise at construction** — not at the first embed call, and not by
   downloading. Failing early names the problem while it is still a provisioning error.
2. **The loader is pinned to local files** — a static read of the source, so it holds even
   when weights *are* present and the download path would never be taken.
3. **No socket is opened** — the behavioural backstop, with the network actually removed.
"""

from __future__ import annotations

import pathlib
import re
import socket
from typing import Final

import pytest

from eaios_core.embedding import bge_m3

pytestmark = pytest.mark.security

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[2]
SOURCE: Final[pathlib.Path] = REPO / "packages/core/src/eaios_core/embedding/bge_m3.py"


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Refuse every *outbound* call, and record it.

    **What is guarded, and what deliberately is not.** FR-011f forbids contacting a third
    party. It does not forbid creating a socket object — and the difference matters here,
    because `urllib3` constructs an `AF_INET6` socket at import time purely to detect
    whether the machine supports IPv6. Nothing is sent and nothing is resolved.

    An earlier version of this fixture patched `socket.socket` itself and so counted that
    capability probe as a network call. It failed a correct implementation, which is the
    worst kind of security test: the fix for a false alarm is usually to weaken the check.

    So the guard is placed on the three ways bytes actually leave: `connect`,
    `create_connection`, and `getaddrinfo`.
    """
    attempts: list[str] = []

    def refuse(*args: object, **kwargs: object) -> object:
        attempts.append(f"{args!r}")
        raise OSError("network access is not permitted on the embedding path (FR-011c)")

    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse, raising=False)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse, raising=False)
    return attempts


class TestTheSourceIsReadable:
    """The static checks below read this file; an unreadable path passes them silently."""

    def test_the_embedder_source_exists(self) -> None:
        assert SOURCE.is_file(), f"missing {SOURCE.relative_to(REPO)}"

    def test_the_source_mentions_from_pretrained(self) -> None:
        assert "from_pretrained" in SOURCE.read_text(encoding="utf-8"), (
            "the loader no longer calls `from_pretrained`, so the local-files assertion"
            " below is checking a call that is not made"
        )


class TestAbsentWeightsRaiseAtConstruction:
    def test_a_missing_directory_raises(self, tmp_path: pathlib.Path) -> None:
        with pytest.raises(FileNotFoundError) as raised:
            bge_m3.BgeM3Embedder(tmp_path / "definitely-absent")
        assert "provisioning" in str(raised.value).lower(), (
            "the error should say this is a provisioning step, so whoever hits it knows"
            f" to download rather than to retry: {raised.value}"
        )

    def test_an_empty_directory_raises(self, tmp_path: pathlib.Path) -> None:
        with pytest.raises(FileNotFoundError):
            bge_m3.BgeM3Embedder(tmp_path)

    def test_it_raises_rather_than_downloading(
        self, tmp_path: pathlib.Path, no_network: list[str]
    ) -> None:
        """The sharp version: with no network *and* no weights, the failure must still be
        `FileNotFoundError`. An `OSError` from the socket guard would mean the code tried
        to fetch."""
        with pytest.raises(FileNotFoundError):
            bge_m3.BgeM3Embedder(tmp_path)
        assert no_network == [], f"construction attempted a network call: {no_network}"


def _from_pretrained_calls(text: str) -> list[str]:
    """Argument lists of every `from_pretrained(...)` call, parentheses balanced.

    A non-greedy `\\(.*?\\)` is wrong here and quietly so: it stops at the first `)`,
    which for `from_pretrained(str(directory), local_files_only=True)` is the one closing
    `str(`. The assertion would then read only `str(directory` and fail on correct code.
    """
    calls: list[str] = []
    for match in re.finditer(r"from_pretrained\(", text):
        depth, index = 0, match.end() - 1
        while index < len(text):
            if text[index] == "(":
                depth += 1
            elif text[index] == ")":
                depth -= 1
                if depth == 0:
                    calls.append(text[match.end() : index])
                    break
            index += 1
    return calls


class TestTheLoaderIsPinnedToLocalFiles:
    def test_the_call_scan_finds_the_calls(self) -> None:
        calls = _from_pretrained_calls(SOURCE.read_text(encoding="utf-8"))
        assert len(calls) >= 2, (
            f"expected the tokenizer and model loads, found {len(calls)}; the assertion"
            " below would run over an empty list"
        )

    def test_from_pretrained_passes_local_files_only(self) -> None:
        for arguments in _from_pretrained_calls(SOURCE.read_text(encoding="utf-8")):
            assert "local_files_only=True" in arguments, (
                "a `from_pretrained` call does not pass `local_files_only=True`, so it"
                f" falls back to fetching from the Hub: from_pretrained({arguments})"
            )

    def test_the_source_names_no_repository_shorthand(self) -> None:
        """`from_pretrained("BAAI/bge-m3")` resolves against the Hub even with a cache."""
        text = SOURCE.read_text(encoding="utf-8")
        calls = re.findall(r"from_pretrained\(\s*[\"']([^\"']+)[\"']", text)
        assert calls == [], (
            f"the loader passes a repository name rather than a local path: {calls}."
            " A repository name is resolved against the Hub"
        )


class TestTheRealConstructorPathUnderNoNetwork:
    """The real `__init__`, not `from_backend`, with the network removed.

    `from_backend` bypasses `__init__` entirely — useful for exercising the request path
    without 2 GB of weights, but it proves nothing about construction. These cases drive
    the actual constructor as far as it can go without weights present, which is exactly
    the path a cold, unprovisioned machine takes.
    """

    def test_construction_with_a_present_but_wrong_weight_file_never_reaches_the_network(
        self, tmp_path: pathlib.Path, no_network: list[str]
    ) -> None:
        """Weights *present* but not the pinned ones: the checksum branch runs for real."""
        (tmp_path / "pytorch_model.bin").write_bytes(b"these are not the pinned weights")

        with pytest.raises(ValueError, match="checksum"):
            bge_m3.BgeM3Embedder(tmp_path)

        assert no_network == [], (
            f"verifying the checksum reached the network: {no_network}. Nothing on this"
            " path may resolve a revision or consult a cache"
        )

    def test_the_checksum_branch_actually_hashed_the_file(self, tmp_path: pathlib.Path) -> None:
        """Falsification: if the message does not carry the real digest, no hash ran."""
        import hashlib

        body = b"these are not the pinned weights"
        (tmp_path / "pytorch_model.bin").write_bytes(body)
        expected = hashlib.sha256(body).hexdigest()

        with pytest.raises(ValueError) as raised:
            bge_m3.BgeM3Embedder(tmp_path)
        assert expected in str(raised.value), (
            "the failure did not report the digest it computed, so the checksum branch"
            f" may not have run: {raised.value}"
        )

    def test_checksum_verification_can_be_declined_only_explicitly(
        self, tmp_path: pathlib.Path, no_network: list[str]
    ) -> None:
        """With verification off, construction proceeds to the runtime — still offline.

        It fails at the model load rather than at the checksum, which is the point: the
        only thing that changed is *which* guard stopped it, never whether the network
        was touched.
        """
        (tmp_path / "pytorch_model.bin").write_bytes(b"not real weights")

        with pytest.raises((OSError, ValueError, KeyError, RuntimeError)):
            bge_m3.BgeM3Embedder(tmp_path, verify_checksum=False)

        assert no_network == [], (
            f"loading the model reached the network: {no_network}. `local_files_only`"
            " is what should have stopped it"
        )


class TestQueryEmbeddingOpensNoSocket:
    def test_embedding_a_query_makes_no_outbound_call(
        self, tmp_path: pathlib.Path, no_network: list[str]
    ) -> None:
        """Runs against a stub backend, so it exercises the request path with no weights.

        The point is the *path*, not the vector: whatever the backend is, `embed_query`
        must not reach the network on the way there.
        """
        embedder = bge_m3.BgeM3Embedder.from_backend(
            _ConstantBackend(), identity=bge_m3.declared_identity()
        )
        vector = embedder.embed_query("who approves travel above the limit?")

        assert len(vector) == 1024
        assert no_network == [], f"embedding a query attempted a network call: {no_network}"

    def test_embedding_documents_makes_no_outbound_call(self, no_network: list[str]) -> None:
        embedder = bge_m3.BgeM3Embedder.from_backend(
            _ConstantBackend(), identity=bge_m3.declared_identity()
        )
        vectors = embedder.embed_documents(["first document", "second document"])

        assert len(vectors) == 2
        assert all(len(v) == 1024 for v in vectors)
        assert no_network == [], f"embedding documents attempted a network call: {no_network}"


class TestTheGuardItselfWorks:
    """Falsification: if the guard does not fire, every test above proves nothing."""

    def test_the_guard_catches_a_real_connection_attempt(self, no_network: list[str]) -> None:
        with pytest.raises(OSError):
            socket.create_connection(("huggingface.co", 443), timeout=1)
        assert no_network, "the guard recorded nothing despite a connection attempt"

    def test_the_guard_catches_a_name_resolution(self, no_network: list[str]) -> None:
        with pytest.raises(OSError):
            socket.getaddrinfo("huggingface.co", 443)
        assert no_network

    def test_the_guard_ignores_a_local_capability_probe(self, no_network: list[str]) -> None:
        """Creating a socket is not a network call, and treating it as one is why a
        correct implementation was reported as leaking."""
        probe = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        probe.close()
        assert no_network == [], (
            "constructing a socket was recorded as an outbound call; `urllib3` does"
            " exactly this at import time to detect IPv6 support"
        )


class _ConstantBackend:
    """A stand-in for the loaded model: right shape, no weights, no network."""

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 1024 for _ in texts]
