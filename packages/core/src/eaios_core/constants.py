"""Pinned constants that define this dataset's identity.

Changing any value here produces a *different but equally valid* dataset. That is a
deliberate act, not a refactor: it invalidates the committed fingerprint (spec
FR-017a) and every frozen identifier fixture.
"""

from __future__ import annotations

import datetime as dt
from typing import Final

# --------------------------------------------------------------------------
# Determinism anchors (spec FR-012c, research R2/R3)
# --------------------------------------------------------------------------

#: The committed default seed. Overridable for experimentation, but this is the
#: value every team member, verification run, and demo uses.
ROOT_SEED: Final[str] = "20260630"

#: Every generated date derives from this. Chosen as the last day of a month *and*
#: a quarter so the blueprint's "last month's sales report" demo lands on a complete
#: June with a full quarter behind it, and year-over-year reaches a complete 2024-07.
REFERENCE_DATE: Final[dt.date] = dt.date(2026, 6, 30)

#: Months of transactional history ending at REFERENCE_DATE.
HISTORY_MONTHS: Final[int] = 24

#: Attendance is capped separately: per-employee-per-working-day rows dominate total
#: volume and would otherwise threaten the seed-time budget in SC-008 (spec FR-020a).
ATTENDANCE_MONTHS: Final[int] = 6

# --------------------------------------------------------------------------
# Tenants
# --------------------------------------------------------------------------

NILETECH: Final[str] = "niletech"
DELTA_RETAIL: Final[str] = "delta-retail"

#: Order matters — it is the generation order and therefore part of the dataset.
COMPANY_SLUGS: Final[tuple[str, ...]] = (NILETECH, DELTA_RETAIL)

COMPANY_NAMES: Final[dict[str, str]] = {
    NILETECH: "NileTech Solutions",
    DELTA_RETAIL: "Delta Retail Group",
}

COMPANY_DOMAINS: Final[dict[str, str]] = {
    NILETECH: "niletech.example",
    DELTA_RETAIL: "deltaretail.example",
}

#: Single reporting currency per company (spec Assumptions); the country lives on
#: the office and the user, not on the money.
COMPANY_CURRENCIES: Final[dict[str, str]] = {
    NILETECH: "USD",
    DELTA_RETAIL: "USD",
}

# --------------------------------------------------------------------------
# Generator identity
# --------------------------------------------------------------------------

#: Bump when a change legitimately alters generated content, so a deliberate
#: dataset change is distinguishable from an accidental one.
GENERATOR_VERSION: Final[str] = "0.1.6"

MANIFEST_SCHEMA_VERSION: Final[int] = 1
