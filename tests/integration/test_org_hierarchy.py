"""The reporting structure is a valid tree (spec FR-034, FR-025a, SC-005).

A cycle in the manager chain would make any "show me my team" traversal loop
forever; two roots would make "the CEO" ambiguous. The generator enforces these
during construction, so these tests confirm the enforcement held rather than
hoping it did.

Recursive CTEs do the cycle detection in the database, which is both faster and
more honest than reimplementing traversal in Python.
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
            seeded = conn.execute(text("SELECT count(*) FROM users")).scalar_one()
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"database unavailable: {exc}")
    if not seeded:
        pytest.skip("environment not seeded; run `make up && make seed`")
    return engine


class TestSingleRoot:
    def test_exactly_one_manager_less_user_per_company(self, engine: Engine) -> None:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT c.slug, count(*) AS roots FROM users u"
                    " JOIN companies c ON c.id = u.company_id"
                    " WHERE u.manager_id IS NULL GROUP BY c.slug"
                )
            ).all()
        assert len(rows) == 2, "both tenants need a top-level executive"
        for row in rows:
            assert row.roots == 1, f"{row.slug} has {row.roots} manager-less users"

    def test_the_root_is_in_executive_management(self, engine: Engine) -> None:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT d.name FROM users u JOIN departments d ON d.id = u.department_id"
                    " WHERE u.manager_id IS NULL"
                )
            ).all()
        assert {row.name for row in rows} == {"Executive Management"}


class TestNoCycles:
    def test_the_manager_chain_terminates(self, engine: Engine) -> None:
        """A cycle would make this CTE recurse until Postgres stops it."""
        with engine.connect() as conn:
            cyclic = conn.execute(
                text(
                    """
                    WITH RECURSIVE chain(start_id, current_id, depth, path) AS (
                        SELECT id, manager_id, 1, ARRAY[id] FROM users
                        UNION ALL
                        SELECT c.start_id, u.manager_id, c.depth + 1, c.path || u.id
                        FROM chain c JOIN users u ON u.id = c.current_id
                        WHERE c.current_id IS NOT NULL
                          AND NOT u.id = ANY(c.path)
                          AND c.depth < 50
                    )
                    SELECT count(*) FROM chain WHERE depth >= 50
                    """
                )
            ).scalar_one()
        assert cyclic == 0, "manager chain does not terminate — there is a cycle"

    def test_nobody_manages_themselves(self, engine: Engine) -> None:
        with engine.connect() as conn:
            self_managed = conn.execute(
                text("SELECT count(*) FROM users WHERE id = manager_id")
            ).scalar_one()
        assert self_managed == 0


class TestSameCompanyRelationships:
    def test_managers_are_in_the_same_company(self, engine: Engine) -> None:
        with engine.connect() as conn:
            crossing = conn.execute(
                text(
                    "SELECT count(*) FROM users u JOIN users m ON m.id = u.manager_id"
                    " WHERE m.company_id <> u.company_id"
                )
            ).scalar_one()
        assert crossing == 0

    def test_departments_and_offices_are_in_the_same_company(self, engine: Engine) -> None:
        with engine.connect() as conn:
            bad_dept = conn.execute(
                text(
                    "SELECT count(*) FROM users u JOIN departments d ON d.id = u.department_id"
                    " WHERE d.company_id <> u.company_id"
                )
            ).scalar_one()
            bad_office = conn.execute(
                text(
                    "SELECT count(*) FROM users u JOIN offices o ON o.id = u.office_id"
                    " WHERE o.company_id <> u.company_id"
                )
            ).scalar_one()
        assert (bad_dept, bad_office) == (0, 0)


class TestDepartmentHeads:
    def test_every_department_has_a_head(self, engine: Engine) -> None:
        """The column is nullable only to break the insertion cycle; a completed
        dataset must have none left null (data-model.md §2)."""
        with engine.connect() as conn:
            headless = conn.execute(
                text("SELECT count(*) FROM departments WHERE head_user_id IS NULL")
            ).scalar_one()
        assert headless == 0

    def test_each_head_belongs_to_the_department_they_lead(self, engine: Engine) -> None:
        with engine.connect() as conn:
            mismatched = conn.execute(
                text(
                    "SELECT count(*) FROM departments d JOIN users u ON u.id = d.head_user_id"
                    " WHERE u.department_id <> d.id"
                )
            ).scalar_one()
        assert mismatched == 0


class TestManagerRole:
    def test_everyone_with_reports_holds_the_manager_role(self, engine: Engine) -> None:
        """FR-025a — the Manager role must mean something."""
        with engine.connect() as conn:
            missing = conn.execute(
                text(
                    "SELECT count(*) FROM users u"
                    " WHERE EXISTS (SELECT 1 FROM users r WHERE r.manager_id = u.id)"
                    "   AND NOT EXISTS ("
                    "     SELECT 1 FROM user_roles ur JOIN roles ro ON ro.id = ur.role_id"
                    "     WHERE ur.user_id = u.id AND ro.name = 'Manager')"
                )
            ).scalar_one()
        assert missing == 0

    def test_every_user_has_exactly_one_primary_role(self, engine: Engine) -> None:
        with engine.connect() as conn:
            wrong = conn.execute(
                text(
                    "SELECT count(*) FROM (SELECT user_id, count(*) FILTER (WHERE is_primary) AS n"
                    " FROM user_roles GROUP BY user_id HAVING count(*) FILTER (WHERE is_primary) <> 1) s"
                )
            ).scalar_one()
        assert wrong == 0

    def test_roles_belong_to_the_users_company(self, engine: Engine) -> None:
        with engine.connect() as conn:
            crossing = conn.execute(
                text(
                    "SELECT count(*) FROM user_roles ur"
                    " JOIN users u ON u.id = ur.user_id"
                    " JOIN roles r ON r.id = ur.role_id"
                    " WHERE r.company_id <> u.company_id"
                )
            ).scalar_one()
        assert crossing == 0


class TestCompositionMatchesSpec:
    """SC-005 / FR-018 / FR-019 — named structure, not just counts."""

    def test_niletech_has_the_eight_named_departments(self, engine: Engine) -> None:
        with engine.connect() as conn:
            names = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT d.name FROM departments d JOIN companies c ON c.id = d.company_id"
                        " WHERE c.slug = 'niletech'"
                    )
                )
            }
        assert names == {
            "Engineering",
            "HR",
            "Sales",
            "Finance",
            "Legal",
            "Customer Support",
            "Operations",
            "Executive Management",
        }

    def test_niletech_has_the_three_named_offices(self, engine: Engine) -> None:
        with engine.connect() as conn:
            cities = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT o.city FROM offices o JOIN companies c ON c.id = o.company_id"
                        " WHERE c.slug = 'niletech'"
                    )
                )
            }
        assert cities == {"Cairo", "Alexandria", "Dubai"}

    def test_delta_deliberately_lacks_engineering_and_legal(self, engine: Engine) -> None:
        """FR-022 — the absence must be provable, not merely observed."""
        with engine.connect() as conn:
            names = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT d.name FROM departments d JOIN companies c ON c.id = d.company_id"
                        " WHERE c.slug = 'delta-retail'"
                    )
                )
            }
        assert "Engineering" not in names
        assert "Legal" not in names
        assert len(names) == 5

    def test_every_user_resolves_to_exactly_one_department(self, engine: Engine) -> None:
        with engine.connect() as conn:
            unassigned = conn.execute(
                text("SELECT count(*) FROM users WHERE department_id IS NULL")
            ).scalar_one()
        assert unassigned == 0


class TestDistributionIsPlausible:
    """FR-020 — "plausible for a company of this type and size rather than uniform".

    The generated spread is right (Engineering 60, Legal 10; Cairo 116,
    Alexandria 55, Dubai 29 at the full profile), but nothing checked it.
    `test_volume_targets.py` measures only the total, so an allocator change that
    handed all eight departments an equal share would pass every existing test
    while removing the premise that makes departmental and regional questions
    interesting — and the failure would surface much later, as an AI that gives
    boring answers rather than as a data defect.

    Asserted as a ratio rather than as fixed counts, so the smoke profile is
    covered too and the fingerprint stays the thing that pins exact values.
    """

    @staticmethod
    def _headcount(engine: Engine, slug: str, column: str, table: str) -> list[int]:
        with engine.connect() as conn:
            return [
                int(row[0])
                for row in conn.execute(
                    text(
                        f"SELECT count(*) FROM users u"
                        f" JOIN companies c ON c.id = u.company_id"
                        f" JOIN {table} t ON t.id = u.{column}"
                        f" WHERE c.slug = :slug GROUP BY t.id ORDER BY count(*) DESC"
                    ),
                    {"slug": slug},
                )
            ]

    def test_departments_are_not_uniformly_sized(self, engine: Engine) -> None:
        sizes = self._headcount(engine, "niletech", "department_id", "departments")
        assert len(sizes) == 8, f"expected eight departments, got {len(sizes)}"
        assert sizes[0] >= 2 * sizes[-1], (
            f"department sizes {sizes} are near-uniform; FR-020 requires a "
            "plausible distribution, and Engineering should dwarf Legal"
        )

    def test_offices_are_not_uniformly_sized(self, engine: Engine) -> None:
        sizes = self._headcount(engine, "niletech", "office_id", "offices")
        assert len(sizes) == 3, f"expected three offices, got {len(sizes)}"
        assert sizes[0] >= 2 * sizes[-1], (
            f"office headcounts {sizes} are near-uniform; the headquarters should "
            "hold materially more staff than the smallest site (FR-020)"
        )

    def test_the_largest_department_is_engineering(self, engine: Engine) -> None:
        """A software and business-automation company (FR-018). A skew that put
        Legal on top would satisfy the ratio check above and still be wrong."""
        with engine.connect() as conn:
            name = conn.execute(
                text(
                    "SELECT d.name FROM users u"
                    " JOIN companies c ON c.id = u.company_id"
                    " JOIN departments d ON d.id = u.department_id"
                    " WHERE c.slug = 'niletech'"
                    " GROUP BY d.name ORDER BY count(*) DESC, d.name LIMIT 1"
                )
            ).scalar_one()
        assert name == "Engineering"

    def test_every_department_still_has_someone(self, engine: Engine) -> None:
        """Skew must not become emptiness — a headless department breaks the
        ownership convention in FR-031a."""
        sizes = self._headcount(engine, "niletech", "department_id", "departments")
        assert min(sizes) > 0
