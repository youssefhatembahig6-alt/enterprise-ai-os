"""The embedder declares exactly which model produced a vector (FR-011, FR-011b).

**Why identity is recorded rather than assumed.** Similarity between two embedding models
is meaningless — cosine distance across vector spaces is a number with no interpretation.
So an index built with one revision and queried with another does not degrade gracefully;
it returns confident nonsense. The only defence is to record which model produced each
vector and refuse to mix (FR-011).

This test is **pure and in-memory**. It reads declared constants and compares them with
`docs/models.md`; it loads no weights, constructs no Qdrant client, and builds no preview
index. That keeps §0C inside the bare-checkout boundary and stops a cycle forming with §0G,
where the preview builder legitimately needs both this module and a running store.
"""

from __future__ import annotations

import pathlib
import re
from typing import Final

import pytest

from eaios_core.embedding import bge_m3

pytestmark = pytest.mark.unit

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[2]
MODEL_CARD: Final[pathlib.Path] = REPO / "docs" / "models.md"


def _documented(label: str) -> str:
    """Pull one value out of the BGE-M3 table in `docs/models.md`.

    Reads the document rather than duplicating its values here. A test that restates the
    constant it is checking proves only that someone typed it twice.
    """
    text = MODEL_CARD.read_text(encoding="utf-8")
    section = text.split("## Qwen2.5-3B-Instruct")[0]
    match = re.search(rf"^\|\s*{re.escape(label)}\s*\|\s*(.+?)\s*\|", section, re.MULTILINE)
    assert match, f"`docs/models.md` no longer records `{label}` for BGE-M3"
    return match.group(1).strip().strip("`*")


class TestTheModelCardIsReadable:
    """Every assertion below compares against this file; an unreadable file passes them all."""

    def test_the_model_card_exists(self) -> None:
        assert MODEL_CARD.is_file(), f"missing {MODEL_CARD.relative_to(REPO)}"

    def test_the_bge_section_carries_the_fields(self) -> None:
        for label in (
            "Repository",
            "Revision SHA",
            "Weight checksum (SHA-256)",
            "Vector dimension",
        ):
            assert _documented(label), f"`{label}` parsed as empty"


class TestTheDeclaredIdentity:
    def test_the_dimension_is_1024(self) -> None:
        assert bge_m3.EMBEDDING_DIMENSION == 1024, (
            "the vector store's collections are provisioned at 1024; any other width"
            " means re-provisioning the store rather than changing this constant"
        )

    def test_the_dimension_matches_the_model_card(self) -> None:
        assert str(bge_m3.EMBEDDING_DIMENSION) == _documented("Vector dimension")

    def test_the_repository_matches_the_model_card(self) -> None:
        assert _documented("Repository") == bge_m3.MODEL_REPOSITORY

    def test_the_revision_matches_the_model_card(self) -> None:
        assert _documented("Revision SHA") == bge_m3.PINNED_REVISION, (
            "the pinned revision disagrees with docs/models.md. One of them is what the"
            " index was built with and the other is a note; they must not differ"
        )

    def test_the_weight_checksum_matches_the_model_card(self) -> None:
        assert _documented("Weight checksum (SHA-256)") == bge_m3.WEIGHT_SHA256

    def test_the_revision_is_a_full_commit_sha(self) -> None:
        assert re.fullmatch(r"[0-9a-f]{40}", bge_m3.PINNED_REVISION), (
            f"{bge_m3.PINNED_REVISION!r} is not a 40-character commit SHA. A branch name"
            " or short SHA is not a pin — it resolves to different weights over time"
        )

    def test_the_checksum_is_a_full_sha256(self) -> None:
        assert re.fullmatch(r"[0-9a-f]{64}", bge_m3.WEIGHT_SHA256)


class TestTheIdentityRecord:
    """What gets written beside an index, and later beside every evaluation run."""

    def test_the_identity_carries_every_attributable_field(self) -> None:
        identity = bge_m3.declared_identity()
        assert identity.model == bge_m3.MODEL_REPOSITORY
        assert identity.revision == bge_m3.PINNED_REVISION
        assert identity.weight_checksum == bge_m3.WEIGHT_SHA256
        assert identity.dimension == 1024

    def test_the_identity_is_hashable_and_comparable(self) -> None:
        """An index records one of these and compares it later; equality must be value-based."""
        assert bge_m3.declared_identity() == bge_m3.declared_identity()
        assert len({bge_m3.declared_identity(), bge_m3.declared_identity()}) == 1

    def test_a_different_revision_is_a_different_identity(self) -> None:
        import dataclasses

        other = dataclasses.replace(bge_m3.declared_identity(), revision="0" * 40)
        assert other != bge_m3.declared_identity(), (
            "two identities differing only by revision compared equal, so an index could"
            " not detect that its vectors came from a different model"
        )


class TestTheModuleStaysPure:
    """§0C must not reach a store, or the preview builder in §0G becomes a cycle."""

    def test_importing_the_module_creates_no_store_client(self) -> None:
        import sys

        for forbidden in ("qdrant_client", "psycopg", "minio"):
            assert forbidden not in sys.modules or forbidden not in repr(bge_m3.__dict__), (
                f"`{forbidden}` is reachable from the embedder's namespace"
            )

    def test_the_declared_identity_needs_no_weights(self) -> None:
        """It is called while recording a manifest, long before weights are loaded."""
        assert bge_m3.declared_identity().dimension == 1024
