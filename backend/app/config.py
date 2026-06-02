from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str = Field(..., alias="BOT_TOKEN")
    database_url: str = Field(..., alias="DATABASE_URL")
    jwt_secret: str = Field(..., alias="JWT_SECRET")
    jwt_algorithm: str = Field("HS256", alias="JWT_ALGORITHM")
    jwt_expire_minutes: int = Field(1440, alias="JWT_EXPIRE_MINUTES")
    timezone: str = Field("Asia/Novosibirsk", validation_alias=AliasChoices("TZ", "TIMEZONE"))
    app_env: str = Field("development", alias="APP_ENV")
    api_host: str = Field("0.0.0.0", alias="API_HOST")
    api_port: int = Field(8000, alias="API_PORT")
    api_cors_origins: str = Field("", alias="API_CORS_ORIGINS")
    mini_app_url: str | None = Field(None, alias="MINI_APP_URL")
    bot_username: str | None = Field(None, alias="BOT_USERNAME")
    telegram_init_data_max_age_seconds: int = Field(0, alias="TELEGRAM_INIT_DATA_MAX_AGE_SECONDS")
    uploads_dir: Path = Field(Path("uploads"), alias="UPLOADS_DIR")
    max_upload_size_mb: int = Field(20, alias="MAX_UPLOAD_SIZE_MB")
    dryrun: bool = Field(False, alias="DRYRUN")
    super_admin_id: int | None = Field(None, validation_alias=AliasChoices("SUPER_ADMIN_ID", "SUPER_ADMIN_TG_ID"))

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
