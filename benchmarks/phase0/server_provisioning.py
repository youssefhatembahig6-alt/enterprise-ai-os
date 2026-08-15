"""Verify all seven FR-035o prerequisites before any first-token sample (SC-055).

**Why this gate exists at all.** A latency figure is a claim about a specific model, on
specific hardware, behind a specific runtime. Take the sample before establishing those and
you get a number that looks like evidence and attributes to nothing. That is worse than no
number: an absent figure invites the question, a wrong one closes it.

So the rule is all-or-nothing. Seven prerequisites, each verified, before the first sample.
A run missing even one records `NOT RUN` or `INVALID` — never a pass.

**The T4 is a reference class, not a floor** (FR-035c, FR-043a). This is the part that reads
backwards at first: a *faster* GPU is rejected too. An A100 proves the answers are reachable
and says nothing about whether the threshold holds on the hardware it was defined against,
so accepting it would mean publishing a figure that describes a machine nobody promised.

**Network-free by construction.** This module verifies observations; it does not make them.
Whatever gathers them — a live probe against the tunnel, or a fake in a test — is passed in.
That is what lets the verification logic run in ordinary CI, which is the code most worth
exercising on every commit (FR-035b).
"""

from __future__ import annotations

import dataclasses
import enum
import re
from typing import Any, Final, Protocol

__all__ = [
    "PREREQUISITES",
    "Prerequisite",
    "ProvisioningProbe",
    "ProvisioningReport",
    "Verdict",
    "verify",
]


class Prerequisite(enum.StrEnum):
    """The seven things FR-035o requires before a first-token measurement."""

    PINNED_WEIGHTS = "pinned-weights"
    HTTPS_ENDPOINT = "https-endpoint"
    SERVICE_TOKEN = "service-token"
    VERIFIED_T4 = "verified-t4"
    RUNTIME_IDENTITY = "runtime-identity"
    HEALTH_ENDPOINT = "health-endpoint"
    STREAMING_PROTOCOL = "streaming-protocol"


#: In FR-035o's order, so the report reads like the requirement.
PREREQUISITES: Final[tuple[Prerequisite, ...]] = (
    Prerequisite.PINNED_WEIGHTS,
    Prerequisite.HTTPS_ENDPOINT,
    Prerequisite.SERVICE_TOKEN,
    Prerequisite.VERIFIED_T4,
    Prerequisite.RUNTIME_IDENTITY,
    Prerequisite.HEALTH_ENDPOINT,
    Prerequisite.STREAMING_PROTOCOL,
)


class Verdict(enum.StrEnum):
    """What the provisioning state permits.

    `NOT_RUN` and `INVALID` are distinct on purpose. `NOT_RUN` means something was not
    provisioned — an absence someone can go and fix. `INVALID` means something *was*
    provisioned and is the wrong thing, which is a different conversation. Neither is a
    pass, and the gate treats them identically; the distinction is for the human reading
    the record afterwards.
    """

    READY = "READY"
    NOT_RUN = "NOT RUN"
    INVALID = "INVALID"


class ProvisioningProbe(Protocol):
    """Whatever can report the observed state of the generation server."""

    def observe(self) -> dict[str, Any]:
        """Observed fields. Absent or falsy values mean *not provisioned*."""


#: Accepted GPU names. Anchored so "T4" does not match "RTX 4090" or "T400".
_T4_PATTERN: Final[re.Pattern[str]] = re.compile(r"\b(?:tesla\s+)?t4\b", re.IGNORECASE)

#: A 40-character git commit SHA. A branch name is not a pin.
_REVISION_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")

#: A 64-character SHA-256 digest.
_CHECKSUM_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")


@dataclasses.dataclass(frozen=True, slots=True)
class ProvisioningReport:
    """What was verified, what was not, and whether measurement may proceed."""

    satisfied: tuple[Prerequisite, ...]
    missing: tuple[Prerequisite, ...]
    verdict: Verdict
    observed: dict[str, Any]
    notes: tuple[str, ...] = ()

    @property
    def permits_measurement(self) -> bool:
        """True only when all seven are satisfied and nothing is the wrong thing."""
        return not self.missing and self.verdict is Verdict.READY

    def describe(self) -> str:
        """A human-readable account naming every missing prerequisite.

        Named rather than counted: "3 of 7 satisfied" tells nobody what to go and fix.
        """
        if self.permits_measurement:
            return "READY — all seven FR-035o prerequisites verified"
        lines = [f"{self.verdict.value} — first-token measurement is not permitted"]
        for prerequisite in self.missing:
            lines.append(f"  missing: {prerequisite.value}")
        lines.extend(f"  note: {note}" for note in self.notes)
        return "\n".join(lines)


