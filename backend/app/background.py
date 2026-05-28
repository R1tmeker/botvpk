from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings
from .database import AsyncSessionLocal
from .models import (
    Appeal,
    Attendance,
    AttendanceGrade,
    EventResponse,
    Normative,
    NormativeSubmission,
    Notification,
    ScheduleEvent,
    User,
)

logger = logging.getLogger(__name__)

CONFIRMED_ROLE_CODES = (
    "PARTICIPANT",
    "DEPUTY_SQUAD_COMMANDER",
    "SQUAD_COMMANDER",
    "DEPUTY_PLATOON_COMMANDER",
    "PLATOON_COMMANDER",
    "ADMIN",
    "SUPER_ADMIN",
)

COMMANDER_ROLE_CODES = (
    "SQUAD_COMMANDER",
    "DEPUTY_SQUAD_COMMANDER",
    "DEPUTY_PLATOON_COMMANDER",
    "PLATOON_COMMANDER",
    "ADMIN",
    "SUPER_ADMIN",
)


def create_scheduler(settings: Settings) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=settings.timezone)
    # Every 30s: flush pending TG notifications
    scheduler.add_job(send_pending_tg_notifications, "interval", seconds=30, args=[settings], max_instances=1)
    # Every 5m: convert NOT_COMING responses → ABSENT attendance after event
    scheduler.add_job(materialize_absent_responses, "interval", minutes=5, max_instances=1)
    # Every 15m: remind commanders to fill attendance 2h after event
    scheduler.add_job(remind_commanders_about_attendance, "interval", minutes=15, max_instances=1)
    # Every 15m: personalized event reminder 2h before start
    scheduler.add_job(send_event_reminders_2h, "interval", minutes=15, max_instances=1)
    # Daily at 07:00: morning briefing to all participants
    scheduler.add_job(send_morning_briefing, "cron", hour=7, minute=0, max_instances=1)
    # Hourly: SLA check for unanswered appeals
    scheduler.add_job(check_appeal_sla, "interval", hours=1, max_instances=1)
    # Daily at 20:00: low attendance & grade warnings to commanders
    scheduler.add_job(check_low_attendance_and_grades, "cron", hour=20, minute=0, max_instances=1)
    # Daily at 19:00: overdue normative warnings to participants
    scheduler.add_job(check_overdue_normatives, "cron", hour=19, minute=0, max_instances=1)
    return scheduler


# ─────────────────────── helpers ────────────────────────────


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _get_user_event_response(session: AsyncSession, user_id: int, event_id: int) -> EventResponse | None:
    return await session.scalar(
        select(EventResponse).where(EventResponse.user_id == user_id, EventResponse.event_id == event_id)
    )


async def _notification_exists(
    session: AsyncSession, *, user_id: int, type_code: str, entity_name: str, entity_id: int
) -> bool:
    return bool(
        await session.scalar(
            select(Notification.id).where(
                Notification.user_id == user_id,
                Notification.type_code == type_code,
                Notification.entity_name == entity_name,
                Notification.entity_id == entity_id,
            )
        )
    )


# ─────────────────────── flush TG queue ─────────────────────


async def send_pending_tg_notifications(settings: Settings) -> None:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(Notification, User.telegram_id)
                .join(User, User.id == Notification.user_id)
                .where(
                    Notification.send_to_tg.is_(True),
                    Notification.tg_sent_at.is_(None),
                    User.telegram_id.is_not(None),
                    User.status_code == "ACTIVE",
                )
                .order_by(Notification.created_at)
                .limit(50)
            )
        ).all()
        if not rows:
            return
        bot = Bot(settings.bot_token)
        try:
            for notification, telegram_id in rows:
                try:
                    text = notification.title if not notification.body else f"{notification.title}\n\n{notification.body}"
                    await bot.send_message(telegram_id, text)
                    notification.tg_sent_at = utcnow()
                except Exception:  # noqa: BLE001
                    logger.exception("Failed to send notification id=%s", notification.id)
            await session.commit()
        finally:
            await bot.session.close()


# ─────────────────────── NOT_COMING → ABSENT ────────────────


