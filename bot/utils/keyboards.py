from __future__ import annotations

from typing import Iterable

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from .roles import Role, ADMIN_ROLES


BASE_LAYOUT = [
    ["Помощь", "Мой статус"],
    ["Полный состав", "Моё отделение"],
    ["Все отделения", "ДР сегодня"],
    ["ДР ближайшие 7 дней"],
]

ADMIN_ROW = ["Опросы", "Рассылка", "Реестр"]
SUPER_ROW = ["Настройки"]


def main_menu_keyboard(is_admin: bool, is_super_admin: bool) -> ReplyKeyboardMarkup:
    keyboard_layout: list[list[str]] = [row[:] for row in BASE_LAYOUT]
    if is_admin:
        keyboard_layout.append(ADMIN_ROW)
    if is_super_admin:
        keyboard_layout.append(SUPER_ROW)

    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=label) for label in row] for row in keyboard_layout],
        resize_keyboard=True,
    )
