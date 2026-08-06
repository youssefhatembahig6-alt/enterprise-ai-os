"""Password hashing and verification (spec 003 FR-002, FR-022).

FR-002 is deliberately worded as a property rather than an algorithm: "a stored value
that can be reversed to the original credential is a defect regardless of how the
storage is described". So the tests here check the property — the stored value is not
the password, two hashes of the same password differ, and the wrong password fails —
rather than checking that a particular library was called.

The last class is the one that is easy to leave out. FR-022 requires that a refusal
not distinguish "no such account" from "wrong credentials", and a response body that
satisfies that still answers the question in tens of milliseconds if the
unknown-account path skips the hash. The fix is a dummy verification, and it only works
if it actually runs.
"""

from __future__ import annotations

import pytest

from eaios_core.passwords import DUMMY_HASH, hash_password, verify_dummy, verify_password

pytestmark = pytest.mark.unit

PASSWORD = "eaios-demo-local-only"


class TestTheStoredValueIsNotThePassword:
    def test_the_hash_does_not_contain_the_password(self) -> None:
        assert PASSWORD not in hash_password(PASSWORD)

    def test_the_hash_is_argon2id(self) -> None:
        """Named rather than inferred. The encoded prefix carries the algorithm and the
        parameters, so this also pins that a future change to weaker settings is a
        visible diff rather than a silent one."""
        stored = hash_password(PASSWORD)
        assert stored.startswith("$argon2id$"), stored

    def test_the_parameters_are_carried_in_the_value(self) -> None:
        """`verify` reads cost parameters from the stored string, not from
        configuration. That is what makes a later parameter change a per-hash migration
        instead of a flag day — and what stops configuration drifting away from what
        was actually used."""
        stored = hash_password(PASSWORD)
        assert "m=" in stored and "t=" in stored and "p=" in stored, stored

    def test_two_hashes_of_the_same_password_differ(self) -> None:
        """Per-hash random salt. Equal hashes would mean a shared salt, which makes one
        precomputation break every account at once."""
        assert hash_password(PASSWORD) != hash_password(PASSWORD)


class TestVerification:
    def test_the_right_password_verifies(self) -> None:
        assert verify_password(PASSWORD, hash_password(PASSWORD)) is True

    def test_the_wrong_password_does_not(self) -> None:
        assert verify_password("not-the-password", hash_password(PASSWORD)) is False

    def test_an_empty_password_does_not(self) -> None:
        assert verify_password("", hash_password(PASSWORD)) is False

    def test_a_near_miss_does_not(self) -> None:
        """One character. Stated because a comparison that truncated or normalised
        would pass every test above and fail only here."""
        assert verify_password(PASSWORD + "x", hash_password(PASSWORD)) is False
        assert verify_password(PASSWORD.upper(), hash_password(PASSWORD)) is False

    @pytest.mark.parametrize(
        "stored",
        ["", "not-a-hash", "$argon2id$broken", "$2b$12$abcdefghijklmnopqrstuv"],
        ids=["empty", "garbage", "truncated-argon2", "a-bcrypt-hash"],
    )
    def test_a_malformed_stored_value_returns_false_rather_than_raising(
        self, stored: str
    ) -> None:
        """Every caller has the same response to every failure mode: refuse,
        identically. Raising here would let a malformed row produce a 500 while a wrong
        password produced a 401 — which tells an attacker which accounts have
        credentials at all."""
        assert verify_password(PASSWORD, stored) is False


class TestTheConstantWorkPath:
    """FR-022's timing half.

    A sign-in form returning one generic message for "no such account" and "wrong
    password" still answers "does this account exist?" with a stopwatch, if the
    unknown-account path returns without hashing. `verify_dummy` closes that.
    """

    def test_the_dummy_hash_is_a_real_argon2_hash(self) -> None:
        """If it were a placeholder string, `verify_dummy` would fail fast on a
        malformed value and do none of the work it exists to do — the timing gap would
        be exactly as wide as before, with a function named as though it were closed."""
        assert DUMMY_HASH.startswith("$argon2id$"), DUMMY_HASH

    def test_the_dummy_hash_has_the_same_parameters_as_a_real_one(self) -> None:
        """Same cost, or the work is not the same work. Compared by the parameter
        segment of the encoding rather than by timing, because a wall-clock comparison
        on a loaded runner is exactly the flaky, low-power check this avoids."""
        real = hash_password(PASSWORD)
        assert DUMMY_HASH.split("$")[3] == real.split("$")[3], (
            f"dummy parameters {DUMMY_HASH.split('$')[3]} differ from"
            f" {real.split('$')[3]}"
        )

    def test_it_always_returns_false(self) -> None:
        assert verify_dummy(PASSWORD) is False
        assert verify_dummy("anything at all") is False

    def test_it_performs_a_verification(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The structural version of the timing claim.

        Rather than measuring elapsed time — which is flaky and proves little on a busy
        machine — this counts the verifications. `verify_dummy` must make one, or the
        unknown-account path is cheaper than the known-account path and the enumeration
        gap is open.
        """
        from argon2 import PasswordHasher

        calls: list[str] = []
        # Patched on the class, not the instance: `PasswordHasher` uses `__slots__`, so
        # the module-level hasher has no `__dict__` to set an attribute on.
        original = PasswordHasher.verify

        def counting(self: PasswordHasher, stored: str, password: str) -> bool:
            calls.append(stored)
            return bool(original(self, stored, password))

        monkeypatch.setattr(PasswordHasher, "verify", counting)
        verify_dummy("whatever")

        assert len(calls) == 1, f"verify_dummy performed {len(calls)} verifications"
        assert calls[0] == DUMMY_HASH