async def materialize_absent_responses() -> None:
    now = utcnow()
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(EventResponse, ScheduleEvent)
                .join(ScheduleEvent, ScheduleEvent.id == EventResponse.event_id)
                .where(
                    EventResponse.response_code.in_(("NOT_COMING", "NO")),
                    ScheduleEvent.status_code != "CANCELLED",
                    (
                        (ScheduleEvent.end_datetime.is_not(None) & (ScheduleEvent.end_datetime <= now))
                        | (ScheduleEvent.start_datetime <= now)
                    ),
                )
                .limit(200)
            )
        ).all()
        changed = 0
        for response, event in rows:
            exists = await session.scalar(
                select(Attendance).where(Attendance.event_id == event.id, Attendance.user_id == response.user_id)
            )
            if exists:
                continue
            session.add(
                Attendance(
                    event_id=event.id,
                    user_id=response.user_id,
                    status_code="ABSENT",
                    absence_reason_id=response.absence_reason_id,
                    custom_reason=response.custom_reason,
                    marked_at=now,
                    updated_at=now,
                )
            )
            changed += 1
        if changed:
            await session.commit()


# ─────────────────────── attendance fill reminder ───────────


async def remind_commanders_about_attendance() -> None:
    now = utcnow()
    threshold = now - timedelta(hours=2)
    async with AsyncSessionLocal() as session:
        events = list(
            (
                await session.scalars(
                    select(ScheduleEvent)
                    .where(
                        ScheduleEvent.status_code.in_(("PLANNED", "ACTIVE", "FINISHED")),
                        ScheduleEvent.start_datetime <= threshold,
                        ScheduleEvent.start_datetime >= now - timedelta(days=1),
                    )
                    .limit(100)
                )
            ).all()
        )
        for event in events:
            existing = await session.scalar(select(Attendance.id).where(Attendance.event_id == event.id).limit(1))
            if existing:
                continue
            commanders = await session.scalars(
                select(User).where(
                    User.status_code == "ACTIVE",
                    User.telegram_id.is_not(None),
                    User.role_code.in_(COMMANDER_ROLE_CODES),
                    (User.squad_id == event.squad_id) if event.squad_id is not None else True,
                )
            )
            for commander in commanders:
                if await _notification_exists(session, user_id=commander.id, type_code="ATTENDANCE", entity_name="schedule_events", entity_id=event.id):
                    continue
                session.add(
                    Notification(
                        user_id=commander.id,
                        type_code="ATTENDANCE",
                        title="Заполните посещаемость",
                        body=f"По событию «{event.title}» ещё нет отметок явки.",
                        entity_name="schedule_events",
                        entity_id=event.id,
                        send_to_tg=True,
                    )
                )
        await session.commit()


# ─────────────────────── 2h personalized reminder ───────────


async def send_event_reminders_2h() -> None:
    """Runs every 15m. Sends a personalized reminder 2h before event start."""
    now = utcnow()
    window_start = now + timedelta(hours=2)
    window_end = now + timedelta(hours=2, minutes=15)  # matches job interval

    async with AsyncSessionLocal() as session:
        events = list(
            (
                await session.scalars(
                    select(ScheduleEvent)
                    .where(
                        ScheduleEvent.start_datetime >= window_start,
                        ScheduleEvent.start_datetime < window_end,
                        ScheduleEvent.status_code != "CANCELLED",
                    )
                )
            ).all()
        )
        for event in events:
            users = list(
                (
                    await session.scalars(
                        select(User).where(
                            User.status_code == "ACTIVE",
                            User.telegram_id.is_not(None),
                            User.role_code.in_(CONFIRMED_ROLE_CODES),
                            (User.squad_id == event.squad_id) if event.squad_id is not None else True,
                        )
                    )
                ).all()
            )
            for user in users:
                # Skip duplicate
                if await _notification_exists(session, user_id=user.id, type_code="SCHEDULE", entity_name="schedule_events_2h", entity_id=event.id):
                    continue
                response = await _get_user_event_response(session, user.id, event.id)
                rc = response.response_code if response else None
                start_str = event.start_datetime.strftime("%H:%M")
                place_str = f" • {event.place}" if event.place else ""
                if rc == "COMING":
                    body = f"Через 2 часа занятие «{event.title}»!\n{start_str}{place_str}\nВы сказали «Приду» ✅"
                elif rc == "NOT_COMING":
                    body = f"Напоминание: «{event.title}» в {start_str}. Вы не придёте — причина записана."
                elif rc == "MAYBE":
                    body = f"«{event.title}» через 2 часа ({start_str}{place_str}).\nВы ещё не решили! Пожалуйста, ответьте."
                else:
                    body = f"Через 2 часа занятие «{event.title}»!\n{start_str}{place_str}\nВы ещё не ответили — не забудьте!"
                session.add(
                    Notification(
                        user_id=user.id,
                        type_code="SCHEDULE",
                        title=f"⏰ Скоро: {event.title}",
                        body=body,
                        entity_name="schedule_events_2h",
                        entity_id=event.id,
                        send_to_tg=True,
                    )
                )
        await session.commit()