def _text(observed: dict[str, Any], key: str) -> str:
    value = observed.get(key)
    return value.strip() if isinstance(value, str) else ""


def verify(probe: ProvisioningProbe) -> ProvisioningReport:
    """Check all seven prerequisites against one set of observations.

    Every prerequisite is evaluated independently, so a single absence does not cascade
    into six others. A report that blames everything is a report nobody can act on.
    """
    observed = dict(probe.observe())
    satisfied: list[Prerequisite] = []
    missing: list[Prerequisite] = []
    notes: list[str] = []
    invalid = False

    revision = _text(observed, "weights_revision")
    checksum = _text(observed, "weights_checksum")
    if _REVISION_PATTERN.match(revision) and _CHECKSUM_PATTERN.match(checksum):
        satisfied.append(Prerequisite.PINNED_WEIGHTS)
    else:
        missing.append(Prerequisite.PINNED_WEIGHTS)
        if revision and not _REVISION_PATTERN.match(revision):
            invalid = True
            notes.append(f"weights_revision {revision!r} is not a 40-character commit SHA")
        if checksum and not _CHECKSUM_PATTERN.match(checksum):
            invalid = True
            notes.append(f"weights_checksum {checksum!r} is not a SHA-256 digest")

    endpoint = _text(observed, "endpoint_url")
    if endpoint.startswith("https://"):
        satisfied.append(Prerequisite.HTTPS_ENDPOINT)
    else:
        missing.append(Prerequisite.HTTPS_ENDPOINT)
        if endpoint:
            invalid = True
            notes.append(
                f"endpoint {endpoint!r} is not HTTPS; a plaintext tunnel exposes the"
                " service token and every passage sent through it"
            )

    if _text(observed, "service_token"):
        satisfied.append(Prerequisite.SERVICE_TOKEN)
    else:
        missing.append(Prerequisite.SERVICE_TOKEN)

    gpu = _text(observed, "gpu_name")
    if _T4_PATTERN.search(gpu):
        satisfied.append(Prerequisite.VERIFIED_T4)
    else:
        missing.append(Prerequisite.VERIFIED_T4)
        if gpu:
            # Present but not the declared class. Includes *faster* hardware: the T4 is
            # the reference class the threshold is defined against, not a bar to clear.
            invalid = True
            notes.append(
                f"GPU {gpu!r} is not the declared T4 reference class. A different"
                " allocation — faster or slower — produces a figure that describes"
                " hardware the threshold was never defined against (FR-035c, FR-043a)"
            )

    if _text(observed, "runtime_identity") and _text(observed, "quantization"):
        satisfied.append(Prerequisite.RUNTIME_IDENTITY)
    else:
        missing.append(Prerequisite.RUNTIME_IDENTITY)

    if bool(observed.get("health_ok")):
        satisfied.append(Prerequisite.HEALTH_ENDPOINT)
    else:
        missing.append(Prerequisite.HEALTH_ENDPOINT)

    if bool(observed.get("streams_first_token")):
        satisfied.append(Prerequisite.STREAMING_PROTOCOL)
    else:
        missing.append(Prerequisite.STREAMING_PROTOCOL)

    if not missing:
        verdict = Verdict.READY
    elif invalid:
        verdict = Verdict.INVALID
    else:
        verdict = Verdict.NOT_RUN

    order = {prerequisite: index for index, prerequisite in enumerate(PREREQUISITES)}
    return ProvisioningReport(
        satisfied=tuple(sorted(satisfied, key=order.__getitem__)),
        missing=tuple(sorted(missing, key=order.__getitem__)),
        verdict=verdict,
        observed=observed,
        notes=tuple(notes),
    )
