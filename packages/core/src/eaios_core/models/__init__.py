"""All SQLAlchemy models.

Importing this package registers every table on ``Base.metadata``, which is what
Alembic and the schema audit both walk.
"""

from __future__ import annotations

from .auth import UserCredential, UserSession
from .base import Base
from .global_ import DatasetManifest, Permission, PlatformAdministrator
from .hr import (
    AttendanceRecord,
    EmployeeProfile,
    LeaveBalance,
    LeaveRequest,
    PerformanceReview,
    TrainingRecord,
)
from .legal import Contract, Document, DocumentAcl, PolicyDocument, classification_enum
from .organization import Company, Department, Office, Role, RolePermission, User, UserRole
from .platform import AuditLog, JobRecord
from .public import LeadershipProfile, NewsItem, PublicProduct, Service, Vacancy
from .public_site import ContactSubmission
from .sales import (
    Budget,
    Customer,
    Expense,
    Invoice,
    MonthlyRevenue,
    Order,
    OrderLine,
    Product,
    SalesTarget,
)

__all__ = [
    "POST_BASELINE_TABLES",
    "AttendanceRecord",
    "AuditLog",
    "Base",
    "Budget",
    "Company",
    "ContactSubmission",
    "Contract",
    "Customer",
    "DatasetManifest",
    "Department",
    "Document",
    "DocumentAcl",
    "EmployeeProfile",
    "Expense",
    "Invoice",
    "JobRecord",
    "LeadershipProfile",
    "LeaveBalance",
    "LeaveRequest",
    "MonthlyRevenue",
    "NewsItem",
    "Office",
    "Order",
    "OrderLine",
    "PerformanceReview",
    "Permission",
    "PlatformAdministrator",
    "PolicyDocument",
    "Product",
    "PublicProduct",
    "Role",
    "RolePermission",
    "SalesTarget",
    "Service",
    "TrainingRecord",
    "User",
    "UserCredential",
    "UserRole",
    "UserSession",
    "Vacancy",
    "baseline_tables",
    "classification_enum",
    "tenant_tables",
]


#: Tables introduced by a migration *after* the 0001 baseline.
#:
#: Migration 0001 builds the schema with ``Base.metadata.create_all``, which was a
#: reasonable shortcut for a greenfield baseline and became a trap the moment a
#: later feature added a model: the metadata is read at migration time, so 0001
#: started creating a table that migration 0003 then tried to create again. A fresh
#: ``alembic upgrade head`` failed with *relation already exists*, while every
#: already-migrated database kept working — the schema could no longer be built
#: from scratch and nothing said so.
#:
#: A model added by a future migration MUST be named here. `tests/integration/
#: test_migrations.py` runs the full round trip and fails if it is not.
POST_BASELINE_TABLES: frozenset[str] = frozenset(
    {
        # Migration 0003
        "contact_submissions",
        # Migration 0004 (feature 003)
        "user_credentials",
        "sessions",
    }
)


def baseline_tables() -> list[str]:
    """The tables migration 0001 is responsible for creating."""
    return sorted(name for name in Base.metadata.tables if name not in POST_BASELINE_TABLES)


def tenant_tables(*, baseline_only: bool = False) -> list[str]:
    """Tables that RLS policies apply to — everything except the global allowlist.

    Derived from the metadata rather than hand-listed, so a newly added model cannot
    be silently left without a policy.

    ``baseline_only`` excludes tables that a later migration introduces, for the
    benefit of migration 0002: it runs before those tables exist, and each of them
    applies its own policy in the migration that creates it.
    """
    from ..tenancy import is_tenant_scoped

    names = baseline_tables() if baseline_only else list(Base.metadata.tables)
    return sorted(name for name in names if is_tenant_scoped(name))
