from __future__ import annotations

from sqlalchemy import select

from ..models import Normative, NormativeSubmission
from ..roles import RoleLevel, role_level
from .normative_cycles import is_current_submission, normative_period


def assigned_to(normative, user) -> bool:
    if normative.squad_id is not None and normative.squad_id != user.squad_id:
        return False
    audience = normative.target_audience
    level = role_level(user.role_code)
    return (
        audience in {"ALL", user.role_code}
        or audience == "SQUAD"
        and normative.squad_id == user.squad_id
        or audience == "PARTICIPANTS"
        and level >= RoleLevel.PARTICIPANT
        or audience == "COMMANDERS"
        and level >= RoleLevel.DEPUTY_SQUAD_COMMANDER
    )


def member_progress(user, normatives, submissions) -> dict:
    own = [submission for submission in submissions if submission.user_id == user.id]
    items = []
    for normative in normatives:
        if not normative.is_active or not assigned_to(normative, user):
            continue
        matches = [
            submission
            for submission in own
            if submission.normative_id == normative.id and is_current_submission(normative, submission)
        ]
        current = max(matches, key=lambda item: item.submitted_at) if matches else None
        code = current.status_code if current else "NOT_SUBMITTED"
        status = (
            "ACCEPTED"
            if code == "ACCEPTED"
            else "PENDING"
            if code in {"PENDING", "SUBMITTED", "PENDING_REVIEW"}
            else "NEEDS_REDO"
            if code in {"REJECTED", "NEEDS_REDO"}
            else "NOT_SUBMITTED"
        )
        period = normative_period(normative)
        items.append(
            {
                "normative_id": normative.id,
                "title": normative.title,
                "status": status,
                "period_start_date": period.start,
                "period_end_date": period.end,
                "next_reset_at": period.closes_at,
            }
        )
    counts = {
        name: sum(item["status"] == status for item in items)
        for name, status in (
            ("accepted", "ACCEPTED"),
            ("pending", "PENDING"),
            ("redo", "NEEDS_REDO"),
            ("missing", "NOT_SUBMITTED"),
        )
    }
    return {
        "user_id": user.id,
        "full_name": user.full_name,
        "squad_id": user.squad_id,
        "total": len(items),
        **counts,
        "accepted_all_time": sum(item.status_code == "ACCEPTED" for item in own),
        "percent": round(counts["accepted"] / len(items) * 100) if items else 0,
        "items": items,
    }


async def progress_for_users(session, users) -> list[dict]:
    if not users:
        return []
    normatives = list(
        (await session.scalars(select(Normative).where(Normative.is_active.is_(True)).order_by(Normative.title))).all()
    )
    submissions = list(
        (
            await session.scalars(
                select(NormativeSubmission).where(NormativeSubmission.user_id.in_([user.id for user in users]))
            )
        ).all()
    )
    return [member_progress(user, normatives, submissions) for user in users]
