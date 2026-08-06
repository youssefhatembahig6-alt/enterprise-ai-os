"""Zero cross-tenant access for an authenticated caller (FR-021, FR-030, FR-034, SC-004).

Constitution Principle I is the project's central claim, and this is the first feature
in which an *authenticated* caller could attempt to cross the boundary. Features 001 and
002 established it structurally and for anonymous callers; here somebody with a valid
session asks for another company's record.

**The answer must be "not found", never "forbidden".** FR-030 explains why that is not
an exception to FR-020: the tenant boundary is layer 1 of the authorization ordering,
applied *before* authorization is consulted, so another tenant's resource is **absent**
rather than denied. A 403 would confirm the record exists — which is the enumeration
the ordering exists to prevent, and the whole reason layer 1 comes first.

**Every assertion here has a non-empty denominator.** "Zero Delta Retail records
reached" is trivially true of a caller who can reach nothing at all, and a suite that
proved only that would be the most reassuring possible way to check nothing. So each
class asserts what the caller *can* see before asserting what they cannot, and the
ground truth comes from the owner connection — the one that sees across tenants —
rather than from the app role, which would be proving that a filtered view is filtered.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from eaios_core.db import create_owner_engine

from .auth_helpers import (
    DELTA_EMPLOYEE,
    EMPLOYEE,
    HR,
    Person,
    auth,
    load_person,
    token_for,
)

pytestmark = pytest.mark.security


def _people_in_other_tenant(person: Person, limit: int = 12) -> list[uuid.UUID]:
    """Real user ids belonging to the *other* company, from ground truth."""
    with create_owner_engine().connect() as conn:
        return [
            row.id
            for row in conn.execute(
                text(
                    "SELECT id FROM users WHERE company_id <> :c AND is_active"
                    " ORDER BY id LIMIT :n"
                ),
                {"c": person.company_id, "n": limit},
            )
        ]


#: Every address this feature adds that takes a user id. A new one must be added here,
#: which is what stops an endpoint shipping without an isolation case (FR-034).
SUBJECT_ENDPOINTS = (
    "/hr/profiles/{id}",
    "/hr/profiles/{id}/compensation",
)

#: Every address that takes no subject — these must return the *caller's own* tenant's
#: data and never leak across, which is a different property from the above.
SELF_ENDPOINTS = (
    "/me",
    "/me/access-context",
    "/me/hr-profile",
    "/me/direct-reports",
    "/auth/session",
)


class TestTheDenominatorIsReal:
    """Everything below is "zero of theirs". Without these, zero is free."""

    def test_both_tenants_have_people(self) -> None:
        with create_owner_engine().connect() as conn:
            counts = dict(
                conn.execute(
                    text(
                        "SELECT c.slug, count(u.id) FROM companies c"
                        " JOIN users u ON u.company_id = c.id GROUP BY c.slug"
                    )
                ).all()
            )
        assert len(counts) == 2, f"expected two tenants, found {counts}"
        assert all(n > 0 for n in counts.values()), counts

    def test_the_other_tenant_has_reachable_looking_records(self) -> None:
        delta = load_person(DELTA_EMPLOYEE)
        others = _people_in_other_tenant(delta)
        assert others, "no NileTech users to attempt; the whole file would be vacuous"

    def test_the_caller_can_reach_their_own_records(self, client: TestClient) -> None:
        """The load-bearing control. A Delta Retail caller who could reach *nothing*
        would satisfy every isolation assertion in this file."""
        token = token_for(client, DELTA_EMPLOYEE)
        person = load_person(DELTA_EMPLOYEE)

        assert client.get("/me", headers=auth(token)).status_code == 200
        own = client.get(f"/hr/profiles/{person.user_id}", headers=auth(token))
        assert own.status_code == 200, own.text
        assert own.json()["user_id"] == str(person.user_id)


class TestAnotherTenantsRecordIsAbsent:
    def test_every_subject_endpoint_answers_not_found(self, client: TestClient) -> None:
        """FR-034: across every address this feature adds."""
        token = token_for(client, DELTA_EMPLOYEE)
        delta = load_person(DELTA_EMPLOYEE)
        targets = _people_in_other_tenant(delta)

        wrong: list[str] = []
        for template in SUBJECT_ENDPOINTS:
            for target in targets:
                response = client.get(template.format(id=target), headers=auth(token))
                if response.status_code != 404:
                    wrong.append(f"{template.format(id=target)} -> {response.status_code}")

        assert wrong == [], (
            "a cross-tenant request did not answer not-found. 403 confirms the record"
            " exists, which is what layer 1 ordering prevents (FR-021, FR-030):\n  "
            + "\n  ".join(wrong[:10])
        )

    def test_it_is_indistinguishable_from_an_identifier_belonging_to_nobody(
        self, client: TestClient
    ) -> None:
        """SC-004's exact wording. Same status *and* same body — a difference in either
        is a signal, and the body is the one an implementation forgets."""
        token = token_for(client, DELTA_EMPLOYEE)
        delta = load_person(DELTA_EMPLOYEE)
        real_elsewhere = _people_in_other_tenant(delta)[0]
        nobody = uuid.uuid4()

        elsewhere = client.get(f"/hr/profiles/{real_elsewhere}", headers=auth(token))
        nowhere = client.get(f"/hr/profiles/{nobody}", headers=auth(token))

        assert elsewhere.status_code == nowhere.status_code == 404
        assert elsewhere.text == nowhere.text, (
            "a record in another tenant answers differently from one that does not"
            f" exist:\n  elsewhere: {elsewhere.text}\n  nowhere:   {nowhere.text}"
        )

    def test_the_refusal_names_nothing(self, client: TestClient) -> None:
        token = token_for(client, DELTA_EMPLOYEE)
        delta = load_person(DELTA_EMPLOYEE)
        body = client.get(
            f"/hr/profiles/{_people_in_other_tenant(delta)[0]}", headers=auth(token)
        ).text.lower()

        for leak in ("niletech", "tenant", "company", "forbidden", "permission", "other"):
            assert leak not in body, f"the not-found body mentions {leak!r}: {body}"


class TestItHoldsInBothDirections:
    """Isolation is not a property of one tenant. A NileTech caller must be equally
    unable to reach Delta Retail — and a suite that only tested one direction would
    miss a policy accidentally keyed to a specific company id."""

    def test_a_niletech_caller_cannot_reach_delta_retail(
        self, client: TestClient
    ) -> None:
        token = token_for(client, EMPLOYEE)
        niletech = load_person(EMPLOYEE)
        targets = _people_in_other_tenant(niletech)
        assert targets, "no Delta Retail users to attempt"

        for target in targets[:5]:
            response = client.get(f"/hr/profiles/{target}", headers=auth(token))
            assert response.status_code == 404, f"{target} -> {response.status_code}"

    def test_even_the_widest_permission_does_not_cross(self, client: TestClient) -> None:
        """`hr:read_all` reaches every HR record **in the caller's company**. The
        tenant boundary is layer 1 and is not something a permission can widen — this
        is the case where an implementation that checked RBAC first would leak."""
        token = token_for(client, HR)
        hr_person = load_person(HR)
        targets = _people_in_other_tenant(hr_person)

        for target in targets[:5]:
            profile = client.get(f"/hr/profiles/{target}", headers=auth(token))
            compensation = client.get(
                f"/hr/profiles/{target}/compensation", headers=auth(token)
            )
            assert profile.status_code == 404, f"profile {target}"
            assert compensation.status_code == 404, f"compensation {target}"

    def test_the_same_caller_reaches_those_records_inside_their_own_tenant(
        self, client: TestClient
    ) -> None:
        """Paired with the test above. Without it, "HR reached nothing" is satisfied by
        an HR account whose permission is broken."""
        token = token_for(client, HR)
        colleague = load_person(EMPLOYEE)  # same company as HR

        assert client.get(
            f"/hr/profiles/{colleague.user_id}", headers=auth(token)
        ).status_code == 200
        assert client.get(
            f"/hr/profiles/{colleague.user_id}/compensation", headers=auth(token)
        ).status_code == 200


class TestSelfEndpointsStayInTheirTenant:
    def test_every_self_endpoint_returns_the_callers_own_company(
        self, client: TestClient
    ) -> None:
        delta = load_person(DELTA_EMPLOYEE)
        token = token_for(client, DELTA_EMPLOYEE)

        for path in SELF_ENDPOINTS:
            response = client.get(path, headers=auth(token))
            assert response.status_code == 200, f"{path}: {response.text}"

        context = client.get("/me/access-context", headers=auth(token)).json()
        assert context["company_id"] == str(delta.company_id)

    def test_no_response_contains_another_tenants_identifier(
        self, client: TestClient
    ) -> None:
        """The blunt sweep. Every id belonging to the other company, searched for in
        every response body — this is what would catch a join that forgot its
        predicate and pulled in a name from across the boundary."""
        delta = load_person(DELTA_EMPLOYEE)
        token = token_for(client, DELTA_EMPLOYEE)
        foreign = {str(uid) for uid in _people_in_other_tenant(delta, limit=50)}
        assert foreign, "no foreign ids to search for"

        for path in SELF_ENDPOINTS:
            body = client.get(path, headers=auth(token)).text
            leaked = sorted(uid for uid in foreign if uid in body)
            assert leaked == [], f"{path} leaked foreign identifiers: {leaked[:3]}"


class TestTheSessionCannotBeMovedBetweenTenants:
    def test_a_token_for_one_tenant_is_useless_against_the_other(
        self, client: TestClient
    ) -> None:
        """The signature covers `cid`, so editing the claim breaks the token. This is
        the replay of an *intact* one against the other tenant's records."""
        delta_token = token_for(client, DELTA_EMPLOYEE)
        niletech = load_person(EMPLOYEE)

        assert client.get(
            f"/hr/profiles/{niletech.user_id}", headers=auth(delta_token)
        ).status_code == 404

    def test_a_tampered_tenant_claim_is_refused_outright(self, client: TestClient) -> None:
        """Not 404 but **401**: editing the claim breaks the signature, so the request
        never reaches an authorization decision at all. Stated so the two failure modes
        stay distinguishable in the trail — one is a probe, the other is forgery."""
        import jwt

        from eaios_core.settings import get_settings

        token = token_for(client, DELTA_EMPLOYEE)
        niletech = load_person(EMPLOYEE)

        payload = jwt.decode(token, options={"verify_signature": False})
        payload["cid"] = str(niletech.company_id)
        forged = jwt.encode(payload, "not-the-signing-key", algorithm="HS256")

        assert client.get("/me", headers=auth(forged)).status_code == 401

        # And even re-signed with the *real* key, the session row lives in the other
        # tenant's scope, so it is invisible and the request is refused.
        settings = get_settings()
        resigned = jwt.encode(
            payload, settings.auth.jwt_signing_key.get_secret_value(), algorithm="HS256"
        )
        assert client.get("/me", headers=auth(resigned)).status_code == 401


