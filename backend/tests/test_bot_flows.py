from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app import bot, vk_bot
from app.roles import RoleLevel
from app.services import bot_content
from app.services.bot_navigation import entity_id, menu_rows, page_number
from app.utils.vk import notification_keyboard


@pytest.fixture(autouse=True)
def isolated_dialog_storage(monkeypatch):
    # Unit tests must not share a Redis connection across pytest's event loops.
    monkeypatch.setattr(vk_bot, "_get_redis", lambda: None)
    monkeypatch.setattr(vk_bot, "_vk_login_state", {})
    monkeypatch.setattr(vk_bot, "_vk_event_state", {})


@pytest.fixture
def member():
    return SimpleNamespace(id=7, vk_id=42, telegram_id=123, role_code="PARTICIPANT", status_code="ACTIVE", squad_id=2, full_name="Иван Иванов")


@pytest.fixture
def vk_message():
    return SimpleNamespace(from_id=42, peer_id=42, text="Меню", payload=None, attachments=[], answer=AsyncMock())


@pytest.fixture
def session(monkeypatch):
    db = AsyncMock()
    db.scalars.return_value = SimpleNamespace(all=lambda: [])
    context = AsyncMock()
    context.__aenter__.return_value = db
    for module in (bot, vk_bot):
        monkeypatch.setattr(module, "AsyncSessionLocal", Mock(return_value=context))
    return db


@pytest.mark.parametrize("action,helper", [("join", "start_join_dialog"), ("password", "start_password_dialog")])
async def test_menu_starts_dialog_for_callback_owner_not_bot_message_author(monkeypatch, member, action, helper):
    monkeypatch.setattr(bot, "find_user", AsyncMock(return_value=member))
    start = AsyncMock()
    monkeypatch.setattr(bot, helper, start)
    message = SimpleNamespace(from_user=SimpleNamespace(id=999), answer=AsyncMock())
    callback = SimpleNamespace(from_user=SimpleNamespace(id=123), message=message, data=f"menu:{action}", answer=AsyncMock())
    state = AsyncMock()
    await bot.menu_callback(callback, state)
    start.assert_awaited_once_with(message, state, 123)


@pytest.mark.parametrize("role", list(RoleLevel))
def test_navigation_never_truncates_three_competing_labels(role):
    for section in ("home", "personal", "contact", "account", "command"):
        rows = menu_rows(role, section)
        assert all(1 <= len(row) <= 2 for row in rows)
        assert all(len(label) <= 18 for row in rows for label, _ in row)
        actions = {action for row in rows for _, action in row}
        if role < RoleLevel.PARTICIPANT:
            assert not actions.intersection({"schedule", "checkin", "normatives", "notifications"})
        if role < RoleLevel.DEPUTY_SQUAD_COMMANDER:
            assert not actions.intersection({"command", "applications", "admin", "journal"})


@pytest.mark.parametrize("value", [True, False, -1, 1.5, "-1", "1e2", "١", [], {}, 10001, "999999999999999"])
def test_forged_page_offsets_are_rejected(value):
    assert page_number(value) is None


@pytest.mark.parametrize("value", [True, False, -1, 0, "-7", "١", [], {}, 2**63])
def test_forged_entity_ids_are_rejected(value):
    assert entity_id(value) is None


@pytest.mark.asyncio
async def test_telegram_section_navigation_reuses_message_and_leaves_dialog(monkeypatch, member):
    monkeypatch.setattr(bot, "find_user", AsyncMock(return_value=member))
    message = SimpleNamespace(edit_text=AsyncMock(), answer=AsyncMock())
    callback = SimpleNamespace(from_user=SimpleNamespace(id=123), data="menu:personal", message=message, answer=AsyncMock())
    state = AsyncMock()
    await bot.menu_callback(callback, state)
    state.clear.assert_awaited_once()
    message.edit_text.assert_awaited_once()
    message.answer.assert_not_awaited()
    assert "Моя явка" in [button.text for row in message.edit_text.await_args.kwargs['reply_markup'].inline_keyboard for button in row]


