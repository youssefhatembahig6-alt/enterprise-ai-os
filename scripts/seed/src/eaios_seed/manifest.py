"""Dataset manifest and fingerprinting (spec FR-015, FR-016, FR-014b).

The completion marker is the important detail. ``completed_at`` is written last, in
the same transaction as the fingerprint, so an interrupted seed leaves an
environment that reads as *incomplete* rather than as complete-but-wrong. That is
what lets `verify` distinguish "the seed died" from "the data drifted" — two
failures that need very different responses.

This module is exempt from the wall-clock ban: ``started_at`` and ``completed_at``
are genuine run metadata, deliberately excluded from the fingerprint.
"""

from __future__ import annotations

import datetime as dt
import platform
from typing import Any

from eaios_core import fingerprint as fp
from eaios_core.constants import MANIFEST_SCHEMA_VERSION
from eaios_core.ids import derive_global

from .config import SeedConfig
from .dataset import Dataset

__all__ = ["ManifestBuilder", "compute_digests", "utc_now"]


def utc_now() -> dt.datetime:
    """Wall clock, used only for run metadata — never for generated content."""
    return dt.datetime.now(tz=dt.UTC)


def compute_digests(
    dataset: Dataset, company_ids: dict[str, Any]
) -> tuple[dict[str, str], str, str]:
    """Return ``(family_digests, files_digest, root_fingerprint)``.

    Families are keyed '{slug}.{table}' so a mismatch names which tenant's which
    table drifted, rather than reporting one opaque difference across 33 tables.
    """
    by_id = {value: slug for slug, value in company_ids.items()}
    families: dict[str, list[dict[str, Any]]] = {}

    for table, rows in dataset.rows.items():
        if fp.is_excluded(table) or not rows:
            continue
        if "company_id" not in rows[0]:
            families[f"global.{table}"] = list(rows)
            continue
        for row in rows:
            slug = by_id.get(row["company_id"], "unknown")
            families.setdefault(f"{slug}.{table}", []).append(row)

    family_digests = {name: fp.family_digest(rows) for name, rows in sorted(families.items())}
    files_digest = fp.files_digest(dataset.files)
    return family_digests, files_digest, fp.root_fingerprint(family_digests, files_digest)


class ManifestBuilder:
    """Assembles the manifest row. The completion marker is applied separately."""

    def __init__(self, config: SeedConfig) -> None:
        self.config = config
        self.started_at = utc_now()

    def build(
        self, dataset: Dataset, company_ids: dict[str, Any], *, complete: bool
    ) -> dict[str, Any]:
        family_digests, _files_digest, root = compute_digests(dataset, company_ids)
        finished = utc_now() if complete else None
        return {
            "id": derive_global("dataset_manifest", "singleton", seed=self.config.seed),
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "root_seed": self.config.seed,
            "reference_date": self.config.reference_date,
            "generator_version": self.config.generator_version,
            "profile": self.config.profile,
            "entity_counts": dict(dataset.counts_by_company(company_ids)),
            "family_digests": family_digests,
            "root_fingerprint": root,
            "fingerprint_exclusions": sorted(fp.FINGERPRINT_EXCLUSIONS),
            "started_at": self.started_at,
            "completed_at": finished,
            "duration_seconds": (
                (finished - self.started_at).total_seconds() if finished else None
            ),
            "host_platform": platform.system().lower(),
        }
