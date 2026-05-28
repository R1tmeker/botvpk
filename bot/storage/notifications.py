from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .backup import create_backup
from ..utils.files import atomic_write, ensure_directory


NOTIFICATION_HEADERS = [
    "notification_id",
    "created_at",
    "sender_id",
    "scope",
    "department",
    "target_member_id",
    "text",
]


@dataclass
class Notification:
    notification_id: int
    created_at: str
    sender_id: int
    scope: str
    department: str
    target_member_id: int | None
    text: str

    def to_csv_row(self) -> dict[str, str]:
        return {
            "notification_id": str(self.notification_id),
            "created_at": self.created_at,
            "sender_id": str(self.sender_id),
            "scope": self.scope,
            "department": self.department,
            "target_member_id": str(self.target_member_id) if self.target_member_id else "",
            "text": self.text,
        }


class NotificationsStorage:
    def __init__(self, path: Path, backups_dir: Path):
        self.path = path
        self.backups_dir = backups_dir
        ensure_directory(self.path.parent)

    def list_notifications(self) -> list[Notification]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            return [self._row_to_notification(row) for row in reader]

    def add(self, notification: Notification) -> None:
        notifications = self.list_notifications()
        notifications.append(notification)
        notifications.sort(key=lambda item: item.notification_id)
        self._save(notifications)

    def next_id(self) -> int:
        existing = self.list_notifications()
        return max((item.notification_id for item in existing), default=0) + 1

    def _save(self, notifications: Iterable[Notification]) -> None:
        create_backup(self.path, self.backups_dir)
        rows = [item.to_csv_row() for item in notifications]
        content = self._render(rows)
        atomic_write(self.path, content, newline="")

    def _row_to_notification(self, row: dict[str, str]) -> Notification:
        target_raw = row.get("target_member_id", "").strip()
        return Notification(
            notification_id=int(row["notification_id"]),
            created_at=row["created_at"].strip(),
            sender_id=int(row["sender_id"]),
            scope=row["scope"].strip(),
            department=row.get("department", "").strip(),
            target_member_id=int(target_raw) if target_raw else None,
            text=row["text"].strip(),
        )

    def _render(self, rows: list[dict[str, str]]) -> str:
        import io

        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=NOTIFICATION_HEADERS)
        writer.writeheader()
        writer.writerows(rows)
        return buffer.getvalue()
