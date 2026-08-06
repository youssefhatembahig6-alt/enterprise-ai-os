"""`X-Forwarded-For` is believed only from a configured proxy (spec 002 FR-024d).

Feature 003 introduced a proxy. Browser traffic now reaches the API through the site's
own origin, because direct cross-origin calls never worked — the API sends no CORS
headers, and `OPTIONS /public/contact` answers 405.

That fix has a consequence `public/rate_limit.py` predicted in its own words: "a
deployment that adds a proxy must configure the proxy's real-address handling and
revisit this." Without the forwarding, every submission arrives from the web container,
so the per-address bound counts the *proxy* — five enquiries an hour from anybody
exhausts the allowance for everybody. A rate limit that counts the proxy is a
denial-of-service surface introduced by the fix.

The forwarding is what makes it count visitors again. **The trust is what stops it
becoming a bypass**, and that is the half worth testing hardest: a header any caller can
set is a way to mint an unlimited number of buckets, which is strictly worse than having
no bound at all, because it looks like one.

Both halves are here, and neither means anything without the other.
"""

from __future__ import annotations

import pytest

from eaios_api.public.rate_limit import client_address, client_identity

pytestmark = pytest.mark.security


class _Peer:
    def __init__(self, host: str) -> None:
        self.host = host


class _Request:
    """The two things `client_address` reads. Not a FastAPI Request — constructing one
    needs an ASGI scope, and what is under test is a decision about two values."""

    def __init__(self, peer: str | None, forwarded: str | None = None) -> None:
        self.client = _Peer(peer) if peer is not None else None
        self.headers = {"x-forwarded-for": forwarded} if forwarded else {}


@pytest.fixture
def trusting(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """Configure a trusted proxy without touching DNS.

    `_trusted_addresses` resolves names so the configuration can say `web` while the
    request arrives from an address. Here the resolution is stubbed: what is under test
    is the trust decision, and a test that depended on Docker's resolver would fail on
    a laptop for reasons unrelated to the rule.
    """

    def _configure(*addresses: str) -> None:
        import eaios_api.public.rate_limit as module

        monkeypatch.setattr(module, "_is_trusted_proxy", lambda peer: peer in addresses)

    return _configure


class TestAnUntrustedCallerIsNeverBelieved:
    def test_a_forged_header_is_ignored(self) -> None:
        """The default, and the one that matters most. With no proxy configured, the
        header is ignored outright — the behaviour this module had before."""
        request = _Request("203.0.113.9", forwarded="10.0.0.1")
        assert client_address(request) == "203.0.113.9"  # type: ignore[arg-type]

    def test_varying_the_header_does_not_change_the_bucket(self) -> None:
        """The attack the trust exists to prevent: one caller minting a fresh bucket per
        request by varying a header, defeating the bound while appearing to respect it."""
        buckets = {
            client_identity(_Request("203.0.113.9", forwarded=f"10.0.0.{n}"))  # type: ignore[arg-type]
            for n in range(20)
        }
        assert len(buckets) == 1, (
            f"an untrusted caller obtained {len(buckets)} distinct rate-limit buckets by"
            " varying X-Forwarded-For"
        )

    def test_a_trusted_proxy_does_not_launder_an_untrusted_hop(
        self, trusting  # type: ignore[no-untyped-def]
    ) -> None:
        """Left-most entry wins, and that is a deliberate trade worth naming.

        With one trusted proxy in front, the left-most value is the client's — which the
        proxy appended honestly. If a visitor sends their own `X-Forwarded-For`, a proxy
        that *appends* leaves the forged value left-most and this reads it. That is why
        the route handler is the only thing allowed to set the header for us, and why
        adding a second proxy layer means revisiting this again.
        """
        trusting("172.18.0.7")
        request = _Request("172.18.0.7", forwarded="198.51.100.4, 172.18.0.7")
        assert client_address(request) == "198.51.100.4"  # type: ignore[arg-type]


class TestATrustedProxyIsBelieved:
    def test_the_visitors_address_is_used(self, trusting) -> None:  # type: ignore[no-untyped-def]
        trusting("172.18.0.7")
        request = _Request("172.18.0.7", forwarded="198.51.100.4")
        assert client_address(request) == "198.51.100.4"  # type: ignore[arg-type]

    def test_two_visitors_behind_it_get_different_buckets(
        self, trusting  # type: ignore[no-untyped-def]
    ) -> None:
        """The point of the whole exercise. Without this the proxy collapses every
        visitor into one bucket and the bound becomes a site-wide outage waiting for a
        fifth enquiry."""
        trusting("172.18.0.7")
        first = client_identity(_Request("172.18.0.7", forwarded="198.51.100.4"))  # type: ignore[arg-type]
        second = client_identity(_Request("172.18.0.7", forwarded="198.51.100.5"))  # type: ignore[arg-type]
        assert first != second

    def test_the_proxys_own_address_is_used_when_it_forwards_nothing(
        self, trusting  # type: ignore[no-untyped-def]
    ) -> None:
        trusting("172.18.0.7")
        assert client_address(_Request("172.18.0.7")) == "172.18.0.7"  # type: ignore[arg-type]

    def test_an_empty_header_falls_back_to_the_peer(
        self, trusting  # type: ignore[no-untyped-def]
    ) -> None:
        trusting("172.18.0.7")
        assert client_address(_Request("172.18.0.7", forwarded="   ")) == "172.18.0.7"  # type: ignore[arg-type]


class TestTheIdentityIsStillADigest:
    def test_no_address_appears_in_the_key(self, trusting) -> None:  # type: ignore[no-untyped-def]
        """FR-024c's reasoning applies to a forwarded address exactly as it does to a
        direct one — arguably more, since this is now the visitor's real address rather
        than a shared egress."""
        trusting("172.18.0.7")
        identity = client_identity(_Request("172.18.0.7", forwarded="198.51.100.4"))  # type: ignore[arg-type]
        assert "198.51.100.4" not in identity
        assert len(identity) == 32
        assert all(c in "0123456789abcdef" for c in identity)

    def test_an_unidentifiable_caller_still_gets_a_bucket(self) -> None:
        """No client at all — a unix socket or a test harness. They share one bucket
        rather than escaping the bound by being unidentifiable."""
        assert client_identity(_Request(None)) == client_identity(_Request(None))  # type: ignore[arg-type]


class TestTheConfigurationDefaultsToTrustingNothing:
    def test_no_proxy_is_trusted_out_of_the_box(self) -> None:
        from eaios_core.settings import Settings

        assert Settings().trusted_proxy_hosts == frozenset(), (
            "a default that trusted something would mean any deployment which forgot to"
            " configure this had a header-forgery bypass rather than a missing feature"
        )
