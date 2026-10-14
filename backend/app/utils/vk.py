from __future__ import annotations

import random
import json
import logging

import httpx

VK_API_URL = "https://api.vk.com/method"
VK_API_VERSION = "5.199"
logger = logging.getLogger(__name__)


def notification_keyboard(notification, site_url: str | None) -> str:
    def button(label: str, payload: dict, color: str = "secondary") -> dict:
        return {"action": {"type": "text", "label": label, "payload": json.dumps(payload)}, "color": color}

    rows = []
    if notification.type_code == "SCHEDULE_POLL" and notification.entity_id:
        base = {"action": "event_response", "event_id": notification.entity_id}
        rows = [[button("Приду", {**base, "response_code": "COMING"}, "positive"),
                 button("Не приду", {**base, "response_code": "NOT_COMING"}, "negative")],
                [button("Уточню", {**base, "response_code": "MAYBE"})]]
    elif notification.entity_name == "appeals" and notification.entity_id:
        rows.append([button("Переписка", {"action": "appeal_thread", "id": notification.entity_id, "page": 0})])
    elif notification.type_code == "EVENT_RESPONSE_REMINDER":
        rows.append([button("Ответить в расписании", {"action": "menu", "section": "schedule"})])
    rows.append([button("Подробнее", {"action": "inbox_view", "id": notification.id, "page": 0})])
    if site_url and notification.deep_link and notification.deep_link.startswith("/") and not notification.deep_link.startswith("//") and "\\" not in notification.deep_link:
        from urllib.parse import urljoin
        rows.append([{"action": {"type": "open_link", "label": "Открыть на сайте", "link": urljoin(site_url.rstrip("/") + "/", notification.deep_link.lstrip("/"))}}])
    return json.dumps({"inline": True, "buttons": rows}, ensure_ascii=False)


class VkApiError(RuntimeError):
    def __init__(self, message: str, *, error_code: int | None = None):
        super().__init__(message)
        self.error_code = error_code


async def vk_call(token: str, method: str, params: dict) -> dict:
    payload = {"access_token": token, "v": VK_API_VERSION, **params}
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(f"{VK_API_URL}/{method}", data=payload)
    data = resp.json()
    if "error" in data:
        err = data["error"]
        raise VkApiError(f"VK {method} failed: {err.get('error_code')} {err.get('error_msg')}", error_code=err.get("error_code"))
    return data.get("response", {})


async def send_vk_message(
    token: str,
    peer_id: int,
    text: str,
    keyboard: str | None = None,
    attachment: str | None = None,
    random_id: int | None = None,
) -> dict:
    """Send a personal message to a VK user (peer_id == user's vk_id)."""
    params: dict = {
        "peer_id": peer_id,
        "message": text,
        "random_id": random_id if random_id is not None else random.randint(1, 2_000_000_000),
    }
    if keyboard:
        params["keyboard"] = keyboard
    if attachment:
        params["attachment"] = attachment
    try:
        return await vk_call(token, "messages.send", params)
    except VkApiError as exc:
        # VK can reject an otherwise valid external domain in open_link. The
        # rejected message was not accepted; preserve native buttons and retry
        # this same message ID once instead of blocking notification delivery.
        if exc.error_code != 911 or "invalid link" not in str(exc).lower() or not keyboard:
            raise
        changed, fallback = keyboard_without_links(keyboard)
        if not changed:
            raise
        params = params.copy()
        if fallback:
            params["keyboard"] = fallback
        else:
            params.pop("keyboard", None)
        logger.warning("VK rejected an external keyboard link; retrying with native buttons")
        return await vk_call(token, "messages.send", params)


def keyboard_without_links(keyboard: str) -> tuple[bool, str | None]:
    try:
        data = json.loads(keyboard)
    except (ValueError, TypeError):
        return False, None
    if not isinstance(data, dict) or not isinstance(data.get("buttons"), list):
        return False, None
    rows, changed = [], False
    for row in data["buttons"]:
        if not isinstance(row, list) or any(not isinstance(button, dict) or not isinstance(button.get("action"), dict) for button in row):
            return False, None
        native = [button for button in row if button["action"].get("type") != "open_link"]
        changed |= len(native) != len(row)
        if native:
            rows.append(native)
    if not changed:
        return False, None
    if not rows:
        return True, None
    data["buttons"] = rows
    return True, json.dumps(data, ensure_ascii=False)


async def upload_vk_attachment(token: str, peer_id: int, path: str, mime_type: str) -> str:
    from vkbottle import API, DocMessagesUploader, PhotoMessageUploader
    api = API(token=token)
    try:
        uploader = PhotoMessageUploader(api) if mime_type in {"image/jpeg", "image/png"} else DocMessagesUploader(api)
        return await uploader.upload(file_source=path, peer_id=peer_id)
    finally:
        await api.http_client.close()
