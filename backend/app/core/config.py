from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "УчусьИИ"
    app_env: Literal["development", "staging", "production"] = "production"
    app_debug: bool = False
    app_base_url: str = "https://localhost"
    api_prefix: str = "/api/v1"
    cors_allowed_origins: str = ""
    dev_login_enabled: bool = False

    database_url: str = "postgresql+asyncpg://app:app@postgres:5432/app"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_echo: bool = False

    secret_key: str = Field(default="", repr=False)
    field_encryption_key: str = Field(default="", repr=False)
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 30
    refresh_token_ttl_days: int = 14
    miniapp_auth_window_seconds: int = 3600

    max_bot_token: str = Field(default="", repr=False)
    max_api_base: str = "https://platform-api2.max.ru"
    max_transport: Literal["webhook", "polling", "disabled"] = "webhook"
    max_webhook_url: str = ""
    max_webhook_secret: str = Field(default="", repr=False)
    max_ca_bundle: str = ""
    max_request_timeout: int = 15
    max_verify_ssl: bool = True

    gigachat_credentials: str = Field(default="", repr=False)
    gigachat_scope: str = "GIGACHAT_API_PERS"
    gigachat_model: str = "GigaChat-2"
    gigachat_auth_url: str = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    gigachat_base_url: str = "https://api.giga.chat/v1"
    gigachat_verify_ssl: bool = True
    gigachat_ca_bundle: str = ""
    gigachat_timeout: int = 45
    gigachat_enabled: bool = True

    rate_limit_per_minute: int = 60
    ai_rate_limit_per_hour: int = 20
    log_level: str = "INFO"
    audit_retention_days: int = 1095
    personal_data_retention_days: int = 365

    @field_validator("cors_allowed_origins")
    @classmethod
    def _strip_origins(cls, value: str) -> str:
        return ",".join(origin.strip() for origin in value.split(",") if origin.strip())

    @property
    def cors_origins(self) -> list[str]:
        return [origin for origin in self.cors_allowed_origins.split(",") if origin]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.is_production:
        _require_production_secrets(settings)
    return settings


DEMO_SECRET_PREFIXES = ("dev-only-", "local-development-", "CHANGE_ME")


def _require_production_secrets(settings: Settings) -> None:
    missing = [
        name
        for name, value in (
            ("SECRET_KEY", settings.secret_key),
            ("FIELD_ENCRYPTION_KEY", settings.field_encryption_key),
        )
        if len(value) < 32
    ]
    if settings.max_transport == "webhook" and not settings.max_webhook_secret:
        missing.append("MAX_WEBHOOK_SECRET")
    if missing:
        raise RuntimeError(f"Не заданы обязательные секреты: {', '.join(missing)}")
    if settings.database_url.startswith("sqlite"):
        raise RuntimeError("В production требуется PostgreSQL: DATABASE_URL не может указывать на SQLite")
    if settings.dev_login_enabled:
        raise RuntimeError("DEV_LOGIN_ENABLED недопустим в production")
    demo_secrets = [
        name
        for name, value in (
            ("SECRET_KEY", settings.secret_key),
            ("FIELD_ENCRYPTION_KEY", settings.field_encryption_key),
            ("MAX_WEBHOOK_SECRET", settings.max_webhook_secret),
        )
        if value.startswith(DEMO_SECRET_PREFIXES)
    ]
    if demo_secrets:
        raise RuntimeError(f"Демонстрационные значения секретов недопустимы: {', '.join(demo_secrets)}")
