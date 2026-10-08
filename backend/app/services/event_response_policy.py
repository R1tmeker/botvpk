from __future__ import annotations

from datetime import datetime
from typing import Protocol

from ..roles import RoleLevel


class EventLike(Protocol):
    squad_id: int | None
    status_code: str
    requires_response: bool
    start_datetime: datetime
    response_deadline_at: datetime | None


class ReasonLike(Protocol):
    is_active: bool
    requires_comment: bool


class EventResponseError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def validate_event_available(event: EventLike, *, role: RoleLevel, squad_id: int | None, now: datetime) -> None:
    if role < RoleLevel.PARTICIPANT:
        raise EventResponseError("FORBIDDEN", "Ответы доступны после подтверждения участия.")
    if event.squad_id is not None and event.squad_id != squad_id and role < RoleLevel.SQUAD_COMMANDER:
        raise EventResponseError("FORBIDDEN", "Это занятие недоступно вашему отделению.")
    if event.status_code == "CANCELLED":
        raise EventResponseError("CANCELLED", "Занятие отменено.")
    if now >= event.start_datetime:
        raise EventResponseError("STARTED", "Занятие уже началось, ответ закрыт.")
    if not event.requires_response:
        raise EventResponseError("NOT_REQUIRED", "Для этого занятия ответ не требуется.")
    if event.response_deadline_at and now > event.response_deadline_at and role < RoleLevel.DEPUTY_SQUAD_COMMANDER:
        raise EventResponseError("DEADLINE", "Срок ответа уже прошёл.")


def validate_response_details(
    response_code: str,
    *,
    requires_response: bool,
    absence_reason_id: int | None = None,
    reason: ReasonLike | None = None,
    custom_reason: str | None = None,
) -> tuple[str, int | None, str | None]:
    code = {"YES": "COMING", "NO": "NOT_COMING"}.get(response_code, response_code)
    if code not in {"COMING", "NOT_COMING", "MAYBE"}:
        raise EventResponseError("INVALID_RESPONSE", "Выберите «Приду», «Не приду» или «Пока не знаю».")
    if code != "NOT_COMING":
        return code, None, None
    comment = (custom_reason or "").strip() or None
    if comment and len(comment) > 500:
        raise EventResponseError("INVALID_REASON", "Причина должна быть не длиннее 500 символов.")
    if absence_reason_id is not None and (reason is None or not reason.is_active):
        raise EventResponseError("INVALID_REASON", "Причина отсутствия недоступна. Выберите другую.")
    if reason is not None and reason.requires_comment and not comment:
        raise EventResponseError("REASON_REQUIRED", "Добавьте комментарий к выбранной причине.")
    if requires_response and absence_reason_id is None and not comment:
        raise EventResponseError("REASON_REQUIRED", "Укажите причину отсутствия.")
    return code, absence_reason_id, comment
