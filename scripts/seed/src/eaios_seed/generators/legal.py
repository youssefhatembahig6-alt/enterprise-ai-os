"""Documents: policies, the payroll register, and contracts (spec FR-028–FR-031a).

This module owns every stored file and its metadata row, because policy documents
and contracts share the same rendering, ownership, classification, and ACL
machinery — splitting them would duplicate all four.

Two things here exist specifically to make later features demonstrable:

* a **matched contract pair** with differing notice periods and liability caps but
  identical payment terms, so the blueprint's contract-comparison scenario has a
  verifiable answer (FR-028a);
* a **RESTRICTED payroll register**, so the "employee asks another employee's
  salary → deny" scenario has a real document to be denied (FR-010c, FR-047a).
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from eaios_core.classification import Classification
from eaios_core.clock import reference_datetime
from eaios_core.constants import COMPANY_CURRENCIES, COMPANY_NAMES
from eaios_core.ids import derive
from eaios_core.keys import storage_key

from ..config import SeedConfig
from ..dataset import Dataset
from ..documents.renderer import Document, render
from ..rng import Rng
from .markers import markers_for
from .organization import OrgContext, UserRef
from .policies import POLICY_TYPES, entitlement_days, stated_values_for

__all__ = ["generate_documents"]

_POLICY_TITLES = {
    "HANDBOOK": "Employee Handbook",
    "LEAVE": "Leave Policy",
    "REMOTE_WORK": "Remote Work Policy",
    "EXPENSE": "Expense Policy",
    "SECURITY": "Information Security Policy",
    "CODE_OF_CONDUCT": "Code of Conduct",
    "TRAVEL": "Travel Policy",
    "BENEFITS": "Benefits Guide",
}

#: Which department governs each policy — drives ownership (FR-031a).
_POLICY_OWNER_DEPT = {
    "HANDBOOK": "HR",
    "LEAVE": "HR",
    "REMOTE_WORK": "HR",
    "EXPENSE": "Finance",
    "SECURITY": "Operations",
    "CODE_OF_CONDUCT": "HR",
    "TRAVEL": "Finance",
    "BENEFITS": "HR",
}

_POLICY_CLASSIFICATION = {
    "SECURITY": Classification.CONFIDENTIAL,
    "EXPENSE": Classification.CONFIDENTIAL,
}

_CONTRACT_TYPES = ("CUSTOMER", "SUPPLIER", "NDA", "EMPLOYMENT_TEMPLATE")
_PAYMENT_TERMS = ("NET_30", "NET_45", "NET_60")
_GOVERNING_LAW = {"EG": "Arab Republic of Egypt", "AE": "United Arab Emirates"}


def generate_documents(dataset: Dataset, config: SeedConfig, ctx: OrgContext) -> None:
    for slug in ctx.users:
        _for_company(dataset, config, ctx, slug)


def _slugify(text: str) -> str:
    keep = [c.lower() if c.isalnum() else "-" for c in text]
    out = "".join(keep)
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")


def _document_owner(ctx: OrgContext, slug: str, department: str) -> UserRef:
    """Ownership convention with the documented fallback (FR-031a).

    Delta Retail has no Legal and no Engineering department, so a document governed
    by one falls to the head of Executive Management rather than being ownerless.
    """
    departments = ctx.departments[slug]
    if department in departments:
        return ctx.head_of(slug, department)
    return ctx.head_of(slug, "Executive Management")


def _for_company(dataset: Dataset, config: SeedConfig, ctx: OrgContext, slug: str) -> None:
    rng = Rng(config.seed, "documents", slug)
    now = reference_datetime()
    company_id = ctx.company_ids[slug]
    company_name = COMPANY_NAMES[slug]
    currency = COMPANY_CURRENCIES[slug]
    volumes = config.for_tenant(slug)
    marker = markers_for(slug)[0]
    marker_clause = markers_for(slug)[1]
    marker_ref = markers_for(slug)[2]

    def add_document(
        *,
        natural_key: str,
        title: str,
        document_type: str,
        classification: Classification,
        owner: UserRef,
        country: str | None,
        document: Document,
    ) -> dict[str, Any]:
        content, digest, size = render(document)
        key = storage_key(slug, classification, document_type, f"{_slugify(natural_key)}.md")
        dataset.add_file(key, content)
        row = {
            "id": derive("document", slug, natural_key, seed=config.seed),
            "company_id": company_id,
            # The owning department follows the owning user, which is the same rule
            # FR-031a already states for ownership — so the two cannot disagree.
            #
            # It used to be looked up by name with `.get(department)`, which
            # returned None whenever the company lacked that department. Delta
            # Retail has no Legal team, so all 25 of its contracts were owned by the
            # Executive Management head (the documented FR-031a fallback) while
            # carrying no department at all. FR-010 exists so the authorization
            # feature has these attributes to filter on; a CONFIDENTIAL contract
            # with a null department is invisible to the ABAC department rule that
            # is meant to protect it (Constitution II).
            "department_id": owner.department_id,
            "owner_id": owner.id,
            "title": title,
            "document_type": document_type,
            "storage_key": key,
            "classification": classification.value,
            "country": country,
            "content_sha256": digest,
            "byte_size": size,
            "created_at": now,
            "updated_at": now,
        }
        dataset.add("documents", row)
        return row

    # ---------------------------------------------------------------- policies
    for policy_type in POLICY_TYPES:
        title = _POLICY_TITLES[policy_type]
        values = stated_values_for(policy_type, slug)
        owner_dept = _POLICY_OWNER_DEPT[policy_type]
        owner = _document_owner(ctx, slug, owner_dept)
        classification = _POLICY_CLASSIFICATION.get(policy_type, Classification.INTERNAL)

        doc = Document().heading(f"{company_name} — {title}")
        doc.field("Version", "2026.1").blank()
        doc.field("Effective", config.reference_date.isoformat()).blank()
        doc.field("Owner", f"{owner.full_name}, {owner.job_title}").blank()
        doc.rule()
        doc.para(f"This policy applies to all {company_name} personnel across all offices.")

        if policy_type == "LEAVE":
            # The prose states the same numbers the records use — both read from
            # policies.entitlement_days, so they cannot drift (FR-035).
            doc.heading("Annual Leave Entitlement", 2)
            doc.bullets(
                [
                    f"Egypt (EG): {entitlement_days('EG', 'FULL_TIME')} days per year for full-time staff.",
                    f"United Arab Emirates (AE): {entitlement_days('AE', 'FULL_TIME')} days per year for full-time staff.",
                    f"Part-time staff accrue {entitlement_days('EG', 'PART_TIME')} days (EG) "
                    f"and {entitlement_days('AE', 'PART_TIME')} days (AE), pro-rated.",
                    "Contractors do not accrue paid annual leave.",
                ]
            )
            doc.heading("Conditions", 2)
            doc.bullets(
                [
                    f"Leave accrues monthly after a {values['probation_months']}-month probation period.",
                    f"Up to {values['carry_over_days']} unused days may be carried into the next year.",
                    "All leave requires manager approval before it is taken.",
                ]
            )
        else:
            doc.heading("Scope", 2)
            doc.para(rng.paragraph(4))
            if values:
                doc.heading("Stated Values", 2)
                doc.bullets([f"{k.replace('_', ' ').title()}: {v}" for k, v in sorted(values.items())])

        doc.heading("Reference", 2)
        doc.para(f"Internal reference: {marker_ref}.")

        document_row = add_document(
            natural_key=f"policy-{policy_type}",
            title=title,
            document_type="POLICY",
            classification=classification,
            owner=owner,
            country=None,
            document=doc,
        )

        dataset.add(
            "policy_documents",
            {
                "id": derive("policy_document", slug, policy_type, seed=config.seed),
                "company_id": company_id,
                "document_id": document_row["id"],
                "policy_type": policy_type,
                "version": "2026.1",
                "effective_date": config.reference_date,
                "stated_values": values,
                "created_at": now,
                "updated_at": now,
            },
        )

    # ------------------------------------------------- RESTRICTED payroll doc
    hr_head = _document_owner(ctx, slug, "HR")
    payroll = Document().heading(f"{company_name} — Payroll Register (RESTRICTED)")
    payroll.para(
        "This register contains individual compensation data. Access requires an "
        "explicit grant beyond role membership."
    )
    payroll.field("Period", config.reference_date.strftime("%Y-%m")).blank()
    payroll.field("Prepared by", hr_head.full_name).blank()
    payroll.heading("Summary", 2)
    payroll.bullets(
        [
            f"Headcount: {len(ctx.users[slug])}",
            f"Reporting currency: {currency}",
            f"Confidentiality marker: {marker}",
        ]
    )
    add_document(
        natural_key="payroll-register-2026-06",
        title="Payroll Register 2026-06",
        document_type="REPORT",
        classification=Classification.RESTRICTED,
        owner=hr_head,
        country=None,
        document=payroll,
    )

    # --------------------------------------------------------------- contracts
    # Falls back to the Executive Management head where the company has no Legal
    # department (FR-031a). The document's department now follows this owner, so
    # the fallback no longer leaves Delta Retail's contracts unattributed.
    legal_owner = _document_owner(ctx, slug, "Legal")

    # The matched comparison pair (FR-028a): notice period and liability cap differ,
    # payment terms deliberately identical so a comparison has both a difference and
    # an agreement to report.
    pair = [
        {"key": "contract-compare-a", "counterparty": "Helios Logistics Group",
         "notice": 30, "cap": Decimal("50000.00")},
        {"key": "contract-compare-b", "counterparty": "Zenith Manufacturing Ltd",
         "notice": 90, "cap": None},
    ]

    for spec in pair:
        doc = Document().heading(f"Customer Agreement — {spec['counterparty']}")
        doc.field("Counterparty", spec["counterparty"]).blank()
        doc.field("Governing law", _GOVERNING_LAW["EG"]).blank()
        doc.rule()
        doc.heading("Termination", 2)
        doc.para(
            f"Either party may terminate this agreement on {spec['notice']} days' "
            "written notice."
        )
        doc.heading("Limitation of Liability", 2)
        doc.para(
            f"Aggregate liability is capped at {spec['cap']:f} {currency}."
            if spec["cap"] is not None
            else "Liability under this agreement is uncapped."
        )
        doc.heading("Payment Terms", 2)
        doc.para("Invoices are payable NET_30 from the date of issue.")
        doc.heading("Special Provisions", 2)
        doc.para(f"This agreement incorporates the {marker_clause}.")

        document_row = add_document(
            natural_key=str(spec["key"]),
            title=f"Customer Agreement — {spec['counterparty']}",
            document_type="CONTRACT",
            classification=Classification.CONFIDENTIAL,
            owner=legal_owner,
            country="EG",
            document=doc,
        )

        effective = config.reference_date - dt.timedelta(days=420)
        dataset.add(
            "contracts",
            {
                "id": derive("contract", slug, str(spec["key"]), seed=config.seed),
                "company_id": company_id,
                "document_id": document_row["id"],
                "counterparty_name": spec["counterparty"],
                "contract_type": "CUSTOMER",
                "effective_date": effective,
                "expiry_date": effective + dt.timedelta(days=1095),
                "notice_period_days": spec["notice"],
                "liability_cap_amount": spec["cap"],
                "payment_terms": "NET_30",
                "governing_law": _GOVERNING_LAW["EG"],
                "created_at": now,
                "updated_at": now,
            },
        )

        # Explicit resource grant for the Legal persona — the ACL layer above role
        # and attribute rules.
        if slug == legal_owner.company_slug:
            dataset.add(
                "document_acl",
                {
                    "id": derive("document_acl", slug, f"{spec['key']}:legal", seed=config.seed),
                    "company_id": company_id,
                    "document_id": document_row["id"],
                    "principal_type": "USER",
                    "principal_id": legal_owner.id,
                    "permission": "READ",
                    "created_at": now,
                    "updated_at": now,
                },
            )

    # Remaining contracts, spread across the four types.
    for index in range(max(0, volumes.contracts - len(pair))):
        contract_type = _CONTRACT_TYPES[index % len(_CONTRACT_TYPES)]
        counterparty = rng.company_name()
        natural_key = f"contract-{index + 1:04d}"
        notice = rng.choice(["30", "45", "60", "90"])
        capped = rng.weighted({"yes": 0.7, "no": 0.3}) == "yes"
        cap = Decimal(rng.randint(25, 500) * 1000).quantize(Decimal("0.01")) if capped else None
        country = rng.choice(["EG", "AE"])

        doc = Document().heading(f"{contract_type.replace('_', ' ').title()} — {counterparty}")
        doc.field("Counterparty", counterparty).blank()
        doc.field("Governing law", _GOVERNING_LAW[country]).blank()
        doc.rule()
        doc.heading("Termination", 2)
        doc.para(f"Either party may terminate on {notice} days' written notice.")
        doc.heading("Limitation of Liability", 2)
        doc.para(
            f"Aggregate liability is capped at {cap:f} {currency}."
            if cap is not None
            else "Liability under this agreement is uncapped."
        )
        doc.heading("Payment Terms", 2)
        doc.para(f"Invoices are payable {rng.choice(list(_PAYMENT_TERMS))} from issue.")
        doc.heading("Reference", 2)
        doc.para(f"Filed under {marker_ref}.")

        document_row = add_document(
            natural_key=natural_key,
            title=f"{contract_type.replace('_', ' ').title()} — {counterparty}",
            document_type="CONTRACT",
            classification=Classification.CONFIDENTIAL,
            owner=legal_owner,
            country=country,
            document=doc,
        )

        effective = config.reference_date - dt.timedelta(days=rng.randint(90, 900))
        dataset.add(
            "contracts",
            {
                "id": derive("contract", slug, natural_key, seed=config.seed),
                "company_id": company_id,
                "document_id": document_row["id"],
                "counterparty_name": counterparty,
                "contract_type": contract_type,
                "effective_date": effective,
                "expiry_date": effective + dt.timedelta(days=rng.randint(400, 1460)),
                "notice_period_days": int(notice),
                "liability_cap_amount": cap,
                "payment_terms": rng.choice(list(_PAYMENT_TERMS)),
                "governing_law": _GOVERNING_LAW[country],
                "created_at": now,
                "updated_at": now,
            },
        )
