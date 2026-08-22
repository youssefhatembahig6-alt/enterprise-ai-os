"""Ingestion-side checks that run before any point is written."""

from __future__ import annotations

from .preflight import EXPECTED_DIMENSION, PreflightError, preflight, required_indexes

__all__ = ["EXPECTED_DIMENSION", "PreflightError", "preflight", "required_indexes"]
