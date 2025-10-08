from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from typing import Iterable, Optional

from .errors import ValidationError
from .backup import create_backup
from ..utils.files import atomic_write, ensure_directory

POLL_HEADERS = [
    "poll_id",
    "title",
    "question",
    "options",
    "is_anonymous",
    "allows_multiple_answers",
    "schedule_type",
    "days",
    "time_local",
    "target_chat_id",
    "message_thread_id",
    "is_active",
]

ALLOWED_SCHEDULE_TYPES = {"weekly", "daily", "once"}
ALLOWED_WEEKDAYS = {"MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"}


@dataclass
class Poll:
    poll_id: int
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
    is_active: bool

    def to_csv_row(self) -> dict[str, str]:
        return {
            "poll_id": str(self.poll_id),
            "title": self.title,
            "question": self.question,
            "options": "|".join(self.options),
            "is_anonymous": "true" if self.is_anonymous else "false",
            "allows_multiple_answers": "true" if self.allows_multiple_answers else "false",
            "schedule_type": self.schedule_type,
            "days": "|".join(self.days),
            "time_local": self.time_local.strftime("%H:%M"),
            "target_chat_id": str(self.target_chat_id),
            "message_thread_id": str(self.message_thread_id) if self.message_thread_id else "",
            "is_active": "true" if self.is_active else "false",
        }


class PollsStorage:
    def __init__(self, path: Path, backups_dir: Path):
        self.path = path
        self.backups_dir = backups_dir
        ensure_directory(self.path.parent)

    def list_polls(self) -> list[Poll]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            self._validate_headers(reader.fieldnames)
            return [self._row_to_poll(row, index) for index, row in enumerate(reader, start=2)]

    def save_polls(self, polls: Iterable[Poll]) -> None:
        ensure_directory(self.path.parent)
        create_backup(self.path, self.backups_dir)
        rows = [poll.to_csv_row() for poll in polls]
        content = self._render(rows)
        atomic_write(self.path, content, newline="")

    def get_poll(self, poll_id: int) -> Optional[Poll]:
        return next((poll for poll in self.list_polls() if poll.poll_id == poll_id), None)

    def upsert_poll(self, poll: Poll) -> None:
        polls = self.list_polls()
        existing_index = next((index for index, p in enumerate(polls) if p.poll_id == poll.poll_id), None)
        if existing_index is None:
            polls.append(poll)
        else:
            polls[existing_index] = poll
        self.save_polls(polls)

    def delete_poll(self, poll_id: int) -> None:
        polls = [poll for poll in self.list_polls() if poll.poll_id != poll_id]
        self.save_polls(polls)

    def _validate_headers(self, fieldnames: Optional[list[str]]) -> None:
        if not fieldnames:
            raise ValidationError("Polls CSV has no header")
        missing = [field for field in POLL_HEADERS if field not in fieldnames]
        if missing:
            raise ValidationError(f"Polls CSV missing headers: {', '.join(missing)}")

    def _row_to_poll(self, row: dict[str, str], line_number: int) -> Poll:
        try:
            poll_id = int(row["poll_id"])
        except ValueError as exc:
            raise ValidationError(f"Line {line_number}: invalid poll_id value") from exc

        title = row["title"].strip()
        question = row["question"].strip()
        options_raw = [option.strip() for option in row["options"].split("|") if option.strip()]
        if len(options_raw) < 2:
            raise ValidationError(f"Line {line_number}: poll must have at least 2 options")

        is_anonymous = row["is_anonymous"].strip().lower() == "true"
        allows_multiple = row["allows_multiple_answers"].strip().lower() == "true"
        schedule_type = row["schedule_type"].strip()
        if schedule_type not in ALLOWED_SCHEDULE_TYPES:
            raise ValidationError(f"Line {line_number}: invalid schedule_type '{schedule_type}'")

        days_field = row["days"].strip()
        days: list[str] = []
        if schedule_type == "weekly":
            days = [day.strip().upper() for day in days_field.split("|") if day.strip()]
            if not days:
                raise ValidationError(f"Line {line_number}: weekly poll must specify days")
            for day in days:
                if day not in ALLOWED_WEEKDAYS:
                    raise ValidationError(f"Line {line_number}: unsupported weekday '{day}'")
        elif days_field:
            days = [day.strip().upper() for day in days_field.split("|") if day.strip()]

        time_raw = row["time_local"].strip()
        try:
            time_local = time.fromisoformat(time_raw)
        except ValueError as exc:
            raise ValidationError(f"Line {line_number}: invalid time_local '{time_raw}'") from exc

        target_chat_raw = row["target_chat_id"].strip()
        try:
            target_chat_id = int(target_chat_raw)
        except ValueError as exc:
            raise ValidationError(f"Line {line_number}: invalid target_chat_id '{target_chat_raw}'") from exc

        thread_raw = row["message_thread_id"].strip()
        try:
            message_thread_id = int(thread_raw) if thread_raw else None
        except ValueError as exc:
            raise ValidationError(f"Line {line_number}: invalid message_thread_id '{thread_raw}'") from exc

        is_active = row["is_active"].strip().lower() == "true"

        return Poll(
            poll_id=poll_id,
            title=title,
            question=question,
            options=options_raw,
            is_anonymous=is_anonymous,
            allows_multiple_answers=allows_multiple,
            schedule_type=schedule_type,
            days=days,
            time_local=time_local,
            target_chat_id=target_chat_id,
            message_thread_id=message_thread_id,
            is_active=is_active,
        )

    def _render(self, rows: list[dict[str, str]]) -> str:
        import io

        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=POLL_HEADERS)
        writer.writeheader()
        writer.writerows(rows)
        return buffer.getvalue()
