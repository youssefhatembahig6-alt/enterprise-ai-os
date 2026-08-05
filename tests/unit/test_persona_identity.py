"""Persona identities are frozen (spec FR-025c, SC-014).

FR-025c: persona identifiers, email addresses, department assignments, and reporting
relationships MUST NOT change between seed runs or between generator versions unless
the change is deliberate and documented. Acceptance tests, the evaluation set, and
the defense demo script all reference these people by name.

Nothing enforced it. `test_ids.py` pins the derivation *function* — that
`derive("user", "niletech", "employee-0042")` is stable — not which user a persona
resolves to. `test_scenario_readiness.py` pins company and department for six of the
ten and never id, email, name, or manager. The only remaining control was the
whole-dataset fingerprint, which moves for any row in any table and gets re-pinned
deliberately whenever a dataset change is intended: it was re-pinned twice in a
single session, and would have blessed a persona reassignment in silence.

**Both profiles are pinned, and they differ.** Persona assignment draws from the
generated user population, which `smoke` scales down, so `employee.engineering` is a
different person in each. That is legitimate — but it is also what made a
smoke-seeded database look like proof that the full-profile documentation was wrong.
Recording both removes the ambiguity.

A deliberate change means updating this table in the same commit, which is exactly
the documentation FR-025c asks for.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from eaios_seed.config import SeedConfig
from eaios_seed.pipeline import build_complete_dataset

pytestmark = pytest.mark.unit

PROFILES = ("full", "smoke")


@dataclass(frozen=True, slots=True)
class Persona:
    company: str
    department: str
    country: str
    email: str
    full_name: str
    manager_email: str | None


#: persona_key -> frozen identity, per profile.
FROZEN: dict[str, dict[str, Persona]] = {
    "full": {
        "admin.company": Persona(
            "niletech", "Executive Management", "AE",
            "sultan.alhammadi@niletech.example", "Sultan AlHammadi", None,
        ),
        "auditor.readonly": Persona(
            "niletech", "Operations", "EG",
            "hassan.zaki@niletech.example", "Hassan Zaki",
            "sultan.alhammadi@niletech.example",
        ),
        "comms.sender": Persona(
            "niletech", "Customer Support", "EG",
            "karim.nasr@niletech.example", "Karim Nasr",
            "sultan.alhammadi@niletech.example",
        ),
        "employee.delta": Persona(
            "delta-retail", "Sales", "EG",
            "dina.shafik@deltaretail.example", "Dina Shafik",
            "yasmin.bakr@deltaretail.example",
        ),
        "employee.engineering": Persona(
            "niletech", "Engineering", "AE",
            "majid.alzaabi@niletech.example", "Majid AlZaabi",
            "tarek.darwish@niletech.example",
        ),
        "employee.sales": Persona(
            "niletech", "Sales", "EG",
            "sherif.fahmy3@niletech.example", "Sherif Fahmy",
            "sultan.alhammadi@niletech.example",
        ),
        "finance.analyst": Persona(
            "niletech", "Finance", "EG",
            "salma.elgendy@niletech.example", "Salma ElGendy",
            "sultan.alhammadi@niletech.example",
        ),
        "hr.generalist": Persona(
            "niletech", "HR", "EG",
            "sherif.hafez2@niletech.example", "Sherif Hafez",
            "sultan.alhammadi@niletech.example",
        ),
        "legal.counsel": Persona(
            "niletech", "Legal", "AE",
            "sultan.alsuwaidi@niletech.example", "Sultan AlSuwaidi",
            "sultan.alhammadi@niletech.example",
        ),
        "manager.engineering": Persona(
            "niletech", "Engineering", "EG",
            "tarek.darwish@niletech.example", "Tarek Darwish",
            "sultan.alhammadi@niletech.example",
        ),
    },
    "smoke": {
        "admin.company": Persona(
            "niletech", "Executive Management", "AE",
            "sultan.alhammadi@niletech.example", "Sultan AlHammadi", None,
        ),
        "auditor.readonly": Persona(
            "niletech", "Operations", "EG",
            "nadia.fahmy@niletech.example", "Nadia Fahmy",
            "sultan.alhammadi@niletech.example",
        ),
        "comms.sender": Persona(
            "niletech", "Customer Support", "EG",
            "karim.nasr@niletech.example", "Karim Nasr",
            "sultan.alhammadi@niletech.example",
        ),
        "employee.delta": Persona(
            "delta-retail", "Sales", "EG",
            "omar.adel@deltaretail.example", "Omar Adel",
            "yasmin.bakr@deltaretail.example",
        ),
        "employee.engineering": Persona(
            "niletech", "Engineering", "AE",
            "latifa.alnuaimi@niletech.example", "Latifa AlNuaimi",
            "farida.mansour@niletech.example",
        ),
        "employee.sales": Persona(
            "niletech", "Sales", "AE",
            "aisha.alshamsi@niletech.example", "Aisha AlShamsi",
            "sultan.alhammadi@niletech.example",
        ),
        "finance.analyst": Persona(
            "niletech", "Finance", "EG",
            "amir.adel@niletech.example", "Amir Adel",
            "sultan.alhammadi@niletech.example",
        ),
        "hr.generalist": Persona(
            "niletech", "HR", "EG",
            "mariam.lotfy@niletech.example", "Mariam Lotfy",
            "sultan.alhammadi@niletech.example",
        ),
        "legal.counsel": Persona(
            "niletech", "Legal", "EG",
            "hassan.lotfy@niletech.example", "Hassan Lotfy",
            "sultan.alhammadi@niletech.example",
        ),
        "manager.engineering": Persona(
            "niletech", "Engineering", "EG",
            "farida.mansour@niletech.example", "Farida Mansour",
            "sultan.alhammadi@niletech.example",
        ),
    },
}


@pytest.fixture(scope="module")
def actual() -> dict[str, dict[str, Persona]]:
    """persona_key -> observed identity, per profile."""
    out: dict[str, dict[str, Persona]] = {}
    for profile in PROFILES:
        dataset, _ctx = build_complete_dataset(SeedConfig.build(profile=profile))  # type: ignore[arg-type]
        users = {user["id"]: user for user in dataset.rows["users"]}
        departments = {row["id"]: row["name"] for row in dataset.rows["departments"]}
        companies = {row["id"]: row["slug"] for row in dataset.rows["companies"]}
        out[profile] = {
            user["persona_key"]: Persona(
                company=companies[user["company_id"]],
                department=departments[user["department_id"]],
                country=user["country"],
                email=user["email"],
                full_name=user["full_name"],
                manager_email=(
                    users[user["manager_id"]]["email"] if user.get("manager_id") else None
                ),
            )
            for user in dataset.rows["users"]
            if user.get("persona_key")
        }
    return out


class TestFrozenIdentities:
    @pytest.mark.parametrize("profile", PROFILES)
    def test_the_persona_set_is_exactly_the_frozen_one(
        self, actual: dict[str, dict[str, Persona]], profile: str
    ) -> None:
        assert set(actual[profile]) == set(FROZEN[profile])

    @pytest.mark.parametrize("profile", PROFILES)
    def test_every_persona_identity_is_unchanged(
        self, actual: dict[str, dict[str, Persona]], profile: str
    ) -> None:
        drifted = {
            key: (FROZEN[profile][key], observed)
            for key, observed in sorted(actual[profile].items())
            if FROZEN[profile][key] != observed
        }
        assert drifted == {}, (
            "persona identities moved (FR-025c). If deliberate, update FROZEN in this "
            f"file in the same commit and regenerate docs/personas.md:\n{drifted}"
        )


class TestInvariantsHoldAcrossProfiles:
    """Placement is profile-independent even though the people are not — these are
    the properties the access-control scenarios actually depend on."""

    @pytest.mark.parametrize("profile", PROFILES)
    def test_placement_is_identical_across_profiles(
        self, actual: dict[str, dict[str, Persona]], profile: str
    ) -> None:
        for key, persona in actual[profile].items():
            reference = actual["full"][key]
            assert (persona.company, persona.department) == (
                reference.company,
                reference.department,
            ), f"{key} sits in a different department at the {profile} profile"

    @pytest.mark.parametrize("profile", PROFILES)
    def test_the_engineering_manager_manages_the_engineering_employee(
        self, actual: dict[str, dict[str, Persona]], profile: str
    ) -> None:
        """The blueprint's manager scenario collapses if this inverts, and it has
        inverted before."""
        personas = actual[profile]
        assert (
            personas["employee.engineering"].manager_email
            == personas["manager.engineering"].email
        )

    @pytest.mark.parametrize("profile", PROFILES)
    def test_only_the_company_admin_is_manager_less(
        self, actual: dict[str, dict[str, Persona]], profile: str
    ) -> None:
        rootless = [
            key for key, persona in actual[profile].items() if persona.manager_email is None
        ]
        assert rootless == ["admin.company"]

    @pytest.mark.parametrize("profile", PROFILES)
    def test_emails_are_unique(
        self, actual: dict[str, dict[str, Persona]], profile: str
    ) -> None:
        emails = [persona.email for persona in actual[profile].values()]
        assert len(set(emails)) == len(emails)

    @pytest.mark.parametrize("profile", PROFILES)
    def test_the_delta_persona_is_the_only_one_outside_niletech(
        self, actual: dict[str, dict[str, Persona]], profile: str
    ) -> None:
        elsewhere = {
            key for key, persona in actual[profile].items() if persona.company != "niletech"
        }
        assert elsewhere == {"employee.delta"}


class TestTheFreezeCanFail:
    def test_the_two_profiles_really_do_differ(self) -> None:
        """If they were identical, pinning both would be redundant — and the
        cross-profile confusion this file documents could not have happened."""
        assert FROZEN["full"] != FROZEN["smoke"]

    def test_a_changed_field_is_detected(self) -> None:
        original = FROZEN["full"]["manager.engineering"]
        moved = Persona(
            company=original.company,
            department=original.department,
            country=original.country,
            email="someone.else@niletech.example",
            full_name=original.full_name,
            manager_email=original.manager_email,
        )
        assert moved != original
