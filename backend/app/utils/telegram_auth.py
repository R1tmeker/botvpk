from __future__ import annotations

import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

from aiogram.utils.web_app import safe_parse_webapp_init_data


class TelegramInitDataError(ValueError):
    pass


@dataclass(frozen=True)
class TelegramUserData:
    telegram_id: int
    first_name: str = ""
    last_name: str = ""
    username: str | None = None

    @property
    def full_name(self) -> str:
        name = " ".join(part for part in [self.first_name, self.last_name] if part).strip()
        return name or self.username or str(self.telegram_id)


@dataclass(frozen=True)
class TelegramInitData:
    raw: dict[str, str]
    user: TelegramUserData
    auth_date: int


def validate_init_data(init_data: str, bot_token: str, max_age_seconds: int = 86400) -> TelegramInitData:
    try:
        data = safe_parse_webapp_init_data(token=bot_token, init_data=init_data)
    except ValueError as exc:
        raise TelegramInitDataError(str(exc)) from exc

    if max_age_seconds > 0 and time.time() - data.auth_date.timestamp() > max_age_seconds:
        raise TelegramInitDataError("Telegram initData is outdated.")

    u = data.user
    user = TelegramUserData(
        telegram_id=u.id,
        first_name=u.first_name or "",
        last_name=u.last_name or "",
        username=u.username,
    )

    raw = dict(parse_qsl(init_data, keep_blank_values=True))
    raw.pop("hash", None)
    raw.pop("signature", None)

    return TelegramInitData(raw=raw, user=user, auth_date=int(data.auth_date.timestamp()))
