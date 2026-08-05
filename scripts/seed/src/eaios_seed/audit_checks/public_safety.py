"""Public content carries nothing sensitive (spec SC-011).

`PUBLIC` is the one classification an unauthenticated visitor may ever see, so
anything that reaches it is effectively published. This scans every public row and
file for the four categories the specification names: salary figures, contract
terms, internal financial data, and personal contact details of non-executive staff.

Detection is pattern-based, which means it can produce false positives on innocent
prose. That trade is deliberate: for a surface where a miss is a disclosure and a
false alarm is a minute of review, over-flagging is the cheaper error.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import Engine, text

__all__ = ["SENSITIVE_PATTERNS", "PublicSafetyReport", "scan_public_content"]

#: A figure: grouped thousands, three-or-more digits, or a decimal amount.
_FIGURE = r"(?:\d{1,3}(?:[,\s]\d{3})+|\d{3,}|\d+\.\d{2})"

#: (label, pattern).
#:
#: The financial categories require a *figure* nearby. SC-011 forbids salary
#: figures and internal financial data — not the vocabulary. "Manage the marketing
#: budget" is ordinary job-posting language; "budget of 250,000" is a disclosure.
#: Flagging the bare word produced a false positive on generated prose and would
#: have trained readers to ignore the check, which is worse than not having it.
SENSITIVE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "salary figure",
        re.compile(
            rf"\b(?:salary|payroll|compensation|remuneration)\b.{{0,40}}{_FIGURE}"
            rf"|{_FIGURE}.{{0,40}}\b(?:salary|payroll|compensation)\b",
            re.I | re.S,
        ),
    ),
    (
        "internal financial",
        re.compile(
            rf"\b(?:revenue|budget|expense|invoice|margin)\b.{{0,40}}{_FIGURE}"
            rf"|{_FIGURE}.{{0,40}}\b(?:revenue|budget|expense|margin)\b",
            re.I | re.S,
        ),
    ),
    # These need no accompanying figure — each is inherently internal.
    ("salary band", re.compile(r"\bband\s*B[1-5]\b", re.I)),
    ("contract term", re.compile(r"\b(liability cap|notice period|governing law|NET_\d+)\b", re.I)),
    ("email address", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")),
    ("phone number", re.compile(r"\+\d{6,}")),
    ("confidentiality marker", re.compile(r"\b(RESTRICTED|CONFIDENTIAL)\b")),
)

#: Public pages legitimately carry a general enquiries address. Anything matching
#: this is a company mailbox, not a person's contact detail.
_ALLOWED_EMAIL = re.compile(r"\b(hello|info|contact|careers)@", re.I)


@dataclass
class PublicSafetyReport:
    findings: list[str] = field(default_factory=list)
    scanned_rows: int = 0
    scanned_files: int = 0

    @property
    def clean(self) -> bool:
        return not self.findings

    def describe(self) -> str:
        if self.clean:
            return (
                f"OK   public content: {self.scanned_rows} row(s) and "
                f"{self.scanned_files} file(s) clean"
            )
        lines = ["FAIL public content:"]
        lines += [f"     {item}" for item in self.findings]
        return "\n".join(lines)


def _inspect(location: str, body: str, report: PublicSafetyReport) -> None:
    for label, pattern in SENSITIVE_PATTERNS:
        match = pattern.search(body)
        if not match:
            continue
        if label == "email address" and _ALLOWED_EMAIL.search(match.group(0)):
            continue
        report.findings.append(f"{location}: {label} — {match.group(0)!r}")


#: Public-facing tables and the columns a visitor would actually read.
_PUBLIC_TABLES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("services", ("name", "summary", "description")),
    ("public_products", ("name", "tagline", "description")),
    ("leadership_profiles", ("public_title", "bio")),
    ("news_items", ("headline", "body")),
    ("vacancies", ("title", "description")),
)


def scan_public_content(engine: Engine, files: dict[str, bytes] | None = None) -> PublicSafetyReport:
    """Scan public rows, and optionally public files, for sensitive content."""
    report = PublicSafetyReport()

    with engine.connect() as conn:
        for table, columns in _PUBLIC_TABLES:
            rows = conn.execute(
                text(f"SELECT id, {', '.join(columns)} FROM {table}")
            ).mappings().all()
            for row in rows:
                report.scanned_rows += 1
                for column in columns:
                    value = row[column]
                    if value:
                        _inspect(f"{table}.{column} ({row['id']})", str(value), report)

    for key, content in (files or {}).items():
        if "/PUBLIC/" not in key:
            continue
        report.scanned_files += 1
        _inspect(key, content.decode("utf-8", errors="replace"), report)

    return report
