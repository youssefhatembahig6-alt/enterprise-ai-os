"""The public surface exposes public content and nothing adjacent to it
(spec 002 FR-007, FR-011, FR-012, FR-013).

`test_public_field_allowlist.py` proves responses contain only declared *fields*.
This proves they contain only declared *records* — a different claim. A response
could carry exactly the right field names and still be drawn from the wrong table.

The internal `products` catalogue is the sharpest case: it shares a name with the
public one, carries prices and tiers, and sits one join away.
"""

from __future__ import annotations

import os

import httpx
import pytest
from sqlalchemy import Engine, text

pytestmark = pytest.mark.integration

BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")


@pytest.fixture(scope="module")
def client() -> httpx.Client:
    with httpx.Client(base_url=BASE_URL, timeout=15.0) as session:
        try:
            session.get("/health/live")
        except httpx.HTTPError:  # pragma: no cover - environment guard
            pytest.skip("API is not running; start it with `make up`")
        yield session


@pytest.fixture(scope="module")
def engine() -> Engine:
    from eaios_core.db import create_owner_engine

    engine = create_owner_engine()
    try:
        with engine.connect() as conn:
            seeded = conn.execute(text("SELECT count(*) FROM services")).scalar_one()
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"database unavailable: {exc}")
    if not seeded:
        pytest.skip("environment not seeded; run `make up && make seed`")
    return engine


class TestInternalCatalogueIsUnreachable:
    """FR-012 — the internal sellable catalogue is a different table, and no public
    route reads it. Asserted as unreachable rather than merely unrendered."""

    def test_public_products_are_not_the_internal_catalogue(
        self, client: httpx.Client, engine: Engine
    ) -> None:
        with engine.connect() as conn:
            internal = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT p.name FROM products p JOIN companies c"
                        " ON c.id = p.company_id WHERE c.slug = 'niletech'"
                    )
                )
            }
            public = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT p.name FROM public_products p JOIN companies c"
                        " ON c.id = p.company_id WHERE c.slug = 'niletech'"
                    )
                )
            }

        assert internal, "no internal products — the assertion below would be vacuous"
        assert public, "no public products to compare against"

        served = {item["name"] for item in client.get("/public/products").json()}

        # The source table is the claim. Set equality with `public_products` proves
        # the endpoint reads that table and not `products`.
        assert served == public

        # Names legitimately overlap between the two catalogues — the public one is
        # a marketing view of the same product line, and feature 001 generates
        # "Analytics Workspace" publicly alongside "Analytics Workspace 2" and "3"
        # internally. So a no-overlap assertion would fail a correct implementation.
        # What must never appear is an item *exclusive* to the internal catalogue.
        internal_only = internal - public
        assert internal_only, "the two catalogues are identical; this check proves nothing"
        assert not (served & internal_only), (
            f"the public endpoint served internal-only catalogue items: "
            f"{sorted(served & internal_only)}"
        )

    def test_no_price_or_tier_is_exposed(self, client: httpx.Client) -> None:
        body = client.get("/public/products").text.lower()
        for term in ("price", "tier", "cost", "unit_price"):
            assert term not in body, f"the public catalogue exposes {term}"


class TestOrderingIsHonoured:
    """FR-008 — the site presents records in the generator's stated order."""

    @pytest.mark.parametrize("path", ["/public/services", "/public/products"])
    def test_display_order_ascends(self, client: httpx.Client, path: str) -> None:
        orders = [item["display_order"] for item in client.get(path).json()]
        assert orders, f"{path} returned nothing to order"
        assert orders == sorted(orders)

    def test_news_is_newest_first(self, client: httpx.Client) -> None:
        dates = [item["published_on"] for item in client.get("/public/news").json()["items"]]
        assert dates, "no news to order"
        assert dates == sorted(dates, reverse=True)


