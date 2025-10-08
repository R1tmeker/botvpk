from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Optional

from ..storage.polls import Poll, PollsStorage, ALLOWED_SCHEDULE_TYPES, ALLOWED_WEEKDAYS
from .exceptions import NotFoundError, ValidationServiceError


@dataclass
class PollInput:
    poll_id: Optional[int]
    title: str
    question: str
    options: list[str]
    is_anonymous: bool
    allows_multiple_answers: bool
    schedule_type: str
    days: list[str]
    time_local: time
    target_chat_id: int
    message_thread_id: Optional[int]
    is_active: bool = True


class PollService:
    def __init__(self, storage: PollsStorage):
        self.storage = storage

    def list_polls(self) -> list[Poll]:
        return self.storage.list_polls()

    def get_poll(self, poll_id: int) -> Poll:
        poll = self.storage.get_poll(poll_id)
        if not poll:
            raise NotFoundError(f"Poll {poll_id} not found")
        return poll

    def delete_poll(self, poll_id: int) -> None:
        if not self.storage.get_poll(poll_id):
            raise NotFoundError(f"Poll {poll_id} not found")
        self.storage.delete_poll(poll_id)

    def toggle_poll(self, poll_id: int, enabled: bool) -> Poll:
        poll = self.get_poll(poll_id)
        updated = Poll(
            poll_id=poll.poll_id,
            title=poll.title,
            question=poll.question,
            options=poll.options,
            is_anonymous=poll.is_anonymous,
            allows_multiple_answers=poll.allows_multiple_answers,
            schedule_type=poll.schedule_type,
            days=poll.days,
            time_local=poll.time_local,
            target_chat_id=poll.target_chat_id,
            message_thread_id=poll.message_thread_id,
            is_active=enabled,
        )
        self.storage.upsert_poll(updated)
        return updated

    def save_poll(self, data: PollInput) -> Poll:
        self._validate_input(data)
        poll_id = data.poll_id or self._generate_next_id()
        poll = Poll(
            poll_id=poll_id,
            title=data.title,
            question=data.question,
            options=data.options,
            is_anonymous=data.is_anonymous,
            allows_multiple_answers=data.allows_multiple_answers,
            schedule_type=data.schedule_type,
            days=[day.upper() for day in data.days],
            time_local=data.time_local,
            target_chat_id=data.target_chat_id,
            message_thread_id=data.message_thread_id,
            is_active=data.is_active,
        )
        self.storage.upsert_poll(poll)
        return poll

    def _generate_next_id(self) -> int:
        polls = self.storage.list_polls()
        if not polls:
            return 1
        return max(p.poll_id for p in polls) + 1

    def _validate_input(self, data: PollInput) -> None:
        if len(data.options) < 2:
            raise ValidationServiceError("Опрос должен содержать минимум два варианта.")
        if data.schedule_type not in ALLOWED_SCHEDULE_TYPES:
            raise ValidationServiceError("Неверный тип расписания.")
        if data.schedule_type == "weekly":
            if not data.days:
                raise ValidationServiceError("Для weekly нужно указать дни недели.")
            for day in data.days:
                if day.upper() not in ALLOWED_WEEKDAYS:
                    raise ValidationServiceError(f"Недопустимый день недели: {day}")

