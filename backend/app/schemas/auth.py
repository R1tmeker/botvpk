from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class TelegramAuthRequest(BaseModel):
    init_data: str = Field(min_length=1)


class PasswordSetRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)
    current_password: str | None = Field(default=None, max_length=128)


class PasswordLoginRequest(BaseModel):
    telegram_id: int
    password: str = Field(min_length=1, max_length=128)
    totp_code: str | None = Field(default=None, min_length=6, max_length=8)


class PasswordResetRequest(BaseModel):
    telegram_id: int
    code: str = Field(min_length=6, max_length=16)
    new_password: str = Field(min_length=8, max_length=128)


class PasswordStatusResponse(BaseModel):
    has_password: bool
    password_set_at: datetime | None = None


class TwoFactorStatusResponse(BaseModel):
    available: bool
    enabled: bool


class TwoFactorSetupResponse(BaseModel):
    secret: str
    provisioning_uri: str


class TwoFactorCodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class VkLinkCodeResponse(BaseModel):
    code: str
    expires_at: datetime


class VkStatusResponse(BaseModel):
    linked: bool
    vk_id: int | None = None
    bot_url: str | None = None


class UserProfile(BaseModel):
    id: int | None
    telegram_id: int
    username: str | None = None
    full_name: str
    squad_id: int | None = None
    avatar_file_id: int | None = None
    role_code: str
    status_code: str = "ACTIVE"
    birth_date: date | None = None
    phone: str | None = None
    city: str | None = None
    education_place: str | None = None


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    profile: UserProfile
    app_timezone: str = "Asia/Novosibirsk"


class MenuCardResponse(BaseModel):
    code: str
    title: str
    description: str | None = None
    icon_code: str | None = None
    color_code: str = "DEFAULT"
    route: str | None = None
    sort_order: int = 0
    is_required: bool = False
    show_badge: bool = False
