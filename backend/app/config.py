from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str = Field(..., alias="BOT_TOKEN")
    database_url: str = Field(..., alias="DATABASE_URL")
    timezone: str = Field("Asia/Novosibirsk", validation_alias=AliasChoices("TZ", "TIMEZONE"))
    app_env: str = Field("development", alias="APP_ENV")
    api_host: str = Field("0.0.0.0", alias="API_HOST")
    api_port: int = Field(8000, alias="API_PORT")
    api_cors_origins: str = Field("", alias="API_CORS_ORIGINS")
    mini_app_url: str | None = Field(None, alias="MINI_APP_URL")
    bot_username: str | None = Field(None, alias="BOT_USERNAME")
    telegram_init_data_max_age_seconds: int = Field(86400, alias="TELEGRAM_INIT_DATA_MAX_AGE_SECONDS")
    uploads_dir: Path = Field(Path("uploads"), alias="UPLOADS_DIR")
    max_upload_size_mb: int = Field(200, alias="MAX_UPLOAD_SIZE_MB")
    redis_url: str | None = Field(None, alias="REDIS_URL")
    session_secret: str = Field(..., alias="SESSION_SECRET")
    session_cookie_name: str = Field("vpk_session", alias="SESSION_COOKIE_NAME")
    csrf_cookie_name: str = Field("vpk_csrf", alias="CSRF_COOKIE_NAME")
    session_idle_minutes: int = Field(1440, alias="SESSION_IDLE_MINUTES")
    session_absolute_minutes: int = Field(10080, alias="SESSION_ABSOLUTE_MINUTES")
    totp_encryption_key: str = Field(..., alias="TOTP_ENCRYPTION_KEY")
    link_code_pepper: str = Field(..., alias="LINK_CODE_PEPPER")
    clamav_host: str = Field("clamav", alias="CLAMAV_HOST")
    clamav_port: int = Field(3310, alias="CLAMAV_PORT")
    clamav_required: bool = Field(False, alias="CLAMAV_REQUIRED")
    sentry_dsn: str | None = Field(None, alias="SENTRY_DSN")
    sentry_traces_sample_rate: float = Field(0.05, alias="SENTRY_TRACES_SAMPLE_RATE")
    release_version: str | None = Field(None, alias="RELEASE_VERSION")
    bot_heartbeat_path: Path = Field(Path("/tmp/botvpk-bot.heartbeat"), alias="BOT_HEARTBEAT_PATH")
    vk_bot_heartbeat_path: Path = Field(Path("/tmp/botvpk-vk-bot.heartbeat"), alias="VK_BOT_HEARTBEAT_PATH")
    dryrun: bool = Field(False, alias="DRYRUN")
    super_admin_id: int | None = Field(None, validation_alias=AliasChoices("SUPER_ADMIN_ID", "SUPER_ADMIN_TG_ID"))
    vk_bot_enabled: bool = Field(False, alias="VK_BOT_ENABLED")
    vk_group_token: str | None = Field(None, alias="VK_GROUP_TOKEN")
    vk_group_id: int | None = Field(None, alias="VK_GROUP_ID")
    vk_bot_url: str | None = Field(None, alias="VK_BOT_URL")
    site_url: str | None = Field(None, alias="SITE_URL")
    web_push_vapid_public_key: str | None = Field(None, alias="WEB_PUSH_VAPID_PUBLIC_KEY")
    web_push_vapid_private_key: str | None = Field(None, alias="WEB_PUSH_VAPID_PRIVATE_KEY")
    web_push_vapid_sub: str = Field("mailto:admin@example.com", alias="WEB_PUSH_VAPID_SUB")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def cors_origins(self) -> list[str]:
        if not self.api_cors_origins:
            return []
        return [item.strip() for item in self.api_cors_origins.split(",") if item.strip()]

    @property
    def secure_cookies(self) -> bool:
        return self.app_env.casefold() == "production"

    @property
    def effective_session_secret(self) -> str:
        return self.session_secret

    @property
    def effective_totp_encryption_key(self) -> str:
        return self.totp_encryption_key

    @property
    def effective_link_code_pepper(self) -> str:
        return self.link_code_pepper

    @model_validator(mode="after")
    def validate_production_secrets(self) -> Settings:
        if self.app_env.casefold() != "production":
            return self
        required = {
            "SESSION_SECRET": self.session_secret,
            "TOTP_ENCRYPTION_KEY": self.totp_encryption_key,
            "LINK_CODE_PEPPER": self.link_code_pepper,
        }
        for name, value in required.items():
            lowered = (value or "").casefold()
            if len(value or "") < 32 or any(marker in lowered for marker in ("change_me", "example", "test")):
                raise ValueError(f"{name} must be a non-placeholder secret of at least 32 characters in production.")
        if not self.redis_url:
            raise ValueError("REDIS_URL is required in production.")
        if not self.clamav_required:
            raise ValueError("CLAMAV_REQUIRED must be true in production.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