class TestTheAuditTrailStaysInsideTheBoundary:
    def test_a_cross_tenant_attempt_is_recorded_under_the_actors_company(
        self, client: TestClient
    ) -> None:
        """Research F3. Writing a Delta Retail action into NileTech's trail would be a
        cross-tenant leak in the audit log itself — and FR-030 makes it coherent: at
        layer 1 the other tenant's resource is absent, so there is nothing of theirs to
        attribute."""
        delta = load_person(DELTA_EMPLOYEE)
        niletech = load_person(EMPLOYEE)
        token = token_for(client, DELTA_EMPLOYEE)

        with create_owner_engine().connect() as conn:
            before = int(
                conn.execute(
                    text(
                        "SELECT count(*) FROM audit_logs WHERE company_id = :c"
                    ),
                    {"c": niletech.company_id},
                ).scalar_one()
            )

        client.get(f"/hr/profiles/{niletech.user_id}", headers=auth(token))

        with create_owner_engine().connect() as conn:
            after = int(
                conn.execute(
                    text("SELECT count(*) FROM audit_logs WHERE company_id = :c"),
                    {"c": niletech.company_id},
                ).scalar_one()
            )
            actor_entries = int(
                conn.execute(
                    text(
                        "SELECT count(*) FROM audit_logs"
                        " WHERE company_id = :c AND actor_user_id = :u"
                    ),
                    {"c": delta.company_id, "u": delta.user_id},
                ).scalar_one()
            )

        assert after == before, "a Delta Retail action was recorded under NileTech"
        assert actor_entries > 0, "the attempt was not recorded under the actor's tenant"


