"""Dataset provenance endpoint.

Returns 404 when the environment has never been seeded, and reports
``is_complete: false`` when a seed was interrupted — the completion marker is what
distinguishes "incomplete" from "wrong" (spec FR-014b).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from eaios_core.db import create_app_engine, session_scope
from eaios_core.models import DatasetManifest
from eaios_core.settings import Settings, get_settings

from .schemas import DatasetManifestResponse

router = APIRouter(prefix="/dataset", tags=["dataset"])


@router.get(
    "/manifest",
    response_model=DatasetManifestResponse,
    summary="Dataset provenance and completion state",
    responses={404: {"description": "Environment has not been seeded"}},
)
def dataset_manifest(settings: Settings = Depends(get_settings)) -> DatasetManifestResponse:
    engine = create_app_engine(settings)
    with session_scope(engine) as session:
        manifest = session.scalar(select(DatasetManifest).limit(1))

    if manifest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Environment has not been seeded. Run `make seed`.",
        )

    return DatasetManifestResponse(
        root_seed=manifest.root_seed,
        reference_date=manifest.reference_date,
        generator_version=manifest.generator_version,
        profile=manifest.profile,
        entity_counts=manifest.entity_counts,
        family_digests=manifest.family_digests,
        root_fingerprint=manifest.root_fingerprint,
        started_at=manifest.started_at,
        completed_at=manifest.completed_at,
        is_complete=manifest.completed_at is not None,
    )
