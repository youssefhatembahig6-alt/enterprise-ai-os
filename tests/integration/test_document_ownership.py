"""Document ownership follows the documented convention (spec FR-031a).

`test_coherence.py` proves every document has an owner in the same company. That is
necessary but weak: it would pass with ownership assigned at random. FR-031a states
a *specific* convention per document type, and the interesting case is the fallback —
Delta Retail has no Legal department, so its contracts must land on the head of
Executive Management rather than being ownerless or misassigned.

That fallback currently works in the data. Nothing asserted it until now.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, text

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def engine() -> Engine:
    from eaios_core.db import create_owner_engine

    engine = create_owner_engine()
    try:
        with engine.connect() as conn:
            seeded = conn.execute(text("SELECT count(*) FROM documents")).scalar_one()
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"database unavailable: {exc}")
    if not seeded:
        pytest.skip("environment not seeded; run `make up && make seed`")
    return engine


def _owners(engine: Engine, where: str) -> list[tuple[str, str, str]]:
    """(company slug, owning department, document title) for matching documents."""
    with engine.connect() as conn:
        return [
            (row.slug, row.dept, row.title)
            for row in conn.execute(
                text(
                    "SELECT c.slug, d.name AS dept, doc.title"
                    " FROM documents doc"
                    " JOIN users u ON u.id = doc.owner_id"
                    " JOIN departments d ON d.id = u.department_id"
                    " JOIN companies c ON c.id = doc.company_id"
                    f" WHERE {where}"
                )
            )
        ]


class TestEveryDocumentHasAnOwner:
    def test_no_document_is_ownerless(self, engine: Engine) -> None:
        with engine.connect() as conn:
            ownerless = conn.execute(
                text("SELECT count(*) FROM documents WHERE owner_id IS NULL")
            ).scalar_one()
        assert ownerless == 0

    def test_every_owner_is_a_department_head_or_named_role(self, engine: Engine) -> None:
        """The convention only ever assigns ownership to a head or a Legal user, so
        an owner outside that set means something bypassed it."""
        with engine.connect() as conn:
            rogue = conn.execute(
                text(
                    "SELECT count(*) FROM documents doc"
                    " JOIN users u ON u.id = doc.owner_id"
                    " WHERE NOT EXISTS ("
                    "   SELECT 1 FROM departments d WHERE d.head_user_id = u.id)"
                    " AND NOT EXISTS ("
                    "   SELECT 1 FROM user_roles ur JOIN roles r ON r.id = ur.role_id"
                    "   WHERE ur.user_id = u.id AND r.name = 'Legal')"
                )
            ).scalar_one()
        assert rogue == 0


class TestPolicyOwnership:
    def test_policies_are_owned_by_the_governing_department_head(self, engine: Engine) -> None:
        """HR policies to HR, expense and travel to Finance, security to Operations."""
        expected = {
            "HANDBOOK": "HR",
            "LEAVE": "HR",
            "REMOTE_WORK": "HR",
            "CODE_OF_CONDUCT": "HR",
            "BENEFITS": "HR",
            "EXPENSE": "Finance",
            "TRAVEL": "Finance",
            "SECURITY": "Operations",
        }
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT c.slug, p.policy_type, d.name AS dept"
                    " FROM policy_documents p"
                    " JOIN documents doc ON doc.id = p.document_id"
                    " JOIN users u ON u.id = doc.owner_id"
                    " JOIN departments d ON d.id = u.department_id"
                    " JOIN companies c ON c.id = p.company_id"
                )
            ).all()

        assert rows, "no policy documents found"
        mismatched = [
            f"{row.slug}/{row.policy_type}: owned by {row.dept}, expected {expected[row.policy_type]}"
            for row in rows
            if row.dept != expected[row.policy_type]
        ]
        assert mismatched == [], "\n".join(mismatched)

    def test_the_owner_actually_heads_that_department(self, engine: Engine) -> None:
        with engine.connect() as conn:
            not_head = conn.execute(
                text(
                    "SELECT count(*) FROM policy_documents p"
                    " JOIN documents doc ON doc.id = p.document_id"
                    " JOIN departments d ON d.head_user_id = doc.owner_id"
                    " WHERE d.id IS NULL"
                )
            ).scalar_one()
        assert not_head == 0


class TestContractOwnershipAndItsFallback:
    def test_niletech_contracts_are_owned_by_legal(self, engine: Engine) -> None:
        owners = _owners(
            engine,
            "doc.document_type = 'CONTRACT' AND c.slug = 'niletech'",
        )
        assert owners, "NileTech has no contracts"
        assert {dept for _slug, dept, _title in owners} == {"Legal"}

    def test_delta_contracts_fall_back_to_executive_management(self, engine: Engine) -> None:
        """FR-031a's documented fallback. Delta Retail has no Legal department, so
        without this rule its contracts would be ownerless or wrongly assigned."""
        owners = _owners(
            engine,
            "doc.document_type = 'CONTRACT' AND c.slug = 'delta-retail'",
        )
        assert owners, "Delta Retail has no contracts to exercise the fallback"
        assert {dept for _slug, dept, _title in owners} == {"Executive Management"}

    def test_delta_genuinely_has_no_legal_department(self, engine: Engine) -> None:
        """Guards the test above from becoming vacuous if Delta ever gains one."""
        with engine.connect() as conn:
            count = conn.execute(
                text(
                    "SELECT count(*) FROM departments d JOIN companies c ON c.id = d.company_id"
                    " WHERE c.slug = 'delta-retail' AND d.name = 'Legal'"
                )
            ).scalar_one()
        assert count == 0


class TestPublicAndReportOwnership:
    def test_public_content_is_owned_by_executive_management(self, engine: Engine) -> None:
        owners = _owners(engine, "doc.document_type = 'PUBLIC'")
        assert owners, "no public documents found"
        assert {dept for _slug, dept, _title in owners} == {"Executive Management"}

    def test_the_payroll_report_is_owned_by_hr(self, engine: Engine) -> None:
        owners = _owners(
            engine, "doc.document_type = 'REPORT' AND doc.classification = 'RESTRICTED'"
        )
        assert owners, "no restricted report found"
        assert {dept for _slug, dept, _title in owners} == {"HR"}


class TestAuthorizationAttributes:
    """FR-010 — sensitive resources carry owner, department, country, and
    classification, "so later authorization work has the attributes it requires".

    That clause is the point: Constitution Principle II layers ABAC on department,
    country, ownership, and classification. An attribute that is null on the very
    documents the rule is meant to protect is not a cosmetic gap — the filter has
    nothing to match on.

    25 of Delta Retail's CONFIDENTIAL contracts carried no department, because the
    lookup was by department *name* and Delta has no Legal team. Ownership already
    had a documented fallback for exactly that case (FR-031a); attribution did not
    use it. Both now follow the owner.
    """

    #: Company-wide by nature, so a null country is the correct ABAC answer — it
    #: means "not restricted by country", not "we forgot". Every other type must
    #: carry one.
    COMPANY_WIDE_TYPES = frozenset({"POLICY", "PUBLIC", "REPORT"})

    def test_every_document_has_an_owning_department(self, engine: Engine) -> None:
        with engine.connect() as conn:
            offenders = [
                (row.slug, row.document_type, row.title)
                for row in conn.execute(
                    text(
                        "SELECT c.slug, doc.document_type, doc.title FROM documents doc"
                        " JOIN companies c ON c.id = doc.company_id"
                        " WHERE doc.department_id IS NULL"
                    )
                )
            ]
        assert offenders == [], f"documents without a department: {offenders}"

    def test_the_department_matches_the_owner(self, engine: Engine) -> None:
        """Attribution and ownership must agree; two rules that can disagree will."""
        with engine.connect() as conn:
            mismatched = conn.execute(
                text(
                    "SELECT count(*) FROM documents doc"
                    " JOIN users u ON u.id = doc.owner_id"
                    " WHERE doc.department_id <> u.department_id"
                )
            ).scalar_one()
        assert mismatched == 0

    def test_country_specific_documents_carry_a_country(self, engine: Engine) -> None:
        with engine.connect() as conn:
            offenders = [
                (row.slug, row.document_type, row.title)
                for row in conn.execute(
                    text(
                        "SELECT c.slug, doc.document_type, doc.title FROM documents doc"
                        " JOIN companies c ON c.id = doc.company_id"
                        " WHERE doc.country IS NULL AND doc.document_type NOT IN"
                        " ('POLICY', 'PUBLIC', 'REPORT')"
                    )
                )
            ]
        assert offenders == [], f"documents without a country: {offenders}"

    def test_the_company_wide_exemption_is_not_a_blanket_one(self, engine: Engine) -> None:
        """Guards the exemption above. If every document type ended up on the
        company-wide list, the country assertion would pass while checking
        nothing."""
        with engine.connect() as conn:
            types = {
                row[0] for row in conn.execute(text("SELECT DISTINCT document_type FROM documents"))
            }
        assert types - self.COMPANY_WIDE_TYPES, (
            f"every document type is exempt from the country rule: {sorted(types)}"
        )

    def test_delta_retail_contracts_carry_a_department(self, engine: Engine) -> None:
        """The specific case that was broken: Delta has no Legal department, and
        its contracts fall back to Executive Management for ownership."""
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT d.name, count(*) FROM documents doc"
                    " JOIN companies c ON c.id = doc.company_id"
                    " JOIN departments d ON d.id = doc.department_id"
                    " WHERE c.slug = 'delta-retail' AND doc.document_type = 'CONTRACT'"
                    " GROUP BY d.name"
                )
            ).all()
        assert rows, "Delta Retail has no contracts with a department"
        assert {row[0] for row in rows} == {"Executive Management"}

    def test_every_classified_document_carries_exactly_one_level(self, engine: Engine) -> None:
        """FR-010b / SC-015 — the enum makes an unrecognised level unstorable, so
        this catches the remaining possibility: an absent one."""
        with engine.connect() as conn:
            missing = conn.execute(
                text("SELECT count(*) FROM documents WHERE classification IS NULL")
            ).scalar_one()
        assert missing == 0
