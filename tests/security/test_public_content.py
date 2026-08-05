"""Public content leaks nothing sensitive (spec SC-011, FR-030).

`PUBLIC` is the only classification an unauthenticated visitor may ever see, so
anything reaching it is effectively published. This is the last gate before that.

The scanner is deliberately over-eager — for this surface a miss is a disclosure
and a false alarm is a minute of review. Tests below therefore assert both that
real content is clean *and* that the scanner would actually catch a plant, so a
pass cannot come from a detector that never fires.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, text

from eaios_core.clients.stores import get_minio
from eaios_core.settings import get_settings
from eaios_seed.audit_checks.public_safety import (
    SENSITIVE_PATTERNS,
    scan_public_content,
)

pytestmark = pytest.mark.security

TENANTS = ("niletech", "delta-retail")


@pytest.fixture(scope="module")
def public_files() -> dict[str, bytes]:
    cfg = get_settings()
    client = get_minio(cfg)
    if not client.bucket_exists(cfg.minio.bucket):
        pytest.skip("object storage bucket missing; run `make seed`")

    out: dict[str, bytes] = {}
    for obj in client.list_objects(cfg.minio.bucket, recursive=True):
        if obj.object_name and "/PUBLIC/" in obj.object_name:
            response = client.get_object(cfg.minio.bucket, obj.object_name)
            try:
                out[obj.object_name] = response.read()
            finally:
                response.close()
                response.release_conn()
    return out


@pytest.fixture(scope="module")
def report(owner_engine: Engine, public_files: dict[str, bytes]):  # type: ignore[no-untyped-def]
    return scan_public_content(owner_engine, public_files)


class TestScanIsMeaningful:
    """A clean report means nothing if the scanner cannot fire."""

    def test_something_was_actually_scanned(self, report) -> None:  # type: ignore[no-untyped-def]
        assert report.scanned_rows > 0, "no public rows scanned"
        assert report.scanned_files > 0, "no public files scanned"

    @pytest.mark.parametrize(
        ("label", "plant"),
        [
            ("salary figure", "Annual salary is 84,000 USD."),
            ("salary band", "Placed at band B4 on joining."),
            ("contract term", "Subject to a 90 day notice period."),
            ("internal financial", "Q2 revenue reached 4,200,000 USD."),
            ("phone number", "Reach them on +201234567890."),
            ("confidentiality marker", "This page is RESTRICTED."),
        ],
    )
    def test_the_scanner_catches_a_plant(self, label: str, plant: str) -> None:
        matched = [name for name, pattern in SENSITIVE_PATTERNS if pattern.search(plant)]
        assert label in matched, f"scanner missed a planted {label}: {plant!r}"

    def test_a_personal_email_would_be_flagged(self) -> None:
        pattern = dict(SENSITIVE_PATTERNS)["email address"]
        assert pattern.search("Contact nadia.farouk@niletech.example for details")

    def test_a_general_mailbox_is_allowed(self, report) -> None:  # type: ignore[no-untyped-def]
        """Public pages legitimately publish an enquiries address; that is a company
        mailbox, not a person's contact detail."""
        assert not [f for f in report.findings if "hello@" in f]


class TestRealContentIsClean:
    def test_no_findings(self, report) -> None:  # type: ignore[no-untyped-def]
        assert report.clean, report.describe()

    def test_no_salary_or_band_appears_publicly(self, report) -> None:  # type: ignore[no-untyped-def]
        assert not [f for f in report.findings if "salary" in f]

    def test_no_contract_terms_appear_publicly(self, report) -> None:  # type: ignore[no-untyped-def]
        assert not [f for f in report.findings if "contract term" in f]

    def test_no_internal_financials_appear_publicly(self, report) -> None:  # type: ignore[no-untyped-def]
        assert not [f for f in report.findings if "internal financial" in f]


class TestClassificationBoundary:
    def test_only_public_documents_are_publicly_classified(
        self, owner_engine: Engine
    ) -> None:
        with owner_engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT document_type, count(*) FROM documents"
                    " WHERE classification = 'PUBLIC' GROUP BY 1"
                )
            ).all()
        assert dict(rows) == {"PUBLIC": 2}, "unexpected document types marked PUBLIC"

    def test_no_restricted_content_sits_under_a_public_prefix(
        self, owner_engine: Engine
    ) -> None:
        with owner_engine.connect() as conn:
            leaked = conn.execute(
                text(
                    "SELECT count(*) FROM documents"
                    " WHERE classification <> 'PUBLIC' AND storage_key LIKE '%/PUBLIC/%'"
                )
            ).scalar_one()
        assert leaked == 0

    def test_leadership_profiles_reference_executives_only(
        self, owner_engine: Engine
    ) -> None:
        """FR-030 — a public profile must correspond to a real executive."""
        with owner_engine.connect() as conn:
            non_exec = conn.execute(
                text(
                    "SELECT count(*) FROM leadership_profiles lp"
                    " JOIN users u ON u.id = lp.user_id"
                    " JOIN departments d ON d.id = u.department_id"
                    " WHERE d.name <> 'Executive Management'"
                )
            ).scalar_one()
        assert non_exec == 0

    def test_leadership_profiles_stay_in_their_company(self, owner_engine: Engine) -> None:
        with owner_engine.connect() as conn:
            crossing = conn.execute(
                text(
                    "SELECT count(*) FROM leadership_profiles lp"
                    " JOIN users u ON u.id = lp.user_id"
                    " WHERE u.company_id <> lp.company_id"
                )
            ).scalar_one()
        assert crossing == 0
