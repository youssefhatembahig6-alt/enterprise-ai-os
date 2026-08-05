"""Dataset fingerprinting (spec FR-015, FR-015a, research R5).

Turns "the dataset is reproducible" from a claim into a check.

Two properties carry the design. **Order-independence**: row digests are sorted
before being combined, so two runs that insert in different orders but produce the
same content still match — otherwise every future parallelisation would look like a
determinism bug. **Per-family digests**: when a run diverges, the report can name
*which* family drifted, because "fingerprint mismatch" across ~27 tables is close to
undebuggable.
"""

from __future__ import annotations

import datetime as dt
import decimal
import hashlib
import json
import uuid
from collections.abc import Iterable, Mapping
from typing import Any, Final

__all__ = [
    "FINGERPRINT_EXCLUSIONS",
    "canonical_json",
    "family_digest",
    "files_digest",
    "is_excluded",
    "root_fingerprint",
    "row_digest",
]

#: Deliberately minimal (spec FR-015a). An over-broad exclusion silently weakens the
#: guarantee, so the bar for adding one is high.
#:
#: Note what is *not* here: ``created_at`` / ``updated_at``. Rather than exempting
#: them, the generator sets them explicitly from the reference clock, so they are
#: deterministic and get verified like any other field. Excluding them would have
#: left a real class of non-determinism untested.
FINGERPRINT_EXCLUSIONS: Final[frozenset[str]] = frozenset(
    {
        "dataset_manifest",  # contains the fingerprint — including it is self-referential
        "alembic_version",  # migration bookkeeping, not dataset content
        # Written at runtime by anonymous visitors to the public site (spec 002
        # FR-023), never by the generator. Including it would make submitting the
        # contact form change the dataset fingerprint and fail `verify` — a real
        # user action reported as a determinism defect.
        "contact_submissions",
    }
)


def is_excluded(table: str) -> bool:
    return table in FINGERPRINT_EXCLUSIONS


def _encode(value: Any) -> Any:
    """Canonical form for types JSON cannot represent losslessly."""
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dt.datetime):
        return value.isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        # As a string, so scale survives: 18500.00 and 18500.0 are the same number
        # but not the same record.
        return str(value)
    if isinstance(value, bytes):
        return hashlib.sha256(value).hexdigest()
    if isinstance(value, set | frozenset):
        return sorted(str(item) for item in value)
    raise TypeError(f"no canonical encoding for {type(value).__name__}: {value!r}")


def canonical_json(row: Mapping[str, Any]) -> str:
    """Serialize a row so that equal content always yields equal text."""
    return json.dumps(
        dict(row),
        sort_keys=True,
        ensure_ascii=False,  # keep non-ASCII literal, not \\u-escaped
        default=_encode,
        separators=(", ", ": "),
    )


def row_digest(row: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(row).encode("utf-8")).hexdigest()


def family_digest(rows: Iterable[Mapping[str, Any]]) -> str:
    """Digest one entity family, independent of row order.

    Duplicates are preserved rather than collapsed — two identical rows are a data
    bug, and the digest must not hide it.
    """
    digests = sorted(row_digest(row) for row in rows)
    return hashlib.sha256("\n".join(digests).encode("utf-8")).hexdigest()


def files_digest(files: Mapping[str, bytes]) -> str:
    """Digest stored objects by key and content.

    Both matter: changing a file's bytes and moving a file to a different key are
    each real changes to the dataset.
    """
    lines = [
        f"{key}:{hashlib.sha256(content).hexdigest()}" for key, content in sorted(files.items())
    ]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def root_fingerprint(family_digests: Mapping[str, str], files: str) -> str:
    """Combine per-family digests and the files digest into the dataset fingerprint."""
    lines = [f"{name}:{digest}" for name, digest in sorted(family_digests.items())]
    lines.append(f"files:{files}")
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()
