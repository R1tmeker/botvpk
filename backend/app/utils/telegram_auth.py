from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl


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
    import logging
    log = logging.getLogger(__name__)

    values = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = values.pop("hash", None)
    values.pop("signature", None)
    if not received_hash:
        raise TelegramInitDataError("Telegram initData does not contain hash.")

    data_check_string = "\n".join(f"{key}={values[key]}" for key in sorted(values))

    # Try both key orders to detect which one Telegram expects
    sk1 = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    h1 = hmac.new(sk1, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    sk2 = hmac.new(bot_token.encode("utf-8"), b"WebAppData", hashlib.sha256).digest()
    h2 = hmac.new(sk2, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    log.warning("hash_recv=%s h1=%s h2=%s fields=%s dcs=%r", received_hash[:8], h1[:8], h2[:8], list(values.keys()), data_check_string[:200])

    if hmac.compare_digest(h1, received_hash):
        secret_key = sk1
    elif hmac.compare_digest(h2, received_hash):
        secret_key = sk2
        log.warning("Used reverse key order (bot_token as key)")
    else:
        raise TelegramInitDataError("Telegram initData hash is invalid.")

    calculated_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    auth_date_raw = values.get("auth_date")
    if not auth_date_raw:
        raise TelegramInitDataError("Telegram initData does not contain auth_date.")
    try:
        auth_date = int(auth_date_raw)
    except ValueError as exc:
        raise TelegramInitDataError("Telegram initData auth_date is invalid.") from exc
    if max_age_seconds > 0 and time.time() - auth_date > max_age_seconds:
        raise TelegramInitDataError("Telegram initData is outdated.")

    try:
        user_payload = json.loads(values["user"])
        user = TelegramUserData(
            telegram_id=int(user_payload["id"]),
            first_name=user_payload.get("first_name", ""),
            last_name=user_payload.get("last_name", ""),
            username=user_payload.get("username"),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise TelegramInitDataError("Telegram initData user payload is invalid.") from exc

    return TelegramInitData(raw=values, user=user, auth_date=auth_date)
