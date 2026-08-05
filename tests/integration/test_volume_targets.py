"""Realized volumes match the specification's targets (spec FR-020b, SC-010).

FR-020b allows ±10% against the published table. The tolerance applies to the
*profile targets*, not to run-to-run variance — a single seed value always produces
exactly the same counts (that is FR-011, covered by the determinism tests).

SC-010 additionally requires every named entity family to be present and non-empty,
which is what catches a generator that silently stops emitting one table.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text

from eaios_core.db import create_owner_engine
from eaios_seed.config import SeedConfig

pytestmark = pytest.mark.integration

#: Families that must exist for both tenants (SC-010).
REQUIRED_FOR_BOTH = (
    "companies",
    "offices",
    "departments",
    "roles",
    "role_permissions",
    "users",
    "user_roles",
    "employee_profiles",
    "leave_balances",
    "leave_requests",
    "attendance_records",
    "training_records",
    "performance_reviews",
    "customers",
    "products",
    "orders",
    "order_lines",
    "invoices",
    "sales_targets",
    "expenses",
    "budgets",
    "monthly_revenue",
    "documents",
    "contracts",
    "policy_documents",
    "services",
    "public_products",
    "leadership_profiles",
    "news_items",
    "vacancies",
    "audit_logs",
)

TOLERANCE = 0.10


@pytest.fixture(scope="module")
def counts() -> dict[str, Any]:
    try:
        engine = create_owner_engine()
        with engine.connect() as conn:
            row = (
                conn.execute(text("SELECT entity_counts, profile FROM dataset_manifest LIMIT 1"))
                .mappings()
                .first()
            )
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"database unavailable: {exc}")
    if row is None:
        pytest.skip("environment not seeded; run `make seed`")
    return dict(row)


def _count(counts: dict[str, Any], slug: str, table: str) -> int:
    return int(counts["entity_counts"].get(f"{slug}.{table}", 0))


class TestCoverage:
    @pytest.mark.parametrize("slug", ["niletech", "delta-retail"])
    @pytest.mark.parametrize("table", REQUIRED_FOR_BOTH)
    def test_family_is_present_and_non_empty(
        self, counts: dict[str, Any], slug: str, table: str
    ) -> None:
        assert _count(counts, slug, table) > 0, f"{slug}.{table} is empty (SC-010)"

    def test_global_permission_catalog_is_populated(self, counts: dict[str, Any]) -> None:
        assert int(counts["entity_counts"].get("global.permissions", 0)) == 17

    def test_documents_were_written_to_object_storage(self, counts: dict[str, Any]) -> None:
        assert int(counts["entity_counts"].get("files.documents", 0)) > 0


class TestStructuralTargets:
    """Structural counts are exact — they are not subject to the ±10% tolerance."""

    def test_niletech_has_eight_departments(self, counts: dict[str, Any]) -> None:
        assert _count(counts, "niletech", "departments") == 8

    def test_delta_has_five_departments(self, counts: dict[str, Any]) -> None:
        assert _count(counts, "delta-retail", "departments") == 5

    def test_niletech_has_three_offices(self, counts: dict[str, Any]) -> None:
        assert _count(counts, "niletech", "offices") == 3

    def test_delta_has_two_offices(self, counts: dict[str, Any]) -> None:
        assert _count(counts, "delta-retail", "offices") == 2

    def test_each_company_has_seven_roles(self, counts: dict[str, Any]) -> None:
        for slug in ("niletech", "delta-retail"):
            assert _count(counts, slug, "roles") == 7

    def test_each_company_has_eight_policy_documents(self, counts: dict[str, Any]) -> None:
        for slug in ("niletech", "delta-retail"):
            assert _count(counts, slug, "policy_documents") == 8

    def test_one_seed_audit_entry_per_tenant(self, counts: dict[str, Any]) -> None:
        for slug in ("niletech", "delta-retail"):
            assert _count(counts, slug, "audit_logs") == 1


class TestVolumeTargets:
    """FR-020b: within ±10% of the profile's published targets."""

    @pytest.mark.parametrize("slug", ["niletech", "delta-retail"])
    @pytest.mark.parametrize(
        ("table", "attribute"),
        [
            ("users", "users"),
            ("customers", "customers"),
            ("products", "products"),
            ("orders", "orders"),
            ("expenses", "expenses"),
        ],
    )
    def test_within_tolerance(
        self, counts: dict[str, Any], slug: str, table: str, attribute: str
    ) -> None:
        config = SeedConfig.build(profile=counts["profile"])
        target = getattr(config.for_tenant(slug), attribute)
        actual = _count(counts, slug, table)
        low, high = target * (1 - TOLERANCE), target * (1 + TOLERANCE)
        assert low <= actual <= high, (
            f"{slug}.{table} = {actual}, outside ±{TOLERANCE:.0%} of target {target}"
        )

    def test_invoices_match_orders_one_to_one(self, counts: dict[str, Any]) -> None:
        for slug in ("niletech", "delta-retail"):
            assert _count(counts, slug, "invoices") == _count(counts, slug, "orders")

    def test_every_user_has_exactly_one_employee_profile(self, counts: dict[str, Any]) -> None:
        for slug in ("niletech", "delta-retail"):
            assert _count(counts, slug, "employee_profiles") == _count(counts, slug, "users")


class TestSuccessCriterion005:
    """SC-005 states a number, and nothing was checking it.

    `TestVolumeTargets` measures against the *profile's* scaled targets, which at
    smoke is roughly 28 users and at full is 180–220 — neither is the criterion.
    SC-005 commits to **190–210 employees** in NileTech, spanning all eight named
    departments and all three named offices, and that claim only exists at the full
    profile. CI seeded smoke exclusively, so the number the specification promises a
    reviewer had never been measured.

    Skipped rather than adapted at smoke: a criterion quietly re-scaled to whatever
    profile happens to be loaded is not the criterion.
    """

    #: SC-005, verbatim.
    LOWER, UPPER = 190, 210

    @pytest.fixture(autouse=True)
    def _requires_full_profile(self, counts: dict[str, Any]) -> None:
        if counts["profile"] != "full":
            pytest.skip(
                f"SC-005 describes the full dataset; this environment holds "
                f"{counts['profile']!r}. Run `eaios-seed reset --yes --profile full`."
            )

    def test_niletech_employee_count_is_within_the_stated_range(
        self, counts: dict[str, Any]
    ) -> None:
        actual = _count(counts, "niletech", "users")
        assert self.LOWER <= actual <= self.UPPER, (
            f"NileTech has {actual} employees; SC-005 requires {self.LOWER} to {self.UPPER}"
        )

    def test_every_employee_has_a_profile_and_a_department(self, counts: dict[str, Any]) -> None:
        """SC-005 also requires each employee to resolve to exactly one department;
        `test_org_hierarchy.py` proves the resolution, this proves the population it
        was proved over is the full one."""
        assert _count(counts, "niletech", "employee_profiles") == _count(
            counts, "niletech", "users"
        )

    def test_delta_retail_is_about_one_fifth_the_size(self, counts: dict[str, Any]) -> None:
        """The documented ratio (spec Assumptions). A Delta that quietly grew to
        NileTech's size would still satisfy every count-based test above."""
        niletech = _count(counts, "niletech", "users")
        delta = _count(counts, "delta-retail", "users")
        ratio = delta / niletech
        assert 0.15 <= ratio <= 0.25, (
            f"Delta Retail is {ratio:.0%} of NileTech; the specification assumes ~20%"
        )
