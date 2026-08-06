"""Establish local demo credentials after seeding (spec 003 FR-002a, SC-014).

**A separate step from the generator, on purpose.** The generator leaves
``password_hash`` unset — it does so today for all 240 users — and this runs afterwards
against the database. That ordering is what keeps the dataset fingerprint stable: it is
computed from the in-process generated rows, not from the database, so a row written
after generation cannot reach it.

Hashing inside the seed would be worse in two ways at once. It would need a fixed salt
to stay byte-deterministic, weakening the hash by construction, *and* it would change
the generated row set, invalidating both committed fingerprints.

**Idempotence means something specific here.** The seed's idempotence is byte-identical
output. This command's cannot be — Argon2 salts are random per hash, so two runs
necessarily store different bytes. What is idempotent is the *observable outcome*:
after any number of runs the same password signs in and the row count is unchanged.

Rows are **rewritten, never skipped**. Skipping users that already have a hash would
make a changed ``--password`` silently not apply, which is a worse failure than the
rewrite — the operator would believe they had changed something and be wrong.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from eaios_core.models import User, UserCredential
from eaios_core.passwords import hash_password

__all__ = ["AmbiguousEmailError", "ProvisioningResult", "provision_credentials"]


class AmbiguousEmailError(RuntimeError):
    """One email address exists in more than one tenant.

    Sign-in resolves the tenant by looking the address up under each known company in
    turn, so a duplicate has no unambiguous answer. Refused here rather than handled at
    the sign-in form: making the ambiguity impossible in the data is a smaller and more
    honest fix than teaching the form to guess, and a generated dataset that produced
    one would be a generator bug worth seeing.
    """


@dataclass(frozen=True, slots=True)
class ProvisioningResult:
    written: int
    companies: int


def _now() -> dt.datetime:
    """Wall clock. Credentials are runtime state, not part of the pinned dataset, so
    the reference date does not apply."""
    return dt.datetime.now(tz=dt.UTC)


def _assert_unambiguous_emails(session: Session) -> None:
    duplicates = session.execute(
        text(
            "SELECT lower(email) AS address, count(*) AS n"
            " FROM users GROUP BY lower(email) HAVING count(*) > 1"
            " ORDER BY lower(email)"
        )
    ).all()
    if duplicates:
        listed = ", ".join(f"{row.address} ({row.n} tenants)" for row in duplicates[:5])
        raise AmbiguousEmailError(
            f"{len(duplicates)} email address(es) exist in more than one tenant: {listed}."
            " Sign-in resolves the tenant from the address, so these could not be"
            " resolved unambiguously."
        )


def provision_credentials(engine: Engine, password: str) -> ProvisioningResult:
    """Write one credential per active user. Returns what was done, for reporting.

    Runs on the **owner** engine. This is a maintenance command rather than a request
    path, and it deliberately spans both tenants in one transaction — the one thing an
    RLS-scoped session cannot do, and the reason the owner connection exists at all.
    """
    written = 0
    companies: set[uuid.UUID] = set()

    with Session(engine) as session, session.begin():
        _assert_unambiguous_emails(session)

        users = session.execute(
            select(User.id, User.company_id).where(User.is_active).order_by(User.id)
        ).all()

        existing = {
            row.user_id: row.id
            for row in session.execute(
                select(UserCredential.id, UserCredential.user_id)
            ).all()
        }

        now = _now()
        for user in users:
            # One hash per user, each with its own random salt. Hashing once and
            # reusing the value would be faster and would mean a single precomputation
            # broke every account at once.
            digest = hash_password(password)
            companies.add(user.company_id)

            if user.id in existing:
                session.execute(
                    text(
                        "UPDATE user_credentials SET password_hash = :h, updated_at = :t"
                        " WHERE id = :i"
                    ),
                    {"h": digest, "t": now, "i": existing[user.id]},
                )
            else:
                session.add(
                    UserCredential(
                        id=uuid.uuid4(),
                        company_id=user.company_id,
                        user_id=user.id,
                        password_hash=digest,
                        created_at=now,
                        updated_at=now,
                    )
                )
            written += 1

        # Users deactivated since the last run keep no credential. Removing them is the
        # difference between "cannot sign in because the check refuses" and "cannot sign
        # in because there is nothing to check" — and the second needs no check to be
        # correct.
        stale = set(existing) - {user.id for user in users}
        for user_id in stale:
            session.execute(
                text("DELETE FROM user_credentials WHERE user_id = :u"), {"u": user_id}
            )

    return ProvisioningResult(written=written, companies=len(companies))
