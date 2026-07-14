from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..database import get_db_session
from ..dependencies.auth import CurrentUser, require_role
from ..models import (
    Appeal,
    Attendance,
    EventResponse,
    JoinApplication,
    MenuCard,
    NormativeSubmission,
    Notification,
    PromoBlock,
    ScheduleEvent,
    User,
    UserDashboardSetting,
)
from ..roles import CONFIRMED_ROLES, RoleLevel
from ..schemas.core import DashboardSettingRead, DashboardSettingsUpdate, MessageResponse
from ..schemas.product import ActionItem, ActionItemExecutionResult, DashboardBootstrap
from ..services.action_center import ActionCenterError, execute_action_item
from ..services.realtime import publish_realtime_event

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def require_profile(current_user: CurrentUser) -> int:
    if current_user.user_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User profile is required.")
    return current_user.user_id


@router.get("/settings", response_model=list[DashboardSettingRead])
async def dashboard_settings(
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> list[UserDashboardSetting]:
    user_id = require_profile(current_user)
    statement = (
        select(UserDashboardSetting)
        .where(UserDashboardSetting.user_id == user_id)
        .order_by(UserDashboardSetting.sort_order, UserDashboardSetting.block_code)
    )
    return list((await session.scalars(statement)).all())


@router.patch("/settings", response_model=list[DashboardSettingRead])
@router.put("/settings", response_model=list[DashboardSettingRead])
async def update_dashboard_settings(
    payload: DashboardSettingsUpdate,
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> list[UserDashboardSetting]:
    user_id = require_profile(current_user)
    existing = {
        item.block_code: item
        for item in (
            await session.scalars(select(UserDashboardSetting).where(UserDashboardSetting.user_id == user_id))
        ).all()
    }
    now = datetime.now(timezone.utc)
    saved: list[UserDashboardSetting] = []
    required_codes = set(
        (
            await session.scalars(
                select(MenuCard.code).where(MenuCard.is_active.is_(True), MenuCard.is_required.is_(True))
            )
        ).all()
    )
    for payload_item in payload.items:
        if payload_item.is_hidden and payload_item.block_code in required_codes:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Required dashboard block cannot be hidden.")
        item = existing.get(payload_item.block_code)
        if item is None:
            item = UserDashboardSetting(user_id=user_id, block_code=payload_item.block_code)
            session.add(item)
        item.sort_order = payload_item.sort_order
        item.is_hidden = payload_item.is_hidden
        item.is_pinned = payload_item.is_pinned
        item.view_mode_code = payload_item.view_mode_code
        item.updated_at = now
        saved.append(item)
    await session.commit()
    for item in saved:
        await session.refresh(item)
    return sorted(saved, key=lambda item: (item.sort_order, item.block_code))


@router.post("/settings/reset", response_model=MessageResponse)
async def reset_dashboard_settings(
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    user_id = require_profile(current_user)
    items = list(
        (
            await session.scalars(select(UserDashboardSetting).where(UserDashboardSetting.user_id == user_id))
        ).all()
    )
    for item in items:
        await session.delete(item)
    await session.commit()
    return MessageResponse(detail=f"Reset {len(items)} dashboard settings.")


@router.get("/action-items", response_model=list[ActionItem])
async def dashboard_action_items(
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_SQUAD_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> list[ActionItem]:
    now = datetime.now(timezone.utc)
    items: list[ActionItem] = []
    scoped_squad_id = current_user.squad_id if current_user.role_level < RoleLevel.SQUAD_COMMANDER else None

    upcoming_query = select(ScheduleEvent).where(
        ScheduleEvent.requires_response.is_(True),
        ScheduleEvent.status_code != "CANCELLED",
        ScheduleEvent.start_datetime >= now,
        ScheduleEvent.start_datetime <= now + timedelta(days=14),
    )
    if scoped_squad_id is not None:
        upcoming_query = upcoming_query.where(
            (ScheduleEvent.squad_id.is_(None)) | (ScheduleEvent.squad_id == scoped_squad_id)
        )
    upcoming = list((await session.scalars(upcoming_query.limit(100))).all())
    missing_responses = 0
    next_response_due = None
    for event in upcoming:
        users_query = select(func.count(User.id)).where(
            User.status_code == "ACTIVE",
            User.role_code.in_(CONFIRMED_ROLES),
        )
        if event.squad_id is not None:
            users_query = users_query.where(User.squad_id == event.squad_id)
        elif scoped_squad_id is not None:
            users_query = users_query.where(User.squad_id == scoped_squad_id)
        expected = int(await session.scalar(users_query) or 0)
        answered = int(
            await session.scalar(select(func.count(EventResponse.id)).where(EventResponse.event_id == event.id)) or 0
        )
        missing_responses += max(0, expected - answered)
        if event.response_deadline_at and (next_response_due is None or event.response_deadline_at < next_response_due):
            next_response_due = event.response_deadline_at
    if missing_responses:
        items.append(
            ActionItem(
                code="MISSING_EVENT_RESPONSES",
                title="Участники без ответа",
                description="Запросите ответы на ближайшие события.",
                severity="warning",
                count=missing_responses,
                due_at=next_response_due,
                deep_link="/schedule?filter=unanswered",
                bulk_actions=["send_reminder"],
            )
        )

    submissions_query = (
        select(func.count(NormativeSubmission.id))
        .join(User, User.id == NormativeSubmission.user_id)
        .where(NormativeSubmission.status_code.in_(("PENDING", "SUBMITTED", "PENDING_REVIEW")))
    )
    if scoped_squad_id is not None:
        submissions_query = submissions_query.where(User.squad_id == scoped_squad_id)
    pending_submissions = int(await session.scalar(submissions_query) or 0)
    if pending_submissions:
        items.append(
            ActionItem(
                code="PENDING_NORMATIVES",
                title="Нормативы ожидают проверки",
                description="Проверьте новые сдачи и отправьте решение.",
                severity="warning",
                count=pending_submissions,
                deep_link="/normatives?tab=review",
                bulk_actions=["assign_reviewer"],
            )
        )

    appeals_query = select(func.count(Appeal.id)).join(User, User.id == Appeal.author_user_id).where(
        Appeal.status_code == "CREATED"
    )
    if scoped_squad_id is not None:
        appeals_query = appeals_query.where(User.squad_id == scoped_squad_id)
    new_appeals = int(await session.scalar(appeals_query) or 0)
    if new_appeals:
        items.append(
            ActionItem(
                code="UNPROCESSED_APPEALS",
                title="Необработанные обращения",
                description="Назначьте ответственного или дайте первый ответ.",
                severity="critical",
                count=new_appeals,
                due_at=now + timedelta(hours=24),
                deep_link="/appeals?status=created",
                bulk_actions=["assign"],
            )
        )

    past_query = select(ScheduleEvent).where(
        ScheduleEvent.status_code != "CANCELLED",
        ScheduleEvent.start_datetime < now,
        ScheduleEvent.start_datetime >= now - timedelta(days=14),
    )
    if scoped_squad_id is not None:
        past_query = past_query.where(
            (ScheduleEvent.squad_id.is_(None)) | (ScheduleEvent.squad_id == scoped_squad_id)
        )
    unclosed_events = 0
    for event in (await session.scalars(past_query.limit(100))).all():
        marks = int(
            await session.scalar(
                select(func.count(Attendance.id)).where(
                    Attendance.event_id == event.id,
                    Attendance.status_code != "NOT_MARKED",
                    Attendance.is_draft.is_(False),
                )
            ) or 0
        )
        if marks == 0:
            unclosed_events += 1
    if unclosed_events:
        items.append(
            ActionItem(
                code="UNCLOSED_ATTENDANCE",
                title="Незакрытая явка",
                description="В прошедших событиях нет итоговых отметок.",
                severity="critical",
                count=unclosed_events,
                due_at=now,
                deep_link="/attendance?filter=unclosed",
                bulk_actions=["mark_all_present"],
            )
        )

    if current_user.role_level >= RoleLevel.SQUAD_COMMANDER:
        overdue_applications = int(
            await session.scalar(
                select(func.count(JoinApplication.id)).where(
                    JoinApplication.status_code == "NEW",
                    JoinApplication.created_at < now - timedelta(days=2),
                )
            ) or 0
        )
        if overdue_applications:
            items.append(
                ActionItem(
                    code="OVERDUE_APPLICATIONS",
                    title="Просроченные заявки",
                    description="Заявки ожидают решения более двух суток.",
                    severity="warning",
                    count=overdue_applications,
                    due_at=now,
                    deep_link="/admin/applications?filter=overdue",
                    bulk_actions=["assign_reviewer"],
                )
            )

    if current_user.role_level >= RoleLevel.ADMIN:
        delivery_errors = int(
            await session.scalar(select(func.count(Notification.id)).where(Notification.delivery_error.is_not(None))) or 0
        )
        if delivery_errors:
            items.append(
                ActionItem(
                    code="NOTIFICATION_DELIVERY_ERRORS",
                    title="Ошибки доставки уведомлений",
                    description="Проверьте канал и повторите неуспешные отправки.",
                    severity="critical",
                    count=delivery_errors,
                    due_at=now,
                    deep_link="/admin/notifications?status=failed",
                    bulk_actions=["retry_delivery"],
                )
            )

    severity_order = {"critical": 0, "warning": 1, "info": 2}
    return sorted(items, key=lambda item: (severity_order[item.severity], item.due_at or now))


@router.get("/bootstrap", response_model=DashboardBootstrap)
async def dashboard_bootstrap(
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> DashboardBootstrap:
    settings = await dashboard_settings(current_user, session)
    now = datetime.now(timezone.utc)
    promo_query = (
        select(PromoBlock)
        .where(PromoBlock.is_active.is_(True))
        .where((PromoBlock.active_from.is_(None)) | (PromoBlock.active_from <= now))
        .where((PromoBlock.active_to.is_(None)) | (PromoBlock.active_to >= now))
        .where(PromoBlock.audience_code.in_(("ALL", current_user.role_code)))
        .order_by(PromoBlock.sort_order, PromoBlock.created_at.desc())
    )
    promo = list((await session.scalars(promo_query)).all())
    action_items = (
        await dashboard_action_items(current_user, session)
        if current_user.role_level >= RoleLevel.DEPUTY_SQUAD_COMMANDER
        else []
    )
    return DashboardBootstrap(settings=settings, promo=promo, action_items=action_items)


@router.post(
    "/action-items/{item_code}/actions/{action_code}",
    response_model=ActionItemExecutionResult,
)
async def execute_dashboard_action(
    item_code: str,
    action_code: str,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_SQUAD_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> ActionItemExecutionResult:
    actor_id = require_profile(current_user)
    try:
        affected = await execute_action_item(
            session,
            item_code=item_code,
            action_code=action_code,
            actor_id=actor_id,
            role_level=current_user.role_level,
            squad_id=current_user.squad_id,
        )
    except ActionCenterError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await publish_realtime_event(
        settings,
        event_type="dashboard_action_executed",
        query_keys=["dashboard", "attendance", "notifications", "normatives", "appeals"],
    )
    return ActionItemExecutionResult(
        item_code=item_code,
        action_code=action_code,
        affected=affected,
        detail=f"Обработано объектов: {affected}",
    )
