"""Configuration for every service (spec FR-005, FR-006).

Placed in ``eaios_core`` rather than in the API package because the worker and the
seed generator need identical connection settings. Putting it in ``apps/api`` would
force the data generator to import the web service — a backwards dependency.
``eaios_api.settings`` re-exports these names for callers that expect them there.

Local defaults are deliberately complete and working: a newcomer copies
``.env.example`` and runs one command (SC-001). Every default here is a
non-production placeholder — no real secret is ever committed (FR-006).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class PostgresSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="POSTGRES_", extra="ignore")

    host: str = "postgres"
    port: int = 5432
    db: str = "eaios"

    #: Owns the schema; runs migrations and the seed. Table owners bypass RLS unless
    #: FORCE ROW LEVEL SECURITY is set, which is exactly what seeding needs.
    owner_user: str = "eaios_owner"
    owner_password: SecretStr = SecretStr("eaios_owner_local_only")

    #: Non-owner role used by the API and worker. RLS is enforced against it.
    app_user: str = "eaios_app"
    app_password: SecretStr = SecretStr("eaios_app_local_only")

    def url(self, *, as_owner: bool = False) -> str:
        user = self.owner_user if as_owner else self.app_user
        secret = self.owner_password if as_owner else self.app_password
        return (
            f"postgresql+psycopg://{user}:{secret.get_secret_value()}"
            f"@{self.host}:{self.port}/{self.db}"
        )


class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REDIS_", extra="ignore")

    host: str = "redis"
    port: int = 6379
    db: int = 0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def url(self) -> str:
        return f"redis://{self.host}:{self.port}/{self.db}"


class QdrantSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="QDRANT_", extra="ignore")

    host: str = "qdrant"
    port: int = 6333

    #: Provisioned now, populated by the ingestion feature (decision D2).
    vector_size: int = 1024
    distance: Literal["Cosine", "Dot", "Euclid"] = "Cosine"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


class MinioSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MINIO_", extra="ignore")

    endpoint: str = "minio:9000"
    access_key: str = "eaios_local"
    secret_key: SecretStr = SecretStr("eaios_local_only_secret")
    bucket: str = "eaios"
    secure: bool = False


class AuthSettings(BaseSettings):
    """Authentication and session parameters (spec 003).

    Every number here is in configuration rather than in code because the
    specification states them as numbers precisely so they are testable — "MUST
    expire" and "MUST be bounded" are not assertions anything can make.
    """

    model_config = SettingsConfigDict(env_prefix="AUTH_", extra="ignore")

    #: HS256 signing key. A non-production placeholder by the same convention as the
    #: database passwords above: complete and working locally, and never a real
    #: secret. One process both mints and verifies, which is what makes a symmetric
    #: algorithm sufficient (research R2); the day a second service verifies without
    #: minting, this becomes a key pair and nothing else changes.
    jwt_signing_key: SecretStr = SecretStr("eaios_jwt_local_only_not_a_real_secret")
    jwt_issuer: str = "eaios-api"
    jwt_audience: str = "eaios-portal"

    #: Pinned, and pinned as a list at every verification call site. An unpinned
    #: verifier accepts `alg: none` and accepts an RS256 public key presented as an
    #: HMAC secret — both are in `tests/unit/test_tokens.py`.
    jwt_algorithm: Literal["HS256"] = "HS256"

    #: FR-005. Two bounds because they cover different risks: the idle timeout
    #: protects an unattended machine, and the absolute cap limits how long a stolen
    #: credential stays useful. Without the second, a credential taken from an active
    #: session can be kept alive indefinitely simply by using it.
    idle_timeout_seconds: int = Field(default=30 * 60, gt=0)
    absolute_lifetime_seconds: int = Field(default=8 * 3600, gt=0)

    #: FR-007a. Both dimensions are required: an address-only bound is defeated by
    #: spreading attempts across addresses, and an account-only bound lets an attacker
    #: lock a real user out deliberately. The address ceiling is higher because a
    #: shared office egress is one address for many people.
    login_account_max_failures: int = Field(default=5, gt=0)
    login_address_max_failures: int = Field(default=20, gt=0)
    login_bound_window_seconds: int = Field(default=15 * 60, gt=0)

    #: FR-002a. The local demo credential, written by `eaios-seed credentials`, which
    #: refuses to run outside `ENVIRONMENT=local`. Never committed in plain text
    #: anywhere but here, where it is a placeholder in the same sense as
    #: `eaios_app_local_only`.
    demo_password: SecretStr = SecretStr("eaios-demo-local-only")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    environment: Literal["local", "ci", "staging", "production"] = "local"
    service_name: str = "eaios-api"
    version: str = "0.1.0"
    log_level: str = "info"
    log_json: bool = True

    #: Per-dependency readiness timeout. Bounded so a hung dependency produces a
    #: definite answer rather than a hanging request (spec FR-003).
    health_timeout_seconds: float = Field(default=2.0, gt=0, le=30)

    #: Comma-separated hosts whose `X-Forwarded-For` is believed — read through
    #: :attr:`trusted_proxy_hosts` (spec 002 FR-024d, revisited by 003).
    #:
    #: A plain string rather than a collection because pydantic-settings parses complex
    #: types as JSON, so a set would need `TRUSTED_PROXIES='["web"]'` in `.env` — a
    #: quoting rule nobody remembers, which fails at container start with an
    #: unhelpful parse error. It did.
    trusted_proxies: str = ""

    postgres: PostgresSettings = Field(default_factory=PostgresSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    qdrant: QdrantSettings = Field(default_factory=QdrantSettings)
    minio: MinioSettings = Field(default_factory=MinioSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)

    @property
    def is_local(self) -> bool:
        """Guards the destructive reset path (spec FR-014a)."""
        return self.environment == "local"

    @property
    def trusted_proxy_hosts(self) -> frozenset[str]:
        """Hosts whose `X-Forwarded-For` the rate limiter believes.

        Browser traffic reaches the API through the site's own origin now, because
        direct cross-origin calls never worked — so without this every submission
        arrives from the web container and the per-address bound becomes a whole-site
        one: five enquiries an hour from anybody exhausting the allowance for everybody.

        Deliberately a **closed list, empty by default**. A header any caller can vary
        is a way to mint unlimited rate-limit buckets, which is worse than having no
        bound because it looks like one. A deployment behind a load balancer names that
        balancer here and nothing else.
        """
        return frozenset(part.strip() for part in self.trusted_proxies.split(",") if part.strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
