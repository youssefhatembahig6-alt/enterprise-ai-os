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

    postgres: PostgresSettings = Field(default_factory=PostgresSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    qdrant: QdrantSettings = Field(default_factory=QdrantSettings)
    minio: MinioSettings = Field(default_factory=MinioSettings)

    @property
    def is_local(self) -> bool:
        """Guards the destructive reset path (spec FR-014a)."""
        return self.environment == "local"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
