from __future__ import annotations

from ..roles import RoleLevel

# The two messengers expose the same small set of daily actions.
def menu_rows(role: RoleLevel, section: str = "home") -> list[list[tuple[str, str]]]:
    if section == "home":
        if role < RoleLevel.PARTICIPANT:
            return [[("Вступить в ВПК", "join")], [("Мой ID", "my_id"), ("Помощь", "help")]]
        rows = [
            [("Расписание", "schedule"), ("Отметиться", "checkin")],
            [("Нормативы", "normatives"), ("Уведомления", "notifications")],
            [("Мои данные", "personal"), ("Связь", "contact")],
        ]
        if role >= RoleLevel.DEPUTY_SQUAD_COMMANDER:
            rows.append([("Командиру", "command")])
        return rows
    if role < RoleLevel.PARTICIPANT:
        return [[("Главное меню", "home")]]
    sections = {
        "personal": [[("Профиль", "profile"), ("Моя явка", "attendance")],
                     [("Поиск", "search"), ("Аккаунт", "account")]],
        "contact": [[("Написать командиру", "appeal")], [("Мои обращения", "myappeals")]],
        "account": [[("Мой ID", "my_id"), ("Привязать VK", "vk")], [("Сменить пароль", "password")]],
        "command": ([[('Заявки', 'applications')], [('Журнал явки', 'journal'), ('Управление', 'admin')]]
                    if role >= RoleLevel.DEPUTY_PLATOON_COMMANDER else [[('Журнал явки', 'journal')]]),
    }
    rows = list(sections.get(section, [])) if section != "command" or role >= RoleLevel.DEPUTY_SQUAD_COMMANDER else []
    parent = "personal" if section == "account" else "home"
    navigation = [("← Назад", parent)]
    if parent != "home":
        navigation.append(("Главное меню", "home"))
    return [*rows, navigation]


MENU_TEXT = {
    "home": "Что нужно сделать?\nРасписание — ответить о планах. Отметиться — подтвердить присутствие на занятии.",
    "personal": "Ваш профиль, посещаемость и поиск по ВПК.",
    "contact": "Связь с командованием. Обращение и дальнейшая переписка доступны прямо здесь.",
    "account": "Настройки аккаунта и подключение каналов.",
    "command": "Действия командира. Кнопки в уведомлениях также позволяют проверить сдачу и отметить явку.",
}


def page_number(value: object) -> int | None:
    # Reject forged payloads before using them as database offsets.
    if isinstance(value, bool):
        return None
    text = str(value)
    return int(text) if text.isascii() and text.isdigit() and len(text) <= 5 and int(text) <= 10000 else None


def entity_id(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    text = str(value)
    return int(text) if text.isascii() and text.isdigit() and len(text) <= 10 and 0 < int(text) < 2**31 else None