@pytest.mark.asyncio
async def test_telegram_menu_text_escapes_password_or_appeal(monkeypatch):
    show = AsyncMock()
    monkeypatch.setattr(bot, "show_main_menu", show)
    state = AsyncMock()
    message = SimpleNamespace()
    await bot.menu_text(message, state)
    state.clear.assert_awaited_once()
    show.assert_awaited_once_with(message)


@pytest.mark.asyncio
async def test_telegram_search_button_accepts_next_plain_message(monkeypatch, member):
    monkeypatch.setattr(bot, "find_user", AsyncMock(return_value=member))
    callback = SimpleNamespace(data="menu:search", from_user=SimpleNamespace(id=123), message=SimpleNamespace(answer=AsyncMock()), answer=AsyncMock())
    state = AsyncMock()
    await bot.menu_callback(callback, state)
    state.set_state.assert_awaited_once_with(bot.SearchStates.query)
    monkeypatch.setattr(bot, "ensure_dialog_not_expired", AsyncMock(return_value=False))
    search = AsyncMock()
    monkeypatch.setattr(bot, "send_search_results", search)
    message = SimpleNamespace(text="Тренировка", from_user=SimpleNamespace(id=123), answer=AsyncMock())
    await bot.search_query(message, state)
    search.assert_awaited_once_with(message, member, "Тренировка")


@pytest.mark.asyncio
@pytest.mark.parametrize("step", ["reset_password_new", "reset_password_confirm", "appeal_subject", "appeal_description", "appeal_reply", "awaiting_absence_comment", "normative_attachment"])
async def test_vk_menu_is_never_consumed_as_password_or_appeal(monkeypatch, member, vk_message, step):
    monkeypatch.setattr(vk_bot, "find_user_by_vk", AsyncMock(return_value=member))
    state_read = AsyncMock(return_value={"step": step})
    monkeypatch.setattr(vk_bot, "_get_event_state", state_read)
    clear = AsyncMock()
    monkeypatch.setattr(vk_bot, "_clear_event_state", clear)
    await vk_bot.handle_message(vk_message)
    clear.assert_awaited_once_with(42)
    state_read.assert_not_awaited()
    keyboard = json.loads(vk_message.answer.await_args.kwargs['keyboard'])
    assert "Расписание" in [button['action']['label'] for row in keyboard['buttons'] for button in row]


@pytest.mark.asyncio
async def test_vk_old_schedule_text_button_still_works(monkeypatch, member, vk_message):
    vk_message.text = "Расписание"
    monkeypatch.setattr(vk_bot, "find_user_by_vk", AsyncMock(return_value=member))
    monkeypatch.setattr(vk_bot, "_clear_event_state", AsyncMock())
    schedule = AsyncMock()
    monkeypatch.setattr(vk_bot, "_send_schedule", schedule)
    await vk_bot.handle_message(vk_message)
    assert schedule.await_args.args[:2] == (vk_message, member)


@pytest.mark.asyncio
async def test_vk_start_does_not_immediately_request_password(monkeypatch, vk_message):
    vk_message.text = "Начать"
    monkeypatch.setattr(vk_bot, "find_user_by_vk", AsyncMock(return_value=None))
    monkeypatch.setattr(vk_bot, "_clear_login_state", AsyncMock())
    create_state = AsyncMock()
    monkeypatch.setattr(vk_bot, "_set_login_state", create_state)
    await vk_bot.handle_message(vk_message)
    create_state.assert_not_awaited()
    keyboard = json.loads(vk_message.answer.await_args.kwargs['keyboard'])
    assert len(keyboard['buttons']) == 2


