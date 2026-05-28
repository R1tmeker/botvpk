from __future__ import annotations

from datetime import datetime

import pytz

from ..storage.members import Member
from ..storage.notifications import Notification, NotificationsStorage


class NotificationsService:
    def __init__(self, storage: NotificationsStorage, timezone: str):
        self.storage = storage
        self.timezone = timezone

    def update_settings(self, *, timezone: str | None = None) -> None:
        if timezone:
            self.timezone = timezone

    def create(
        self,
        *,
        sender_id: int,
        scope: str,
        text: str,
        department: str = "",
        target_member_id: int | None = None,
    ) -> Notification:
        created_at = datetime.now(pytz.timezone(self.timezone)).isoformat(timespec="minutes")
        notification = Notification(
            notification_id=self.storage.next_id(),
            created_at=created_at,
            sender_id=sender_id,
            scope=scope,
            department=department,
            target_member_id=target_member_id,
            text=text.strip(),
        )
        self.storage.add(notification)
        return notification

    def visible_for(self, member: Member, limit: int = 10) -> list[Notification]:
        result: list[Notification] = []
        for notification in self.storage.list_notifications():
            if notification.scope == "all":
                result.append(notification)
            elif notification.scope == "department" and notification.department == member.department:
                result.append(notification)
            elif notification.scope == "member" and notification.target_member_id == member.id:
                result.append(notification)
        result.sort(key=lambda item: item.notification_id, reverse=True)
        return result[:limit]
