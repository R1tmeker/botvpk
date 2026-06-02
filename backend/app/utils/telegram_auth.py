from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

logger = logging.getLogger(__name__)


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
    """
    Validate Telegram WebApp initData using official HMAC-SHA256 algorithm.
    Handles both old initData (hash only) and new format (hash + signature).
    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    try:
        params = dict(parse_qsl(init_data, keep_blank_values=True))
    except Exception as exc:
        raise TelegramInitDataError(f"Failed to parse initData: {exc}") from exc

    try:
        received_hash = params.pop("hash", None)
        # Remove Ed25519 signature — we validate with HMAC-SHA256 only
        params.pop("signature", None)

        if not received_hash:
            raise TelegramInitDataError("Missing 'hash' in initData.")

        # Build data-check-string: sorted key=value lines joined by \n
        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(params.items())
        )

        # secret_key = HMAC_SHA256(key=b"WebAppData", data=bot_token)
        secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
        # computed_hash = HEX(HMAC_SHA256(key=secret_key, data=data_check_string))
        computed_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(computed_hash, received_hash):
            raise TelegramInitDataError("Hash mismatch — initData is invalid or wrong BOT_TOKEN.")

        # Validate auth_date age
        auth_date = int(params.get("auth_date", "0"))
        if max_age_seconds > 0 and time.time() - auth_date > max_age_seconds:
            raise TelegramInitDataError("initData is outdated.")

        # Parse user JSON
        user_json_str = params.get("user")
        if not user_json_str:
            raise TelegramInitDataError("Missing 'user' field in initData.")
        user_data = json.loads(user_json_str)

        user = TelegramUserData(
            telegram_id=int(user_data["id"]),
            first_name=user_data.get("first_name", ""),
            last_name=user_data.get("last_name", ""),
            username=user_data.get("username"),
        )

        return TelegramInitData(raw=params, user=user, auth_date=auth_date)

    except TelegramInitDataError:
        raise
    except Exception as exc:
        logger.exception("Unexpected error validating Telegram initData")
        raise TelegramInitDataError(f"Validation error: {exc}") from exc
