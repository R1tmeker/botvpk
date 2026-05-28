from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from datetime import time

import pytz


@dataclass(frozen=True)
class BotConfig:
    bot_token: str
    timezone: str
    birthdays_chat_id: Optional[int]
    birthdays_thread_id: Optional[int]
    birthdays_time: time
    default_poll_chat_id: Optional[int]
    dryrun: bool
    leap_policy: str
    super_admin_id: int
    mini_app_url: Optional[str]


class ConfigError(Exception):
    """Raised when the configuration file has invalid values."""


def _parse_bool(value: str) -> bool:
    value_lower = value.strip().lower()
    if value_lower in {"true", "1", "yes", "y", "on"}:
        return True
    if value_lower in {"false", "0", "no", "n", "off"}:
        return False
    raise ConfigError(f"Cannot parse boolean value '{value}'")


def _parse_optional_int(value: str) -> Optional[int]:
    value = value.strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ConfigError(f"Expected integer value, got '{value}'") from exc


def load_config(path: Path) -> BotConfig:
    """
    Load configuration from simple key=value file.
    Validates required fields and supported options.
    """
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")

    raw_values: dict[str, str] = {}
    with path.open("r", encoding="utf-8-sig") as config_file:
        for line_number, raw_line in enumerate(config_file, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                raise ConfigError(f"Line {line_number}: missing '=' separator")
            key, value = line.split("=", 1)
            raw_values[key.strip()] = value.strip()

    try:
        bot_token = raw_values["BOT_TOKEN"]
        timezone = raw_values["TZ"]
    except KeyError as exc:
        raise ConfigError(f"Missing required key: {exc}") from exc

    if not bot_token:
        raise ConfigError("BOT_TOKEN cannot be empty")

    if timezone not in pytz.all_timezones:
        raise ConfigError(f"Unsupported timezone '{timezone}'")

    birthdays_chat_id = _parse_optional_int(raw_values.get("BIRTHDAYS_CHAT_ID", ""))
    birthdays_thread_id = _parse_optional_int(raw_values.get("BIRTHDAYS_THREAD_ID", ""))
    birthdays_time_raw = raw_values.get("BIRTHDAYS_TIME", "09:00")
    try:
        hours, minutes = [int(part) for part in birthdays_time_raw.split(":")]
        birthdays_time = time(hour=hours, minute=minutes)
    except Exception as exc:
        raise ConfigError("BIRTHDAYS_TIME должен быть в формате HH:MM") from exc
    default_poll_chat_id = _parse_optional_int(raw_values.get("DEFAULT_POLL_CHAT_ID", ""))
    dryrun = _parse_bool(raw_values.get("DRYRUN", "false"))
    leap_policy = raw_values.get("LEAP_POLICY", "28")
    if leap_policy not in {"28", "01"}:
        raise ConfigError("LEAP_POLICY must be either '28' or '01'")

    super_admin_raw = raw_values.get("SUPER_ADMIN_ID")
    if not super_admin_raw:
        raise ConfigError("SUPER_ADMIN_ID is required")
    try:
        super_admin_id = int(super_admin_raw)
    except ValueError as exc:
        raise ConfigError("SUPER_ADMIN_ID must be an integer") from exc
    mini_app_url = raw_values.get("MINI_APP_URL", "").strip() or None

    return BotConfig(
        bot_token=bot_token,
        timezone=timezone,
        birthdays_chat_id=birthdays_chat_id,
        birthdays_thread_id=birthdays_thread_id,
        birthdays_time=birthdays_time,
        default_poll_chat_id=default_poll_chat_id,
        dryrun=dryrun,
        leap_policy=leap_policy,
        super_admin_id=super_admin_id,
        mini_app_url=mini_app_url,
    )


def update_config(path: Path, updates: dict[str, str]) -> None:
    """
    Persist selected configuration keys while preserving unknown ones.
    """
    existing_lines: list[str] = []
    seen_keys: set[str] = set()

    if path.exists():
        with path.open("r", encoding="utf-8") as config_file:
            existing_lines = config_file.readlines()

    output_lines: list[str] = []
    for line in existing_lines:
        if "=" not in line or line.strip().startswith("#"):
            output_lines.append(line)
            continue
        key, _ = line.split("=", 1)
        key_stripped = key.strip()
        if key_stripped in updates:
            value = updates[key_stripped]
            output_lines.append(f"{key_stripped}={value}\n")
            seen_keys.add(key_stripped)
        else:
            output_lines.append(line)

    for key, value in updates.items():
        if key not in seen_keys:
            output_lines.append(f"{key}={value}\n")

    with path.open("w", encoding="utf-8") as config_file:
        config_file.writelines(output_lines)
