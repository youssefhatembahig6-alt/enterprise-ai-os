"""Platform determinism self-check (spec FR-047b, SC-002).

Computes a fingerprint over the primitives whose output could plausibly differ
between operating systems, and prints it. CI runs this on more than one platform
and compares the results.

Why this exists separately from the dataset fingerprint: the full seed needs Docker,
and GitHub's Windows runners cannot run Linux containers, so a genuinely cross-OS
*stack* run is not available. But the parts that actually vary by platform are pure
Python — line endings, text encoding, locale-sensitive formatting, hash ordering,
and path handling. Those can be exercised anywhere, and they are where a
cross-platform determinism bug would come from.

The converge pass found the previous CI arrangement ran the fingerprint job on
Ubuntu only, which meant SC-002's cross-machine claim rested on a comparison that
never happened.
"""

from __future__ import annotations

import decimal
import platform
import sys
import uuid

from . import fingerprint as fp
from . import ids
from .classification import Classification
from .clock import attendance_window, history_window, last_full_month, reference_date
from .constants import COMPANY_SLUGS, ROOT_SEED
from .keys import cache_key, storage_key

__all__ = ["main", "platform_fingerprint"]


def _identifier_sample(seed: str) -> list[dict[str, object]]:
    """Derived identifiers across both tenants and several entity types."""
    rows: list[dict[str, object]] = []
    for slug in COMPANY_SLUGS:
        for entity in ("company", "user", "order", "document", "audit_log"):
            for index in range(1, 26):
                rows.append(
                    {
                        "entity": entity,
                        "company": slug,
                        "key": f"{entity}-{index:04d}",
                        "id": ids.derive(entity, slug, f"{entity}-{index:04d}", seed=seed),
                    }
                )
    for code in ("hr:read_all", "documents:read", "communications:send"):
        rows.append({"entity": "permission", "company": None, "key": code,
                     "id": ids.derive_global("permission", code, seed=seed)})
    return rows


def _text_and_number_sample() -> list[dict[str, object]]:
    """Values whose rendering is locale- and encoding-sensitive."""
    return [
        # Non-ASCII must survive as itself, not as an escape sequence.
        {"name": "Nadia Farouk", "city": "Cairo", "note": "Zakï — naïve café"},
        # Decimal scale must survive: 18500.00 is not 18500.0.
        {"amount": decimal.Decimal("18500.00"), "tax": decimal.Decimal("2775.00")},
        # Thousands separators and decimal points are locale-sensitive in most
        # formatting APIs; canonical serialization must not use any of them.
        {"large": decimal.Decimal("1234567.89")},
        {"date": reference_date(), "uuid": uuid.uuid5(uuid.NAMESPACE_DNS, "eaios")},
    ]


def _document_bytes_sample() -> dict[str, bytes]:
    """Text written the way generated documents are written.

    The bytes are constructed explicitly with ``\\n`` rather than by a text write,
    because the whole point is to detect a platform that would have turned them
    into ``\\r\\n``.
    """
    body = "# Leave Policy\n\nAnnual entitlement: 21 days.\n\n- Accrued monthly\n- Cairo, Alexandria, Dubai\n"
    return {
        storage_key(slug, Classification.INTERNAL, "POLICY", "leave.md"): body.encode("utf-8")
        for slug in COMPANY_SLUGS
    }


def _derived_window_sample() -> list[dict[str, object]]:
    history_start, history_end = history_window()
    attendance_start, attendance_end = attendance_window()
    month_start, month_end = last_full_month()
    return [
        {"window": "history", "start": history_start, "end": history_end},
        {"window": "attendance", "start": attendance_start, "end": attendance_end},
        {"window": "last_full_month", "start": month_start, "end": month_end},
    ]


def _key_sample() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for slug in COMPANY_SLUGS:
        for level in Classification:
            rows.append({"key": storage_key(slug, level, "POLICY", "handbook.md")})
        rows.append(
            {
                "key": cache_key(
                    company_slug=slug,
                    permission_fingerprint="employee",
                    normalized_question="how many vacation days do i get",
                    data_version="v1",
                )
            }
        )
    return rows


def platform_fingerprint(seed: str = ROOT_SEED) -> str:
    """Digest over every platform-sensitive primitive. Identical on every OS."""
    families = {
        "identifiers": fp.family_digest(_identifier_sample(seed)),
        "text_and_numbers": fp.family_digest(_text_and_number_sample()),
        "windows": fp.family_digest(_derived_window_sample()),
        "keys": fp.family_digest(_key_sample()),
    }
    return fp.root_fingerprint(families, fp.files_digest(_document_bytes_sample()))


def main() -> int:
    digest = platform_fingerprint()
    # Diagnostics to stderr so stdout carries only the digest and stays pipeable.
    print(
        f"platform={sys.platform} python={platform.python_version()} "
        f"seed={ROOT_SEED} reference_date={reference_date()}",
        file=sys.stderr,
    )
    print(digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
