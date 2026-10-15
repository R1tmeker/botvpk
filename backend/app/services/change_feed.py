from __future__ import annotations

import asyncio

from sqlalchemy import event
from sqlalchemy.orm import Session

QUERY_PREFIXES = {
    "users": {"me", "auth", "users", "admin", "squads", "dashboard", "normatives", "progress"},
    "squads": {"squads", "users", "admin", "dashboard"},
    "join_applications": {"join", "admin", "dashboard", "users", "me"},
    "application_status_history": {"join", "admin", "dashboard"},
    "schedule_events": {"schedule", "admin", "dashboard", "attendance"},
    "schedule_templates": {"schedule", "admin"},
    "event_responses": {"schedule", "dashboard"},
    "attendance": {"attendance", "dashboard", "progress", "reports"},
    "attendance_grades": {"attendance", "progress", "reports"},
    "normatives": {"normatives", "admin", "dashboard", "progress", "reports"},
    "normative_submissions": {"normatives", "submissions", "dashboard", "progress", "reports"},
    "normative_submission_files": {"normatives", "submissions"},
    "notifications": {"notifications", "dashboard"},
    "appeals": {"appeals", "admin", "dashboard"},
    "appeal_messages": {"appeals", "admin", "notifications"},
    "promo_blocks": {"promo", "admin", "dashboard"},
    "menu_cards": {"menu", "admin", "dashboard"},
    "settings": {"settings", "admin", "dashboard", "schedule"},
    "learning_materials": {"learning", "admin"},
    "learning_courses": {"learning", "admin"},
    "learning_progress": {"learning", "progress"},
    "candidate_events": {"join", "public", "admin"},
    "candidate_event_responses": {"join", "public", "admin"},
    "normative_targets": {"normatives", "progress"},
    "absence_reasons": {"absence_reasons", "admin", "schedule"},
    "user_dashboard_settings": {"dashboard", "settings"},
    "notification_preferences": {"me", "notifications", "admin"},
    "attendance_history": {"attendance", "dashboard", "progress"},
    "audit_log": {"admin"},
}
_tasks: set[asyncio.Task] = set()


def collect_changes(session, _flush_context) -> None:
    keys = session.info.setdefault("realtime_query_keys", set())
    for item in list(session.new) + list(session.dirty) + list(session.deleted):
        if item in session.dirty and not session.is_modified(item, include_collections=False):
            continue
        keys.update(QUERY_PREFIXES.get(getattr(item, "__tablename__", ""), set()))
        if getattr(item, "__tablename__", "") == "audit_log":
            keys.update(QUERY_PREFIXES.get(item.entity_name, set()))


def publish_committed_changes(session) -> None:
    if session.in_nested_transaction():
        return
    keys = session.info.pop("realtime_query_keys", set())
    if not keys:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    from ..config import get_settings
    from .realtime import publish_realtime_event

    task = loop.create_task(publish_realtime_event(get_settings(), event_type="data.changed", query_keys=sorted(keys)))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def discard_changes(session) -> None:
    if session.in_nested_transaction():
        return
    session.info.pop("realtime_query_keys", None)


def install_change_feed() -> None:
    if event.contains(Session, "after_flush", collect_changes):
        return
    event.listen(Session, "after_flush", collect_changes)
    event.listen(Session, "after_commit", publish_committed_changes)
    event.listen(Session, "after_rollback", discard_changes)