# ─────────────────────── morning briefing ───────────────────


async def send_morning_briefing() -> None:
    """Daily at 07:00: send today's event summary to each participant."""
    now = utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    async with AsyncSessionLocal() as session:
        events = list(
            (
                await session.scalars(
                    select(ScheduleEvent)
                    .where(
                        ScheduleEvent.start_datetime >= today_start,
                        ScheduleEvent.start_datetime < today_end,
                        ScheduleEvent.status_code != "CANCELLED",
                    )
                )
            ).all()
        )
        if not events:
            return

        users = list(
            (
                await session.scalars(
                    select(User).where(
                        User.status_code == "ACTIVE",
                        User.telegram_id.is_not(None),
                        User.role_code.in_(CONFIRMED_ROLE_CODES),
                    )
                )
            ).all()
        )

        for user in users:
            user_events = [e for e in events if e.squad_id is None or e.squad_id == user.squad_id]
            if not user_events:
                continue

            # Already sent today?
            sent_today = await session.scalar(
                select(Notification.id).where(
                    Notification.user_id == user.id,
                    Notification.type_code == "SYSTEM",
                    Notification.entity_name == "morning_briefing",
                    Notification.created_at >= today_start,
                )
            )
            if sent_today:
                continue

            lines: list[str] = ["☀️ Доброе утро!"]
            for event in user_events:
                start_str = event.start_datetime.strftime("%H:%M")
                place_str = f" · {event.place}" if event.place else ""
                resp = await _get_user_event_response(session, user.id, event.id)
                emoji = {"COMING": "✅", "NOT_COMING": "❌", "MAYBE": "⏳"}.get(resp.response_code if resp else "", "❓")
                lines.append(f"{emoji} {event.title} в {start_str}{place_str}")

            # Commander extra: response summary
            if user.role_code in COMMANDER_ROLE_CODES:
                for event in user_events:
                    squad_filter = (User.squad_id == event.squad_id) if event.squad_id else True
                    squad_users = list(
                        (
                            await session.scalars(
                                select(User).where(User.status_code == "ACTIVE", User.role_code.in_(CONFIRMED_ROLE_CODES), squad_filter)
                            )
                        ).all()
                    )
                    total = len(squad_users)
                    if total == 0:
                        continue
                    coming = not_coming = maybe = no_answer = 0
                    for su in squad_users:
                        r = await _get_user_event_response(session, su.id, event.id)
                        if r is None:
                            no_answer += 1
                        elif r.response_code == "COMING":
                            coming += 1
                        elif r.response_code in ("NOT_COMING", "NO"):
                            not_coming += 1
                        else:
                            maybe += 1
                    lines.append(f"\n📋 {event.title}: придут {coming}, нет {not_coming}, не ответили {no_answer}")

            session.add(
                Notification(
                    user_id=user.id,
                    type_code="SYSTEM",
                    title="☀️ Утренняя сводка",
                    body="\n".join(lines),
                    entity_name="morning_briefing",
                    entity_id=0,
                    send_to_tg=True,
                )
            )
        await session.commit()


# ─────────────────────── appeal SLA ─────────────────────────


SLA_HOURS = {"LOW": 72, "NORMAL": 48, "HIGH": 24, "URGENT": 4}
SLA_ESCALATE_HOURS = {"LOW": 120, "NORMAL": 72, "HIGH": 48, "URGENT": 8}


