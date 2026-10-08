from __future__ import annotations

from pathlib import Path

from aiogram.types import FSInputFile

from ..models import Announcement, File, Notification
from ..utils.vk import send_vk_message, upload_vk_attachment
from .delivery import call_telegram_with_rate_limit


async def announcement_attachment(session, notification: Notification) -> File | None:
    if notification.entity_name != "announcements" or notification.entity_id is None:
        return None
    announcement = await session.get(Announcement, notification.entity_id)
    if announcement is None or announcement.file_id is None:
        return None
    stored = await session.get(File, announcement.file_id)
    if stored is None:
        raise ValueError("Вложение объявления не найдено.")
    if stored.scan_status not in {"CLEAN", "REENCODED", "LEGACY_TRUSTED"}:
        raise ValueError("Вложение объявления не прошло проверку.")
    return stored


def file_source(stored: File):
    if getattr(stored, "_announcement_media_id", None):
        return stored._announcement_media_id
    if stored.file_path and Path(stored.file_path).is_file():
        return FSInputFile(stored.file_path, filename=stored.original_name or Path(stored.file_path).name)
    if stored.telegram_file_id:
        return stored.telegram_file_id
    if not stored.file_path or not Path(stored.file_path).is_file():
        raise ValueError("Файл объявления недоступен на сервере.")
    return FSInputFile(stored.file_path, filename=stored.original_name or Path(stored.file_path).name)


async def deliver_telegram_notification(bot, chat_id: int, text: str, keyboard, stored: File | None = None) -> None:
    remaining = text
    if stored:
        caption = text if len(text) <= 1024 else text.split("\n", 1)[0][:1024]
        remaining = "" if caption == text else text[len(caption):].lstrip("\n")
        source = file_source(stored)
        method = bot.send_photo if stored.mime_type in {"image/jpeg", "image/png"} else bot.send_video if stored.mime_type == "video/mp4" else bot.send_document
        media_key = "photo" if stored.mime_type in {"image/jpeg", "image/png"} else "video" if stored.mime_type == "video/mp4" else "document"
        result = await call_telegram_with_rate_limit(lambda: method(chat_id, **{media_key: source}, caption=caption, reply_markup=keyboard, parse_mode=None))
        media = getattr(result, media_key, None)
        if isinstance(media, (list, tuple)) and media:
            media = media[-1]
        if media is not None and isinstance(getattr(media, "file_id", None), str):
            # A Telegram photo ID cannot be reused by send_document elsewhere.
            # Cache native media only for this batch; keep the shared document ID unchanged.
            stored._announcement_media_id = media.file_id
            if media_key == "document":
                stored.telegram_file_id = media.file_id
    for start in range(0, len(remaining), 4000):
        chunk = remaining[start:start + 4000]
        await call_telegram_with_rate_limit(lambda chunk=chunk, start=start: bot.send_message(chat_id, chunk, reply_markup=keyboard if start == 0 and not stored else None, parse_mode=None))


async def deliver_vk_notification(token: str, peer_id: int, notification: Notification, text: str, keyboard: str, stored: File | None = None) -> None:
    attachment = None
    if stored:
        if not stored.file_path or not Path(stored.file_path).is_file():
            raise ValueError("Файл объявления недоступен для отправки в VK.")
        attachment = await upload_vk_attachment(token, peer_id, stored.file_path, stored.mime_type or "")
    for index, start in enumerate(range(0, max(1, len(text)), 4000)):
        await send_vk_message(token, peer_id, text[start:start + 4000], keyboard=keyboard if index == 0 else None,
            attachment=attachment if index == 0 else None, random_id=(notification.id * 100 + index) % 2_147_483_647 or 1)