@pytest.mark.asyncio
async def test_vk_personal_actions_never_run_in_group_chat(monkeypatch, vk_message):
    vk_message.peer_id = 2000000001
    find = AsyncMock()
    monkeypatch.setattr(vk_bot, "find_user_by_vk", find)
    await vk_bot.handle_message(vk_message)
    find.assert_not_awaited()
    assert "личные" in vk_message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_vk_unlink_needs_current_confirmation(monkeypatch, member, vk_message):
    monkeypatch.setattr(vk_bot, "_set_event_state", AsyncMock())
    unlink = AsyncMock()
    monkeypatch.setattr(vk_bot, "_unlink_vk", unlink)
    await vk_bot._handle_menu(vk_message, member, "unlink", None)
    unlink.assert_not_awaited()
    monkeypatch.setattr(vk_bot, "_get_event_state", AsyncMock(return_value={"step": "unlink_confirm", "user_id": 999}))
    await vk_bot._handle_payload(vk_message, member, {"action": "unlink_confirm"}, None)
    unlink.assert_not_awaited()
    monkeypatch.setattr(vk_bot, "_get_event_state", AsyncMock(return_value={"step": "unlink_confirm", "user_id": 7}))
    monkeypatch.setattr(vk_bot, "_clear_event_state", AsyncMock())
    await vk_bot._handle_payload(vk_message, member, {"action": "unlink_confirm"}, None)
    unlink.assert_awaited_once_with(vk_message, member)


@pytest.mark.asyncio
async def test_vk_urgency_typing_cannot_silently_submit(monkeypatch, member, vk_message):
    create = AsyncMock()
    monkeypatch.setattr(vk_bot, "_create_appeal_from_vk", create)
    await vk_bot._handle_appeal_state(vk_message, member, {"step": "appeal_urgency"}, "неизвестная команда", None)
    await vk_bot._handle_appeal_urgency_payload(vk_message, member, {"urgency": "FORGED"}, None)
    create.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("module, handler", [(bot, "send_self_checkin_result"), (vk_bot, "_self_checkin_from_vk")])
async def test_overlapping_checkin_windows_ask_which_event(monkeypatch, member, vk_message, session, module, handler):
    now = datetime.now(timezone.utc)
    events = [SimpleNamespace(id=i, title=f"Занятие {i}", start_datetime=now) for i in (1, 2)]
    session.scalars.return_value = SimpleNamespace(all=lambda: events)
    checkin = AsyncMock()
    monkeypatch.setattr(module, "self_check_in", checkin)
    args = (vk_message, member) if module is bot else (vk_message, member, None)
    await getattr(module, handler)(*args)
    checkin.assert_not_awaited()
    session.commit.assert_not_awaited()
    assert "каком занятии" in vk_message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_attendance_shows_event_date_not_later_mark_date(member, session):
    event_date = datetime(2025, 1, 2, 10, tzinfo=timezone.utc)
    mark = SimpleNamespace(status_code="PRESENT", updated_at=datetime(2026, 10, 8, tzinfo=timezone.utc))
    session.execute.return_value = SimpleNamespace(all=lambda: [(mark, "Тренировка", event_date)])
    text = await bot_content.attendance_text(session, member)
    assert "02.01.2025" in text
    assert "08.10.2026" not in text


@pytest.mark.asyncio
async def test_schedule_card_uses_club_timezone_and_deadline_policy(member, session, monkeypatch):
    now = datetime.now(timezone.utc)
    event = SimpleNamespace(id=5, title="Тренировка", squad_id=2, status_code="PLANNED", start_datetime=now + timedelta(days=1),
                            requires_response=True, response_deadline_at=now - timedelta(minutes=1), place="Зал", description="Форма спортивная")
    session.scalars.return_value = SimpleNamespace(all=lambda: [event])
    session.scalar.return_value = "COMING"
    monkeypatch.setattr(bot_content, "get_settings", lambda: SimpleNamespace(timezone="Asia/Barnaul"))
    _, text, actionable, has_next = await bot_content.schedule_card(session, member)
    assert not actionable
    assert not has_next
    assert "Приём ответов закрыт" in text
    assert (event.start_datetime + timedelta(hours=7)).strftime("%H:%M") in text