class TestEveryRecordIsServed:
    """SC-002 — every generated public record reaches the site. A silently
    truncated list would look like a smaller company rather than a defect."""

    def test_all_services_are_served(self, client: httpx.Client, engine: Engine) -> None:
        with engine.connect() as conn:
            expected = conn.execute(
                text(
                    "SELECT count(*) FROM services s JOIN companies c"
                    " ON c.id = s.company_id WHERE c.slug = 'niletech'"
                )
            ).scalar_one()
        assert len(client.get("/public/services").json()) == expected

    def test_all_leadership_profiles_are_served(
        self, client: httpx.Client, engine: Engine
    ) -> None:
        with engine.connect() as conn:
            expected = conn.execute(
                text(
                    "SELECT count(*) FROM leadership_profiles l JOIN companies c"
                    " ON c.id = l.company_id WHERE c.slug = 'niletech'"
                )
            ).scalar_one()
        assert len(client.get("/public/leadership").json()) == expected

    def test_only_open_vacancies_are_served(
        self, client: httpx.Client, engine: Engine
    ) -> None:
        """FR-014 — closed vacancies are absent entirely, not flagged."""
        with engine.connect() as conn:
            open_count, total = conn.execute(
                text(
                    "SELECT count(*) FILTER (WHERE v.is_open), count(*)"
                    " FROM vacancies v JOIN companies c ON c.id = v.company_id"
                    " WHERE c.slug = 'niletech'"
                )
            ).one()
        served = client.get("/public/vacancies").json()
        assert len(served) == open_count
        assert open_count <= total


