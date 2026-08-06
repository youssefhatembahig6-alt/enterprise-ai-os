"""The known tenants, and their identifiers, without a query (spec 003 research R4).

Feature 002 hit this first and wrote down why (`public/queries.py:66-74`): looking a
company's identifier up needs a query against `companies`, which is itself under RLS —
and RLS needs the tenant already set, so the lookup cannot run before the scope it
exists to establish. Identifiers are derived deterministically from the natural key, so
the circularity disappears.

Feature 003 needs the same thing twice: sign-in must search each tenant in turn before
it knows which one the address belongs to, and the access context needs a slug for the
cache and object-storage key builders. Both are here rather than in either caller,
because two derivations of the same value are two places for them to disagree.
"""

from __future__ import annotations

import uuid
from typing import Final

from eaios_core.constants import COMPANY_SLUGS
from eaios_core.ids import derive

__all__ = ["TENANT_IDS", "slug_of", "tenant_ids"]

#: Slug → identifier, in the generation order `COMPANY_SLUGS` fixes. The order is part
#: of the dataset, and sign-in iterates this mapping, so it is also the order tenants
#: are searched — stated because "whichever came first" would be a detail that changed
#: silently.
TENANT_IDS: Final[dict[str, uuid.UUID]] = {
    slug: derive("company", slug, slug) for slug in COMPANY_SLUGS
}

_BY_ID: Final[dict[uuid.UUID, str]] = {value: key for key, value in TENANT_IDS.items()}


def tenant_ids() -> tuple[uuid.UUID, ...]:
    """Every known tenant identifier, in generation order."""
    return tuple(TENANT_IDS.values())


def slug_of(company_id: uuid.UUID) -> str:
    """The slug for a company identifier.

    Raises rather than returning a default. An unattributable tenant is a violation,
    not a fallback — the same stance `eaios_core.tenancy.require_company` takes, and for
    the same reason: a key builder handed an unknown slug would produce a key nobody
    could attribute.
    """
    try:
        return _BY_ID[company_id]
    except KeyError as exc:
        raise ValueError(f"unknown company id: {company_id}") from exc
