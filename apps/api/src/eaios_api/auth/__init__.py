"""Authentication: credentials in, a session credential out (spec 003).

Four modules, each with one job:

* :mod:`.tokens` — mint and verify the session credential. Identifies; decides nothing.
* :mod:`.sessions` — the server-side session record, which is what makes signing out
  real and what enforces both expiry bounds.
* :mod:`.login_bounds` — the per-account and per-address attempt limits.
* :mod:`.router` — the three endpoints.

Password hashing is deliberately **not** here. Two workspace members need it — the API
verifies and the seed's `credentials` command hashes — so it lives in
:mod:`eaios_core.passwords`, because `scripts/seed` may not import from `apps/api`
(spec 001 FR-001a: shared code moves down, never sideways).
"""

from __future__ import annotations
