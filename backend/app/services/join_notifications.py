from __future__ import annotations

from sqlalchemy import select

from ..models import Notification, User

APPLICATION_REVIEWER_ROLES = ("DEPUTY_PLATOON_COMMANDER", "PLATOON_COMMANDER", "ADMIN", "SUPER_ADMIN")


async def notify_new_application(session, application) -> int:
    reviewers = list(
        (
            await session.scalars(
                select(User).where(
                    User.status_code == "ACTIVE",
                    User.role_code.in_(APPLICATION_REVIEWER_ROLES),
                )
            )
        ).all()
    )
    existing = set(
        (
            await session.scalars(
                select(Notification.user_id).where(
                    Notification.type_code == "NEW_APPLICATION",
                    Notification.entity_name == "join_applications",
                    Notification.entity_id == application.id,
                )
            )
        ).all()
    )
    for reviewer in reviewers:
        if reviewer.id in existing:
            continue
        session.add(
            Notification(
                user_id=reviewer.id,
                type_code="NEW_APPLICATION",
                category_code="SYSTEM",
                priority_code="URGENT",
                title="Новая заявка на вступление",
                body=f"{application.full_name} подал(а) заявку в ВПК. Откройте заявку, чтобы принять решение.",
                entity_name="join_applications",
                entity_id=application.id,
                deep_link=f"/admin?tab=applications&application={application.id}",
                send_to_tg=True,
                send_to_app=True,
            )
        )
    return len([user for user in reviewers if user.id not in existing])
