"""Enforcement: turning a decision into a response, and recording it.

The decision itself is made by :mod:`eaios_core.authz`, which is pure and knows nothing
about HTTP. This package is everything that decision needs from the outside world:

* :mod:`.context_builder` — reads the caller's attributes from current records;
* :mod:`.dependencies` — the dependency protected routes declare;
* :mod:`.enforce` — maps a decision to a status without reinterpreting it, and writes
  the audit entry;
* :mod:`.tenant_guard` — notices a tenant, role, or permission value in a request, acts
  on none of them, and records the attempt;
* :mod:`.audit` — the single writer, with the field allowlist.

The split is deliberate. Deciding is arithmetic and lives where it can be tested with
nothing running; fetching and responding are I/O and live here.
"""

from __future__ import annotations
