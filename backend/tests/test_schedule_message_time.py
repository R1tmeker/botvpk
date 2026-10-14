from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app import background


@pytest.mark.asyncio
@pytest.mark.parametrize("job", ["reminder", "morning"])
async def test_scheduled_notifications_show_barnaul_wall_time(monkeypatch, job):
    event = SimpleNamespace(id=1, title="Занятие в ВУЦ", start_datetime=datetime(2026, 10, 14, 9, tzinfo=timezone.utc), squad_id=None, place=None)
    user = SimpleNamespace(id=2, role_code="PARTICIPANT", squad_id=1)
    batches = [[event], [user]] if job == "reminder" else [[event], [user], [], []]
    db = SimpleNamespace(scalars=AsyncMock(side_effect=[SimpleNamespace(all=lambda batch=batch: batch) for batch in batches]),
                         scalar=AsyncMock(return_value=None), add=Mock(), commit=AsyncMock())
    ctx = AsyncMock()
    ctx.__aenter__.return_value = db
    monkeypatch.setattr(background, "AsyncSessionLocal", lambda:ctx)
    monkeypatch.setattr(background, "get_settings", lambda:SimpleNamespace(timezone="Asia/Barnaul"))
    if job == "reminder":
        await background.send_event_reminders_2h()
    else:
        await background.send_morning_briefing(SimpleNamespace(timezone="Asia/Barnaul"))
    notification = db.add.call_args.args[0]
    assert "16:00" in notification.body
    assert "13:00" not in notification.body
    assert "Барнаул" in notification.body
