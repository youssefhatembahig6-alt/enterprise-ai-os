"""Distinctive per-tenant marker phrases (spec FR-023).

A cross-tenant leak is only detectable if the leaked text is unmistakably
identifiable. These phrases are deliberately unusual so a substring search can
never produce a false positive from ordinary generated prose, and they are seeded
into each tenant's documents so the isolation probe has something concrete to hunt
for in both directions.
"""

from __future__ import annotations

from eaios_core.constants import DELTA_RETAIL, NILETECH

__all__ = ["MARKERS", "all_markers", "foreign_markers", "markers_for"]

MARKERS: dict[str, tuple[str, ...]] = {
    NILETECH: (
        "ZAPHOD-CATARACT-LEDGER",
        "obsidian pelican provisioning clause",
        "Nile Blueprint Reference NT-77Q",
    ),
    DELTA_RETAIL: (
        "QUIXOTIC-BASALT-MANIFEST",
        "vermilion armadillo restocking clause",
        "Delta Handling Reference DR-42X",
    ),
}


def markers_for(company_slug: str) -> tuple[str, ...]:
    return MARKERS[company_slug]


def foreign_markers(company_slug: str) -> tuple[str, ...]:
    """Markers that must never appear in this tenant's content."""
    return tuple(
        phrase
        for slug, phrases in MARKERS.items()
        if slug != company_slug
        for phrase in phrases
    )


def all_markers() -> tuple[str, ...]:
    return tuple(phrase for phrases in MARKERS.values() for phrase in phrases)
