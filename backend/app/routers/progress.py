from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db_session
from ..dependencies.auth import CurrentUser, require_role
from ..models import AchievementProgress as AchievementProgressModel
from ..models import Attendance, NormativeSubmission, ScheduleEvent
from ..roles import RoleLevel
from ..schemas.product import AchievementProgress, ProgressPeriod, UserProgress
from ..utils.audit import utcnow
from ..utils.timezones import utc_to_local_date
from ..config import Settings, get_settings

router = APIRouter(prefix="/me", tags=["progress"])

ATTENDED_STATUSES = {"PRESENT", "LATE"}
ACHIEVEMENTS = {
    "FIRST_ATTENDANCE": ("Первая явка", 1),
    "STREAK_3": ("Серия из 3", 3),
    "STREAK_7": ("Серия из 7", 7),
    "STREAK_30": ("Серия из 30", 30),
    "PERFECT_MONTH": ("Идеальный месяц", 1),
    "FIRST_NORMATIVE": ("Первый принятый норматив", 1),
}


@router.get("/progress", response_model=UserProgress)
async def my_progress(
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> UserProgress:
    if current_user.user_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User profile is required.")
    attendance_rows = list(
        (
            await session.execute(
                select(Attendance.status_code, ScheduleEvent.start_datetime)
                .join(ScheduleEvent, ScheduleEvent.id == Attendance.event_id)
                .where(
                    Attendance.user_id == current_user.user_id,
                    Attendance.status_code != "NOT_MARKED",
                )
                .order_by(ScheduleEvent.start_datetime.desc())
            )
        ).all()
    )
    normative_rows = list(
        (
            await session.execute(
                select(NormativeSubmission.status_code, NormativeSubmission.submitted_at).where(
                    NormativeSubmission.user_id == current_user.user_id
                )
            )
        ).all()
    )

    attended = sum(1 for status_code, _ in attendance_rows if status_code in ATTENDED_STATUSES)
    current_streak = 0
    for status_code, _ in attendance_rows:
        if status_code not in ATTENDED_STATUSES:
            break
        current_streak += 1
    accepted_normatives = sum(1 for status_code, _ in normative_rows if status_code == "ACCEPTED")

    periods: dict[str, ProgressPeriod] = {}
    month_statuses: dict[str, list[str]] = defaultdict(list)
    for status_code, event_at in attendance_rows:
        period = utc_to_local_date(event_at, settings.timezone).strftime("%Y-%m")
        row = periods.setdefault(period, ProgressPeriod(period=period))
        row.total += 1
        month_statuses[period].append(status_code)
        if status_code in ATTENDED_STATUSES:
            row.attended += 1
    for status_code, submitted_at in normative_rows:
        if status_code != "ACCEPTED":
            continue
        period = utc_to_local_date(submitted_at, settings.timezone).strftime("%Y-%m")
        periods.setdefault(period, ProgressPeriod(period=period)).normatives_accepted += 1
    perfect_month = any(statuses and all(item in ATTENDED_STATUSES for item in statuses) for statuses in month_statuses.values())

    values = {
        "FIRST_ATTENDANCE": min(attended, 1),
        "STREAK_3": min(current_streak, 3),
        "STREAK_7": min(current_streak, 7),
        "STREAK_30": min(current_streak, 30),
        "PERFECT_MONTH": int(perfect_month),
        "FIRST_NORMATIVE": min(accepted_normatives, 1),
    }
    stored = {
        item.achievement_code: item
        for item in (
            await session.scalars(
                select(AchievementProgressModel).where(AchievementProgressModel.user_id == current_user.user_id)
            )
        ).all()
    }
    now = utcnow()
    response_achievements: list[AchievementProgress] = []
    for code, (title, target) in ACHIEVEMENTS.items():
        item = stored.get(code)
        if item is None:
            item = AchievementProgressModel(
                user_id=current_user.user_id,
                achievement_code=code,
                target_value=target,
            )
            session.add(item)
        item.current_value = values[code]
        item.target_value = target
        item.updated_at = now
        if item.unlocked_at is None and item.current_value >= target:
            item.unlocked_at = now
        response_achievements.append(
            AchievementProgress(
                code=code,
                title=title,
                current_value=item.current_value,
                target_value=target,
                unlocked_at=item.unlocked_at,
                is_public=item.is_public,
            )
        )
    await session.commit()
    total = len(attendance_rows)
    return UserProgress(
        attendance_percent=round(attended / total * 100) if total else 0,
        attendance_total=total,
        normatives_accepted=accepted_normatives,
        current_streak=current_streak,
        periods=sorted(periods.values(), key=lambda item: item.period)[-6:],
        achievements=response_achievements,
    )
