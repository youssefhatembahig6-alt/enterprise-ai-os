"""All seven prerequisites, or no first-token measurement (FR-035o, SC-055).

**The failure this prevents.** A first-token figure is only meaningful if you know what
produced it. Measure against an unidentified GPU and the number describes a machine nobody
promised; measure against unverified weights and it describes a model nobody pinned. Either
way you get a plausible number attached to nothing — worse than no number, because a
missing figure invites a question and a wrong one closes it.

So the rule is all-or-nothing: seven prerequisites, every one verified, before any sample is
taken. A run missing even one records `NOT RUN` or `INVALID`, never a pass.

**Why seven negatives and one positive.** The suite has to distinguish a correct verifier
from two degenerate ones. A verifier that refuses everything passes all seven negatives and
fails the positive. A verifier that accepts everything passes the positive and fails all
seven negatives. Only something that actually reads each prerequisite passes all eight.

**Network-free.** Every case runs against a fake probe. Verifying provisioning must not
itself require the thing being provisioned, or the check could never run in ordinary CI —
and the checking logic is exactly what benefits from being exercised on every commit
(FR-035b).
"""

from __future__ import annotations

import dataclasses

import pytest

from benchmarks.phase0.server_provisioning import (
    PREREQUISITES,
    Prerequisite,
    ProvisioningProbe,
    Verdict,
    verify,
)

pytestmark = pytest.mark.unit


@dataclasses.dataclass(frozen=True)
class FakeProbe:
    """A fully provisioned server, with any single prerequisite withholdable.

    Defaults are the satisfied state, so a test names only what it takes away — which
    makes the withheld thing the visible part of each case.
    """

    weights_revision: str | None = "7dabda4d13d513e3e842b20f0d435c732f172cbe"
    weights_checksum: str | None = (
        "626b4a6678b86442240e33df819e00132d3ba7dddfe1cdc4fbb18e0a9615c62d"
    )
    endpoint_url: str | None = "https://example-tunnel.ngrok.app"
    service_token: str | None = "a-service-token-from-ignored-env"
    gpu_name: str | None = "Tesla T4"
    runtime_identity: str | None = "llama.cpp/b4123"
    quantization: str | None = "Q4_K_M"
    health_ok: bool = True
    streams_first_token: bool = True

    def observe(self) -> dict[str, object]:
        return dataclasses.asdict(self)


def _probe(**withheld: object) -> ProvisioningProbe:
    return FakeProbe(**withheld)  # type: ignore[arg-type]


#: Each case: the prerequisite under test, and the fields that withhold exactly it.
WITHHOLDING: tuple[tuple[Prerequisite, dict[str, object]], ...] = (
    (Prerequisite.PINNED_WEIGHTS, {"weights_revision": None}),
    (Prerequisite.PINNED_WEIGHTS, {"weights_checksum": None}),
    (Prerequisite.HTTPS_ENDPOINT, {"endpoint_url": None}),
    (Prerequisite.SERVICE_TOKEN, {"service_token": None}),
    (Prerequisite.VERIFIED_T4, {"gpu_name": None}),
    (Prerequisite.RUNTIME_IDENTITY, {"runtime_identity": None}),
    (Prerequisite.RUNTIME_IDENTITY, {"quantization": None}),
    (Prerequisite.HEALTH_ENDPOINT, {"health_ok": False}),
    (Prerequisite.STREAMING_PROTOCOL, {"streams_first_token": False}),
)


class TestThereAreExactlySevenPrerequisites:
    """FR-035o enumerates seven. Six would mean one is unchecked; eight would be invented."""

    def test_seven(self) -> None:
        assert len(PREREQUISITES) == 7, f"expected 7 prerequisites, found {len(PREREQUISITES)}"

    def test_each_is_distinct(self) -> None:
        assert len(set(PREREQUISITES)) == 7

    def test_every_prerequisite_has_a_withholding_case(self) -> None:
        """Falsification of the suite itself: an unwithheld prerequisite is unchecked."""
        covered = {prerequisite for prerequisite, _ in WITHHOLDING}
        assert covered == set(PREREQUISITES), (
            f"no test withholds {set(PREREQUISITES) - covered}, so nothing proves the"
            " verifier reads it"
        )


