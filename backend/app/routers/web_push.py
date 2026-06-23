from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..database import get_db_session
from ..dependencies.auth import CurrentUser, get_current_user
from ..models import WebPushSubscription
from ..roles import RoleLevel
from ..utils.audit import record_audit

router = APIRouter(prefix="/web-push", tags=["web-push"])


class WebPushSubscriptionRequest(BaseModel):
    endpoint: str = Field(min_length=1, max_length=500)
    keys: dict[str, str]
    expirationTime: int | None = None


class WebPushPublicKeyResponse(BaseModel):
    available: bool
    public_key: str | None = None


@router.get("/public-key", response_model=WebPushPublicKeyResponse)
async def web_push_public_key(settings: Settings = Depends(get_settings)) -> WebPushPublicKeyResponse:
    return WebPushPublicKeyResponse(
        available=bool(settings.web_push_vapid_public_key and settings.web_push_vapid_private_key),
        public_key=settings.web_push_vapid_public_key,
    )


@router.post("/subscriptions", status_code=status.HTTP_201_CREATED)
async def upsert_web_push_subscription(
    payload: WebPushSubscriptionRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, bool]:
    if current_user.user_id is None or current_user.role_level < RoleLevel.PARTICIPANT:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User profile is required.")
    if not payload.keys.get("p256dh") or not payload.keys.get("auth"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid push subscription keys.")
    subscription_json: dict[str, Any] = payload.model_dump()
    item = await session.scalar(select(WebPushSubscription).where(WebPushSubscription.endpoint == payload.endpoint))
    now = datetime.now(timezone.utc)
    if item is None:
        item = WebPushSubscription(
            user_id=current_user.user_id,
            endpoint=payload.endpoint,
            subscription_json=subscription_json,
            user_agent=request.headers.get("user-agent"),
            is_active=True,
        )
        session.add(item)
    else:
        item.user_id = current_user.user_id
        item.subscription_json = subscription_json
        item.user_agent = request.headers.get("user-agent")
        item.is_active = True
        item.updated_at = now
    await session.flush()
    await record_audit(
        session,
        user_id=current_user.user_id,
        action_code="web_push.subscribe",
        entity_name="web_push_subscriptions",
        entity_id=item.id,
    )
    await session.commit()
    return {"subscribed": True}


@router.delete("/subscriptions")
async def delete_web_push_subscription(
    payload: WebPushSubscriptionRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, bool]:
    if current_user.user_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User profile is required.")
    item = await session.scalar(
        select(WebPushSubscription).where(
            WebPushSubscription.endpoint == payload.endpoint,
            WebPushSubscription.user_id == current_user.user_id,
        )
    )
    if item is not None:
        item.is_active = False
        item.updated_at = datetime.now(timezone.utc)
        await record_audit(
            session,
            user_id=current_user.user_id,
            action_code="web_push.unsubscribe",
            entity_name="web_push_subscriptions",
            entity_id=item.id,
        )
        await session.commit()
    return {"subscribed": False}
