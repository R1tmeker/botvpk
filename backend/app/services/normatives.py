from __future__ import annotations

from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Normative, NormativeSubmission, NormativeSubmissionFile, Notification, User
from ..roles import ROLE_LEVELS, RoleLevel
from ..utils.audit import model_snapshot, record_audit, utcnow
from .normative_cycles import normative_period, period_submission_clause
from .normative_progress import assigned_to


HIGH_COMMANDER_ROLES = ("DEPUTY_PLATOON_COMMANDER", "PLATOON_COMMANDER", "ADMIN", "SUPER_ADMIN")
SQUAD_COMMANDER_ROLES = (
    "SQUAD_COMMANDER",
    "DEPUTY_SQUAD_COMMANDER",
    *HIGH_COMMANDER_ROLES,
)


async def _commander_recipients(
    session: AsyncSession,
    submitter: User,
    *,
    scope: str,
) -> list[User]:
    if scope == "submitter_squad":
        if submitter.squad_id is None:
            statement = select(User).where(
                User.status_code == "ACTIVE",
                User.role_code.in_(HIGH_COMMANDER_ROLES),
            )
        else:
            statement = select(User).where(
                User.status_code == "ACTIVE",
                User.role_code.in_(SQUAD_COMMANDER_ROLES),
                (User.squad_id == submitter.squad_id) | User.role_code.in_(HIGH_COMMANDER_ROLES),
            )
    else:
        commander_role_codes = [role_code for role_code, level in ROLE_LEVELS.items() if level >= RoleLevel.DEPUTY_SQUAD_COMMANDER]
        statement = select(User).where(
            User.status_code == "ACTIVE",
            User.role_code.in_(commander_role_codes),
        )
    return list((await session.scalars(statement)).all())


async def submit_normative(
    session: AsyncSession,
    *,
    normative: Normative,
    submitter: User,
    status_code: str,
    comment: str | None,
    file_ids: list[int] | None,
    audit_action_code: str,
    audit_value: dict,
    notification_body: str | None = None,
    notification_scope: str = "all_commanders",
    expected_period_start: date | None = None,
) -> NormativeSubmission:
    # Serialize repeated taps and submissions through Telegram/VK/API for this normative.
    locked = await session.scalar(select(Normative).where(Normative.id == normative.id).with_for_update().execution_options(populate_existing=True))
    if locked is not None:
        normative = locked
    now = utcnow()
    period = normative_period(normative, now)
    if expected_period_start is not None and expected_period_start != period.start:
        raise ValueError("Началась новая неделя. Откройте норматив заново и отправьте работу для текущего периода.")
    if not getattr(normative, "is_active", True) or (period.opens_at and now < period.opens_at):
        raise ValueError("Сдача этого норматива ещё не открыта.")
    if not assigned_to(normative, submitter):
        raise ValueError("Этот норматив назначен другой группе участников.")
    submission = await session.scalar(
        select(NormativeSubmission).where(
            NormativeSubmission.normative_id == normative.id,
            NormativeSubmission.user_id == submitter.id,
            period_submission_clause(normative, now),
        )
    )
    if submission is None:
        submission = NormativeSubmission(normative_id=normative.id, user_id=submitter.id, period_start_date=period.start, period_end_date=period.end)
        session.add(submission)
    elif submission.status_code in {"ACCEPTED", "PENDING", "SUBMITTED", "PENDING_REVIEW"}:
        return submission
    old = model_snapshot(submission, ["status_code", "file_id", "comment"]) if submission.id else None

    submission.status_code = status_code
    submission.comment = comment
    submission.submitted_at = now
    submission.updated_at = now
    submission.reviewer_comment = None
    submission.grade_value = None
    submission.reviewed_by_id = None
    submission.reviewed_at = None
    if file_ids is not None:
        unique_file_ids = list(dict.fromkeys(file_ids))
        submission.file_id = unique_file_ids[0] if unique_file_ids else None
    await session.flush()

    if file_ids is not None:
        await session.execute(delete(NormativeSubmissionFile).where(NormativeSubmissionFile.submission_id == submission.id))
        for file_id in list(dict.fromkeys(file_ids)):
            session.add(NormativeSubmissionFile(submission_id=submission.id, file_id=file_id))

    await record_audit(
        session,
        user_id=submitter.id,
        action_code=audit_action_code,
        entity_name="normative_submissions",
        entity_id=submission.id,
        old_value=old,
        new_value=audit_value,
    )

    body = notification_body or f"{submitter.full_name} сдал норматив «{normative.title}» на проверку."
    commanders = await _commander_recipients(session, submitter, scope=notification_scope)
    for commander in commanders:
        session.add(
            Notification(
                user_id=commander.id,
                type_code="NORMATIVE",
                title=f"Новая сдача: {normative.title}",
                body=body,
                entity_name="normative_submissions",
                entity_id=submission.id,
                send_to_tg=True,
            )
        )
    return submission
