"""Seed configuration: seed value, reference date, and volume profiles.

Volumes come from spec FR-020b. The `smoke` profile exists so CI can exercise the
whole pipeline in seconds; it scales every family down by a fixed factor rather
than changing the shape of the dataset, so a smoke run still has managers with
reports, orders with lines, and both classification extremes.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Literal

from eaios_core.constants import (
    DELTA_RETAIL,
    GENERATOR_VERSION,
    NILETECH,
    REFERENCE_DATE,
    ROOT_SEED,
)

__all__ = ["VOLUMES", "Profile", "SeedConfig", "TenantVolumes"]

Profile = Literal["full", "smoke"]


@dataclass(frozen=True, slots=True)
class TenantVolumes:
    """Target counts for one tenant (spec FR-020b, ±10%)."""

    departments: int
    offices: int
    users: int
    customers: int
    products: int
    orders: int
    leave_requests: int
    training_records: int
    contracts: int
    expenses: int
    public_items: int

    def scaled(self, factor: float) -> TenantVolumes:
        """Shrink proportionally, never below the minimum that keeps shape intact."""

        def s(value: int, floor: int = 1) -> int:
            return max(floor, round(value * factor))

        return TenantVolumes(
            departments=self.departments,  # never scaled — structure, not volume
            offices=self.offices,
            # Floor chosen so the structural invariants still hold: eight
            # departments each need a head, and manager.engineering needs three
            # direct reports (FR-025b, FR-034).
            users=s(self.users, 28),
            customers=s(self.customers, 4),
            products=s(self.products, 4),
            orders=s(self.orders, 12),
            leave_requests=s(self.leave_requests, 6),
            training_records=s(self.training_records, 4),
            contracts=s(self.contracts, 4),
            expenses=s(self.expenses, 6),
            public_items=s(self.public_items, 6),
        )


#: Full-profile targets, straight from the specification's volume table.
VOLUMES: dict[str, TenantVolumes] = {
    NILETECH: TenantVolumes(
        departments=8,
        offices=3,
        users=200,
        customers=120,
        products=25,
        orders=2400,
        leave_requests=1200,
        training_records=400,
        contracts=60,
        expenses=2000,
        public_items=45,
    ),
    DELTA_RETAIL: TenantVolumes(
        departments=5,
        offices=2,
        users=40,
        customers=60,
        products=80,
        orders=1200,
        leave_requests=240,
        training_records=80,
        contracts=25,
        expenses=400,
        public_items=20,
    ),
}

_SMOKE_FACTOR = 0.06


@dataclass(frozen=True, slots=True)
class SeedConfig:
    seed: str = ROOT_SEED
    reference_date: dt.date = REFERENCE_DATE
    profile: Profile = "full"
    generator_version: str = GENERATOR_VERSION
    volumes: dict[str, TenantVolumes] = field(default_factory=lambda: dict(VOLUMES))

    @classmethod
    def build(
        cls,
        *,
        seed: str = ROOT_SEED,
        reference_date: dt.date = REFERENCE_DATE,
        profile: Profile = "full",
    ) -> SeedConfig:
        volumes = dict(VOLUMES)
        if profile == "smoke":
            volumes = {slug: vol.scaled(_SMOKE_FACTOR) for slug, vol in volumes.items()}
        return cls(
            seed=seed, reference_date=reference_date, profile=profile, volumes=volumes
        )

    def for_tenant(self, company_slug: str) -> TenantVolumes:
        return self.volumes[company_slug]
