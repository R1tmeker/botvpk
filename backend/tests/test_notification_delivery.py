from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.types import FSInputFile

from app.services import notification_delivery as delivery


@pytest.mark.parametrize("mime,method,field", [("image/png", "send_photo", "photo"), ("image/jpeg", "send_photo", "photo"), ("video/mp4", "send_video", "video"), ("application/pdf", "send_document", "document")])
async def test_announcement_sends_native_media_with_caption(tmp_path, mime, method, field):
    path = tmp_path / "announcement.bin"
    path.write_bytes(b"uploaded data")
    stored = SimpleNamespace(mime_type=mime, file_path=str(path), original_name="announcement.bin", telegram_file_id=None)
    bot = SimpleNamespace(send_photo=AsyncMock(), send_video=AsyncMock(), send_document=AsyncMock(), send_message=AsyncMock())
    media = SimpleNamespace(file_id="telegram-media-id")
    getattr(bot, method).return_value = SimpleNamespace(**{field: [media] if field == "photo" else media})
    await delivery.deliver_telegram_notification(bot, 123, "Заголовок\n\nТекст объявления", "buttons", stored)
    kwargs = getattr(bot, method).await_args.kwargs
    assert isinstance(kwargs[field], FSInputFile)
    assert kwargs["caption"] == "Заголовок\n\nТекст объявления"
    assert kwargs["reply_markup"] == "buttons"
    assert stored._announcement_media_id == "telegram-media-id"
    assert stored.telegram_file_id == ("telegram-media-id" if field == "document" else None)
    bot.send_message.assert_not_called()


async def test_long_caption_keeps_entire_body_and_reuses_telegram_media_id():
    stored = SimpleNamespace(mime_type="image/png", telegram_file_id="cached-photo", file_path=None)
    bot = SimpleNamespace(send_photo=AsyncMock(return_value=SimpleNamespace(photo=[])), send_message=AsyncMock())
    text = "Заголовок\n\n" + "Текст " * 1500
    await delivery.deliver_telegram_notification(bot, 123, text, None, stored)
    assert bot.send_photo.await_args.kwargs["photo"] == "cached-photo"
    assert bot.send_photo.await_args.kwargs["caption"] == "Заголовок"
    assert "".join(call.args[1] for call in bot.send_message.await_args_list) == text.split("\n\n", 1)[1]
    assert all(len(call.args[1]) <= 4000 for call in bot.send_message.await_args_list)


async def test_unsafe_or_missing_attachment_never_falls_back_to_successful_text():
    notification = SimpleNamespace(entity_name="announcements", entity_id=42)
    session = SimpleNamespace(get=AsyncMock(side_effect=[SimpleNamespace(file_id=4), SimpleNamespace(scan_status="QUARANTINED")]))
    with pytest.raises(ValueError, match="проверку"):
        await delivery.announcement_attachment(session, notification)
    session.get.side_effect = [SimpleNamespace(file_id=4), None]
    with pytest.raises(ValueError, match="не найдено"):
        await delivery.announcement_attachment(session, notification)
    bot = SimpleNamespace(send_photo=AsyncMock(), send_message=AsyncMock())
    with pytest.raises(ValueError, match="недоступен"):
        await delivery.deliver_telegram_notification(bot, 123, "Text", None, SimpleNamespace(mime_type="image/png", telegram_file_id=None, file_path="/missing/file"))
    bot.send_photo.assert_not_called()
    bot.send_message.assert_not_called()


async def test_vk_attachment_is_native_and_retries_use_same_message_id(tmp_path, monkeypatch):
    path = tmp_path / "photo.png"
    path.write_bytes(b"image")
    stored = SimpleNamespace(file_path=str(path), mime_type="image/png")
    upload, send = AsyncMock(return_value="photo-123_456"), AsyncMock()
    monkeypatch.setattr(delivery, "upload_vk_attachment", upload)
    monkeypatch.setattr(delivery, "send_vk_message", send)
    for _ in range(2):
        await delivery.deliver_vk_notification("test-token", 123, SimpleNamespace(id=42), "Text", "buttons", stored)
    assert send.await_args.kwargs["attachment"] == "photo-123_456"
    assert send.await_args.kwargs["keyboard"] == "buttons"
    assert send.await_args_list[0].kwargs["random_id"] == send.await_args_list[1].kwargs["random_id"]
