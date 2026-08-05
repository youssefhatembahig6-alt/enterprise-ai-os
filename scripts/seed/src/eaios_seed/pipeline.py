"""Generation pipeline: runs every generator in dependency order.

Order matters only because later generators read the :class:`OrgContext` the first
one produces. Within a generator, output is order-independent by construction — the
fingerprint sorts row digests, so nothing here depends on insertion sequence.
"""

from __future__ import annotations

from .audit import record_seed_audit
from .config import SeedConfig
from .dataset import Dataset
from .generators.hr import generate_hr
from .generators.legal import generate_documents
from .generators.organization import OrgContext, generate_organization
from .generators.public import generate_public_content
from .generators.sales import generate_sales

__all__ = ["INSERT_ORDER", "build_complete_dataset", "build_dataset"]

#: Foreign-key-safe insertion order for the relational loader. Derived by hand
#: rather than by topological sort because the graph is small, stable, and an
#: explicit list is easier to review than an inferred one.
INSERT_ORDER: tuple[str, ...] = (
    # global first — roles reference permissions
    "permissions",
    "platform_administrators",
    # organization
    "companies",
    "offices",
    "departments",
    "users",
    "roles",
    "role_permissions",
    "user_roles",
    # hr
    "employee_profiles",
    "leave_balances",
    "leave_requests",
    "attendance_records",
    "training_records",
    "performance_reviews",
    # sales & finance
    "customers",
    "products",
    "orders",
    "order_lines",
    "invoices",
    "sales_targets",
    "expenses",
    "budgets",
    "monthly_revenue",
    # documents
    "documents",
    "document_acl",
    "contracts",
    "policy_documents",
    # public content
    "services",
    "public_products",
    "leadership_profiles",
    "news_items",
    "vacancies",
    # platform
    "job_records",
    "audit_logs",
)


def build_dataset(config: SeedConfig) -> tuple[Dataset, OrgContext]:
    """Generate the complete dataset in memory. No I/O happens here."""
    dataset = Dataset()
    ctx = generate_organization(dataset, config)
    generate_hr(dataset, config, ctx)
    generate_sales(dataset, config, ctx)
    generate_documents(dataset, config, ctx)
    generate_public_content(dataset, config, ctx)
    return dataset, ctx


def build_complete_dataset(config: SeedConfig) -> tuple[Dataset, OrgContext]:
    """The dataset exactly as it is persisted and fingerprinted.

    `build_dataset` produces business content; the seed also records its own audit
    entries (FR-043), and those rows are part of the dataset. Every caller that
    fingerprints, loads, or verifies must use *this* function — computing a digest
    over the pre-audit dataset yields a different value, which is precisely the
    inconsistency that appeared between the CLI and the test helper.
    """
    dataset, ctx = build_dataset(config)
    record_seed_audit(dataset, config, ctx.company_ids)
    return dataset, ctx
