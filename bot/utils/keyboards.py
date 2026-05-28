from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, WebAppInfo

from .roles import (
    CONFIRMED_ROLES,
    PLATOON_STAFF_ROLES,
    SQUAD_NOTIFY_ROLES,
    effective_role,
)


BTN_DASHBOARD = "Дашборд"
BTN_SCHEDULE = "Расписание"
BTN_MY_SQUAD = "Моё отделение"
BTN_FULL_ROSTER = "Общий состав"
BTN_ATTENDANCE = "Посещаемость"
BTN_NORMS = "Нормативы"
BTN_NOTIFICATIONS = "Уведомления"
BTN_REPORT = "Проблема"
BTN_ANNOUNCEMENTS = "Объявления"
BTN_REPORTS = "Отчёты"
BTN_ADMIN = "Админка"
BTN_HELP = "Памятка"
BTN_MINI_APP = "Mini App"


def _has_role(member_role: str | None, allowed_roles) -> bool:
    current = effective_role(member_role)
    return bool(current and current in {effective_role(role) for role in allowed_roles})


def main_menu_keyboard(
    *,
    member_role: str | None = None,
    mini_app_url: str | None = None,
    is_admin: bool = False,
    is_super_admin: bool = False,
) -> ReplyKeyboardMarkup:
    can_use = _has_role(member_role, CONFIRMED_ROLES) or is_admin or is_super_admin
    can_notify_squad = _has_role(member_role, SQUAD_NOTIFY_ROLES) or is_admin or is_super_admin
    can_manage_all = _has_role(member_role, PLATOON_STAFF_ROLES) or is_admin or is_super_admin

    if not can_use:
        layout = [[_button(BTN_DASHBOARD), _button(BTN_HELP)]]
        if mini_app_url:
            layout.append([KeyboardButton(text=BTN_MINI_APP, web_app=WebAppInfo(url=mini_app_url))])
        return ReplyKeyboardMarkup(keyboard=layout, resize_keyboard=True)

    layout: list[list[KeyboardButton]] = [
        [_button(BTN_DASHBOARD), _button(BTN_SCHEDULE)],
        [_button(BTN_MY_SQUAD), _button(BTN_FULL_ROSTER)],
        [_button(BTN_ATTENDANCE), _button(BTN_NORMS)],
        [_button(BTN_NOTIFICATIONS), _button(BTN_HELP)],
    ]

    if can_notify_squad:
        layout.append([_button(BTN_ANNOUNCEMENTS), _button(BTN_REPORT)])
    elif can_use:
        layout.append([_button(BTN_REPORT)])

    if can_manage_all:
        layout.append([_button(BTN_REPORTS)])

    if can_manage_all:
        layout.append([_button(BTN_ADMIN)])

    if mini_app_url:
        layout.append([KeyboardButton(text=BTN_MINI_APP, web_app=WebAppInfo(url=_mini_app_url(mini_app_url, member_role)))])

    return ReplyKeyboardMarkup(keyboard=layout, resize_keyboard=True)


def _button(label: str) -> KeyboardButton:
    return KeyboardButton(text=label)


def _mini_app_url(base_url: str, member_role: str | None) -> str:
    role = effective_role(member_role)
    if not role:
        return base_url
    parts = urlsplit(base_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["role"] = role.value
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
