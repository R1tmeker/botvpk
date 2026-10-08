from __future__ import annotations

import random
import json

import httpx

VK_API_URL = "https://api.vk.com/method"
VK_API_VERSION = "5.199"


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
    rows.append([button("Подробнее", {"action": "inbox_view", "id": notification.id, "page": 0})])
    if site_url and notification.deep_link and notification.deep_link.startswith("/") and not notification.deep_link.startswith("//") and "\\" not in notification.deep_link:
        from urllib.parse import urljoin
        rows.append([{"action": {"type": "open_link", "label": "Открыть на сайте", "link": urljoin(site_url.rstrip("/") + "/", notification.deep_link.lstrip("/"))}}])
    return json.dumps({"inline": True, "buttons": rows}, ensure_ascii=False)


class VkApiError(RuntimeError):
    pass


async def vk_call(token: str, method: str, params: dict) -> dict:
    payload = {"access_token": token, "v": VK_API_VERSION, **params}
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(f"{VK_API_URL}/{method}", data=payload)
    data = resp.json()
    if "error" in data:
        err = data["error"]
        raise VkApiError(f"VK {method} failed: {err.get('error_code')} {err.get('error_msg')}")
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
    return await vk_call(token, "messages.send", params)


async def upload_vk_attachment(token: str, peer_id: int, path: str, mime_type: str) -> str:
    from vkbottle import API, DocMessagesUploader, PhotoMessageUploader
    api = API(token=token)
    try:
        uploader = PhotoMessageUploader(api) if mime_type in {"image/jpeg", "image/png"} else DocMessagesUploader(api)
        return await uploader.upload(file_source=path, peer_id=peer_id)
    finally:
        await api.http_client.close()
