"""Everything the Phase 0 measurement assumes, checked before it starts (FR-001, FR-035a).

A benchmark that starts against a half-prepared environment does not fail cleanly. It
fails a minute in, from inside a model loader or a store client, with a message about a
missing file rather than about the environment — and sometimes it does not fail at all: it
measures the smoke profile's 12 documents and reports a latency figure that describes a
corpus nobody meant to measure. That second outcome is the dangerous one, because the
number looks fine.

So every assumption is named and checked first:

* PostgreSQL, MinIO and Qdrant reachable
* the active seed profile is **`full`**
* exactly **105** text documents available
* the **code corpus excluded** — it is deliberately empty this feature (FR-001a)
* every required source object **readable** from MinIO
* local **BGE weights present**, with the pinned **revision and checksum verified**

**The environment is injected.** This module decides; something else observes. That split
is what lets the deciding logic — the part with the interesting failure modes — run in
ordinary CI with no stack at all (FR-035b).
"""

from __future__ import annotations

import dataclasses
from typing import Any, Final, Protocol

__all__ = [
    "EXPECTED_DOCUMENT_COUNT",
    "EXPECTED_PROFILE",
    "Environment",
    "PreflightCheck",
    "PreflightReport",
    "run",
]

#: The full profile's text corpus. Not a lower bound — a different count is a different
#: corpus, and a latency figure over a different corpus is not the declared measurement.
EXPECTED_DOCUMENT_COUNT: Final[int] = 105

#: `make seed` defaults to `full`; the smoke profile holds far fewer documents.
EXPECTED_PROFILE: Final[str] = "full"

#: From `docs/models.md`, verified against the authoritative model card.
EXPECTED_WEIGHTS_REVISION: Final[str] = "5617a9f61b028005a4858fdac845db406aefb181"
EXPECTED_WEIGHTS_CHECKSUM: Final[str] = (
    "b5e0ce3470abf5ef3831aa1bd5553b486803e83251590ab7ff35a117cf6aad38"
)


class Environment(Protocol):
    """Whatever can report the observed state of the local stack and weights."""

    def observe(self) -> dict[str, Any]:
        """Observed fields; see `run` for the keys it reads."""


@dataclasses.dataclass(frozen=True, slots=True)
class PreflightCheck:
    """One named prerequisite and its outcome."""

    name: str
    ok: bool
    detail: str = ""


@dataclasses.dataclass(frozen=True, slots=True)
class PreflightReport:
    """Every check, and whether the benchmark may proceed."""

    checks: tuple[PreflightCheck, ...]

    @property
    def failures(self) -> tuple[PreflightCheck, ...]:
        return tuple(check for check in self.checks if not check.ok)

    @property
    def ok(self) -> bool:
        return not self.failures

    @property
    def exit_code(self) -> int:
        """`2` rather than `1`, so a preflight refusal is distinguishable from a missed
        threshold — the first is an environment problem, the second is a result."""
        return 0 if self.ok else 2

    def describe(self) -> str:
        if self.ok:
            return f"preflight passed — {len(self.checks)} checks"
        lines = ["preflight failed; the benchmark did not start"]
        lines.extend(f"  {check.name}: {check.detail}" for check in self.failures)
        return "\n".join(lines)


def run(environment: Environment) -> PreflightReport:
    """Check every prerequisite, independently.

    Independently matters: one broken thing must produce one failure. A report that blames
    six things when one is wrong is a report nobody reads twice.
    """
    observed = dict(environment.observe())
    checks: list[PreflightCheck] = []

    for service in ("postgres", "minio", "qdrant"):
        reachable = bool(observed.get(f"{service}_reachable"))
        checks.append(
            PreflightCheck(
                name=f"{service} reachable",
                ok=reachable,
                detail="" if reachable else f"{service} is not reachable; run `make up`",
            )
        )

    profile = str(observed.get("active_profile") or "")
    checks.append(
        PreflightCheck(
            name="seed profile",
            ok=profile == EXPECTED_PROFILE,
            detail=(
                ""
                if profile == EXPECTED_PROFILE
                else f"active profile is {profile or '<none>'!r}, expected"
                f" {EXPECTED_PROFILE!r}; the declared measurement is over the full corpus"
            ),
        )
    )

    text_documents = int(observed.get("text_document_count") or 0)
    checks.append(
        PreflightCheck(
            name="text corpus size",
            ok=text_documents == EXPECTED_DOCUMENT_COUNT,
            detail=(
                ""
                if text_documents == EXPECTED_DOCUMENT_COUNT
                else f"found {text_documents} text documents, expected exactly"
                f" {EXPECTED_DOCUMENT_COUNT}"
            ),
        )
    )

    code_documents = int(observed.get("code_document_count") or 0)
    checks.append(
        PreflightCheck(
            name="code corpus excluded",
            ok=code_documents == 0,
            detail=(
                ""
                if code_documents == 0
                else f"found {code_documents} code documents; the code corpus is"
                " deliberately empty for this feature (FR-001a)"
            ),
        )
    )

    unreadable = tuple(observed.get("unreadable_objects") or ())
    checks.append(
        PreflightCheck(
            name="source objects readable",
            ok=not unreadable,
            detail=(
                ""
                if not unreadable
                else f"{len(unreadable)} source object(s) are not readable from MinIO:"
                f" {', '.join(map(str, unreadable[:5]))}"
            ),
        )
    )

    revision = str(observed.get("weights_revision") or "")
    checks.append(
        PreflightCheck(
            name="BGE weights revision",
            ok=revision == EXPECTED_WEIGHTS_REVISION,
            detail=(
                ""
                if revision == EXPECTED_WEIGHTS_REVISION
                else f"weights revision is {revision or '<absent>'!r}, expected the pinned"
                f" {EXPECTED_WEIGHTS_REVISION!r}; see docs/models.md"
            ),
        )
    )

    checksum = str(observed.get("weights_checksum") or "")
    checks.append(
        PreflightCheck(
            name="BGE weights checksum",
            ok=checksum == EXPECTED_WEIGHTS_CHECKSUM,
            detail=(
                ""
                if checksum == EXPECTED_WEIGHTS_CHECKSUM
                else f"weights checksum is {checksum or '<absent>'!r}, expected the pinned"
                f" {EXPECTED_WEIGHTS_CHECKSUM!r}. An unverified download is a guess about"
                " what will run (FR-011f)"
            ),
        )
    )

    return PreflightReport(checks=tuple(checks))
