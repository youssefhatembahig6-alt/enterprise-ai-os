"""Organization generator: companies, offices, departments, roles, users, hierarchy.

Everything downstream references what this produces, so it runs first and hands
back an :class:`OrgContext` the other generators read.

Two structural requirements shape the code here. The reporting hierarchy must be a
valid tree with exactly one manager-less executive per company (FR-034), and every
user with direct reports must hold the Manager role (FR-025a). Both are built in
rather than checked afterwards — a generator that can emit an invalid org chart and
relies on a test to notice is the wrong shape.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from eaios_core.clock import reference_datetime
from eaios_core.constants import (
    COMPANY_CURRENCIES,
    COMPANY_DOMAINS,
    COMPANY_NAMES,
    DELTA_RETAIL,
    NILETECH,
)
from eaios_core.ids import derive, derive_global

from ..config import SeedConfig
from ..dataset import Dataset
from ..rng import Rng

__all__ = ["PERMISSIONS", "ROLE_PERMISSIONS", "OrgContext", "generate_organization"]

# --------------------------------------------------------------------------
# Static vocabulary — from the blueprint, identical for both tenants (FR-009b)
# --------------------------------------------------------------------------

PERMISSIONS: dict[str, str] = {
    "documents:read": "Read documents the user is authorized to see",
    "documents:upload": "Upload new documents",
    "documents:delete": "Delete documents",
    "hr:read_self": "Read one's own HR records",
    "hr:read_team": "Read HR records for direct reports",
    "hr:read_all": "Read HR records company-wide, including payroll",
    "hr:update": "Modify HR records",
    "sales:read": "Read sales data",
    "finance:read": "Read financial data",
    "contracts:read": "Read contracts and agreements",
    "reports:generate": "Generate reports",
    "users:manage": "Create and modify users",
    "roles:manage": "Assign roles and permissions",
    "actions:approve": "Approve irreversible actions",
    "audit:read": "Read audit logs",
    "communications:draft": "Draft outbound communications",
    "communications:send": "Send outbound communications",
}

ROLE_PERMISSIONS: dict[str, list[str]] = {
    "Company Admin": [
        "documents:read", "documents:upload", "users:manage", "roles:manage",
        "audit:read", "reports:generate", "actions:approve",
    ],
    "Employee": ["documents:read", "hr:read_self"],
    "Manager": ["documents:read", "hr:read_self", "hr:read_team", "actions:approve"],
    "HR": [
        "documents:read", "documents:upload", "hr:read_self", "hr:read_all",
        "hr:update", "reports:generate",
    ],
    "Finance": ["documents:read", "hr:read_self", "finance:read", "sales:read", "reports:generate"],
    "Legal": ["documents:read", "documents:upload", "hr:read_self", "contracts:read"],
    "Auditor": ["documents:read", "hr:read_self", "audit:read"],
}

#: Delta Retail deliberately has no Engineering and no Legal department (FR-022).
DEPARTMENTS: dict[str, dict[str, float]] = {
    NILETECH: {
        "Engineering": 0.30,
        "Sales": 0.18,
        "Customer Support": 0.14,
        "Operations": 0.12,
        "Finance": 0.08,
        "HR": 0.07,
        "Executive Management": 0.06,
        "Legal": 0.05,
    },
    DELTA_RETAIL: {
        "Sales": 0.40,
        "Operations": 0.28,
        "Finance": 0.12,
        "HR": 0.12,
        "Executive Management": 0.08,
    },
}

OFFICES: dict[str, list[dict[str, Any]]] = {
    NILETECH: [
        {"code": "CAI", "city": "Cairo", "country": "EG", "hq": True,
         "address": "14 Nile Corniche, Maadi, Cairo"},
        {"code": "ALX", "city": "Alexandria", "country": "EG", "hq": False,
         "address": "8 Sidi Gaber Street, Alexandria"},
        {"code": "DXB", "city": "Dubai", "country": "AE", "hq": False,
         "address": "Office 1203, Business Bay Tower, Dubai"},
    ],
    DELTA_RETAIL: [
        {"code": "CAI", "city": "Cairo", "country": "EG", "hq": True,
         "address": "42 Abbas El Akkad, Nasr City, Cairo"},
        {"code": "DXB", "city": "Dubai", "country": "AE", "hq": False,
         "address": "Unit 7, Al Quoz Industrial Area, Dubai"},
    ],
}

#: Office weighting per company — headcount is not spread evenly across sites.
OFFICE_WEIGHTS: dict[str, dict[str, float]] = {
    NILETECH: {"CAI": 0.60, "ALX": 0.22, "DXB": 0.18},
    DELTA_RETAIL: {"CAI": 0.70, "DXB": 0.30},
}

JOB_TITLES: dict[str, list[str]] = {
    "Engineering": ["Software Engineer", "Senior Software Engineer", "QA Engineer",
                    "DevOps Engineer", "Engineering Manager", "Data Engineer"],
    "Sales": ["Sales Representative", "Account Executive", "Sales Manager",
              "Solutions Consultant"],
    "Customer Support": ["Support Specialist", "Support Team Lead", "Technical Support Engineer"],
    "Operations": ["Operations Analyst", "Operations Manager", "Logistics Coordinator"],
    "Finance": ["Financial Analyst", "Accountant", "Finance Manager", "Payroll Specialist"],
    "HR": ["HR Generalist", "Recruiter", "HR Manager", "People Operations Specialist"],
    "Legal": ["Legal Counsel", "Contracts Manager", "Compliance Officer"],
    "Executive Management": ["Chief Executive Officer", "Chief Operating Officer",
                             "Chief Financial Officer", "Chief Technology Officer"],
}

SALARY_BANDS: dict[str, tuple[int, int]] = {
    "B1": (28000, 42000),
    "B2": (42000, 62000),
    "B3": (62000, 88000),
    "B4": (88000, 125000),
    "B5": (125000, 190000),
}

EMPLOYMENT_TYPES = {"FULL_TIME": 0.86, "PART_TIME": 0.06, "CONTRACT": 0.08}

#: Personas that must occupy their department's head slot. Assignment was
#: previously alphabetical, which made `employee.engineering` the Engineering head
#: and left `manager.engineering` reporting *to the employee* — inverting the
#: blueprint's manager-scope scenario (FR-025b).
HEAD_PERSONAS: frozenset[str] = frozenset({"manager.engineering", "admin.company"})

#: Fixed persona set (FR-025b). Keyed by persona, valued by (company, department).
PERSONA_PLACEMENT: dict[str, tuple[str, str]] = {
    "employee.engineering": (NILETECH, "Engineering"),
    "manager.engineering": (NILETECH, "Engineering"),
    "employee.sales": (NILETECH, "Sales"),
    "hr.generalist": (NILETECH, "HR"),
    "finance.analyst": (NILETECH, "Finance"),
    "legal.counsel": (NILETECH, "Legal"),
    "auditor.readonly": (NILETECH, "Operations"),
    "admin.company": (NILETECH, "Executive Management"),
    "comms.sender": (NILETECH, "Customer Support"),
    "employee.delta": (DELTA_RETAIL, "Sales"),
}


@dataclass
class UserRef:
    """Everything downstream generators need about a generated user."""

    id: Any
    company_slug: str
    company_id: Any
    natural_key: str
    full_name: str
    email: str
    department: str
    department_id: Any
    office_code: str
    office_id: Any
    country: str
    employment_type: str
    manager_id: Any | None
    job_title: str
    salary_band: str
    hire_date: dt.date
    primary_role: str
    is_manager: bool = False
    persona_key: str | None = None


@dataclass
class OrgContext:
    company_ids: dict[str, Any] = field(default_factory=dict)
    users: dict[str, list[UserRef]] = field(default_factory=dict)
    departments: dict[str, dict[str, Any]] = field(default_factory=dict)
    offices: dict[str, dict[str, Any]] = field(default_factory=dict)
    role_ids: dict[str, dict[str, Any]] = field(default_factory=dict)
    heads: dict[str, dict[str, UserRef]] = field(default_factory=dict)

    def users_in(self, slug: str, department: str) -> list[UserRef]:
        return [u for u in self.users[slug] if u.department == department]

    def head_of(self, slug: str, department: str) -> UserRef:
        return self.heads[slug][department]

    def persona(self, key: str) -> UserRef:
        for members in self.users.values():
            for user in members:
                if user.persona_key == key:
                    return user
        raise KeyError(f"persona not generated: {key}")


def _allocate(total: int, weights: dict[str, float]) -> dict[str, int]:
    """Split `total` across weighted buckets, deterministically and exactly.

    Every bucket gets at least one member. A department with zero people would have
    no head, which breaks FR-034 — and at smoke-profile volumes that is not a
    hypothetical: 12 users across 5 departments rounds several of them to zero.
    """
    keys = sorted(weights, key=lambda k: (-weights[k], k))
    if total < len(keys):
        raise ValueError(
            f"cannot allocate {total} users across {len(keys)} departments; "
            "every department needs at least a head"
        )

    counts = {key: max(1, int(total * weights[key])) for key in keys}

    # Trim from the largest buckets if the floors pushed the total over.
    while sum(counts.values()) > total:
        for key in keys:
            if sum(counts.values()) <= total:
                break
            if counts[key] > 1:
                counts[key] -= 1

    while sum(counts.values()) < total:
        for key in keys:
            if sum(counts.values()) >= total:
                break
            counts[key] += 1

    return counts


def generate_organization(dataset: Dataset, config: SeedConfig) -> OrgContext:
    now = reference_datetime()
    ctx = OrgContext()

    # -- global permission catalog (no company_id) ------------------------
    for code, description in sorted(PERMISSIONS.items()):
        dataset.add(
            "permissions",
            {
                "id": derive_global("permission", code, seed=config.seed),
                "code": code,
                "description": description,
                "created_at": now,
                "updated_at": now,
            },
        )

    dataset.add(
        "platform_administrators",
        {
            "id": derive_global("platform_administrator", "root", seed=config.seed),
            "email": "platform.admin@eaios.local",
            "display_name": "Platform Administrator",
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        },
    )

    for slug in (NILETECH, DELTA_RETAIL):
        _generate_company(dataset, config, ctx, slug, now)

    return ctx


def _generate_company(
    dataset: Dataset, config: SeedConfig, ctx: OrgContext, slug: str, now: dt.datetime
) -> None:
    rng = Rng(config.seed, "organization", slug)
    volumes = config.for_tenant(slug)
    company_id = derive("company", slug, slug, seed=config.seed)
    ctx.company_ids[slug] = company_id
    currency = COMPANY_CURRENCIES[slug]

    dataset.add(
        "companies",
        {
            "id": company_id,
            "company_id": company_id,
            "slug": slug,
            "name": COMPANY_NAMES[slug],
            "domain": COMPANY_DOMAINS[slug],
            "status": "ACTIVE",
            "reporting_currency": currency,
            "created_at": now,
            "updated_at": now,
        },
    )

    # -- offices ----------------------------------------------------------
    office_ids: dict[str, Any] = {}
    for office in OFFICES[slug]:
        oid = derive("office", slug, office["code"], seed=config.seed)
        office_ids[office["code"]] = oid
        dataset.add(
            "offices",
            {
                "id": oid, "company_id": company_id, "code": office["code"],
                "city": office["city"], "country": office["country"],
                "address": office["address"], "is_headquarters": office["hq"],
                "created_at": now, "updated_at": now,
            },
        )
    ctx.offices[slug] = office_ids

    # -- roles ------------------------------------------------------------
    role_ids: dict[str, Any] = {}
    for role_name in sorted(ROLE_PERMISSIONS):
        rid = derive("role", slug, role_name, seed=config.seed)
        role_ids[role_name] = rid
        dataset.add(
            "roles",
            {
                "id": rid, "company_id": company_id, "name": role_name,
                "description": f"{role_name} role for {COMPANY_NAMES[slug]}",
                "created_at": now, "updated_at": now,
            },
        )
        for code in sorted(ROLE_PERMISSIONS[role_name]):
            dataset.add(
                "role_permissions",
                {
                    "id": derive("role_permission", slug, f"{role_name}:{code}", seed=config.seed),
                    "company_id": company_id,
                    "role_id": rid,
                    "permission_id": derive_global("permission", code, seed=config.seed),
                    "created_at": now, "updated_at": now,
                },
            )
    ctx.role_ids[slug] = role_ids

    # -- departments (head assigned after users exist) ---------------------
    hq_code = next(o["code"] for o in OFFICES[slug] if o["hq"])
    dept_ids: dict[str, Any] = {}
    for name in sorted(DEPARTMENTS[slug]):
        did = derive("department", slug, name, seed=config.seed)
        dept_ids[name] = did
        dataset.add(
            "departments",
            {
                "id": did, "company_id": company_id, "name": name,
                "office_id": office_ids[hq_code], "head_user_id": None,
                "created_at": now, "updated_at": now,
            },
        )
    ctx.departments[slug] = dept_ids

    # -- users and hierarchy ----------------------------------------------
    users = _generate_users(config, ctx, rng, slug, company_id, volumes.users, dept_ids, office_ids)
    ctx.users[slug] = users

    for user in users:
        dataset.add(
            "users",
            {
                "id": user.id, "company_id": company_id,
                "department_id": user.department_id, "office_id": user.office_id,
                "manager_id": user.manager_id, "email": user.email,
                "full_name": user.full_name, "country": user.country,
                "employment_type": user.employment_type, "is_active": True,
                "password_hash": None,
                "is_persona": user.persona_key is not None,
                "persona_key": user.persona_key,
                "created_at": now, "updated_at": now,
            },
        )
        roles = [user.primary_role]
        if user.is_manager and "Manager" not in roles:
            roles.append("Manager")
        for index, role_name in enumerate(roles):
            dataset.add(
                "user_roles",
                {
                    "id": derive("user_role", slug, f"{user.natural_key}:{role_name}", seed=config.seed),
                    "company_id": company_id, "user_id": user.id,
                    "role_id": role_ids[role_name], "is_primary": index == 0,
                    "created_at": now, "updated_at": now,
                },
            )

    # Backfill department heads now that users exist.
    for row in dataset.rows["departments"]:
        if row["company_id"] == company_id:
            name = row["name"]
            row["head_user_id"] = ctx.heads[slug][name].id


def _generate_users(
    config: SeedConfig,
    ctx: OrgContext,
    rng: Rng,
    slug: str,
    company_id: Any,
    total: int,
    dept_ids: dict[str, Any],
    office_ids: dict[str, Any],
) -> list[UserRef]:
    per_dept = _allocate(total, DEPARTMENTS[slug])
    country_of = {o["code"]: o["country"] for o in OFFICES[slug]}
    domain = COMPANY_DOMAINS[slug]

    personas_here = {
        key: dept for key, (company, dept) in PERSONA_PLACEMENT.items() if company == slug
    }
    persona_by_dept: dict[str, list[str]] = {}
    for key, dept in personas_here.items():
        persona_by_dept.setdefault(dept, []).append(key)
    # Head-slot personas first, then the rest alphabetically, so the department
    # head is chosen by intent rather than by name.
    for keys in persona_by_dept.values():
        keys.sort(key=lambda key: (key not in HEAD_PERSONAS, key))

    users: list[UserRef] = []
    heads: dict[str, UserRef] = {}
    index = 0
    seen_emails: set[str] = set()

    def make_user(dept: str, title: str, band: str, role: str, persona: str | None) -> UserRef:
        nonlocal index
        index += 1
        natural_key = f"employee-{index:04d}"
        office_code = rng.weighted(OFFICE_WEIGHTS[slug])
        country = country_of[office_code]
        name = rng.person_name(country)

        base = name.lower().replace(" ", ".")
        email = f"{base}@{domain}"
        suffix = 2
        while email in seen_emails:  # names legitimately collide; ids must not
            email = f"{base}{suffix}@{domain}"
            suffix += 1
        seen_emails.add(email)

        low, high = SALARY_BANDS[band]
        hire_offset = rng.randint(120, 2600)
        return UserRef(
            id=derive("user", slug, natural_key, seed=config.seed),
            company_slug=slug,
            company_id=company_id,
            natural_key=natural_key,
            full_name=name,
            email=email,
            department=dept,
            department_id=dept_ids[dept],
            office_code=office_code,
            office_id=office_ids[office_code],
            country=country,
            employment_type=rng.weighted(EMPLOYMENT_TYPES),
            manager_id=None,
            job_title=title,
            salary_band=band,
            hire_date=config.reference_date - dt.timedelta(days=hire_offset),
            primary_role=_role_for(dept, persona),
            persona_key=persona,
        )

    # CEO first — the single manager-less user for this company (FR-034).
    # The CEO also carries the company-admin persona where one is placed in this
    # tenant: Executive Management is the smallest department, so at reduced volumes
    # there is no spare headcount for a separate admin user, and leaving the persona
    # unassigned would silently break the fixed persona set (FR-025b).
    admin_persona = None
    exec_personas = persona_by_dept.get("Executive Management", [])
    if "admin.company" in exec_personas:
        admin_persona = "admin.company"
        exec_personas.remove("admin.company")

    ceo = make_user(
        "Executive Management", "Chief Executive Officer", "B5", "Company Admin", admin_persona
    )
    ceo.primary_role = "Company Admin"
    ceo.is_manager = True
    users.append(ceo)
    heads["Executive Management"] = ceo

    for dept in sorted(per_dept):
        count = per_dept[dept]
        if dept == "Executive Management":
            count -= 1  # the CEO already occupies one slot
        if count <= 0:
            continue

        pending_personas = list(persona_by_dept.get(dept, []))
        titles = JOB_TITLES[dept]

        head = heads.get(dept)
        if head is None:
            head_persona = pending_personas.pop(0) if pending_personas else None
            head = make_user(dept, f"{dept} Lead", "B4", _role_for(dept, head_persona), head_persona)
            head.manager_id = ceo.id
            head.is_manager = True
            users.append(head)
            heads[dept] = head
            count -= 1

        # Departments beyond a certain size get team leads, so no manager ends up
        # with an implausible span of control and the Manager role is meaningful.
        leads: list[UserRef] = []
        if count > 12:
            for lead_index in range((count + 7) // 8):
                lead = make_user(dept, f"{dept} Team Lead", "B3", "Employee", None)
                lead.manager_id = head.id
                lead.is_manager = True
                users.append(lead)
                leads.append(lead)
                count -= 1
                if lead_index > 6:
                    break

        for member_index in range(max(0, count)):
            persona = pending_personas.pop(0) if pending_personas else None
            band = rng.weighted({"B1": 0.34, "B2": 0.38, "B3": 0.22, "B4": 0.06})
            member = make_user(dept, rng.choice(titles), band, "Employee", persona)
            member.manager_id = (
                leads[member_index % len(leads)].id if leads else head.id
            )
            users.append(member)

    _ensure_manager_persona_has_reports(users, heads)
    ctx.heads[slug] = heads
    return users


def _role_for(department: str, persona: str | None) -> str:
    if persona == "auditor.readonly":
        return "Auditor"
    if persona == "admin.company":
        return "Company Admin"
    if persona == "manager.engineering":
        return "Manager"
    return {
        "HR": "HR",
        "Finance": "Finance",
        "Legal": "Legal",
    }.get(department, "Employee")


MIN_MANAGER_REPORTS = 3


def _ensure_manager_persona_has_reports(users: list[UserRef], heads: dict[str, UserRef]) -> None:
    """`manager.engineering` must hold at least three direct reports (FR-025b).

    Enforced rather than attempted. The blueprint's manager-scope scenario is
    meaningless with fewer, so a dataset that cannot satisfy it is a generation
    failure that should be loud — not something a downstream test discovers later.
    """
    manager = next((u for u in users if u.persona_key == "manager.engineering"), None)
    if manager is None:
        return
    manager.is_manager = True

    # The employee persona is the one the blueprint's scenarios pair with this
    # manager, so it must actually be a direct report — otherwise "manager asks for
    # direct reports' leave" and "employee asks for their own" describe unrelated
    # people.
    employee = next((u for u in users if u.persona_key == "employee.engineering"), None)
    if employee is not None and employee.id != manager.id:
        employee.manager_id = manager.id

    def report_count() -> int:
        return sum(1 for u in users if u.manager_id == manager.id)

    if report_count() >= MIN_MANAGER_REPORTS:
        return

    # Prefer non-manager peers in the same department; fall back to anyone else in
    # that department who is not a persona, so the reports stay departmentally
    # coherent for the cross-department denial scenario.
    for allow_managers in (False, True):
        candidates = [
            u
            for u in users
            if u.department == manager.department
            and u.id != manager.id
            and u.persona_key is None
            and u.manager_id != manager.id
            and u.manager_id is not None
            and (allow_managers or not u.is_manager)
        ]
        for user in candidates:
            if report_count() >= MIN_MANAGER_REPORTS:
                break
            user.manager_id = manager.id
        if report_count() >= MIN_MANAGER_REPORTS:
            break

    if report_count() < MIN_MANAGER_REPORTS:
        raise ValueError(
            f"manager.engineering has {report_count()} direct reports but needs "
            f"{MIN_MANAGER_REPORTS}; the {manager.department} department is too small "
            "at this volume profile (FR-025b)"
        )
