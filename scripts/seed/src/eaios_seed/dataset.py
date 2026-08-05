"""In-memory dataset accumulated by the generators.

Generators emit plain row dicts keyed by table name rather than ORM objects. That
keeps two things simple: the loader can bulk-insert with SQLAlchemy Core, and the
fingerprint can digest rows directly without reflection. Files are held alongside
so the object-storage digest covers exactly what gets uploaded.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

__all__ = ["Dataset"]


@dataclass
class Dataset:
    #: table name -> rows, in insertion order (FK-safe)
    rows: dict[str, list[dict[str, Any]]] = field(
        default_factory=lambda: defaultdict(list)
    )
    #: storage key -> file bytes
    files: dict[str, bytes] = field(default_factory=dict)

    def add(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        self.rows[table].append(row)
        return row

    def extend(self, table: str, rows: list[dict[str, Any]]) -> None:
        self.rows[table].extend(rows)

    def add_file(self, key: str, content: bytes) -> None:
        if key in self.files:
            raise ValueError(f"duplicate storage key: {key}")
        self.files[key] = content

    def count(self, table: str) -> int:
        return len(self.rows.get(table, []))

    def counts_by_company(self, company_ids: dict[str, Any]) -> dict[str, int]:
        """Per-family counts keyed '{slug}.{table}', plus 'global.{table}'."""
        by_id = {value: slug for slug, value in company_ids.items()}
        counts: dict[str, int] = {}
        for table, rows in self.rows.items():
            if not rows:
                continue
            if "company_id" not in rows[0]:
                counts[f"global.{table}"] = len(rows)
                continue
            per: dict[str, int] = defaultdict(int)
            for row in rows:
                per[by_id.get(row["company_id"], "unknown")] += 1
            for slug, total in per.items():
                counts[f"{slug}.{table}"] = total
        counts["files.documents"] = len(self.files)
        return dict(sorted(counts.items()))

    @property
    def total_rows(self) -> int:
        return sum(len(rows) for rows in self.rows.values())
