from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File as UploadParam, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..database import get_db_session
from ..dependencies.auth import CurrentUser, require_role
from ..models import File as StoredFile
from ..models import User
from ..roles import RoleLevel
from ..schemas.core import FileRead
from ..utils.audit import record_audit

router = APIRouter(prefix="/files", tags=["files"])

ALLOWED_MIME_PREFIXES = ("image/", "video/")
ALLOWED_MIME_TYPES = {
    "application/pdf",
}


def require_profile(current_user: CurrentUser) -> int:
    if current_user.user_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User profile is required.")
    return current_user.user_id


def is_allowed_mime(mime_type: str | None) -> bool:
    if not mime_type:
        return False
    return mime_type in ALLOWED_MIME_TYPES or mime_type.startswith(ALLOWED_MIME_PREFIXES)


@router.get("/avatars/{file_id}")
async def download_avatar(
    file_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    stored = await session.get(StoredFile, file_id)
    if stored is None or not stored.file_path or not (stored.mime_type or "").startswith("image/"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Avatar not found.")
    owner_id = await session.scalar(select(User.id).where(User.avatar_file_id == file_id).limit(1))
    if owner_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Avatar not found.")
    path = Path(stored.file_path)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Avatar content not found.")
    return FileResponse(path, media_type=stored.mime_type, filename=stored.original_name or path.name)


@router.post("/upload", response_model=FileRead, status_code=status.HTTP_201_CREATED)
async def upload_file(
    upload: UploadFile = UploadParam(...),
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> StoredFile:
    user_id = require_profile(current_user)
    if not is_allowed_mime(upload.content_type):
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Unsupported file type.")
    content = await upload.read()
    if len(content) > settings.max_upload_size_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File is too large.")
    now = datetime.now(timezone.utc)
    upload_dir = settings.uploads_dir / str(now.year) / f"{now.month:02d}"
    upload_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(upload.filename or "").suffix.lower()[:20]
    target = upload_dir / f"{uuid4().hex}{suffix}"
    target.write_bytes(content)
    stored = StoredFile(
        file_path=str(target),
        original_name=upload.filename,
        mime_type=upload.content_type,
        size_bytes=len(content),
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
        new_value={"original_name": upload.filename, "mime_type": upload.content_type, "size_bytes": len(content)},
    )
    await session.commit()
    await session.refresh(stored)
    return stored


def _check_file_access(stored: StoredFile, current_user: CurrentUser) -> None:
    if current_user.role_level >= RoleLevel.DEPUTY_PLATOON_COMMANDER:
        return
    if stored.uploaded_by_id is not None and stored.uploaded_by_id == current_user.user_id:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")


@router.get("/{file_id}", response_model=FileRead)
async def get_file_meta(
    file_id: int,
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
) -> StoredFile:
    stored = await session.get(StoredFile, file_id)
    if stored is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")
    _check_file_access(stored, current_user)
    return stored


@router.get("/{file_id}/download")
async def download_file(
    file_id: int,
    current_user: CurrentUser = Depends(require_role(RoleLevel.PARTICIPANT)),
    session: AsyncSession = Depends(get_db_session),
):
    stored = await session.get(StoredFile, file_id)
    if stored is None or not stored.file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")
    _check_file_access(stored, current_user)
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
