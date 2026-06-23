from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Normative, NormativeSubmission, NormativeSubmissionFile, Notification, User
from ..roles import ROLE_LEVELS, RoleLevel
from ..utils.audit import model_snapshot, record_audit, utcnow


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
) -> NormativeSubmission:
    submission = await session.scalar(
        select(NormativeSubmission).where(
            NormativeSubmission.normative_id == normative.id,
            NormativeSubmission.user_id == submitter.id,
        )
    )
    if submission is None:
        submission = NormativeSubmission(normative_id=normative.id, user_id=submitter.id)
        session.add(submission)
    old = model_snapshot(submission, ["status_code", "file_id", "comment"]) if submission.id else None

    submission.status_code = status_code
    submission.comment = comment
    submission.submitted_at = utcnow()
    submission.updated_at = utcnow()
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
