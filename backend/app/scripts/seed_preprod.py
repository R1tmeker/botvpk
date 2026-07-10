from __future__ import annotations

import asyncio
from datetime import timedelta

from sqlalchemy import select

from ..database import AsyncSessionLocal
from ..models import Attendance, Normative, ScheduleEvent, Squad, User
from ..utils.audit import utcnow
from ..utils.password import hash_password

SYNTHETIC_USERS = (
    (990000001, "Участник Тестовый", "PARTICIPANT"),
    (990000002, "Командир Тестовый", "SQUAD_COMMANDER"),
    (990000003, "Администратор Тестовый", "SUPER_ADMIN"),
)


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        users: dict[int, User] = {}
        for telegram_id, full_name, role_code in SYNTHETIC_USERS:
            user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
            if user is None:
                user = User(
                    telegram_id=telegram_id,
                    full_name=full_name,
                    username=f"preprod_{telegram_id}",
                    role_code=role_code,
                    status_code="ACTIVE",
                    password_hash=hash_password("Preprod!12345"),
                    password_set_at=utcnow(),
                )
                session.add(user)
                await session.flush()
            users[telegram_id] = user
        squad = await session.scalar(select(Squad).where(Squad.name == "Тестовое отделение"))
        if squad is None:
            squad = Squad(
                name="Тестовое отделение",
                commander_user_id=users[990000002].id,
            )
            session.add(squad)
            await session.flush()
        for user in users.values():
            user.squad_id = squad.id

        event = await session.scalar(select(ScheduleEvent).where(ScheduleEvent.title == "Тестовая самоотметка"))
        if event is None:
            event = ScheduleEvent(
                title="Тестовая самоотметка",
                description="Синтетическое событие предрелизного стенда",
                start_datetime=utcnow() + timedelta(minutes=5),
                end_datetime=utcnow() + timedelta(hours=1),
                place="Учебный класс",
                squad_id=squad.id,
                self_checkin_enabled=True,
                requires_response=True,
                created_by_user_id=users[990000003].id,
            )
            session.add(event)
            await session.flush()
        attendance = await session.scalar(
            select(Attendance).where(
                Attendance.event_id == event.id,
                Attendance.user_id == users[990000001].id,
            )
        )
        if attendance is None:
            session.add(Attendance(event_id=event.id, user_id=users[990000001].id))
        normative = await session.scalar(select(Normative).where(Normative.title == "Тестовый норматив"))
        if normative is None:
            session.add(
                Normative(
                    title="Тестовый норматив",
                    description="Синтетические данные",
                    type_code="GENERAL",
                    target_audience="PARTICIPANTS",
                    squad_id=squad.id,
                    created_by_user_id=users[990000003].id,
                )
            )
        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed())
