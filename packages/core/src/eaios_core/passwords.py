"""Password hashing and verification (spec 003 FR-002, FR-022).

**Why this lives in `packages/core` and not in the API.** Two workspace members need
it: the API verifies, and the seed's `credentials` command hashes. Spec 001 FR-001a
fixes the direction — `scripts/seed` may not import from `apps/api`, and code needed by
two members moves *down* into `packages/`, never sideways. Putting it in the API and
importing it from the seed is the exact violation
`tests/unit/test_dependency_direction.py` exists to catch.

**Argon2id**, with the library's default parameters. The encoded output carries the
algorithm, the parameters, and a per-hash random salt, so `verify` reads them from the
stored value rather than from configuration that could have drifted away from it, and a
later parameter change becomes a per-hash migration rather than a flag day.

**Constant work, not constant time.** `verify_password` and `verify_dummy` do the same
amount of work, so a caller that has no matching user can still pay the cost of a
verification. That closes the timing side channel FR-022 leaves open otherwise: a
sign-in form that returns the same generic message for "no such account" and "wrong
password" still answers "does this account exist?" in tens of milliseconds if the
unknown-account path skips the hash. This is not a claim of constant-time execution —
Argon2 is data-independent by design, but Python is not — it is a claim that the
expensive step happens either way.
"""

from __future__ import annotations

from typing import Final

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

__all__ = ["DUMMY_HASH", "hash_password", "verify_dummy", "verify_password"]

#: Library defaults, not hand-tuned. They track the maintainers' reading of current
#: guidance, which is a better source than a number chosen once and never revisited.
_HASHER: Final[PasswordHasher] = PasswordHasher()

#: Verified against when no user matches, so the unknown-account path costs what the
#: known-account path costs. Computed once at import: doing it per request would add a
#: hash to every sign-in *and* still leave the two paths asymmetric.
#:
#: The plaintext behind it is irrelevant and never compared against anything — only the
#: work of verifying it matters.
DUMMY_HASH: Final[str] = _HASHER.hash("eaios-dummy-verification-target")


def hash_password(password: str) -> str:
    """Hash a password for storage. Never logged, never returned, never audited."""
    return _HASHER.hash(password)


def verify_password(password: str, stored: str) -> bool:
    """True when ``password`` produced ``stored``.

    Returns a bool rather than raising, because every caller has the same response to
    every failure mode: refuse, identically. Distinguishing "wrong password" from
    "malformed stored value" at the call site is how a refusal starts leaking which
    accounts have credentials at all.
    """
    try:
        return _HASHER.verify(stored, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def verify_dummy(password: str) -> bool:
    """Do a verification's worth of work and return False.

    Called when no user matched, so the sign-in path performs the same work whether or
    not the account exists. Always False — a true result would be a bug in argon2, and
    treating it as meaningful would be worse.
    """
    verify_password(password, DUMMY_HASH)
    return False
