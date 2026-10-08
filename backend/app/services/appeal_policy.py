from __future__ import annotations

from ..roles import RoleLevel

APPEAL_STATUSES = {"CREATED", "IN_PROGRESS", "NEEDS_INFO", "RESOLVED", "REJECTED", "CLOSED"}
APPEAL_STATUS_LABELS = {
    "CREATED": "Создано", "IN_PROGRESS": "В работе", "NEEDS_INFO": "Нужна информация",
    "RESOLVED": "Решено", "REJECTED": "Отклонено", "CLOSED": "Закрыто",
}
APPEAL_MESSAGE_LIMIT = 4000


def can_access_appeal(*, author_id: int | None, user_id: int | None, role: RoleLevel) -> bool:
    return role >= RoleLevel.PARTICIPANT and (
        role >= RoleLevel.DEPUTY_PLATOON_COMMANDER or (user_id is not None and author_id == user_id)
    )


def validate_appeal_text(value: str, *, maximum: int = APPEAL_MESSAGE_LIMIT) -> str:
    text = value.strip()
    if not text:
        raise ValueError("Сообщение не может быть пустым.")
    if len(text) > maximum:
        raise ValueError(f"Максимум {maximum} символов в одном сообщении.")
    return text


def reply_recipient_ids(*, author_id: int | None, sender_id: int, commander_ids: list[int], assignee_id: int | None) -> list[int]:
    # The author may also be a commander: route by their part in this conversation.
    if sender_id != author_id:
        return [author_id] if author_id is not None else []
    targets = [assignee_id] if assignee_id in commander_ids and assignee_id != sender_id else commander_ids
    return sorted({user_id for user_id in targets if user_id is not None and user_id != sender_id})