class TestTheFullyProvisionedCase:
    """The positive. Without it, a verifier that always refuses would pass this file."""

    def test_all_seven_present_permits_measurement(self) -> None:
        report = verify(_probe())
        assert report.missing == (), f"a complete probe reported missing: {report.missing}"
        assert report.verdict is Verdict.READY
        assert report.permits_measurement is True

    def test_all_seven_are_reported_satisfied(self) -> None:
        assert set(verify(_probe()).satisfied) == set(PREREQUISITES)

    def test_the_report_records_what_it_verified(self) -> None:
        """A verdict with no attribution is not evidence (FR-011b)."""
        report = verify(_probe())
        assert report.observed["weights_revision"] == ("7dabda4d13d513e3e842b20f0d435c732f172cbe")
        assert report.observed["quantization"] == "Q4_K_M"
        assert report.observed["gpu_name"] == "Tesla T4"


class TestEachMissingPrerequisiteBlocksMeasurement:
    """The seven negatives, one per withheld prerequisite."""

    @pytest.mark.parametrize(
        ("expected", "withheld"),
        WITHHOLDING,
        ids=[f"{p.value}-{next(iter(w))}" for p, w in WITHHOLDING],
    )
    def test_withholding_one_prevents_measurement(
        self, expected: Prerequisite, withheld: dict[str, object]
    ) -> None:
        report = verify(_probe(**withheld))

        assert report.permits_measurement is False, (
            f"measurement was permitted with {expected.value} withheld via {withheld}"
        )
        assert report.verdict is not Verdict.READY
        assert expected in report.missing, (
            f"withholding {withheld} did not report {expected.value} missing;"
            f" reported {[m.value for m in report.missing]}"
        )

    @pytest.mark.parametrize(
        ("expected", "withheld"),
        WITHHOLDING,
        ids=[f"{p.value}-{next(iter(w))}" for p, w in WITHHOLDING],
    )
    def test_the_missing_prerequisite_is_named(
        self, expected: Prerequisite, withheld: dict[str, object]
    ) -> None:
        """Named, not counted. "3 of 7 satisfied" does not tell anyone what to fix."""
        assert expected.value in verify(_probe(**withheld)).describe()

    @pytest.mark.parametrize(
        ("expected", "withheld"),
        WITHHOLDING,
        ids=[f"{p.value}-{next(iter(w))}" for p, w in WITHHOLDING],
    )
    def test_the_other_prerequisites_still_pass(
        self, expected: Prerequisite, withheld: dict[str, object]
    ) -> None:
        """Withholding one must not cascade; otherwise the report cannot be acted on."""
        report = verify(_probe(**withheld))
        assert set(report.satisfied) == set(PREREQUISITES) - {expected}, (
            f"withholding {withheld} knocked out more than {expected.value}:"
            f" missing {[m.value for m in report.missing]}"
        )


class TestTheGpuMustBeTheDeclaredClass:
    """FR-035c: the T4 is the reference class. Anything else is INVALID, never a pass."""

    def test_a_cpu_only_allocation_is_invalid(self) -> None:
        report = verify(_probe(gpu_name="CPU"))
        assert report.verdict is Verdict.INVALID
        assert report.permits_measurement is False

    def test_an_unidentified_gpu_is_invalid(self) -> None:
        report = verify(_probe(gpu_name="Unknown Device"))
        assert report.verdict is Verdict.INVALID

    def test_a_faster_gpu_is_also_invalid(self) -> None:
        """The reading that matters: the T4 is a reference class, not a floor.

        An A100 proves the answers are reachable and says nothing about whether the
        threshold holds on the class it was defined against, so it cannot pass the gate.
        """
        report = verify(_probe(gpu_name="NVIDIA A100-SXM4-40GB"))
        assert report.verdict is Verdict.INVALID, (
            "a faster GPU was accepted; the resulting figure would describe a machine"
            " the threshold was never defined against (FR-043a)"
        )
        assert report.permits_measurement is False

    def test_the_declared_t4_is_accepted(self) -> None:
        for name in ("Tesla T4", "NVIDIA T4", "Tesla T4 16GB"):
            assert verify(_probe(gpu_name=name)).verdict is Verdict.READY, name


class TestTheEndpointMustBeAuthenticatedHttps:
    def test_plain_http_is_refused(self) -> None:
        report = verify(_probe(endpoint_url="http://example-tunnel.ngrok.app"))
        assert Prerequisite.HTTPS_ENDPOINT in report.missing
        assert report.permits_measurement is False

    def test_https_is_accepted(self) -> None:
        assert verify(_probe()).permits_measurement is True


class TestDegenerateVerifiersCannotPass:
    """States the two failure modes the eight cases exist to separate."""

    def test_a_blanket_refusal_fails_the_positive(self) -> None:
        assert verify(_probe()).permits_measurement is True

    def test_a_blanket_acceptance_fails_every_negative(self) -> None:
        refused = [verify(_probe(**withheld)).permits_measurement for _, withheld in WITHHOLDING]
        assert not any(refused), f"some withheld case still permitted measurement: {refused}"
