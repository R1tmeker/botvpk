from __future__ import annotations

import io
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import openpyxl
import pytest

from app.models.squad import Squad
from app.models.user import User
from app.roles import RoleLevel
from app.routers.reports import _build_attendance_matrix


@pytest.mark.asyncio
async def test_attendance_matrix_groups_members_by_squad_and_dates() -> None:
    member = User(
        id=10,
        telegram_id=1000,
        full_name="Антонов Дмитрий Владимирович",
        squad_id=1,
        role_code="PARTICIPANT",
        status_code="ACTIVE",
    )
    squad = Squad(id=1, name="1 Отделение", commander_user_id=None, deputy_user_id=None, is_active=True)
    event_rows = [(101, datetime(2025, 9, 1, 12, tzinfo=timezone.utc))]
    attendance_rows = [(member.id, 101, "PRESENT")]

    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                SimpleNamespace(all=lambda: event_rows),
                SimpleNamespace(all=lambda: attendance_rows),
            ]
        ),
        scalars=AsyncMock(
            side_effect=[
                SimpleNamespace(all=lambda: [member]),
                SimpleNamespace(all=lambda: [squad]),
            ]
        ),
    )

    data, filename, member_count = await _build_attendance_matrix(
        squad_id=None,
        month="2025-09",
        current_user=SimpleNamespace(role_level=RoleLevel.DEPUTY_PLATOON_COMMANDER, squad_id=None),
        session=session,
        settings=SimpleNamespace(timezone="Asia/Novosibirsk"),
    )

    workbook = openpyxl.load_workbook(io.BytesIO(data))
    sheet = workbook["Посещаемость"]

    assert filename == "attendance-2025-09.xlsx"
    assert member_count == 1
    assert sheet["A1"].value == "1 Отделение - 1 чел"
    assert sheet["C1"].value == "01.09.2025"
    assert sheet["A2"].value == member.full_name
    assert sheet["C2"].value == "Был"
    assert sheet["A2"].border.left.style == "thin"
    assert len(sheet.data_validations.dataValidation) == 1