async def check_appeal_sla() -> None:
    """Hourly: remind assignee and escalate overdue appeals."""
    now = utcnow()
    async with AsyncSessionLocal() as session:
        open_appeals = list(
            (
                await session.scalars(
                    select(Appeal).where(Appeal.status_code.in_(("CREATED", "IN_PROGRESS", "NEEDS_INFO")))
                )
            ).all()
        )
        for appeal in open_appeals:
            sla_h = SLA_HOURS.get(appeal.urgency_code, 48)
            escalate_h = SLA_ESCALATE_HOURS.get(appeal.urgency_code, 72)
            age_h = (now - appeal.created_at.replace(tzinfo=timezone.utc)).total_seconds() / 3600

            # First reminder at SLA threshold
            if age_h >= sla_h:
                remind_key = f"appeal_sla_{appeal.id}_remind"
                exists = await session.scalar(
                    select(Notification.id).where(
                        Notification.entity_name == "appeal_sla_remind",
                        Notification.entity_id == appeal.id,
                    )
                )
                if not exists:
                    # Notify assignee or admins
                    targets: list[User] = []
                    if appeal.assignee_user_id:
                        u = await session.get(User, appeal.assignee_user_id)
                        if u:
                            targets.append(u)
                    if not targets:
                        targets = list(
                            (
                                await session.scalars(
                                    select(User).where(
                                        User.status_code == "ACTIVE",
                                        User.role_code.in_(("ADMIN", "SUPER_ADMIN", "PLATOON_COMMANDER")),
                                    )
                                )
                            ).all()
                        )
                    for t in targets:
                        session.add(
                            Notification(
                                user_id=t.id,
                                type_code="APPEAL",
                                title=f"⏰ Обращение #{appeal.id} без ответа",
                                body=f"Тема: «{appeal.subject}». Создано {int(age_h)} ч назад. Срочность: {appeal.urgency_code}.",
                                entity_name="appeal_sla_remind",
                                entity_id=appeal.id,
                                send_to_tg=True,
                            )
                        )

            # Escalation to admins
            if age_h >= escalate_h:
                exists_esc = await session.scalar(
                    select(Notification.id).where(
                        Notification.entity_name == "appeal_sla_escalate",
                        Notification.entity_id == appeal.id,
                    )
                )
                if not exists_esc:
                    admins = list(
                        (
                            await session.scalars(
                                select(User).where(
                                    User.status_code == "ACTIVE",
                                    User.role_code.in_(("ADMIN", "SUPER_ADMIN")),
                                )
                            )
                        ).all()
                    )
                    for admin in admins:
                        session.add(
                            Notification(
                                user_id=admin.id,
                                type_code="URGENT",
                                title=f"🚨 Эскалация: обращение #{appeal.id}",
                                body=f"Обращение «{appeal.subject}» без ответа {int(age_h)} ч. Требует вмешательства.",
                                entity_name="appeal_sla_escalate",
                                entity_id=appeal.id,
                                send_to_tg=True,
                            )
                        )
        await session.commit()


# ─────────────────────── low attendance / grades ────────────


