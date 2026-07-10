from __future__ import annotations

import hashlib
import hmac
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..database import get_db_session
from ..dependencies.auth import CurrentUser, require_role
from ..models import CalendarSubscription, ScheduleEvent, User
from ..roles import RoleLevel
from ..schemas.core import MessageResponse
from ..schemas.product import CalendarSubscription as CalendarSubscriptionSchema
from ..services.calendar import build_calendar
from ..utils.audit import record_audit, utcnow

router = APIRouter(prefix="/calendar", tags=["calendar"])


def token_digest(settings: Settings, token: str) -> str:
    return hmac.new(
        settings.effective_session_secret.encode(),
        token.encode(),
        hashlib.sha256,
    ).hexdigest()


def require_profile(current_user: CurrentUser) -> int:
    if current_user.user_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User profile is required.")
    return current_user.user_id


@router.post("/subscription", response_model=CalendarSubscriptionSchema)
async def create_calendar_subscription(
    request: Request,
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> CalendarSubscriptionSchema:
    user_id = require_profile(current_user)
    token = secrets.token_urlsafe(32)
    subscription = await session.scalar(
        select(CalendarSubscription).where(CalendarSubscription.user_id == user_id).with_for_update()
    )
    now = utcnow()
    if subscription is None:
        subscription = CalendarSubscription(user_id=user_id, token_digest=token_digest(settings, token))
        session.add(subscription)
    else:
        subscription.token_digest = token_digest(settings, token)
        subscription.created_at = now
        subscription.revoked_at = None
    await session.flush()
    await record_audit(
        session,
        user_id=user_id,
        action_code="calendar.subscription.issue",
        entity_name="calendar_subscriptions",
        entity_id=subscription.id,
    )
    await session.commit()
    if settings.site_url:
        url = f"{settings.site_url.rstrip('/')}/api/calendar/{token}.ics"
    else:
        url = str(request.url_for("calendar_feed", token=token))
    return CalendarSubscriptionSchema(url=url, created_at=subscription.created_at)


@router.delete("/subscription", response_model=MessageResponse)
async def revoke_calendar_subscription(
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    user_id = require_profile(current_user)
    subscription = await session.scalar(
        select(CalendarSubscription).where(CalendarSubscription.user_id == user_id).with_for_update()
    )
    if subscription is not None and subscription.revoked_at is None:
        subscription.revoked_at = utcnow()
        await record_audit(
            session,
            user_id=user_id,
            action_code="calendar.subscription.revoke",
            entity_name="calendar_subscriptions",
            entity_id=subscription.id,
        )
        await session.commit()
    return MessageResponse(detail="Calendar subscription revoked.")


@router.get("/{token}.ics", name="calendar_feed", include_in_schema=False)
async def calendar_feed(
    token: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    subscription = await session.scalar(
        select(CalendarSubscription).where(
            CalendarSubscription.token_digest == token_digest(settings, token),
            CalendarSubscription.revoked_at.is_(None),
        )
    )
    if subscription is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calendar subscription not found.")
    user = await session.get(User, subscription.user_id)
    if user is None or user.status_code != "ACTIVE":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calendar subscription not found.")
    events = list(
        (
            await session.scalars(
                select(ScheduleEvent)
                .where(or_(ScheduleEvent.squad_id.is_(None), ScheduleEvent.squad_id == user.squad_id))
                .order_by(ScheduleEvent.start_datetime)
                .limit(5000)
            )
        ).all()
    )
    host = request.url.hostname or "botvpk.local"
    content = build_calendar(events, calendar_name="ВПК Звезда", host=host)
    return Response(
        content=content,
        media_type="text/calendar; charset=utf-8",
        headers={"Cache-Control": "private, no-store", "Content-Disposition": "inline; filename=botvpk.ics"},
    )
