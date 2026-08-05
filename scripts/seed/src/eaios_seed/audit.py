"""Audit entries written by the seed itself (spec FR-043, Constitution X).

The generator is a consequential operation on company data, so it records what it
did — same as any other actor. These rows are also the first proof that the
append-only trigger works against real traffic rather than only in a test.
"""

from __future__ import annotations

from typing import Any

from eaios_core.clock import reference_datetime
from eaios_core.ids import derive

from .config import SeedConfig
from .dataset import Dataset

__all__ = ["record_seed_audit"]


def record_seed_audit(
    dataset: Dataset, config: SeedConfig, company_ids: dict[str, Any]
) -> None:
    now = reference_datetime()
    for slug, company_id in sorted(company_ids.items()):
        counts = dataset.counts_by_company(company_ids)
        own = {key: value for key, value in counts.items() if key.startswith(f"{slug}.")}
        dataset.add(
            "audit_logs",
            {
                "id": derive("audit_log", slug, "dataset.create", seed=config.seed),
                "company_id": company_id,
                "actor_user_id": None,
                "actor_type": "SEED",
                "action": "dataset.create",
                "resource_type": "company",
                "resource_id": slug,
                "decision": "NA",
                "reason": (
                    f"Synthetic dataset generated with seed {config.seed}, "
                    f"reference date {config.reference_date.isoformat()}, "
                    f"profile {config.profile}."
                ),
                "sources": sorted(own),
                "created_at": now,
            },
        )