async def check_low_attendance_and_grades() -> None:
    """Daily 20:00: warn commanders about participants with <50% attendance or avg grade <3.5."""
    now = utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    async with AsyncSessionLocal() as session:
        # Count attendance per user this month
        rows = (
            await session.execute(
                select(Attendance.user_id, Attendance.status_code, func.count(Attendance.id).label("cnt"))
                .join(ScheduleEvent, ScheduleEvent.id == Attendance.event_id)
                .where(ScheduleEvent.start_datetime >= month_start)
                .group_by(Attendance.user_id, Attendance.status_code)
            )
        ).all()

        # Build per-user stats
        user_present: dict[int, int] = {}
        user_total: dict[int, int] = {}
        for user_id, status_code, cnt in rows:
            user_total[user_id] = user_total.get(user_id, 0) + cnt
            if status_code == "PRESENT":
                user_present[user_id] = user_present.get(user_id, 0) + cnt

        low_attendance_users: list[int] = []
        for uid, total in user_total.items():
            if total >= 3:  # only if enough events
                pct = user_present.get(uid, 0) / total
                if pct < 0.5:
                    low_attendance_users.append(uid)

        # Avg grades per user this month
        grade_rows = (
            await session.execute(
                select(Attendance.user_id, AttendanceGrade.grade_value)
                .join(AttendanceGrade, AttendanceGrade.attendance_id == Attendance.id)
                .join(ScheduleEvent, ScheduleEvent.id == Attendance.event_id)
                .where(
                    ScheduleEvent.start_datetime >= month_start,
                    AttendanceGrade.grade_value.in_(("5", "4", "3", "2", "1")),
                )
            )
        ).all()

        user_grades: dict[int, list[int]] = {}
        for uid, gv in grade_rows:
            user_grades.setdefault(uid, []).append(int(gv))

        low_grade_users: list[int] = []
        for uid, grades in user_grades.items():
            if len(grades) >= 3 and sum(grades) / len(grades) < 3.5:
                low_grade_users.append(uid)

        problem_users = set(low_attendance_users) | set(low_grade_users)
        if not problem_users:
            return

        # Notify commanders
        for uid in problem_users:
            user = await session.get(User, uid)
            if not user or not user.squad_id:
                continue
            commanders = list(
                (
                    await session.scalars(
                        select(User).where(
                            User.status_code == "ACTIVE",
                            User.role_code.in_(COMMANDER_ROLE_CODES),
                            User.squad_id == user.squad_id,
                        )
                    )
                ).all()
            )
            parts: list[str] = []
            if uid in low_attendance_users:
                total = user_total.get(uid, 0)
                present = user_present.get(uid, 0)
                pct = round(present / total * 100) if total else 0
                parts.append(f"явка {pct}% за месяц ({present}/{total})")
            if uid in low_grade_users:
                grades = user_grades.get(uid, [])
                avg = round(sum(grades) / len(grades), 1) if grades else 0
                parts.append(f"средний балл {avg}")
            problem_text = ", ".join(parts)

            for commander in commanders:
                exists = await session.scalar(
                    select(Notification.id).where(
                        Notification.user_id == commander.id,
                        Notification.entity_name == "low_stats_warning",
                        Notification.entity_id == uid,
                        Notification.created_at >= month_start,
                    )
                )
                if exists:
                    continue
                session.add(
                    Notification(
                        user_id=commander.id,
                        type_code="COMMANDER",
                        title=f"⚠️ {user.full_name} — низкие показатели",
                        body=f"У участника {user.full_name}: {problem_text}. Рекомендуем уделить внимание.",
                        entity_name="low_stats_warning",
                        entity_id=uid,
                        send_to_tg=True,
                    )
                )
        await session.commit()


# ─────────────────────── overdue normatives ─────────────────


async def check_overdue_normatives() -> None:
    """Daily 19:00: remind participants who haven't submitted an active normative 3 days before deadline."""
    now = utcnow()
    in_3_days = now + timedelta(days=3)

    async with AsyncSessionLocal() as session:
        normatives = list(
            (
                await session.scalars(
                    select(Normative).where(
                        Normative.is_active.is_(True),
                        Normative.deadline_at.is_not(None),
                        Normative.deadline_at >= now,
                        Normative.deadline_at <= in_3_days,
                    )
                )
            ).all()
        )
        for norm in normatives:
            # Find users who have NOT submitted
            submitted_user_ids = set(
                (
                    await session.scalars(
                        select(NormativeSubmission.user_id).where(
                            NormativeSubmission.normative_id == norm.id,
                            NormativeSubmission.status_code.not_in(("REJECTED",)),
                        )
                    )
                ).all()
            )
            users = list(
                (
                    await session.scalars(
                        select(User).where(
                            User.status_code == "ACTIVE",
                            User.role_code.in_(CONFIRMED_ROLE_CODES),
                            (User.squad_id == norm.squad_id) if norm.squad_id else True,
                        )
                    )
                ).all()
            )
            deadline_str = norm.deadline_at.strftime("%d.%m %H:%M") if norm.deadline_at else "—"
            for user in users:
                if user.id in submitted_user_ids:
                    continue
                exists = await _notification_exists(
                    session, user_id=user.id, type_code="NORMATIVE", entity_name="normative_deadline_warn", entity_id=norm.id
                )
                if exists:
                    continue
                days_left = int((norm.deadline_at - now).total_seconds() // 86400) if norm.deadline_at else 0
                session.add(
                    Notification(
                        user_id=user.id,
                        type_code="NORMATIVE",
                        title=f"📋 Норматив «{norm.title}» — осталось {days_left} д.",
                        body=f"Срок сдачи: {deadline_str}. Вы ещё не сдали. Откройте раздел «Нормативы».",
                        entity_name="normative_deadline_warn",
                        entity_id=norm.id,
                        send_to_tg=True,
                    )
                )
        await session.commit()
