from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select, union_all, literal
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..database import get_db_session
from ..dependencies.auth import CurrentUser, require_role
from ..models import Appeal, Attendance, AttendanceGrade, EventResponse, JoinApplication, NormativeSubmission, ScheduleEvent, User
from ..roles import RoleLevel
from ..schemas.core import ReportSummary

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/attendance", response_model=ReportSummary)
async def attendance_report(
    squad_id: int | None = None,
    current_user: CurrentUser = Depends(require_role(RoleLevel.SQUAD_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> ReportSummary:
    statement = select(Attendance.status_code, func.count(Attendance.id)).join(User, User.id == Attendance.user_id)
    if squad_id is not None:
        statement = statement.where(User.squad_id == squad_id)
    elif current_user.role_level < RoleLevel.DEPUTY_PLATOON_COMMANDER:
        statement = statement.where(User.squad_id == current_user.squad_id)
    rows = (await session.execute(statement.group_by(Attendance.status_code))).all()
    return ReportSummary(title="Посещаемость", items=[{"status_code": key, "count": count} for key, count in rows])


@router.get("/grades", response_model=ReportSummary)
async def grades_report(
    squad_id: int | None = None,
    current_user: CurrentUser = Depends(require_role(RoleLevel.SQUAD_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> ReportSummary:
    statement = (
        select(AttendanceGrade.grade_value, func.count(AttendanceGrade.id))
        .join(Attendance, Attendance.id == AttendanceGrade.attendance_id)
        .join(User, User.id == Attendance.user_id)
    )
    if squad_id is not None:
        statement = statement.where(User.squad_id == squad_id)
    elif current_user.role_level < RoleLevel.DEPUTY_PLATOON_COMMANDER:
        statement = statement.where(User.squad_id == current_user.squad_id)
    rows = (await session.execute(statement.group_by(AttendanceGrade.grade_value))).all()
    return ReportSummary(title="Оценки", items=[{"grade_value": key, "count": count} for key, count in rows])


@router.get("/normatives", response_model=ReportSummary)
async def normatives_report(
    squad_id: int | None = None,
    current_user: CurrentUser = Depends(require_role(RoleLevel.SQUAD_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> ReportSummary:
    statement = (
        select(NormativeSubmission.status_code, func.count(NormativeSubmission.id))
        .join(User, User.id == NormativeSubmission.user_id)
    )
    if squad_id is not None:
        statement = statement.where(User.squad_id == squad_id)
    elif current_user.role_level < RoleLevel.DEPUTY_PLATOON_COMMANDER:
        statement = statement.where(User.squad_id == current_user.squad_id)
    rows = (await session.execute(statement.group_by(NormativeSubmission.status_code))).all()
    return ReportSummary(title="Нормативы", items=[{"status_code": key, "count": count} for key, count in rows])


@router.get("/applications", response_model=ReportSummary)
async def applications_report(
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_PLATOON_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> ReportSummary:
    rows = (
        await session.execute(
            select(JoinApplication.status_code, func.count(JoinApplication.id)).group_by(JoinApplication.status_code)
        )
    ).all()
    return ReportSummary(title="Заявки", items=[{"status_code": key, "count": count} for key, count in rows])


@router.get("/export")
async def export_report(
    squad_id: int | None = None,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_PLATOON_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> StreamingResponse:
    attendance = await attendance_report(squad_id, current_user, session)
    grades = await grades_report(squad_id, current_user, session)
    normatives = await normatives_report(squad_id, current_user, session)
    applications = await applications_report(current_user, session)
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["section", "key", "value", "count"])
    for section in [attendance, grades, normatives, applications]:
        for item in section.items:
            key, value = next(((k, v) for k, v in item.items() if k != "count"), ("item", ""))
            writer.writerow([section.title, key, value, item.get("count", "")])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="vpk-report.csv"'},
    )


@router.post("/export/send", status_code=200)
async def export_report_send(
    squad_id: int | None = None,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_PLATOON_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Generate report CSV and send it to the requester via Telegram bot DM."""
    from ..background import _get_bot
    from aiogram.types import BufferedInputFile

    attendance = await attendance_report(squad_id, current_user, session)
    grades = await grades_report(squad_id, current_user, session)
    normatives = await normatives_report(squad_id, current_user, session)
    applications = await applications_report(current_user, session)
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["section", "key", "value", "count"])
    for section in [attendance, grades, normatives, applications]:
        for item in section.items:
            key, value = next(((k, v) for k, v in item.items() if k != "count"), ("item", ""))
            writer.writerow([section.title, key, value, item.get("count", "")])
    data = output.getvalue().encode("utf-8")
    bot = _get_bot(settings)
    await bot.send_document(
        current_user.telegram_id,
        BufferedInputFile(data, filename="vpk-report.csv"),
        caption="Сводный отчёт ВПК Звезда",
    )
    return {"sent": True}


@router.get("/activity-feed", response_model=list[dict])
async def activity_feed(
    limit: int = 40,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_SQUAD_COMMANDER)),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict]:
    """Recent activity feed for commanders: responses, submissions, appeals, attendance marks."""
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=7)
    squad_filter = current_user.role_level < RoleLevel.DEPUTY_PLATOON_COMMANDER and current_user.squad_id is not None

    feed: list[dict] = []

    # Event responses
    resp_rows = (
        await session.execute(
            select(EventResponse.response_code, EventResponse.responded_at, User.full_name, ScheduleEvent.title)
            .join(User, User.id == EventResponse.user_id)
            .join(ScheduleEvent, ScheduleEvent.id == EventResponse.event_id)
            .where(
                EventResponse.responded_at >= since,
                (User.squad_id == current_user.squad_id) if squad_filter else True,
            )
            .order_by(EventResponse.responded_at.desc())
            .limit(20)
        )
    ).all()
    for rc, ts, name, event_title in resp_rows:
        label = {"COMING": "ответил «Приду»", "NOT_COMING": "ответил «Не приду»", "MAYBE": "ответил «Пока не знаю»"}.get(rc, "ответил")
        feed.append({"type": "response", "text": f"{name} {label} на «{event_title}»", "created_at": ts.isoformat()})

    # Normative submissions
    subm_rows = (
        await session.execute(
            select(NormativeSubmission.status_code, NormativeSubmission.submitted_at, User.full_name)
            .join(User, User.id == NormativeSubmission.user_id)
            .where(
                NormativeSubmission.submitted_at >= since,
                (User.squad_id == current_user.squad_id) if squad_filter else True,
            )
            .order_by(NormativeSubmission.submitted_at.desc())
            .limit(15)
        )
    ).all()
    for sc, ts, name in subm_rows:
        feed.append({"type": "normative", "text": f"{name} сдал норматив (статус: {sc})", "created_at": ts.isoformat()})

    # Appeals created
    appeal_rows = (
        await session.execute(
            select(Appeal.subject, Appeal.urgency_code, Appeal.created_at, User.full_name)
            .join(User, User.id == Appeal.author_user_id)
            .where(
                Appeal.created_at >= since,
                (User.squad_id == current_user.squad_id) if squad_filter else True,
            )
            .order_by(Appeal.created_at.desc())
            .limit(10)
        )
    ).all()
    for subject, urgency, ts, name in appeal_rows:
        urgency_label = {"URGENT": "срочное", "HIGH": "важное", "NORMAL": "обычное", "LOW": "низкий приоритет"}.get(urgency, "обычное")
        feed.append({"type": "appeal", "text": f"{name} отправил обращение ({urgency_label}): «{subject}»", "created_at": ts.isoformat()})

    # Recent attendance marks
    att_rows = (
        await session.execute(
            select(Attendance.status_code, Attendance.marked_at, User.full_name, ScheduleEvent.title)
            .join(User, User.id == Attendance.user_id)
            .join(ScheduleEvent, ScheduleEvent.id == Attendance.event_id)
            .where(
                Attendance.marked_at >= since,
                Attendance.marked_at.is_not(None),
                (User.squad_id == current_user.squad_id) if squad_filter else True,
            )
            .order_by(Attendance.marked_at.desc())
            .limit(15)
        )
    ).all()
    status_label = {"PRESENT": "присутствовал", "ABSENT": "отсутствовал", "LATE": "опоздал", "EXCUSED": "уважительная причина", "SICK": "болел"}
    for sc, ts, name, event_title in att_rows:
        label = status_label.get(sc, sc)
        feed.append({"type": "attendance", "text": f"{name} — {label} на «{event_title}»", "created_at": ts.isoformat()})

    # Sort by created_at desc and limit
    feed.sort(key=lambda x: x["created_at"], reverse=True)
    return feed[:limit]
