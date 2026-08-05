"""Deterministic identifier derivation (spec FR-011, research R1).

Identifiers are the load-bearing part of the determinism guarantee. If IDs shift,
every foreign key shifts with them and the whole dataset fingerprint changes. These
tests exist to make an accidental change to the namespace or key format impossible
to land silently.
"""

from __future__ import annotations

import uuid

import pytest

from eaios_core import ids
from eaios_core.constants import ROOT_SEED

pytestmark = pytest.mark.unit


class TestDerivationIsPure:
    def test_same_inputs_produce_same_id(self) -> None:
        a = ids.derive("user", "niletech", "employee-0042")
        b = ids.derive("user", "niletech", "employee-0042")
        assert a == b

    def test_id_is_a_uuid5(self) -> None:
        value = ids.derive("user", "niletech", "employee-0042")
        assert isinstance(value, uuid.UUID)
        assert value.version == 5

    @pytest.mark.parametrize(
        ("entity", "company", "key"),
        [
            ("user", "niletech", "employee-0043"),
            ("user", "delta-retail", "employee-0042"),
            ("order", "niletech", "employee-0042"),
        ],
    )
    def test_changing_any_component_changes_the_id(
        self, entity: str, company: str, key: str
    ) -> None:
        baseline = ids.derive("user", "niletech", "employee-0042")
        assert ids.derive(entity, company, key) != baseline

    def test_different_seed_produces_a_different_dataset(self) -> None:
        assert ids.derive("user", "niletech", "employee-0042", seed="other") != ids.derive(
            "user", "niletech", "employee-0042"
        )


class TestTenantSeparation:
    def test_the_same_natural_key_in_two_tenants_never_collides(self) -> None:
        """Both companies number their employees from 1; the IDs must still differ."""
        seen = {
            ids.derive("user", "niletech", f"employee-{n:04d}") for n in range(1, 200)
        } | {ids.derive("user", "delta-retail", f"employee-{n:04d}") for n in range(1, 200)}
        assert len(seen) == 398

    def test_global_entities_derive_without_a_company(self) -> None:
        a = ids.derive_global("permission", "hr:read_all")
        assert a == ids.derive_global("permission", "hr:read_all")
        # A global id must not be reachable by passing "global" as a company slug,
        # or the two namespaces could be confused.
        assert a != ids.derive("permission", "global", "hr:read_all")


class TestOrderIndependence:
    def test_derivation_does_not_depend_on_call_order(self) -> None:
        forward = [ids.derive("user", "niletech", f"employee-{n:04d}") for n in range(1, 50)]
        backward = [
            ids.derive("user", "niletech", f"employee-{n:04d}") for n in reversed(range(1, 50))
        ]
        assert forward == list(reversed(backward))


class TestFrozenFixtures:
    """Regression guard.

    These values were computed once from the committed ROOT_SEED. They are not
    magic: they are a tripwire. If a refactor changes the namespace constant or the
    URN format, every identifier in the dataset moves and this test says so
    immediately instead of the failure surfacing as an unexplained fingerprint
    mismatch three phases later.
    """

    def test_root_seed_is_the_committed_default(self) -> None:
        # spec FR-012c — the default seed is fixed and committed.
        assert ROOT_SEED == "20260630"

    def test_frozen_identifiers_are_unchanged(self) -> None:
        assert str(ids.derive("company", "niletech", "niletech")) == (
            "91fc82ba-df24-510d-9fc4-8922fd2c55fa"
        )
        assert str(ids.derive("user", "niletech", "employee-0042")) == (
            "9c4cc56d-2512-5fa5-8f05-9bf498d3bcd3"
        )
        assert str(ids.derive_global("permission", "hr:read_all")) == (
            "7ac4fdde-9397-50cc-85b0-0d1f1d9b4a4c"
        )
