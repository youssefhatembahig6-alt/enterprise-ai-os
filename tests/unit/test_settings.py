"""Configuration behaviour (spec FR-005, FR-006, FR-014a).

Two properties are worth locking down. First, that local defaults are complete
enough for a newcomer to run one command (SC-001) while containing nothing that
could pass for a production secret. Second, that `is_local` genuinely gates the one
destructive command in the system — reset is guarded by three checks, and this is
the innermost of them.
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from eaios_core.settings import (
    MinioSettings,
    PostgresSettings,
    QdrantSettings,
    RedisSettings,
    Settings,
)

pytestmark = pytest.mark.unit


class TestLocalDefaultsAreComplete:
    def test_settings_construct_with_no_environment(self) -> None:
        """FR-005 — no hand-editing required to start the system."""
        settings = Settings()
        assert settings.postgres.host
        assert settings.redis.host
        assert settings.qdrant.host
        assert settings.minio.endpoint

    def test_all_four_stores_are_configured(self) -> None:
        settings = Settings()
        assert isinstance(settings.postgres, PostgresSettings)
        assert isinstance(settings.redis, RedisSettings)
        assert isinstance(settings.qdrant, QdrantSettings)
        assert isinstance(settings.minio, MinioSettings)

    def test_service_hostnames_default_to_compose_service_names(self) -> None:
        """Assert the declared defaults, not the resolved values.

        Reading `Settings().postgres.host` would pass or fail depending on whether
        POSTGRES_HOST happens to be exported — which is exactly what happens when
        the integration suite points the tests at localhost. A test whose result
        depends on the shell that launched it is worse than no test.
        """
        assert PostgresSettings.model_fields["host"].default == "postgres"
        assert RedisSettings.model_fields["host"].default == "redis"
        assert QdrantSettings.model_fields["host"].default == "qdrant"
        assert MinioSettings.model_fields["endpoint"].default == "minio:9000"

    def test_environment_overrides_the_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The flip side: an override must actually take effect (FR-005)."""
        monkeypatch.setenv("POSTGRES_HOST", "localhost")
        assert PostgresSettings().host == "localhost"


class TestSecretsAreNotProductionShaped:
    def test_passwords_are_secretstr(self) -> None:
        settings = Settings()
        assert isinstance(settings.postgres.owner_password, SecretStr)
        assert isinstance(settings.postgres.app_password, SecretStr)
        assert isinstance(settings.minio.secret_key, SecretStr)

    def test_secrets_do_not_leak_through_repr(self) -> None:
        """A settings object reaching a log line must not print credentials."""
        settings = Settings()
        rendered = repr(settings) + str(settings)
        assert "eaios_owner_local_only" not in rendered
        assert "eaios_local_only_secret" not in rendered

    @pytest.mark.parametrize(
        "value",
        [
            Settings().postgres.owner_password.get_secret_value(),
            Settings().postgres.app_password.get_secret_value(),
            Settings().minio.secret_key.get_secret_value(),
        ],
    )
    def test_defaults_are_self_evidently_non_production(self, value: str) -> None:
        """FR-006 — committed defaults must be obviously placeholders, so that a
        real secret accidentally added here would look out of place in review."""
        assert "local" in value.lower()


class TestConnectionUrls:
    def test_owner_and_app_urls_use_different_roles(self) -> None:
        """The whole RLS design depends on these being distinct roles."""
        settings = Settings()
        assert settings.postgres.url(as_owner=True) != settings.postgres.url(as_owner=False)
        assert "eaios_owner" in settings.postgres.url(as_owner=True)
        assert "eaios_app" in settings.postgres.url(as_owner=False)

    def test_app_url_does_not_grant_owner_credentials(self) -> None:
        settings = Settings()
        assert settings.postgres.owner_password.get_secret_value() not in settings.postgres.url(
            as_owner=False
        )

    def test_redis_url_includes_the_database_index(self) -> None:
        assert Settings().redis.url.endswith("/0")


class TestResetGate:
    def test_default_environment_is_local(self) -> None:
        assert Settings().environment == "local"
        assert Settings().is_local is True

    @pytest.mark.parametrize("environment", ["ci", "staging", "production"])
    def test_non_local_environments_do_not_permit_reset(self, environment: str) -> None:
        """FR-014a — the destructive command must refuse anywhere but local,
        regardless of any confirmation flag the caller passes."""
        assert Settings(environment=environment).is_local is False  # type: ignore[arg-type]

    def test_unknown_environment_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            Settings(environment="prod-ish")  # type: ignore[arg-type]


class TestHealthTimeout:
    def test_default_timeout_is_bounded(self) -> None:
        assert 0 < Settings().health_timeout_seconds <= 30

    @pytest.mark.parametrize("value", [0, -1, 31])
    def test_out_of_range_timeouts_are_rejected(self, value: float) -> None:
        """An unbounded health timeout turns a wedged dependency into a wedged
        health endpoint."""
        with pytest.raises(ValueError):
            Settings(health_timeout_seconds=value)


class TestTheSuiteTalksToTheHostNotTheContainer:
    """A guard on the harness itself, not on the product.

    The stores run in Compose and the suite runs on the host, so settings must
    resolve `localhost`. When they resolved the in-container names instead, every
    store-backed test skipped itself with "database unavailable" and the run still
    reported success — 69 security tests, covering the constitution's first
    non-negotiable principle, were silently absent.

    `get_settings` is `lru_cache`d, so whichever import calls it first wins. These
    assertions fail loudly if that first caller ever sees the wrong values again.
    """

    def test_settings_resolve_host_side_addresses(self) -> None:
        from eaios_core.settings import get_settings

        settings = get_settings()
        assert settings.postgres.host == "localhost"
        assert settings.redis.host == "localhost"
        assert settings.qdrant.host == "localhost"
        assert settings.minio.endpoint.startswith("localhost")

    def test_importing_the_worker_does_not_repoison_the_cache(self) -> None:
        """`eaios_worker.celery_app` calls `get_settings()` at import time — the
        original culprit. Importing it here proves the ordering fix holds."""
        import eaios_worker.celery_app  # noqa: F401
        from eaios_core.settings import get_settings

        assert get_settings().postgres.host == "localhost"