class TestClosedVacanciesDisappear:
    """FR-014 and the "closed vacancy reached directly" edge case.

    `test_only_open_vacancies_are_served` above asserts `len(served) == open_count`.
    That assertion has never been able to fail: `generators/public.py` hard-codes
    `is_open=True`, so NileTech carries eleven open vacancies and zero closed ones in
    both profiles, and the comparison reduces to `11 == 11` whether the `is_open`
    predicate in `queries.py` is present or deleted. `contracts/public-fields.md`
    explains that closed vacancies are "absent from the response entirely… so there
    is no state for a client to misread" — a documented behaviour with no evidence.

    So this creates the condition instead of waiting for the seed to supply it.

    **Why not change the generator.** `vacancies` is part of the fingerprinted
    dataset; emitting a closed row there would move the committed digest and turn a
    test-coverage fix into a determinism change. The mutation happens at runtime and
    is reverted, the same approach `test_request_time_rendering.py` takes.
    """

    @pytest.fixture
    def closed_vacancy(self, client: httpx.Client, engine: Engine):
        """Close the first listed vacancy for the duration of one test.

        The subject is taken from the API's own listing rather than chosen by a
        separate query. An earlier test in this suite picked a row with `ORDER BY
        display_order LIMIT 1`, which is ambiguous across the two tenants and
        silently selected Delta Retail's record half the time.
        """
        listed = client.get("/public/vacancies").json()
        assert listed, "no vacancies to close; the fixture has nothing to work with"
        subject = listed[0]

        def set_open(value: bool) -> int:
            with engine.begin() as conn:
                return int(
                    conn.execute(
                        text(
                            "UPDATE vacancies SET is_open = :open"
                            " WHERE title = :title AND office_id = ("
                            "   SELECT id FROM offices WHERE city = :city"
                            "   AND company_id = (SELECT id FROM companies WHERE slug = 'niletech')"
                            " ) AND company_id = (SELECT id FROM companies WHERE slug = 'niletech')"
                        ),
                        {"open": value, "title": subject["title"], "city": subject["office_city"]},
                    ).rowcount
                )

        changed = set_open(False)
        assert changed >= 1, f"closed no row for {subject['title']!r}"
        try:
            yield subject, len(listed)
        finally:
            # In the fixture, not the test body: a mid-test failure that left a
            # vacancy closed would fail the fingerprint check later and read as a
            # generator defect.
            set_open(True)

    def test_the_subject_is_served_before_it_is_closed(
        self, client: httpx.Client
    ) -> None:
        """Anti-vacuity guard, without the fixture. Everything below asserts that
        something *stops* being served, which is trivially true of a slug that was
        never served in the first place."""
        listed = client.get("/public/vacancies").json()
        assert listed
        assert client.get(f"/public/vacancies/{listed[0]['slug']}").status_code == 200

    def test_a_closed_vacancy_leaves_the_list(
        self, client: httpx.Client, closed_vacancy
    ) -> None:
        subject, _ = closed_vacancy
        slugs = [item["slug"] for item in client.get("/public/vacancies").json()]
        assert subject["slug"] not in slugs

    def test_exactly_one_vacancy_leaves_the_list(
        self, client: httpx.Client, closed_vacancy
    ) -> None:
        """Closing one role must not remove two. A filter written against the wrong
        column would empty the list and still satisfy the assertion above."""
        _, before = closed_vacancy
        assert len(client.get("/public/vacancies").json()) == before - 1

    def test_its_detail_address_is_not_found(
        self, client: httpx.Client, closed_vacancy
    ) -> None:
        """The edge case itself: a role that is no longer open must not answer with a
        page inviting applications. The list and the detail read through the same
        `_vacancy_rows`, so this is the assertion that keeps them together."""
        subject, _ = closed_vacancy
        response = client.get(f"/public/vacancies/{subject['slug']}")

        assert response.status_code == 404
        body = response.text.lower()
        for invitation in ("apply", "applications", subject["title"].lower()):
            assert invitation not in body, f"the refusal still mentions {invitation!r}"

    def test_it_returns_when_reopened(self, client: httpx.Client, engine: Engine) -> None:
        """The fixture restores; this proves the restore is real rather than assumed,
        and that the row survived the round trip intact."""
        listed = client.get("/public/vacancies").json()
        assert listed
        assert client.get(f"/public/vacancies/{listed[0]['slug']}").status_code == 200

    def test_no_vacancy_is_left_closed(self, engine: Engine) -> None:
        """Runs after the mutating tests in file order. A leaked closure would alter
        the dataset and fail the fingerprint check under an unrelated name."""
        with engine.connect() as conn:
            closed = conn.execute(
                text(
                    "SELECT count(*) FROM vacancies v JOIN companies c ON c.id = v.company_id"
                    " WHERE c.slug = 'niletech' AND NOT v.is_open"
                )
            ).scalar_one()
        assert closed == 0, f"{closed} vacancy(ies) left closed by this module"


