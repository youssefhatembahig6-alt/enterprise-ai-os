"""API settings.

The definitions live in :mod:`eaios_core.settings` because the worker and the seed
generator need identical connection configuration; hosting them here would force the
data generator to import the web service. Re-exported so callers can use either path.
"""

from __future__ import annotations

from eaios_core.settings import (
    MinioSettings,
    PostgresSettings,
    QdrantSettings,
    RedisSettings,
    Settings,
    get_settings,
)

__all__ = [
    "MinioSettings",
    "PostgresSettings",
    "QdrantSettings",
    "RedisSettings",
    "Settings",
    "get_settings",
]
