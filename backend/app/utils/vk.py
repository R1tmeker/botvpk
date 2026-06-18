from __future__ import annotations

import random

import httpx

VK_API_URL = "https://api.vk.com/method"
VK_API_VERSION = "5.199"


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
) -> dict:
    """Send a personal message to a VK user (peer_id == user's vk_id)."""
    params: dict = {
        "peer_id": peer_id,
        "message": text,
        "random_id": random.randint(1, 2_000_000_000),
    }
    if keyboard:
        params["keyboard"] = keyboard
    return await vk_call(token, "messages.send", params)
