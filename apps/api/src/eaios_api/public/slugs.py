"""Deterministic, human-readable addresses for detail pages (spec 002 FR-004).

The dataset carries no slug column — feature 001 identifies records by UUIDv5 — and
FR-004 rejects opaque identifiers in addresses. So the slug is derived here, at read
time, from the record's own text plus a short digest of its natural key.

The digest suffix is not decoration. Feature 001 generates repeated vacancy titles
across offices, and its organization generator appends numeric suffixes to collided
emails, so collisions are known to occur in this dataset rather than merely being
possible. A title-only slug with a positional counter would depend on iteration
order, and two environments could assign the counter differently — the class of
non-determinism that feature 001 spent its whole convergence effort eliminating.
The digest depends only on the record, so it cannot.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

__all__ = ["derive_slug", "kebab", "slug_suffix"]

#: Long enough to read as a title, short enough to stay usable in a URL bar.
MAX_KEBAB = 60

#: Six hex characters: 16.7 million values against a few dozen records per entity.
SUFFIX_LENGTH = 6

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def kebab(text: str, *, max_length: int = MAX_KEBAB) -> str:
    """Lowercase, hyphen-separated, ASCII-only, truncated on a word boundary.

    Generated names include Arabic-derived Latin spellings with diacritics, so the
    text is normalised to ASCII first — otherwise the same record could produce a
    different slug depending on how its name happened to be composed.
    """
    normalised = unicodedata.normalize("NFKD", text)
    ascii_only = normalised.encode("ascii", "ignore").decode("ascii").lower()
    hyphenated = _NON_ALNUM.sub("-", ascii_only).strip("-")

    if len(hyphenated) <= max_length:
        return hyphenated

    # Cut on a word boundary so a truncated slug still reads as words.
    cut = hyphenated[:max_length]
    if "-" in cut:
        cut = cut.rsplit("-", 1)[0]
    return cut.strip("-")


def slug_suffix(entity: str, company_slug: str, natural_key: str) -> str:
    """Short digest of the record's natural key — the same key its UUID derives from.

    Because feature 001 derives identifiers deterministically from natural keys, a
    record's suffix is as stable as its identifier: the same seed produces the same
    suffix on every machine and every run.
    """
    material = f"{entity}:{company_slug}:{natural_key}".encode()
    return hashlib.sha256(material).hexdigest()[:SUFFIX_LENGTH]


def derive_slug(entity: str, company_slug: str, natural_key: str, text: str) -> str:
    """The full address segment, e.g. `information-security-analyst-cairo-7f3a2c`.

    Falls back to the suffix alone when the text yields nothing kebab-able — a
    headline of only punctuation would otherwise produce an empty address.
    """
    stem = kebab(text)
    suffix = slug_suffix(entity, company_slug, natural_key)
    return f"{stem}-{suffix}" if stem else suffix
