from __future__ import annotations

import json
import logging

from ..config import Settings
from ..models import Notification, WebPushSubscription

logger = logging.getLogger(__name__)


def web_push_available(settings: Settings) -> bool:
    return bool(settings.web_push_vapid_public_key and settings.web_push_vapid_private_key)


async def send_web_push_notification(
    settings: Settings,
    subscription: WebPushSubscription,
    notification: Notification,
) -> bool:
    if not web_push_available(settings):
        return False
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        logger.warning("Web Push requested, but pywebpush is not installed")
        return False
    payload = json.dumps(
        {
            "title": notification.title,
            "body": notification.body or "",
            "url": notification.deep_link or "/notifications",
            "notification_id": notification.id,
        },
        ensure_ascii=False,
    )
    try:
        webpush(
            subscription_info=subscription.subscription_json,
            data=payload,
            vapid_private_key=settings.web_push_vapid_private_key,
            vapid_claims={"sub": settings.web_push_vapid_sub},
        )
        return True
    except WebPushException as exc:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        if status_code in {404, 410}:
            subscription.is_active = False
        logger.warning("Failed to send Web Push subscription_id=%s status=%s", subscription.id, status_code)
        return False
    except Exception:  # noqa: BLE001
        logger.exception("Unexpected Web Push failure subscription_id=%s", subscription.id)
        return False
