from __future__ import annotations

import re
from datetime import date, datetime

SKIP_WORDS = {"", "-", "нет", "пропустить"}


def join_text(value: str, *, label: str, minimum: int = 1, maximum: int = 255, optional: bool = False) -> str | None:
    text = value.strip()
    if optional and text.casefold() in SKIP_WORDS:
        return None
    if text.startswith("/"):
        raise ValueError("Команда не записана в анкету. Для возврата /back, для отмены /cancel.")
    if len(text) < minimum or len(text) > maximum:
        raise ValueError(f"{label}: от {minimum} до {maximum} символов.")
    return text


def normalize_join_phone(value: str | None) -> str | None:
    text = (value or "").strip()
    if text.casefold() in SKIP_WORDS:
        return None
    if not re.fullmatch(r"\+?[\d\s().-]+", text, flags=re.ASCII):
        raise ValueError("Укажите телефон цифрами, например +7 999 123-45-67, или «пропустить».")
    digits = re.sub(r"\D", "", text)
    if not text.startswith("+"):
        if len(digits) == 10:
            digits = "7" + digits
        elif len(digits) == 11 and digits.startswith("8"):
            digits = "7" + digits[1:]
    if not 7 <= len(digits) <= 15 or digits.startswith("0"):
        raise ValueError("Телефон должен содержать от 7 до 15 цифр с кодом страны.")
    return "+" + digits


def validate_join_birth_date(value: date | None, *, today: date | None = None) -> date | None:
    if value is not None and value > (today or date.today()):
        raise ValueError("Дата рождения не может быть в будущем.")
    return value


def parse_join_birth_date(value: str) -> date | None:
    text = value.strip()
    if text.casefold() in SKIP_WORDS:
        return None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(text, fmt).date()
        except ValueError:
            continue
        return validate_join_birth_date(parsed)
    raise ValueError("Укажите дату в формате ДД.ММ.ГГГГ, например 14.02.2010, или «пропустить».")