@pytest.mark.asyncio
async def test_vk_foreign_appeal_cannot_be_opened_or_replied_to(member, session, vk_message, monkeypatch):
    session.scalar.return_value = SimpleNamespace(id=17, author_user_id=99)
    state = AsyncMock()
    monkeypatch.setattr(vk_bot, "_set_event_state", state)
    await vk_bot._send_appeal_thread(vk_message, member, 17)
    await vk_bot._handle_payload(vk_message, member, {"action": "appeal_reply", "id": 17}, None)
    state.assert_not_awaited()
    session.scalars.assert_not_awaited()


@pytest.mark.asyncio
async def test_vk_forged_payloads_do_not_query_database(member, session, vk_message):
    for payload in ({"action": []}, {"action": "appeal_thread", "id": -1}, {"action": "schedule_page", "page": True}, {"action": "checkin", "event_id": {}}, {"action": "inbox_view", "id": 0}):
        await vk_bot._handle_payload(vk_message, member, payload, None)
    session.scalar.assert_not_awaited()
    session.scalars.assert_not_awaited()


@pytest.mark.asyncio
async def test_vk_inbox_buttons_keep_context_and_obey_inline_limits(member, session, vk_message, monkeypatch):
    monkeypatch.setattr(vk_bot, "inbox_counts", AsyncMock(return_value={"total": 20, "unread": 20}))
    monkeypatch.setattr(vk_bot, "inbox_page", AsyncMock(return_value=[SimpleNamespace(id=i, title="Уведомление", is_read=False) for i in range(4)]))
    await vk_bot._send_notifications(vk_message, member, page=1, unread=True)
    keyboard = json.loads(vk_message.answer.await_args.kwargs['keyboard'])
    assert keyboard['inline'] is True
    assert len(keyboard['buttons']) <= 6
    actions = [json.loads(button['action'].get('payload', '{}')) for row in keyboard['buttons'] for button in row]
    assert all(item['unread'] for item in actions if item.get('action') == 'inbox_view')
    assert any(item.get('action') == 'inbox_page' and item.get('page') == 2 and item.get('unread') for item in actions)


@pytest.mark.parametrize("kind, entity, expected", [("SCHEDULE_POLL", "schedule_events", "event_response"), ("APPEAL", "appeals", "appeal_thread"), ("NORMATIVE", "normatives", "inbox_view")])
def test_vk_notification_contains_native_action(kind, entity, expected):
    item = SimpleNamespace(id=12, type_code=kind, entity_id=42, entity_name=entity, deep_link="/appeals?id=42")
    keyboard = json.loads(notification_keyboard(item, "https://example.com"))
    actions = [json.loads(button['action'].get('payload', '{}')).get('action') for row in keyboard['buttons'] for button in row]
    assert expected in actions
    assert keyboard['inline'] is True
    assert len(keyboard['buttons']) <= 6


@pytest.mark.asyncio
async def test_telegram_stale_file_choice_cannot_submit(monkeypatch, member, session):
    monkeypatch.setattr(bot, "find_user", AsyncMock(return_value=member))
    monkeypatch.setattr(bot, "ensure_dialog_not_expired", AsyncMock(return_value=False))
    submit = AsyncMock()
    monkeypatch.setattr(bot, "submit_normative_service", submit)
    callback = SimpleNamespace(data="norm_submit:5", from_user=SimpleNamespace(id=123), message=SimpleNamespace(answer=AsyncMock()), answer=AsyncMock())
    state = AsyncMock()
    state.get_data.return_value = {"user_id": 7, "file_id": "old-file"}
    state.get_state.return_value = None
    await bot.normative_file_submit(callback, state)
    submit.assert_not_awaited()
    session.get.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("current, previous, field", [(bot.AppealStates.description, bot.AppealStates.subject, "subject"), (bot.AppealStates.urgency, bot.AppealStates.description, "description")])
