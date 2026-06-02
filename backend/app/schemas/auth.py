from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class TelegramAuthRequest(BaseModel):
    init_data: str = Field(min_length=1)


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
