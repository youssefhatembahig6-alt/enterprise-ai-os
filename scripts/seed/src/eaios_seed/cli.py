"""The `eaios-seed` command line (contracts/seed-cli.md).

Exit codes are a contract, relied on by CI and the Makefile:

* ``0`` success
* ``1`` unexpected error
* ``2`` refused — a precondition was not met (this is a *correct* outcome, and is
  deliberately distinct from ``1`` so CI can tell "the tool protected the
  environment" from "the tool broke")
* ``3`` verification failed
* ``4`` confirmation required but not supplied
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from typing import Annotated

import typer

from eaios_core.constants import REFERENCE_DATE, ROOT_SEED
from eaios_core.db import create_owner_engine
from eaios_core.settings import get_settings

from .audit_checks.structural import run_structural_audit
from .config import SeedConfig
from .loaders.stores import (
    inspect_stores,
    load_objects,
    load_relational,
    provision_qdrant,
    provision_redis,
    reset_all,
)
from .manifest import ManifestBuilder, compute_digests
from .pipeline import build_complete_dataset

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Deterministic synthetic-enterprise generator for two isolated tenants.",
)

EXIT_REFUSED = 2
EXIT_VERIFY_FAILED = 3
EXIT_NEEDS_CONFIRMATION = 4

SeedOpt = Annotated[str, typer.Option("--seed", help="Root seed value.")]
DateOpt = Annotated[str, typer.Option("--reference-date", help="Pinned generation date.")]
ProfileOpt = Annotated[str, typer.Option("--profile", help="'full' or 'smoke'.")]
JsonOpt = Annotated[bool, typer.Option("--json", help="Machine-readable stdout.")]


def _config(seed: str, reference_date: str, profile: str) -> SeedConfig:
    if profile not in ("full", "smoke"):
        typer.echo(f"unknown profile: {profile!r} (expected 'full' or 'smoke')", err=True)
        raise typer.Exit(EXIT_REFUSED)
    return SeedConfig.build(
        seed=seed,
        reference_date=dt.date.fromisoformat(reference_date),
        profile=profile,  # type: ignore[arg-type]
    )


@app.command()
def seed(
    seed: SeedOpt = ROOT_SEED,
    reference_date: DateOpt = REFERENCE_DATE.isoformat(),
    profile: ProfileOpt = "full",
    json_output: JsonOpt = False,
) -> None:
    """Populate an empty environment. Refuses if anything is already present."""
    config = _config(seed, reference_date, profile)
    settings = get_settings()

    counts = inspect_stores(settings)
    if not counts.is_empty:
        typer.echo("REFUSED: environment is not empty.", err=True)
        typer.echo(counts.describe(), err=True)
        typer.echo("To destroy and regenerate, run:  make reset", err=True)
        raise typer.Exit(EXIT_REFUSED)

    builder = ManifestBuilder(config)
    typer.echo("Generating…", err=True)
    dataset, ctx = build_complete_dataset(config)

    manifest_row = builder.build(dataset, ctx.company_ids, complete=True)

    typer.echo(f"Loading {dataset.total_rows:,} rows…", err=True)
    load_relational(dataset, manifest_row, create_owner_engine(settings))

    typer.echo(f"Uploading {len(dataset.files)} documents…", err=True)
    load_objects(dataset, settings)

    typer.echo("Provisioning vector store…", err=True)
    provision_qdrant(settings)
    provision_redis(settings)

    payload = {
        "root_fingerprint": manifest_row["root_fingerprint"],
        "reference_date": config.reference_date.isoformat(),
        "root_seed": config.seed,
        "profile": config.profile,
        "rows": dataset.total_rows,
        "files": len(dataset.files),
        "entity_counts": manifest_row["entity_counts"],
    }
    if json_output:
        typer.echo(json.dumps(payload, indent=2, default=str))
    else:
        typer.echo("")
        typer.echo(f"  rows        {dataset.total_rows:,}")
        typer.echo(f"  documents   {len(dataset.files)}")
        typer.echo(f"  fingerprint {manifest_row['root_fingerprint']}")


@app.command()
def reset(
    yes: Annotated[bool, typer.Option("--yes", help="Required. Confirms destruction.")] = False,
    seed: SeedOpt = ROOT_SEED,
    reference_date: DateOpt = REFERENCE_DATE.isoformat(),
    profile: ProfileOpt = "full",
) -> None:
    """Destroy all local data and regenerate. The only destructive command."""
    settings = get_settings()

    # Three gates, all required (spec FR-014a, Constitution VII).
    if not yes:
        typer.echo("reset requires --yes; it destroys every row, object, and vector.", err=True)
        raise typer.Exit(EXIT_NEEDS_CONFIRMATION)

    if not settings.is_local:
        typer.echo(
            f"REFUSED: environment is {settings.environment!r}, not 'local'.", err=True
        )
        raise typer.Exit(EXIT_REFUSED)

    host = settings.postgres.host
    if host not in {"localhost", "127.0.0.1", "postgres"}:
        typer.echo(f"REFUSED: database host {host!r} is not local.", err=True)
        raise typer.Exit(EXIT_REFUSED)

    counts = inspect_stores(settings)
    typer.echo("About to destroy:", err=True)
    typer.echo(counts.describe(), err=True)

    reset_all(settings)
    typer.echo("Destroyed. Regenerating…", err=True)

    seed_config = _config(seed, reference_date, profile)
    builder = ManifestBuilder(seed_config)
    dataset, org = build_complete_dataset(seed_config)
    manifest_row = builder.build(dataset, org.company_ids, complete=True)
    load_relational(dataset, manifest_row, create_owner_engine(settings))
    load_objects(dataset, settings)
    provision_qdrant(settings)
    provision_redis(settings)

    typer.echo("")
    typer.echo(f"  rows        {dataset.total_rows:,}")
    typer.echo(f"  fingerprint {manifest_row['root_fingerprint']}")


@app.command()
def fingerprint(
    seed: SeedOpt = ROOT_SEED,
    reference_date: DateOpt = REFERENCE_DATE.isoformat(),
    profile: ProfileOpt = "full",
    json_output: JsonOpt = False,
) -> None:
    """Recompute the fingerprint from generated data without touching any store."""
    config = _config(seed, reference_date, profile)
    dataset, ctx = build_complete_dataset(config)
    families, files_digest, root = compute_digests(dataset, ctx.company_ids)

    if json_output:
        typer.echo(json.dumps({"root_fingerprint": root, "families": families}, indent=2))
    else:
        typer.echo(root)


@app.command()
def docs(check: bool = typer.Option(False, "--check", help="Fail if the committed docs differ.")) -> None:
    """Render docs/personas.md and docs/dataset.md from the generator.

    `--check` compares without writing, which is what CI and the freshness test
    use: documentation that silently drifts from the dataset it describes is a
    defect, not an inconvenience (FR-048).
    """
    from pathlib import Path

    from .docgen import render_all

    root = Path(__file__).resolve().parents[4]
    stale: list[str] = []
    for relative, content in render_all().items():
        path = root / relative
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        if current == content:
            continue
        if check:
            stale.append(relative)
        else:
            path.write_text(content, encoding="utf-8", newline="\n")
            typer.echo(f"wrote {relative}")

    if check and stale:
        typer.echo(
            "stale documentation: " + ", ".join(stale) + "\n  regenerate with `make docs`",
            err=True,
        )
        raise typer.Exit(EXIT_VERIFY_FAILED)
    if check:
        typer.echo("OK  documentation matches the generated dataset")
    elif not stale:
        typer.echo("documentation already up to date")


@app.command()
def verify(
    seed: SeedOpt = ROOT_SEED,
    reference_date: DateOpt = REFERENCE_DATE.isoformat(),
    profile: ProfileOpt = "full",
) -> None:
    """Compare the stored manifest against a freshly recomputed fingerprint."""
    from sqlalchemy import text

    config = _config(seed, reference_date, profile)
    settings = get_settings()
    engine = create_owner_engine(settings)

    with engine.connect() as conn:
        stored = conn.execute(
            text(
                "SELECT root_fingerprint, family_digests, completed_at, profile"
                " FROM dataset_manifest LIMIT 1"
            )
        ).first()

    if stored is None:
        typer.echo("environment has not been seeded", err=True)
        raise typer.Exit(EXIT_VERIFY_FAILED)

    if stored.completed_at is None:
        typer.echo(
            "environment incomplete: the seed did not finish (no completion marker)", err=True
        )
        raise typer.Exit(EXIT_VERIFY_FAILED)

    # Recompute against the profile the environment was actually seeded with. Asking
    # the caller to remember it invites a false mismatch — comparing a full-profile
    # regeneration against a smoke-seeded database reports 48 diverging families and
    # looks exactly like a real determinism failure.
    if stored.profile != config.profile:
        typer.echo(
            f"note: environment was seeded with profile {stored.profile!r};"
            f" verifying against that rather than {config.profile!r}",
            err=True,
        )
        config = _config(seed, reference_date, stored.profile)

    dataset, ctx = build_complete_dataset(config)
    families, _files, root = compute_digests(dataset, ctx.company_ids)

    typer.echo("OK   manifest complete")

    # Structural audit runs alongside the fingerprint (FR-044). A dataset can be
    # perfectly reproducible and still be wrong — an unscoped table or a
    # cross-tenant reference would reproduce exactly, every time.
    audit = run_structural_audit(engine)
    typer.echo(audit.describe(), err=not audit.ok)
    if not audit.ok:
        raise typer.Exit(EXIT_VERIFY_FAILED)

    if root == stored.root_fingerprint:
        typer.echo(f"OK   fingerprint matches  {root}")
        return

    typer.echo("FAIL fingerprint mismatch", err=True)
    stored_families = stored.family_digests or {}
    diverged = [
        name
        for name in sorted(set(families) | set(stored_families))
        if families.get(name) != stored_families.get(name)
    ]
    for name in diverged:
        typer.echo(
            f"    {name:32s} expected {str(stored_families.get(name))[:8]}…"
            f" got {str(families.get(name))[:8]}…",
            err=True,
        )
    typer.echo(f"  {len(families) - len(diverged)} other families match.", err=True)
    raise typer.Exit(EXIT_VERIFY_FAILED)


def main() -> None:
    app()


if __name__ == "__main__":
    sys.exit(app())
