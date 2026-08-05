"""Tenant-namespaced object-storage and cache keys (spec FR-039, FR-040).

These builders are the only sanctioned way to address a stored object or a cache
entry. They validate the tenant up front and refuse to produce an unattributable
key, so a cross-tenant collision is impossible to construct rather than merely
detectable afterwards.
"""

from __future__ import annotations

import hashlib
import re
from typing import Final

from .classification import Classification
from .tenancy import require_company

__all__ = [
    "RATE_LIMIT_PREFIX",
    "cache_key",
    "cache_namespace",
    "company_of_storage_key",
    "rate_limit_key",
    "rate_limit_namespace",
    "storage_key",
]

_CACHE_PREFIX: Final[str] = "eaios:cache"

#: Prefix for the anonymous write bounds (spec 002 FR-024d, FR-047b).
#:
#: Declared here rather than in the API package for one reason: `reset_all` has to
#: delete these keys, and the seed must not import from `apps/api`. Key *patterns*
#: belong in one place precisely so the code that writes them and the code that
#: clears them cannot disagree — which they did, silently, until a convergence pass
#: noticed that `make reset` promises to destroy every cache entry and left these
#: behind for an hour.
RATE_LIMIT_PREFIX: Final[str] = "eaios:ratelimit"
_SAFE_FILENAME: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _require_safe_filename(filename: str) -> str:
    """Reject anything that could escape its prefix or be unattributable."""
    if not filename or not filename.strip():
        raise ValueError("filename must not be empty")
    if filename != filename.strip():
        raise ValueError(f"filename must not have surrounding whitespace: {filename!r}")
    if not _SAFE_FILENAME.match(filename):
        raise ValueError(
            f"unsafe filename: {filename!r} (no path separators, traversal, or spaces)"
        )
    return filename


def storage_key(
    company_slug: str,
    classification: Classification,
    document_type: str,
    filename: str,
) -> str:
    """Build an object-storage key.

    Layout is ``{company}/{classification}/{document_type}/{filename}`` — tenant
    first, so one company's objects can never be enumerated from another's prefix.
    """
    company = require_company(company_slug)
    safe = _require_safe_filename(filename)
    return f"{company}/{classification.value}/{document_type}/{safe}"


def company_of_storage_key(key: str) -> str:
    """Recover the owning tenant from a storage key.

    Raises when the key has no recognisable tenant prefix — an object that cannot be
    attributed is a violation, not a default.
    """
    head, _, _ = key.partition("/")
    return require_company(head)


def cache_key(
    *,
    company_slug: str,
    permission_fingerprint: str,
    normalized_question: str,
    data_version: str,
) -> str:
    """Build a permission-aware cache key.

    Every component is load-bearing. Tenant and permission fingerprint together are
    what stop an HR-scoped answer from ever being served to an ordinary employee;
    the data version is what stops a stale answer surviving a dataset change.
    """
    company = require_company(company_slug)
    question_digest = hashlib.sha256(normalized_question.strip().lower().encode("utf-8")).hexdigest()[
        :32
    ]
    return f"{_CACHE_PREFIX}:{company}:{permission_fingerprint}:{question_digest}:{data_version}"


def cache_namespace(company_slug: str) -> str:
    """Scan pattern for one tenant's cache entries — used by reset and by audits."""
    return f"{_CACHE_PREFIX}:{require_company(company_slug)}:*"


def rate_limit_key(bucket: str, identity: str) -> str:
    """One counter. ``identity`` is a digest of the caller's address, never the
    address itself — see `rate_limit.py` for why, and for the limits of that."""
    return f"{RATE_LIMIT_PREFIX}:{bucket}:{identity}"


def rate_limit_namespace() -> str:
    """Scan pattern for every rate-limit counter — used by reset.

    Not tenant-scoped, unlike `cache_namespace`. The callers these bound are
    anonymous and have no tenant, which is the whole reason the bounds exist.
    """
    return f"{RATE_LIMIT_PREFIX}:*"