async def test_telegram_back_preserves_appeal_draft(monkeypatch, current, previous, field):
    state = AsyncMock()
    state.get_state.return_value = current.state
    state.get_data.return_value = {"subject": "Старая тема", "description": "Подробное описание"}
    monkeypatch.setattr(bot, "ensure_dialog_not_expired", AsyncMock(return_value=False))
    message = SimpleNamespace(answer=AsyncMock())
    await bot.go_back(message, state, 123)
    state.set_state.assert_awaited_once_with(previous)
    state.clear.assert_not_awaited()
    state.update_data.assert_not_awaited()
    assert state.get_data.return_value[field] in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_telegram_back_from_password_confirmation_discards_secret(monkeypatch):
    state = AsyncMock()
    state.get_state.return_value = bot.PasswordResetStates.confirm_password.state
    state.get_data.return_value = {"new_password": "secret-value"}
    monkeypatch.setattr(bot, "ensure_dialog_not_expired", AsyncMock(return_value=False))
    message = SimpleNamespace(answer=AsyncMock())
    await bot.go_back(message, state, 123)
    state.update_data.assert_awaited_once_with(new_password=None)
    state.set_state.assert_awaited_once_with(bot.PasswordResetStates.new_password)
    assert "secret-value" not in message.answer.await_args.args[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("current, previous", [("appeal_description", "appeal_subject"), ("appeal_urgency", "appeal_description")])
async def test_vk_back_preserves_appeal_draft(monkeypatch, member, vk_message, current, previous):
    monkeypatch.setattr(vk_bot, "_get_event_state", AsyncMock(return_value={"step": current, "subject": "Старая тема", "description": "Описание", "ts": "ignored"}))
    write = AsyncMock()
    monkeypatch.setattr(vk_bot, "_set_event_state", write)
    await vk_bot._go_back(vk_message, member, None)
    write.assert_awaited_once_with(42, step=previous, subject="Старая тема", description="Описание")


@pytest.mark.asyncio
async def test_vk_back_button_is_routed_before_appeal_text(monkeypatch, member, vk_message):
    vk_message.text = "← Назад"
    vk_message.payload = json.dumps({"action": "dialog_back"})
    monkeypatch.setattr(vk_bot, "find_user_by_vk", AsyncMock(return_value=member))
    back = AsyncMock()
    monkeypatch.setattr(vk_bot, "_go_back", back)
    await vk_bot.handle_message(vk_message)
    assert back.await_args.args[:2] == (vk_message, member)


def test_nested_account_back_returns_to_personal_section(member):
    telegram = bot.main_menu_inline(RoleLevel.PARTICIPANT, "account")
    assert any(button.text == "← Назад" and button.callback_data == "menu:personal" for row in telegram.inline_keyboard for button in row)
    vk = json.loads(vk_bot.section_keyboard(member, "account"))
    assert any(button['action']['label'] == "← Назад" and json.loads(button['action']['payload'])['section'] == "personal" for row in vk['buttons'] for button in row)


def test_dialog_and_commander_keyboards_have_back():
    assert "Назад" in [button.text for row in bot.cancel_keyboard().keyboard for button in row]
    journal = bot.attendance_mark_keyboard(event_id=1, users=[], existing_status={}, page=0, total=0)
    assert any(button.callback_data == "menu:command" for row in journal.inline_keyboard for button in row)
    for keyboard in (vk_bot.cancel_keyboard(), vk_bot.appeal_urgency_keyboard(), vk_bot.normative_choice_keyboard([])):
        assert any(button['action']['label'] == "← Назад" for row in json.loads(keyboard)['buttons'] for button in row)
