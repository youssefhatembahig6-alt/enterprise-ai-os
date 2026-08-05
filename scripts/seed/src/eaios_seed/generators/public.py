"""Public-facing content for both companies (spec FR-030, SC-011).

FR-030 was amended during checklist remediation to cover both tenants: `PUBLIC`
classification must exist for each of them (FR-010c), and public content is itself
an isolation surface that has to be provable per tenant.

Everything here is deliberately free of salary figures, contract terms, internal
financial values, and non-executive contact details — that is what the public-safety
scan asserts, and generating it correctly is cheaper than filtering it afterwards.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from eaios_core.classification import Classification
from eaios_core.clock import history_window, reference_datetime
from eaios_core.constants import COMPANY_DOMAINS, COMPANY_NAMES, DELTA_RETAIL, NILETECH
from eaios_core.ids import derive
from eaios_core.keys import storage_key

from ..config import SeedConfig
from ..dataset import Dataset
from ..documents.renderer import Document, render
from ..rng import Rng
from .organization import OFFICES, OrgContext

__all__ = ["generate_public_content"]

_SERVICES: dict[str, list[tuple[str, str]]] = {
    NILETECH: [
        ("Business Process Automation", "Replace manual back-office steps with governed workflows."),
        ("Custom Software Engineering", "Build and maintain line-of-business systems end to end."),
        ("Data Platform Engineering", "Consolidate scattered data into a governed analytics layer."),
        ("Systems Integration", "Connect existing systems without replacing them."),
        ("Cloud Migration", "Move workloads with a documented rollback path at every stage."),
        ("Managed Support", "Ongoing operation and improvement of delivered systems."),
    ],
    DELTA_RETAIL: [
        ("Wholesale Distribution", "Bulk supply to independent retailers across Egypt and the Gulf."),
        ("Cold Chain Logistics", "Temperature-controlled handling for perishable goods."),
        ("Retail Fulfilment", "Pick, pack, and last-mile delivery for partner storefronts."),
        ("Category Management", "Assortment planning and shelf strategy for partner stores."),
    ],
}

_PRODUCTS: dict[str, list[tuple[str, str]]] = {
    NILETECH: [
        ("Workflow Automation Platform", "Design, run, and audit business workflows."),
        ("Document Intelligence Suite", "Turn document backlogs into searchable, governed knowledge."),
        ("Integration Gateway", "One managed connection point between internal systems."),
        ("Analytics Workspace", "Self-service reporting over governed data."),
    ],
    DELTA_RETAIL: [
        ("Delta Wholesale Catalogue", "Seasonal bulk catalogue for partner retailers."),
        ("Delta Fresh Programme", "Short-lead produce supply with cold-chain guarantees."),
        ("Delta Partner Portal", "Ordering and fulfilment tracking for partner stores."),
    ],
}

_NEWS_TEMPLATES = [
    ("{company} opens {city} office", "The new site adds capacity for regional delivery teams."),
    ("{company} completes ISO 27001 surveillance audit", "No major non-conformities were raised."),
    ("{company} publishes annual sustainability summary", "Covering energy, travel, and supplier standards."),
    ("{company} partners with regional distributors", "Expanding coverage across the Gulf region."),
    ("{company} launches internal graduate programme", "Twelve places across engineering and operations."),
    ("{company} reaches service availability target", "Third consecutive quarter above the published target."),
]

_VACANCY_TITLES = {
    "Engineering": ["Senior Software Engineer", "QA Engineer", "DevOps Engineer"],
    "Sales": ["Account Executive", "Sales Representative"],
    "HR": ["Recruiter", "HR Generalist"],
    "Finance": ["Financial Analyst"],
    "Operations": ["Operations Analyst", "Logistics Coordinator"],
    "Customer Support": ["Support Specialist"],
    "Legal": ["Legal Counsel"],
    "Executive Management": ["Chief of Staff"],
}


def generate_public_content(dataset: Dataset, config: SeedConfig, ctx: OrgContext) -> None:
    for slug in ctx.users:
        _for_company(dataset, config, ctx, slug)


def _for_company(dataset: Dataset, config: SeedConfig, ctx: OrgContext, slug: str) -> None:
    rng = Rng(config.seed, "public", slug)
    now = reference_datetime()
    company_id = ctx.company_ids[slug]
    company_name = COMPANY_NAMES[slug]
    volumes = config.for_tenant(slug)
    history_start, history_end = history_window()

    def row(**kwargs: Any) -> dict[str, Any]:
        return {"company_id": company_id, "created_at": now, "updated_at": now, **kwargs}

    # -- services ---------------------------------------------------------
    for order, (name, summary) in enumerate(_SERVICES[slug]):
        dataset.add(
            "services",
            row(
                id=derive("service", slug, name, seed=config.seed),
                name=name, summary=summary,
                description=(
                    f"{summary} Delivered by a dedicated team, with support "
                    "continuing after handover."
                ),
                display_order=order,
            ),
        )

    # -- public products --------------------------------------------------
    for order, (name, tagline) in enumerate(_PRODUCTS[slug]):
        dataset.add(
            "public_products",
            row(
                id=derive("public_product", slug, name, seed=config.seed),
                name=name, tagline=tagline,
                description=(
                    f"{tagline} Available to partners across every region "
                    "we operate in."
                ),
                display_order=order,
            ),
        )

    # -- leadership profiles ----------------------------------------------
    # Executives only, and only public-appropriate fields: no salary, no personal
    # contact details, no employment terms (SC-011).
    executives = [u for u in ctx.users[slug] if u.department == "Executive Management"]
    for order, executive in enumerate(sorted(executives, key=lambda u: u.natural_key)[:6]):
        dataset.add(
            "leadership_profiles",
            row(
                id=derive("leadership_profile", slug, executive.natural_key, seed=config.seed),
                user_id=executive.id,
                public_title=executive.job_title,
                bio=(
                    f"{executive.full_name} leads {company_name}'s "
                    f"{executive.job_title.lower()} function from the "
                    f"{executive.office_code} office, and has led the function "
                    "through the company's recent growth."
                ),
                photo_key=None,
                display_order=order,
            ),
        )

    # -- news -------------------------------------------------------------
    cities = [office["city"] for office in OFFICES[slug]]
    news_count = max(4, volumes.public_items // 4)
    for index in range(news_count):
        headline_template, body = _NEWS_TEMPLATES[index % len(_NEWS_TEMPLATES)]
        headline = headline_template.format(company=company_name, city=cities[index % len(cities)])
        if index >= len(_NEWS_TEMPLATES):
            headline = f"{headline} ({index // len(_NEWS_TEMPLATES) + 1})"
        published = history_start + dt.timedelta(
            days=rng.randint(0, (history_end - history_start).days)
        )
        dataset.add(
            "news_items",
            row(
                id=derive("news_item", slug, f"news-{index + 1:03d}", seed=config.seed),
                headline=headline,
                body=(
                    f"{body} Further detail is available from the "
                    "communications team."
                ),
                published_on=published,
            ),
        )

    # -- vacancies --------------------------------------------------------
    departments = sorted(ctx.departments[slug])
    offices = ctx.offices[slug]
    office_codes = sorted(offices)
    vacancy_count = max(4, volumes.public_items // 4)
    seen: set[tuple[str, str]] = set()
    for index in range(vacancy_count):
        department = departments[index % len(departments)]
        titles = _VACANCY_TITLES.get(department, ["Specialist"])
        title = titles[index % len(titles)]
        office_code = office_codes[index % len(office_codes)]
        if (title, office_code) in seen:
            title = f"{title} ({index + 1})"
        seen.add((title, office_code))
        dataset.add(
            "vacancies",
            row(
                id=derive("vacancy", slug, f"vacancy-{index + 1:03d}", seed=config.seed),
                department_id=ctx.departments[slug][department],
                office_id=offices[office_code],
                title=title,
                description=(
                    f"{company_name} is hiring a {title} to join the {department} "
                    "team. The role suits someone with strong fundamentals who wants "
                    "real ownership of their work. Applications are reviewed on a "
                    "rolling basis."
                ),
                posted_on=history_end - dt.timedelta(days=rng.randint(5, 120)),
                is_open=True,
            ),
        )

    # -- the public site's own document, so PUBLIC exists in storage too ----
    about = Document().heading(f"About {company_name}")
    about.para(
        f"{company_name} operates from "
        f"{', '.join(office['city'] for office in OFFICES[slug])}."
    )
    about.heading("Services", 2)
    about.bullets([f"{name} — {summary}" for name, summary in _SERVICES[slug]])
    about.heading("Contact", 2)
    about.para(f"General enquiries: hello@{COMPANY_DOMAINS[slug]}")

    content, digest, size = render(about)
    key = storage_key(slug, Classification.PUBLIC, "PUBLIC", "about.md")
    dataset.add_file(key, content)
    dataset.add(
        "documents",
        row(
            id=derive("document", slug, "public-about", seed=config.seed),
            # Follows the owner, like every other document (FR-010, FR-031a). Public
            # content carries no country because it is company-wide, but there is no
            # reason for it to carry no department when it has a definite owner.
            department_id=ctx.head_of(slug, "Executive Management").department_id,
            owner_id=ctx.head_of(slug, "Executive Management").id,
            title=f"About {company_name}",
            document_type="PUBLIC",
            storage_key=key,
            classification=Classification.PUBLIC.value,
            country=None,
            content_sha256=digest,
            byte_size=size,
        ),
    )