class TestUnresolvableLeadershipProfiles:
    """FR-013a — an unresolvable profile is omitted **and** the omission is recorded.

    The omission half already held, by accident rather than by decision: the query
    joins `users` inline, so a profile whose employee row is missing simply never
    appears. Nothing noticed, which meant a profile silently vanishing from a public
    page was indistinguishable from one the generator never produced.

    Every profile resolves in the seeded dataset, so this behaviour is unreachable
    from the data — the same shape as the closed-vacancy gap above. The condition is
    created at runtime and reverted.
    """

    @pytest.fixture
    def unlinked_profile(self, client: httpx.Client, engine: Engine):
        """Point one NileTech profile at a **Delta Retail** employee row.

        The first attempt repointed to a random UUID and the database refused it:
        `leadership_profiles.user_id` carries a foreign key, so a dangling reference
        is not a state this schema can hold. That is worth knowing — it means the
        realistic fault is not a missing row but one the serving role cannot see.

        Which is exactly what this produces. The public query runs as `eaios_app`
        inside NileTech's tenant scope, so RLS filters `users` to NileTech; a profile
        pointing at another tenant's employee finds nothing to join to. The foreign
        key is satisfied, the row exists, and the linked record still "cannot be
        resolved" from the public surface — FR-013a's condition, reached the way it
        could actually occur.

        It also demonstrates the isolation working: without RLS on `users`, that join
        would have resolved and put a Delta Retail employee's name on NileTech's
        Leadership page.
        """
        before = client.get("/public/leadership").json()
        assert before, "no leadership profiles to work with"
        subject = before[0]

        with engine.connect() as conn:
            original = conn.execute(
                text(
                    "SELECT lp.user_id FROM leadership_profiles lp"
                    " JOIN users u ON u.id = lp.user_id"
                    " JOIN companies c ON c.id = lp.company_id"
                    " WHERE c.slug = 'niletech' AND u.full_name = :name"
                ),
                {"name": subject["full_name"]},
            ).scalar_one()
            other_tenant_user = conn.execute(
                text(
                    "SELECT u.id FROM users u JOIN companies c ON c.id = u.company_id"
                    " WHERE c.slug = 'delta-retail' ORDER BY u.id LIMIT 1"
                )
            ).scalar_one()

        def repoint(target, current) -> None:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "UPDATE leadership_profiles SET user_id = :target"
                        " WHERE user_id = :current AND company_id ="
                        " (SELECT id FROM companies WHERE slug = 'niletech')"
                    ),
                    {"target": target, "current": current},
                )

        repoint(other_tenant_user, original)
        try:
            yield subject, len(before)
        finally:
            repoint(original, other_tenant_user)

    def test_the_profile_is_omitted(self, client: httpx.Client, unlinked_profile) -> None:
        subject, _ = unlinked_profile
        names = [item["full_name"] for item in client.get("/public/leadership").json()]
        assert subject["full_name"] not in names

    def test_the_other_profiles_still_render(
        self, client: httpx.Client, unlinked_profile
    ) -> None:
        """FR-030 — one broken record must not remove the page."""
        _, before = unlinked_profile
        served = client.get("/public/leadership").json()
        assert len(served) == before - 1
        assert served, "the whole page emptied because one profile was unresolvable"

    def test_the_omission_is_recorded(
        self, client: httpx.Client, engine: Engine, unlinked_profile
    ) -> None:
        with engine.connect() as conn:
            before = int(
                conn.execute(
                    text("SELECT count(*) FROM audit_logs WHERE action = 'public.content_omitted'")
                ).scalar_one()
            )

        client.get("/public/leadership")

        with engine.connect() as conn:
            after = int(
                conn.execute(
                    text("SELECT count(*) FROM audit_logs WHERE action = 'public.content_omitted'")
                ).scalar_one()
            )
        assert after > before, "a profile disappeared from a public page with no record of it"

    def test_the_record_names_no_person(
        self, client: httpx.Client, engine: Engine, unlinked_profile
    ) -> None:
        """FR-013 forbids exposing any other attribute of that individual, and an
        identifier written into a diagnostic record is still an exposure."""
        subject, _ = unlinked_profile
        client.get("/public/leadership")

        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT resource_id, reason FROM audit_logs"
                    " WHERE action = 'public.content_omitted' ORDER BY created_at DESC LIMIT 1"
                )
            ).one()

        blob = f"{row.resource_id} {row.reason}"
        assert subject["full_name"] not in blob
        assert subject["public_title"] not in blob
        assert "user_id" not in blob.lower()

    def test_everything_resolves_again_afterwards(
        self, client: httpx.Client, engine: Engine
    ) -> None:
        """Runs after the mutating tests in file order. A leaked repoint would leave
        the dataset short a profile and fail the fingerprint under another name."""
        with engine.connect() as conn:
            orphaned = int(
                conn.execute(
                    text(
                        "SELECT count(*) FROM leadership_profiles lp"
                        " LEFT JOIN users u ON u.id = lp.user_id WHERE u.id IS NULL"
                    )
                ).scalar_one()
            )
        assert orphaned == 0
        assert len(client.get("/public/leadership").json()) == 6
