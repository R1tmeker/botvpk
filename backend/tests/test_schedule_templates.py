from datetime import date, datetime, time, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.services import schedule_templates as templates


def template(**changes):
    return SimpleNamespace(id=1, title="Занятие", description=None, place=None, squad_id=None, requires_response=True,
        response_deadline_minutes=60, week_days="1,3", week_parity=None, start_time=time(16), end_time=time(18),
        valid_from=None, valid_to=None, is_active=True, **changes)


def test_days_are_normalized_and_multiple_days_are_generated():
    values = templates.validate_template({"title": " Занятие ", "week_days": "3,1,3", "start_time": time(16)})
    assert values["week_days"] == "1,3"
    assert values["title"] == "Занятие"
    dates = templates.occurrence_dates(template(), "Asia/Barnaul", 14, None, datetime(2026, 10, 11, 18, tzinfo=timezone.utc))
    assert dates == [date(2026, 10, 12), date(2026, 10, 14), date(2026, 10, 19), date(2026, 10, 21)]


@pytest.mark.parametrize("updates", [{"week_days": ""}, {"week_days": "0,8"}, {"week_days": "пн"}, {"end_time": time(15)},
    {"valid_from": date(2026, 10, 10), "valid_to": date(2026, 10, 9)}, {"response_deadline_minutes": -1}, {"title": " "}])
def test_invalid_template_has_useful_error(updates):
    with pytest.raises(ValueError):
        templates.validate_template({**vars(template()), **updates})


def test_week_parity_period_and_past_dates():
    item = template()
    item.week_parity = "A"
    now = datetime(2026, 10, 12, 10, tzinfo=timezone.utc)  # Monday 17:00 at the club: today's 16:00 is past.
    with pytest.raises(ValueError, match="недели 1"):
        templates.occurrence_dates(item, "Asia/Barnaul", 30, None, now)
    assert templates.occurrence_dates(item, "Asia/Barnaul", 14, date(2026, 10, 12), now) == [date(2026, 10, 14)]
    item.valid_to = date(2026, 10, 13)
    assert templates.occurrence_dates(item, "Asia/Barnaul", 30, date(2026, 10, 12), now) == []


async def test_sync_preserves_answered_manual_cancelled_and_historical_sessions(monkeypatch):
    now = datetime(2026, 10, 12, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(templates, "utcnow", lambda: now)
    def event(event_id, day, **updates):
        return SimpleNamespace(id=event_id, title="Старое название", description=None, place=None, squad_id=None, requires_response=True,
            start_datetime=datetime(2026, 10, day, 9, tzinfo=timezone.utc), end_datetime=datetime(2026, 10, day, 11, tzinfo=timezone.utc),
            response_deadline_at=None, is_overridden=False, status_code="PLANNED", **updates)
    events = [event(1, 12), event(2, 14), event(3, 19), event(4, 21), event(5, 13)]
    events[1].is_overridden = True
    events[3].status_code = "CANCELLED"
    session = AsyncMock()
    session.add = Mock()
    session.scalars.side_effect = [SimpleNamespace(all=lambda: events), SimpleNamespace(all=lambda: [events[2].id]),
        SimpleNamespace(all=lambda: []), SimpleNamespace(all=lambda: []), SimpleNamespace(all=lambda: [])]
    created, summary = await templates.generate_events(session, template(), days=14, timezone_name="Asia/Barnaul", week_a_start=None, actor_id=7, sync=True)
    assert not created
    assert summary == {"created": 0, "updated": 1, "cancelled": 1, "preserved": 3}
    assert events[0].title == "Занятие"
    assert events[1].title == events[2].title == events[3].title == "Старое название"
    assert events[4].status_code == "CANCELLED"

