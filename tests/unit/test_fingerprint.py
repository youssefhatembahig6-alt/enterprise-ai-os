"""Dataset fingerprinting (spec FR-015, FR-015a, research R5).

The fingerprint is what turns "the dataset is reproducible" from a claim into a
check. Two properties matter most: it must be independent of row ordering (so two
runs that insert in different orders still match), and it must be sensitive to
content (so a real change is never missed).
"""

from __future__ import annotations

import datetime as dt
import decimal
import uuid

import pytest

from eaios_core import fingerprint as fp

pytestmark = pytest.mark.unit

ROW_A = {
    "id": uuid.UUID("9a4c8fd1-1d92-5a5f-a9a6-2ec0c9c7f6a8"),
    "name": "Nadia Farouk",
    "hired": dt.date(2024, 3, 11),
    "salary": decimal.Decimal("18500.00"),
    "manager_id": None,
}
ROW_B = {
    "id": uuid.UUID("e3d3e6e5-83c6-5b7b-9f66-3ff6a0bd0f4c"),
    "name": "Omar Zaki",
    "hired": dt.date(2025, 1, 6),
    "salary": decimal.Decimal("22750.50"),
    "manager_id": uuid.UUID("9a4c8fd1-1d92-5a5f-a9a6-2ec0c9c7f6a8"),
}


class TestCanonicalSerialization:
    def test_key_order_does_not_matter(self) -> None:
        shuffled = {k: ROW_A[k] for k in reversed(list(ROW_A))}
        assert fp.canonical_json(ROW_A) == fp.canonical_json(shuffled)

    def test_uuids_serialize_lowercase_and_hyphenated(self) -> None:
        assert "9a4c8fd1-1d92-5a5f-a9a6-2ec0c9c7f6a8" in fp.canonical_json(ROW_A)

    def test_dates_serialize_iso8601(self) -> None:
        assert "2024-03-11" in fp.canonical_json(ROW_A)

    def test_decimals_keep_their_scale(self) -> None:
        """18500.00 and 18500.0 are the same number but not the same record."""
        assert '"18500.00"' in fp.canonical_json(ROW_A)

    def test_none_is_explicit(self) -> None:
        assert '"manager_id": null' in fp.canonical_json(ROW_A)

    def test_non_ascii_is_preserved_not_escaped(self) -> None:
        assert "Zakï" in fp.canonical_json({"name": "Zakï"})


class TestFamilyDigest:
    def test_row_order_does_not_change_the_digest(self) -> None:
        """The core FR-015a property: order-independence."""
        assert fp.family_digest([ROW_A, ROW_B]) == fp.family_digest([ROW_B, ROW_A])

    def test_content_change_changes_the_digest(self) -> None:
        altered = dict(ROW_A, name="Nadia Farouq")
        assert fp.family_digest([ROW_A, ROW_B]) != fp.family_digest([altered, ROW_B])

    def test_a_missing_row_changes_the_digest(self) -> None:
        assert fp.family_digest([ROW_A, ROW_B]) != fp.family_digest([ROW_A])

    def test_duplicate_rows_are_not_collapsed(self) -> None:
        """Two identical rows are a data bug; the digest must not hide it."""
        assert fp.family_digest([ROW_A, ROW_A]) != fp.family_digest([ROW_A])

    def test_empty_family_has_a_stable_digest(self) -> None:
        assert fp.family_digest([]) == fp.family_digest([])
        assert len(fp.family_digest([])) == 64

    def test_digest_is_hex_sha256(self) -> None:
        digest = fp.family_digest([ROW_A])
        assert len(digest) == 64
        assert set(digest) <= set("0123456789abcdef")


class TestFilesDigest:
    def test_file_content_is_hashed_with_its_key(self) -> None:
        a = fp.files_digest({"niletech/INTERNAL/POLICY/leave.md": b"21 days"})
        b = fp.files_digest({"niletech/INTERNAL/POLICY/leave.md": b"22 days"})
        assert a != b

    def test_moving_a_file_changes_the_digest(self) -> None:
        a = fp.files_digest({"niletech/INTERNAL/POLICY/leave.md": b"21 days"})
        b = fp.files_digest({"delta-retail/INTERNAL/POLICY/leave.md": b"21 days"})
        assert a != b

    def test_insertion_order_does_not_matter(self) -> None:
        one = fp.files_digest({"a": b"1", "b": b"2"})
        two = fp.files_digest({"b": b"2", "a": b"1"})
        assert one == two


class TestRootFingerprint:
    def test_root_combines_families_and_files(self) -> None:
        families = {"niletech.users": fp.family_digest([ROW_A])}
        files = fp.files_digest({"k": b"v"})
        assert len(fp.root_fingerprint(families, files)) == 64

    def test_family_order_does_not_matter(self) -> None:
        one = {"a.users": fp.family_digest([ROW_A]), "b.users": fp.family_digest([ROW_B])}
        two = {"b.users": fp.family_digest([ROW_B]), "a.users": fp.family_digest([ROW_A])}
        files = fp.files_digest({})
        assert fp.root_fingerprint(one, files) == fp.root_fingerprint(two, files)

    def test_any_family_change_changes_the_root(self) -> None:
        files = fp.files_digest({})
        base = {"niletech.users": fp.family_digest([ROW_A, ROW_B])}
        changed = {"niletech.users": fp.family_digest([ROW_A])}
        assert fp.root_fingerprint(base, files) != fp.root_fingerprint(changed, files)


class TestExclusions:
    def test_exclusion_list_is_minimal_and_documented(self) -> None:
        """FR-015a — an over-broad exclusion silently weakens the guarantee.

        created_at/updated_at are deliberately NOT excluded: they are set from the
        reference clock, so they are deterministic and must be verified like any
        other field.

        `contact_submissions` joined the list with feature 002. It is the only
        exclusion holding *tenant-owned* data, which makes it the one worth
        watching: excluding a table means nothing verifies its contents, and that
        is only safe because the generator never writes there. See
        `tests/integration/test_runtime_table_integration.py` for the companion
        guarantees — reset truncates it, and the seed pre-flight counts it.
        """
        assert (
            frozenset({"dataset_manifest", "alembic_version", "contact_submissions"})
            == fp.FINGERPRINT_EXCLUSIONS
        )

    def test_excluded_tables_are_skipped(self) -> None:
        assert fp.is_excluded("alembic_version") is True
        assert fp.is_excluded("users") is False
