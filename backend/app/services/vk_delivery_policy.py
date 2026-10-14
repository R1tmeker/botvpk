from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import aliased

from ..models import EventResponse, Notification, NotificationPreference, ScheduleEvent, User

VK_QUEUE_LOCK = 825739102


def pending_vk_statement(now: datetime):
    preference = aliased(NotificationPreference)
    delivered = aliased(Notification)
    recent_count = select(func.count(delivered.id)).where(
        delivered.user_id == Notification.user_id,
        delivered.vk_sent_at >= now - timedelta(minutes=1),
    ).correlate(Notification).scalar_subquery()
    # One queued item per recipient keeps large backlogs from starving other members.
    candidates = select(
        Notification.id,
        func.row_number().over(partition_by=Notification.user_id, order_by=(
            (Notification.priority_code == "URGENT").desc(), Notification.created_at, Notification.id,
        )).label("position"),
    ).join(User, User.id == Notification.user_id).outerjoin(preference, and_(
        preference.user_id == Notification.user_id,
        preference.category_code == Notification.category_code,
    )).where(
        Notification.send_to_tg.is_(True), Notification.vk_sent_at.is_(None),
        Notification.vk_suppressed_at.is_(None),
        or_(Notification.vk_retry_after.is_(None), Notification.vk_retry_after <= now),
        or_(preference.id.is_(None), preference.vk_enabled.is_(True)),
        or_(Notification.deliver_after.is_(None), Notification.deliver_after <= now),
        User.vk_id.is_not(None), User.status_code == "ACTIVE",
        or_(recent_count == 0, and_(Notification.priority_code == "URGENT", recent_count < 3)),
    ).subquery()
    return select(Notification, User.vk_id).join(User, User.id == Notification.user_id).join(
        candidates, candidates.c.id == Notification.id,
    ).where(candidates.c.position == 1).order_by(
        (Notification.priority_code == "URGENT").desc(), Notification.created_at, Notification.id,
    ).limit(50)


async def suppression_reason(session, notification: Notification, now: datetime) -> str | None:
    if notification.entity_name == "morning_briefing" and notification.created_at < now - timedelta(days=1):
        return "expired_morning_briefing"
    if notification.type_code == "EVENT_RESPONSE_REMINDER" and notification.created_at < now - timedelta(days=1):
        return "expired_response_reminder"
    if notification.entity_name in {"schedule_events", "schedule_events_2h"} and notification.type_code in {
        "SCHEDULE_POLL", "SCHEDULE", "EVENT_RESPONSE_REMINDER",
    }:
        event = await session.get(ScheduleEvent, notification.entity_id)
        if event is None or event.status_code == "CANCELLED" or (event.end_datetime or event.start_datetime) <= now:
            return "event_closed"
        if notification.type_code in {"SCHEDULE_POLL", "EVENT_RESPONSE_REMINDER"}:
            if event.response_deadline_at and event.response_deadline_at < now:
                return "response_closed"
            answered = await session.scalar(select(EventResponse.id).where(
                EventResponse.event_id == event.id, EventResponse.user_id == notification.user_id,
                EventResponse.response_code.in_(("COMING", "NOT_COMING")),
            ))
            if answered:
                return "already_answered"
    # Conversations and announcements can intentionally contain repeated text.
    # Only automated notifications about the same entity are coalesced.
    if notification.type_code in {"SCHEDULE_POLL", "SCHEDULE", "EVENT_RESPONSE_REMINDER", "ATTENDANCE", "SYSTEM", "COMMANDER"} and notification.entity_name:
        window = timedelta(minutes=10) if notification.type_code == "SYSTEM" else timedelta(hours=24)
        same = await session.scalar(select(Notification.id).where(
            Notification.id != notification.id, Notification.user_id == notification.user_id,
            Notification.type_code == notification.type_code,
            Notification.entity_name == notification.entity_name,
            Notification.entity_id.is_not_distinct_from(notification.entity_id),
            Notification.title == notification.title, Notification.body.is_not_distinct_from(notification.body),
            Notification.vk_sent_at >= now - timedelta(hours=24),
            Notification.created_at >= notification.created_at - window,
            Notification.created_at <= notification.created_at + window,
        ).limit(1))
        if same:
            return "duplicate_automated_notification"
    return None
