from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.roles import RoleLevel
from app.schemas.product import AdminUsersBulkUpdate
from app.services import action_center
from app.services.action_center import ActionCenterError, execute_action_item


def test_bulk_user_update_distinguishes_clear_squad_from_no_changes() -> None:
    payload = AdminUsersBulkUpdate(user_ids=[1, 2], squad_id=None)
    assert "squad_id" in payload.model_fields_set
    assert payload.squad_id is None

    with pytest.raises(ValidationError):
        AdminUsersBulkUpdate(user_ids=[1, 2])


@pytest.mark.asyncio
async def test_action_center_rejects_unknown_or_unauthorized_actions() -> None:
    session = AsyncMock()
    with pytest.raises(ActionCenterError, match="не поддерживается"):
        await execute_action_item(
            session,
            item_code="UNKNOWN",
            action_code="delete_everything",
            actor_id=10,
            role_level=RoleLevel.SQUAD_COMMANDER,
            squad_id=1,
        )

    with pytest.raises(ActionCenterError, match="отделение"):
        await execute_action_item(
            session,
            item_code="PENDING_NORMATIVES",
            action_code="assign_reviewer",
            actor_id=10,
            role_level=RoleLevel.DEPUTY_SQUAD_COMMANDER,
            squad_id=None,
        )

    with pytest.raises(ActionCenterError, match="Недостаточно прав"):
        await execute_action_item(
            session,
            item_code="NOTIFICATION_DELIVERY_ERRORS",
            action_code="retry_delivery",
            actor_id=10,
            role_level=RoleLevel.SQUAD_COMMANDER,
            squad_id=1,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("item_code", "action_code", "helper_name"),
    [
        ("MISSING_EVENT_RESPONSES", "send_reminder", "_send_response_reminders"),
        ("PENDING_NORMATIVES", "assign_reviewer", "_assign_pending_normatives"),
        ("UNPROCESSED_APPEALS", "assign", "_assign_appeals"),
        ("UNCLOSED_ATTENDANCE", "mark_all_present", "_mark_unclosed_present"),
        ("OVERDUE_APPLICATIONS", "assign_reviewer", "_claim_overdue_applications"),
        ("NOTIFICATION_DELIVERY_ERRORS", "retry_delivery", "_retry_failed_notifications"),
    ],
)
async def test_action_center_dispatches_audits_and_commits(
    monkeypatch: pytest.MonkeyPatch,
    item_code: str,
    action_code: str,
    helper_name: str,
) -> None:
    session = AsyncMock()
    helper = AsyncMock(return_value=4)
    audit = AsyncMock()
    monkeypatch.setattr(action_center, helper_name, helper)
    monkeypatch.setattr(action_center, "record_audit", audit)

    affected = await execute_action_item(
        session,
        item_code=item_code,
        action_code=action_code,
        actor_id=10,
        role_level=RoleLevel.ADMIN,
        squad_id=1,
    )

    assert affected == 4
    helper.assert_awaited_once()
    audit.assert_awaited_once()
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_action_center_rolls_back_failed_action(monkeypatch: pytest.MonkeyPatch) -> None:
    session = AsyncMock()
    monkeypatch.setattr(
        action_center,
        "_assign_appeals",
        AsyncMock(side_effect=RuntimeError("database unavailable")),
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        await execute_action_item(
            session,
            item_code="UNPROCESSED_APPEALS",
            action_code="assign",
            actor_id=10,
            role_level=RoleLevel.ADMIN,
            squad_id=None,
        )
    session.rollback.assert_awaited_once()
