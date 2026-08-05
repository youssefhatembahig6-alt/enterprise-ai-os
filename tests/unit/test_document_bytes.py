"""Generated documents are byte-identical everywhere (spec FR-032, FR-012a).

This is the file-level tripwire research R4 called for. Without it, a line-ending
or encoding regression surfaces only as a whole-dataset fingerprint mismatch —
technically detected, but pointing nowhere useful. Here it fails on one document
with an obvious cause.

The pinned digests below were computed on 2026-08-01. If a template legitimately
changes, bump GENERATOR_VERSION and update them; if they change unexpectedly, the
generator picked up a platform dependency.
"""

from __future__ import annotations

import hashlib

import pytest

from eaios_seed.config import SeedConfig
from eaios_seed.documents.renderer import Document, encode, render
from eaios_seed.pipeline import build_dataset

pytestmark = pytest.mark.unit


def _fixture_document() -> Document:
    doc = Document().heading("Leave Policy")
    doc.field("Version", "2026.1").blank()
    doc.rule()
    doc.heading("Annual Leave Entitlement", 2)
    doc.bullets(["Egypt (EG): 21 days per year.", "United Arab Emirates (AE): 22 days per year."])
    doc.para("Accrued monthly after probation.")
    return doc


class TestByteDiscipline:
    def test_fixture_document_has_an_exact_digest(self) -> None:
        _content, digest, _size = render(_fixture_document())
        assert digest == "683ec4584fe45fc1b1203f3699601f6136bae4fd6104ef82533450ddadd71ef0"

    def test_no_carriage_returns(self) -> None:
        """The Windows failure mode: text mode turning \\n into \\r\\n."""
        content, _digest, _size = render(_fixture_document())
        assert b"\r" not in content

    def test_no_byte_order_mark(self) -> None:
        content, _digest, _size = render(_fixture_document())
        assert not content.startswith(b"\xef\xbb\xbf")

    def test_encoding_is_utf8(self) -> None:
        content, _digest, _size = render(_fixture_document())
        content.decode("utf-8")  # raises if it is anything else

    def test_exactly_one_trailing_newline(self) -> None:
        content, _digest, _size = render(_fixture_document())
        assert content.endswith(b"\n")
        assert not content.endswith(b"\n\n")

    def test_encode_normalises_crlf_input(self) -> None:
        """Even if a template arrives with CRLF, what we store is LF."""
        assert encode("a\r\nb\r\n") == b"a\nb\n"
        assert encode("a\rb\r") == b"a\nb\n"

    def test_size_matches_content_length(self) -> None:
        content, _digest, size = render(_fixture_document())
        assert size == len(content)

    def test_digest_matches_content(self) -> None:
        content, digest, _size = render(_fixture_document())
        assert digest == hashlib.sha256(content).hexdigest()


class TestGeneratedCorpus:
    """The same guarantees across every document the generator actually produces."""

    @pytest.fixture(scope="class")
    def files(self) -> dict[str, bytes]:
        dataset, _ctx = build_dataset(SeedConfig.build(profile="smoke"))
        return dataset.files

    def test_corpus_is_not_empty(self, files: dict[str, bytes]) -> None:
        assert len(files) >= 20

    def test_no_document_contains_a_carriage_return(self, files: dict[str, bytes]) -> None:
        offenders = [key for key, content in files.items() if b"\r" in content]
        assert offenders == []

    def test_no_document_has_a_bom(self, files: dict[str, bytes]) -> None:
        offenders = [key for key, content in files.items() if content.startswith(b"\xef\xbb\xbf")]
        assert offenders == []

    def test_every_document_is_valid_utf8(self, files: dict[str, bytes]) -> None:
        for key, content in files.items():
            try:
                content.decode("utf-8")
            except UnicodeDecodeError as exc:  # pragma: no cover - failure path
                pytest.fail(f"{key} is not valid UTF-8: {exc}")

    def test_no_document_carries_a_generation_timestamp(self, files: dict[str, bytes]) -> None:
        """A timestamp in a body would make bytes vary by run (research R4)."""
        for key, content in files.items():
            text = content.decode("utf-8")
            assert "Generated at" not in text
            assert "generated_at" not in text, key

    def test_regenerating_produces_identical_bytes(self) -> None:
        first, _ = build_dataset(SeedConfig.build(profile="smoke"))
        second, _ = build_dataset(SeedConfig.build(profile="smoke"))
        assert first.files.keys() == second.files.keys()
        assert all(first.files[key] == second.files[key] for key in first.files)
