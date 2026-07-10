from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import httpx

from fastapi import APIRouter, Depends, File as UploadParam, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..database import get_db_session
from ..dependencies.auth import CurrentUser, can_manage_squad, require_role
from ..models import Announcement, Appeal, LearningMaterial, Normative, NormativeSubmission, NormativeSubmissionFile
from ..models import File as StoredFile
from ..models import User
from ..roles import RoleLevel
from ..ratelimit import limiter
from .normatives import normative_visible as _normative_visible
from ..schemas.core import FileRead
from ..services.uploads import GENERAL_UPLOAD_MIME_TYPES, UploadValidationError, build_upload_path, prepare_upload
from ..services.malware import MalwareScannerError, scan_bytes
from ..utils.audit import record_audit

router = APIRouter(prefix="/files", tags=["files"])


def require_profile(current_user: CurrentUser) -> int:
    if current_user.user_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User profile is required.")
    return current_user.user_id


@router.get("/avatars/{file_id}")
async def download_avatar(
    file_id: int,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    stored = await session.get(StoredFile, file_id)
    if stored is None or not stored.file_path or not (stored.mime_type or "").startswith("image/"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Avatar not found.")
    if stored.scan_status not in {"REENCODED", "LEGACY_TRUSTED"}:
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="Avatar is not approved.")
    owner_id = await session.scalar(select(User.id).where(User.avatar_file_id == file_id).limit(1))
    if owner_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Avatar not found.")
    path = Path(stored.file_path)
    if not path.is_absolute() and not path.exists():
        uploads_root = settings.uploads_dir.resolve()
        candidates = [path.resolve(), uploads_root / path]
        if path.parts and path.parts[0] == settings.uploads_dir.name:
            candidates.append(uploads_root / Path(*path.parts[1:]))
        path = next((candidate for candidate in candidates if candidate.exists()), path)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Avatar content not found.")
    return FileResponse(
        path,
        media_type=stored.mime_type,
        filename=stored.original_name or path.name,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.post("/upload", response_model=FileRead, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def upload_file(
    request: Request,
    upload: UploadFile = UploadParam(...),
    current_user: CurrentUser = Depends(require_role(RoleLevel.CANDIDATE)),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> StoredFile:
    user_id = require_profile(current_user)
    content = await upload.read()
    try:
        prepared = prepare_upload(
            content,
            max_size_bytes=settings.max_upload_size_bytes,
            allowed_mime_types=GENERAL_UPLOAD_MIME_TYPES,
            image_max_side=1920,
            reencode_images=True,
        )
    except UploadValidationError as exc:
        status_code = (
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
            if "слишком большой" in str(exc).casefold()
            else status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
        )
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    now = datetime.now(timezone.utc)
    scan_status = "REENCODED"
    scan_detail = "Image decoded and re-encoded by Pillow."
    scanned_at = now
    rejected_status: int | None = None
    if prepared.mime_type.startswith("image/"):
        target = build_upload_path(
            settings.uploads_dir,
            str(now.year),
            f"{now.month:02d}",
            extension=prepared.extension,
        )
        target.write_bytes(prepared.content)
    else:
        quarantine = build_upload_path(
            settings.uploads_dir,
            "quarantine",
            str(now.year),
            f"{now.month:02d}",
            extension=prepared.extension,
        )
        quarantine.write_bytes(prepared.content)
        target = quarantine
        try:
            result = await scan_bytes(settings, prepared.content)
            scanned_at = now
            scan_detail = result.detail
            if result.clean:
                approved = build_upload_path(
                    settings.uploads_dir,
                    str(now.year),
                    f"{now.month:02d}",
                    extension=prepared.extension,
                )
                quarantine.replace(approved)
                target = approved
                scan_status = "CLEAN"
            else:
                scan_status = "INFECTED"
                quarantine.unlink(missing_ok=True)
                rejected_status = status.HTTP_422_UNPROCESSABLE_ENTITY
        except MalwareScannerError as exc:
            scan_status = "QUARANTINED"
            scan_detail = str(exc)
            rejected_status = status.HTTP_503_SERVICE_UNAVAILABLE
    stored = StoredFile(
        file_path=str(target) if target.exists() else None,
        original_name=upload.filename,
        mime_type=prepared.mime_type,
        size_bytes=prepared.size_bytes,
        scan_status=scan_status,
        scan_detail=scan_detail,
        scanned_at=scanned_at,
        uploaded_by_id=user_id,
    )
    session.add(stored)
    await session.flush()
    await record_audit(
        session,
        user_id=user_id,
        action_code="file.upload",
        entity_name="files",
        entity_id=stored.id,
        new_value={
            "original_name": upload.filename,
            "mime_type": prepared.mime_type,
            "size_bytes": prepared.size_bytes,
            "scan_status": scan_status,
        },
    )
    await session.commit()
    await session.refresh(stored)
    if rejected_status is not None:
        detail = "Файл заражён и удалён." if scan_status == "INFECTED" else "Файл помещён в карантин: антивирус временно недоступен."
        raise HTTPException(status_code=rejected_status, detail=detail)
    return stored


@router.post("/{file_id}/send-to-tg", status_code=200)
async def send_file_to_tg(
    file_id: int,
    current_user: CurrentUser = Depends(require_role(RoleLevel.CANDIDATE)),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Send a stored file to the requesting user via Telegram bot DM."""
    from pathlib import Path
    from aiogram.types import FSInputFile
    from ..background import _get_bot

    stored = await session.get(StoredFile, file_id)
    if not stored:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")
    await _check_file_access(stored, current_user, session)
    bot = _get_bot(settings)
    try:
        if stored.telegram_file_id:
            await bot.send_document(current_user.telegram_id, stored.telegram_file_id)
        elif stored.file_path and Path(stored.file_path).exists():
            await bot.send_document(
                current_user.telegram_id,
                FSInputFile(stored.file_path, filename=stored.original_name or Path(stored.file_path).name),
            )
        else:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File data not available.")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to send file via bot.") from exc
    return {"sent": True}


def _learning_audience_visible(audience_code: str, current_user: CurrentUser) -> bool:
    if audience_code == "ALL" or audience_code == current_user.role_code:
        return True
    if audience_code == "PARTICIPANTS":
        return current_user.role_level >= RoleLevel.PARTICIPANT
    if audience_code == "COMMANDERS":
        return current_user.role_level >= RoleLevel.DEPUTY_SQUAD_COMMANDER
    return False



def _announcement_visible(item: Announcement, current_user: CurrentUser) -> bool:
    if current_user.role_level >= RoleLevel.DEPUTY_PLATOON_COMMANDER:
        return True
    if item.status_code not in {"SENT", "PUBLISHED"}:
        return False
    if item.target_type == "ALL":
        return True
    if item.target_type == "SQUAD":
        return item.target_squad_id == current_user.squad_id
    if item.target_type == "ROLE":
        return item.target_role_code == current_user.role_code
    return False


async def _check_file_access(stored: StoredFile, current_user: CurrentUser, session: AsyncSession) -> None:
    if stored.scan_status not in {"CLEAN", "REENCODED", "LEGACY_TRUSTED"}:
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="File is quarantined or rejected.")
    if current_user.role_level >= RoleLevel.DEPUTY_PLATOON_COMMANDER:
        return
    if stored.uploaded_by_id is not None and stored.uploaded_by_id == current_user.user_id:
        return
    materials = list((
        await session.scalars(
            select(LearningMaterial).where(
                LearningMaterial.file_id == stored.id,
                LearningMaterial.is_active.is_(True),
            )
        )
    ).all())
    if any(_learning_audience_visible(item.audience_code, current_user) for item in materials):
        return
    normatives = list((
        await session.scalars(
            select(Normative).where(
                or_(
                    Normative.file_id == stored.id,
                    Normative.instruction_video_file_id == stored.id,
                )
            )
        )
    ).all())
    if any(_normative_visible(item, current_user) for item in normatives):
        return
    announcements = list((
        await session.scalars(select(Announcement).where(Announcement.file_id == stored.id))
    ).all())
    if any(_announcement_visible(item, current_user) for item in announcements):
        return
    appeals = list((await session.scalars(select(Appeal).where(Appeal.file_id == stored.id))).all())
    if any(item.author_user_id == current_user.user_id for item in appeals):
        return
    if appeals and current_user.role_level >= RoleLevel.DEPUTY_SQUAD_COMMANDER:
        return
    submissions = list((
        await session.scalars(
            select(NormativeSubmission)
            .outerjoin(NormativeSubmissionFile, NormativeSubmissionFile.submission_id == NormativeSubmission.id)
            .where(
                or_(
                    NormativeSubmission.file_id == stored.id,
                    NormativeSubmissionFile.file_id == stored.id,
                )
            )
        )
    ).all())
    for submission in submissions:
        if submission.user_id == current_user.user_id:
            return
        submitter_squad_id = await session.scalar(select(User.squad_id).where(User.id == submission.user_id))
        if can_manage_squad(current_user, submitter_squad_id):
            return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")


@router.get("/{file_id}", response_model=FileRead)
async def get_file_meta(
    file_id: int,
    current_user: CurrentUser = Depends(require_role(RoleLevel.CANDIDATE)),
    session: AsyncSession = Depends(get_db_session),
) -> StoredFile:
    stored = await session.get(StoredFile, file_id)
    if stored is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")
    await _check_file_access(stored, current_user, session)
    return stored


@router.get("/{file_id}/download")
async def download_file(
    file_id: int,
    current_user: CurrentUser = Depends(require_role(RoleLevel.CANDIDATE)),
    session: AsyncSession = Depends(get_db_session),
):
    stored = await session.get(StoredFile, file_id)
    if stored is None or not stored.file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")
    await _check_file_access(stored, current_user, session)
    path = Path(stored.file_path)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File content not found.")
    await record_audit(
        session,
        user_id=current_user.user_id,
        action_code="file.download",
        entity_name="files",
        entity_id=stored.id,
        new_value={"original_name": stored.original_name, "size_bytes": stored.size_bytes},
    )
    await session.commit()
    return FileResponse(path, media_type=stored.mime_type, filename=stored.original_name or path.name)


def _tg_content_type(file_path: str) -> str:
    ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
    if ext in {"mp4", "mov", "avi"}:
        return f"video/{ext}"
    if ext in {"jpg", "jpeg"}:
        return "image/jpeg"
    if ext == "png":
        return "image/png"
    return "application/octet-stream"


@router.get("/tg/{tg_file_id:path}")
async def download_tg_file(
    tg_file_id: str,
    current_user: CurrentUser = Depends(require_role(RoleLevel.DEPUTY_SQUAD_COMMANDER)),
    settings: Settings = Depends(get_settings),
):
    async with httpx.AsyncClient(timeout=30.0) as client:
        get_file_resp = await client.get(
            f"https://api.telegram.org/bot{settings.bot_token}/getFile",
            params={"file_id": tg_file_id},
        )
    if get_file_resp.status_code != 200:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to get file info from Telegram.")
    data = get_file_resp.json()
    if not data.get("ok") or not data.get("result", {}).get("file_path"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Telegram file not found.")
    tg_path: str = data["result"]["file_path"]
    content_type = _tg_content_type(tg_path)
    download_url = f"https://api.telegram.org/file/bot{settings.bot_token}/{tg_path}"

    async def stream_tg_file():
        async with httpx.AsyncClient(timeout=60.0) as stream_client:
            async with stream_client.stream("GET", download_url) as resp:
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    yield chunk

    return StreamingResponse(stream_tg_file(), media_type=content_type)