class TestTheLayerOneMappingItself:
    """Two independent mechanisms produce the 404, and only one of them was tested.

    Deleting `if decision.tenant_absent:` from `enforce.py` changed **nothing** — every
    test above still passed. The reason is that RLS answers first: the other tenant's
    row is invisible to the caller's scoped session, so `subject_exists()` returns
    False and the router raises not-found before the policy engine is ever consulted.

    That is defence in depth working exactly as Principle I describes — "RLS is a
    backstop and not an excuse for an unscoped query" — and it is the *better* of the
    two orders, because a record the connection cannot see cannot be leaked by a
    forgotten branch.

    But it left the mechanism FR-030 actually documents untested through any route. A
    future endpoint that builds a descriptor without a prior existence check would rely
    entirely on the engine's layer 1, and nothing here would have noticed it was
    broken. These tests exercise that path directly.
    """

    def test_a_foreign_tenant_descriptor_raises_absent_not_denied(self) -> None:
        from eaios_api.authz.enforce import authorize
        from eaios_api.errors import AccessDeniedError, ResourceAbsentError
        from eaios_core.authz import Action, ResourceDescriptor, ResourceKind

        subject = _real_subject(HR)
        foreign = ResourceDescriptor(
            kind=ResourceKind.HR_PROFILE,
            resource_id=str(uuid.uuid4()),
            company_id=uuid.uuid4(),  # a company that is not theirs
            owner_id=uuid.uuid4(),
        )

        with pytest.raises(ResourceAbsentError):
            authorize(subject, _NullSession(), Action.READ, foreign)

        # And specifically *not* the denial exception, which would become a 403 and
        # confirm the record exists.
        try:
            authorize(subject, _NullSession(), Action.READ, foreign)
        except AccessDeniedError:  # pragma: no cover - the assertion below reports it
            pytest.fail("a layer-1 refusal was raised as a denial, which answers 403")
        except ResourceAbsentError:
            pass

    def test_a_same_tenant_denial_still_raises_denied(self) -> None:
        """The pair. Without it, an `authorize` that raised `ResourceAbsentError` for
        *everything* would satisfy the test above and turn every 403 into a 404."""
        from eaios_api.authz.enforce import authorize
        from eaios_api.errors import AccessDeniedError
        from eaios_core.authz import Action, ResourceDescriptor, ResourceKind

        subject = _real_subject(EMPLOYEE)
        # Same tenant, somebody else's record — a real authorization denial.
        same_tenant = ResourceDescriptor(
            kind=ResourceKind.HR_PROFILE,
            resource_id=str(uuid.uuid4()),
            company_id=subject.company_id,
            owner_id=uuid.uuid4(),
        )

        with pytest.raises(AccessDeniedError):
            authorize(subject, _NullSession(), Action.READ, same_tenant)


