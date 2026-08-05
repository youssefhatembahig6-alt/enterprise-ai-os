"""API database access — see :mod:`eaios_core.db` for the implementation.

Note the asymmetry: the API only ever uses the *app* engine, against which RLS is
enforced. The owner engine is reachable from core but must never serve a request.
"""

from __future__ import annotations

from eaios_core.db import (
    TENANT_SETTING,
    create_app_engine,
    session_scope,
    tenant_scope,
)

__all__ = ["TENANT_SETTING", "create_app_engine", "session_scope", "tenant_scope"]
