"""Platform determinism (spec FR-047b, SC-002; converge finding F2).

The pinned digest below is the value CI compares across operating systems. If a
change to the generation primitives moves it, that is either a deliberate dataset
change — in which case bump ``GENERATOR_VERSION`` and update this value — or an
accidental one, which is exactly what this is here to catch.
"""

from __future__ import annotations

import pytest

from eaios_core.selfcheck import platform_fingerprint

pytestmark = pytest.mark.unit

#: Computed on 2026-08-01 with ROOT_SEED=20260630. CI asserts the same value on
#: every platform in the matrix; a mismatch between two runners means a
#: platform-dependent code path crept into generation.
EXPECTED_PLATFORM_FINGERPRINT = (
    "6d0b5c64b3fd8e06c3158213b62e65f7e2d88491a8110cfe7187ed551e151fbf"
)


class TestPlatformFingerprint:
    def test_matches_the_pinned_value(self) -> None:
        assert platform_fingerprint() == EXPECTED_PLATFORM_FINGERPRINT

    def test_is_stable_within_a_process(self) -> None:
        assert platform_fingerprint() == platform_fingerprint()

    def test_a_different_seed_produces_a_different_digest(self) -> None:
        """Confirms the digest actually depends on its inputs — a constant that
        never changes would pass the pinned-value test while proving nothing."""
        assert platform_fingerprint(seed="not-the-committed-seed") != platform_fingerprint()

    def test_digest_is_hex_sha256(self) -> None:
        digest = platform_fingerprint()
        assert len(digest) == 64
        assert set(digest) <= set("0123456789abcdef")