def _real_subject(persona: str):  # type: ignore[no-untyped-def]
    """An access context for a **seeded** person.

    Fabricated identifiers were tried first and do not work here, for a reason worth
    recording: `authorize` audits every denial, and the audit row carries
    `actor_user_id` with a foreign key to `users`. An invented subject therefore fails
    the insert on every call. `record_out_of_band` swallows that — it must, an audit
    outage cannot become a 500 — so the test still passed *in isolation* and failed
    only when pytest's captured stdout had been closed and the swallowed handler's own
    logging raised.

    Two bugs in one failure: a test whose fixture could never be audited, and a
    failure handler that could itself throw. Using a real person fixes the first; the
    second is fixed in `audit.py`.
    """
    from eaios_core.authz import AccessContext

    person = load_person(persona)
    with create_owner_engine().connect() as conn:
        row = conn.execute(
            text(
                "SELECT u.office_id, u.country, u.employment_type, c.slug"
                " FROM users u JOIN companies c ON c.id = u.company_id WHERE u.id = :u"
            ),
            {"u": person.user_id},
        ).one()
        codes = frozenset(
            r.code
            for r in conn.execute(
                text(
                    "SELECT DISTINCT p.code FROM permissions p"
                    " JOIN role_permissions rp ON rp.permission_id = p.id"
                    " JOIN user_roles ur ON ur.role_id = rp.role_id"
                    " WHERE ur.user_id = :u"
                ),
                {"u": person.user_id},
            )
        )

    return AccessContext(
        company_id=person.company_id,
        company_slug=row.slug,
        user_id=person.user_id,
        session_id=uuid.uuid4(),
        department_id=person.department_id,
        office_id=row.office_id,
        country=row.country,
        employment_type=row.employment_type,
        manager_id=person.manager_id,
        direct_report_ids=frozenset(),
        role_names=frozenset(),
        role_ids=frozenset(),
        permission_codes=codes,
    )


class _NullSession:
    """Absorbs the *allow* audit write, which `authorize` makes on the request's own
    session. Denials go out of band on their own connection and are unaffected.

    What is under test here is which exception `authorize` chooses; a real session
    would add a tenant scope and a transaction to a question that involves neither.
    """

    def add(self, _row: object) -> None:
        return None

    def flush(self) -> None:
        return None


class TestEveryEndpointIsCovered:
    def test_the_endpoint_lists_match_the_running_api(self, client: TestClient) -> None:
        """FR-034 says "across every store the system reads at request time", and the
        practical version of that is: no address this feature adds may be missing from
        the sweeps above. Read from the app's own routes, so a new endpoint fails here
        until somebody classifies it."""
        from eaios_api.main import create_app

        declared = {
            route.path  # type: ignore[attr-defined]
            for route in create_app().routes
            if getattr(route, "path", "").startswith(("/me", "/hr", "/auth"))
        }
        # `/auth/login` and `/auth/logout` are POSTs and are covered by the session and
        # enumeration suites; everything else must appear in one of the lists here.
        covered = {
            *(p.replace("{id}", "{user_id}") for p in SUBJECT_ENDPOINTS),
            *SELF_ENDPOINTS,
            "/auth/login",
            "/auth/logout",
        }

        missing = sorted(declared - covered)
        assert missing == [], (
            "endpoints with no cross-tenant coverage — add them to SUBJECT_ENDPOINTS or"
            f" SELF_ENDPOINTS: {missing}"
        )
