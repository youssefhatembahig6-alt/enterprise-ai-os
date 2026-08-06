"""Minting and verifying session credentials (spec 003 FR-003, FR-019).

FR-003 lists what every protected request must verify *before anything else*:
signature, issuer, audience, expiry, token type. This file covers the token half of
that list — the active-user and tenant-membership half is a database question and lives
in the integration suite.

The round trip is the easy part. What matters is that each check can actually refuse,
so every rejection test mutates exactly one property of an otherwise-valid token and a
control asserts the unmutated token is accepted. Without the control, an implementation
that rejected everything would pass every rejection test in the file.
"""

from __future__ import annotations

import datetime as dt
import uuid

import jwt
import pytest

from eaios_api.auth.tokens import InvalidTokenError, mint_access_token, verify_access_token
from eaios_core.settings import get_settings

pytestmark = pytest.mark.unit


def _claims() -> dict[str, object]:
    issued = dt.datetime.now(tz=dt.UTC)
    return {
        "user_id": uuid.uuid4(),
        "company_id": uuid.uuid4(),
        "session_id": uuid.uuid4(),
        "issued_at": issued,
        "expires_at": issued + dt.timedelta(hours=8),
    }


def _valid_token() -> tuple[str, dict[str, object]]:
    fields = _claims()
    return mint_access_token(**fields), fields  # type: ignore[arg-type]


class TestTheRoundTrip:
    def test_a_minted_token_verifies(self) -> None:
        token, _ = _valid_token()
        assert verify_access_token(token) is not None

    def test_every_identifier_survives_the_round_trip(self) -> None:
        """The token's whole job is carrying these three. A claim silently dropped
        would surface much later as a lookup returning nothing, which reads as a
        permissions problem rather than a token one."""
        token, fields = _valid_token()
        claims = verify_access_token(token)
        assert claims.user_id == fields["user_id"]
        assert claims.company_id == fields["company_id"]
        assert claims.session_id == fields["session_id"]

    def test_the_expiry_survives_to_the_second(self) -> None:
        token, fields = _valid_token()
        claims = verify_access_token(token)
        expected = fields["expires_at"]
        assert isinstance(expected, dt.datetime)
        assert abs((claims.expires_at - expected).total_seconds()) < 1

    def test_the_token_carries_no_password_or_name(self) -> None:
        """A JWT is signed, not encrypted — anyone holding it can read every claim. It
        must therefore carry identifiers and nothing else (FR-018)."""
        token, _ = _valid_token()
        payload = jwt.decode(token, options={"verify_signature": False})
        for field in ("password", "password_hash", "email", "full_name"):
            assert field not in payload, f"{field} is readable by anyone holding the token"


class TestEachCheckCanRefuse:
    """One property mutated per case. The control below is what makes these mean
    anything."""

    def test_the_control_is_accepted(self) -> None:
        token, _ = _valid_token()
        assert verify_access_token(token) is not None

    def test_a_forged_signature_is_refused(self) -> None:
        settings = get_settings()
        payload = jwt.decode(
            _valid_token()[0],
            settings.auth.jwt_signing_key.get_secret_value(),
            algorithms=["HS256"],
            audience=settings.auth.jwt_audience,
            issuer=settings.auth.jwt_issuer,
        )
        forged = jwt.encode(payload, "a-different-signing-key", algorithm="HS256")
        with pytest.raises(InvalidTokenError):
            verify_access_token(forged)

    def test_a_wrong_issuer_is_refused(self) -> None:
        with pytest.raises(InvalidTokenError):
            verify_access_token(_mutated(iss="somebody-else"))

    def test_a_wrong_audience_is_refused(self) -> None:
        with pytest.raises(InvalidTokenError):
            verify_access_token(_mutated(aud="some-other-app"))

    def test_an_expired_token_is_refused(self) -> None:
        past = dt.datetime.now(tz=dt.UTC) - dt.timedelta(minutes=1)
        with pytest.raises(InvalidTokenError):
            verify_access_token(_mutated(exp=int(past.timestamp())))

    def test_a_token_expiring_one_second_ago_is_refused(self) -> None:
        """Clock skew fails closed (spec edge case). Verification runs with no leeway,
        so a credential marginally outside the window is refused rather than tolerated
        — the direction that costs a user one sign-in rather than granting a minute of
        access nobody authorised."""
        past = dt.datetime.now(tz=dt.UTC) - dt.timedelta(seconds=1)
        with pytest.raises(InvalidTokenError):
            verify_access_token(_mutated(exp=int(past.timestamp())))

    def test_a_refresh_token_presented_as_an_access_token_is_refused(self) -> None:
        """Token-type confusion. Nothing in this feature mints a second type — the
        check exists so the first one that arrives cannot be replayed against a
        protected endpoint."""
        with pytest.raises(InvalidTokenError):
            verify_access_token(_mutated(typ="refresh"))

    def test_a_token_with_no_type_is_refused(self) -> None:
        with pytest.raises(InvalidTokenError):
            verify_access_token(_mutated(typ=None))

    @pytest.mark.parametrize("claim", ["sub", "cid", "sid"])
    def test_a_missing_identifier_is_refused(self, claim: str) -> None:
        with pytest.raises(InvalidTokenError):
            verify_access_token(_mutated(**{claim: None}))

    def test_a_non_uuid_identifier_is_refused(self) -> None:
        """A claim that parses as JSON but not as an identifier. Left unchecked it
        becomes a database error deep in the context builder rather than a refusal at
        the boundary."""
        with pytest.raises(InvalidTokenError):
            verify_access_token(_mutated(sub="not-a-uuid"))


class TestAlgorithmConfusion:
    """The two attacks an unpinned verifier accepts. Both are ordinary, both are
    catastrophic, and neither is visible in a round-trip test."""

    def test_an_unsigned_token_is_refused(self) -> None:
        """`alg: none`. A verifier that trusts the header's algorithm accepts a token
        anyone can write."""
        payload = _payload_of(_valid_token()[0])
        unsigned = jwt.encode(payload, key="", algorithm="none")
        with pytest.raises(InvalidTokenError):
            verify_access_token(unsigned)

    def test_a_token_signed_with_a_different_algorithm_is_refused(self) -> None:
        """HS512 rather than HS256, same key. Accepting it means the algorithm is
        whatever the token says it is, which is the premise every confusion attack
        needs."""
        settings = get_settings()
        payload = _payload_of(_valid_token()[0])
        other = jwt.encode(
            payload, settings.auth.jwt_signing_key.get_secret_value(), algorithm="HS512"
        )
        with pytest.raises(InvalidTokenError):
            verify_access_token(other)

    def test_garbage_is_refused_rather_than_crashing(self) -> None:
        for junk in ("", "not.a.token", "a.b.c", "Bearer something"):
            with pytest.raises(InvalidTokenError):
                verify_access_token(junk)


def _payload_of(token: str) -> dict[str, object]:
    return dict(jwt.decode(token, options={"verify_signature": False}))


def _mutated(**changes: object) -> str:
    """Re-sign a valid token with one claim changed or removed.

    Signed with the real key on purpose: it isolates the claim under test. A token that
    failed both the signature check and the claim check would pass its test without
    proving the claim was ever looked at.
    """
    payload = _payload_of(_valid_token()[0])
    for key, value in changes.items():
        if value is None:
            payload.pop(key, None)
        else:
            payload[key] = value
    settings = get_settings()
    return jwt.encode(
        payload, settings.auth.jwt_signing_key.get_secret_value(), algorithm="HS256"
    )
