"""Structural tenancy audit over a live database (spec FR-044, SC-003).

Three classes of violation, all reported together so one run tells the whole story:

* a tenant-owned table missing its ``company_id``;
* an allowlisted global table that has *gained* one — subtler, and it means the
  shared permission vocabulary has begun to diverge between tenants;
* a foreign key whose target belongs to a different company.

The cross-tenant reference check is generated from the live foreign-key catalogue
rather than a hand-written list, so a relationship added later is covered without
anyone remembering to extend this file.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import Engine, text

from eaios_core.tenancy import GLOBAL_ENTITIES, audit_table_scoping

__all__ = ["AuditReport", "run_structural_audit"]


@dataclass
class AuditReport:
    scoping: list[str] = field(default_factory=list)
    cross_tenant: list[str] = field(default_factory=list)
    orphans: list[str] = field(default_factory=list)

    @property
    def violations(self) -> list[str]:
        return [*self.scoping, *self.cross_tenant, *self.orphans]

    @property
    def ok(self) -> bool:
        return not self.violations

    def describe(self) -> str:
        if self.ok:
            return "OK   structural audit: no violations"
        lines = ["FAIL structural audit:"]
        lines += [f"     {item}" for item in self.violations]
        return "\n".join(lines)


def _application_tables(engine: Engine) -> list[str]:
    with engine.connect() as conn:
        return [
            row[0]
            for row in conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables"
                    " WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
                    " ORDER BY table_name"
                )
            )
        ]


def _has_company_id(engine: Engine, tables: list[str]) -> dict[str, bool]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT table_name FROM information_schema.columns"
                " WHERE table_schema = 'public' AND column_name = 'company_id'"
            )
        ).all()
    with_column = {row[0] for row in rows}
    return {table: table in with_column for table in tables}


def _tenant_foreign_keys(engine: Engine) -> list[tuple[str, str, str]]:
    """Return (source_table, source_column, target_table) for FKs worth checking.

    Only relationships between two tenant-owned tables can cross a boundary, so
    references into the global allowlist are excluded rather than reported.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT tc.table_name, kcu.column_name, ccu.table_name AS target
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON kcu.constraint_name = tc.constraint_name
                JOIN information_schema.constraint_column_usage ccu
                  ON ccu.constraint_name = tc.constraint_name
                WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'
                ORDER BY tc.table_name, kcu.column_name
                """
            )
        ).all()

    return [
        (source, column, target)
        for source, column, target in rows
        if source not in GLOBAL_ENTITIES
        and target not in GLOBAL_ENTITIES
        and column != "company_id"  # the tenant column itself points at companies
        and target != "companies"
    ]


def run_structural_audit(engine: Engine) -> AuditReport:
    report = AuditReport()
    tables = _application_tables(engine)

    report.scoping = audit_table_scoping(_has_company_id(engine, tables))

    with engine.connect() as conn:
        for source, column, target in _tenant_foreign_keys(engine):
            crossing = conn.execute(
                text(
                    f"SELECT count(*) FROM {source} s JOIN {target} t ON t.id = s.{column}"
                    f" WHERE t.company_id <> s.company_id"
                )
            ).scalar_one()
            if crossing:
                report.cross_tenant.append(
                    f"{source}.{column} -> {target}: {crossing} row(s) cross a company boundary"
                )

            orphaned = conn.execute(
                text(
                    f"SELECT count(*) FROM {source} s LEFT JOIN {target} t ON t.id = s.{column}"
                    f" WHERE s.{column} IS NOT NULL AND t.id IS NULL"
                )
            ).scalar_one()
            if orphaned:
                report.orphans.append(
                    f"{source}.{column} -> {target}: {orphaned} orphaned reference(s)"
                )

    return report
