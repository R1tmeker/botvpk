from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File as UploadParam, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..database import get_db_session
from ..dependencies.auth import CurrentUser, get_current_user
from ..models import File as StoredFile
from ..models import JoinApplication, MenuCard, User
from ..roles import RoleCode, RoleLevel, role_level
from ..schemas.auth import AuthResponse, MenuCardResponse, TelegramAuthRequest, UserProfile
from ..utils.audit import record_audit
from ..utils.jwt import create_access_token
from ..utils.telegram_auth import TelegramInitDataError, validate_init_data

router = APIRouter(tags=["auth"])

AVATAR_MIME_PREFIX = "image/"


@router.post("/auth/telegram", response_model=AuthResponse)
async def auth_telegram(
    payload: TelegramAuthRequest,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> AuthResponse:
    try:
        init_data = validate_init_data(payload.init_data, settings.bot_token)
    except TelegramInitDataError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    user = await session.scalar(select(User).where(User.telegram_id == init_data.user.telegram_id))
    application = await session.scalar(
        select(JoinApplication)
        .where(
            JoinApplication.telegram_id == init_data.user.telegram_id,
            JoinApplication.status_code.not_in(["ACCEPTED", "REJECTED", "ARCHIVED"]),
        )
        .order_by(JoinApplication.id.desc())
    )
    if user:
        if settings.super_admin_id and init_data.user.telegram_id == settings.super_admin_id \
                and user.role_code != RoleCode.SUPER_ADMIN.value:
            user.role_code = RoleCode.SUPER_ADMIN.value
            await session.commit()
            await session.refresh(user)
        elif application and user.role_code == RoleCode.PUBLIC_USER.value:
            user.role_code = RoleCode.CANDIDATE.value
            await session.commit()
            await session.refresh(user)
        profile = _profile_from_user(user)
        role_code = user.role_code
        user_id = user.id
        squad_id = user.squad_id
    else:
        if settings.super_admin_id and init_data.user.telegram_id == settings.super_admin_id:
            role_code = RoleCode.SUPER_ADMIN.value
        elif application:
            role_code = RoleCode.CANDIDATE.value
        else:
            role_code = RoleCode.PUBLIC_USER.value
        user = User(
            telegram_id=init_data.user.telegram_id,
            username=init_data.user.username,
            full_name=init_data.user.full_name,
            role_code=role_code,
            status_code="ACTIVE",
        )
        session.add(user)
        await session.flush()
        await session.commit()
        await session.refresh(user)
        profile = _profile_from_user(user)
        user_id = user.id
        squad_id = user.squad_id

    token = create_access_token(
        {
            "user_id": user_id,
            "telegram_id": init_data.user.telegram_id,
            "role_code": role_code,
            "squad_id": squad_id,
        },
        settings,
    )
    return AuthResponse(access_token=token, profile=profile)


@router.get("/me", response_model=UserProfile)
async def get_me(current_user: CurrentUser = Depends(get_current_user)) -> UserProfile:
    if current_user.user:
        return _profile_from_user(current_user.user)
    return UserProfile(
        id=None,
        telegram_id=current_user.telegram_id,
        full_name=str(current_user.telegram_id),
        role_code=current_user.role_code,
        squad_id=current_user.squad_id,
    )


@router.post("/me/avatar", response_model=UserProfile)
async def upload_my_avatar(
    upload: UploadFile = UploadParam(...),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> UserProfile:
    if current_user.user is None or current_user.user_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User profile is required.")
    if not upload.content_type or not upload.content_type.startswith(AVATAR_MIME_PREFIX):
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Avatar must be an image.")
    content = await upload.read()
    if len(content) > settings.max_upload_size_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File is too large.")

    now = datetime.now(timezone.utc)
    upload_dir = settings.uploads_dir / "avatars" / str(now.year) / f"{now.month:02d}"
    upload_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(upload.filename or "").suffix.lower()[:20] or ".jpg"
    target = upload_dir / f"{uuid4().hex}{suffix}"
    target.write_bytes(content)

    stored = StoredFile(
        file_path=str(target),
        original_name=upload.filename,
        mime_type=upload.content_type,
        size_bytes=len(content),
        uploaded_by_id=current_user.user_id,
    )
    session.add(stored)
    await session.flush()

    current_user.user.avatar_file_id = stored.id
    current_user.user.updated_at = now
    await record_audit(
        session,
        user_id=current_user.user_id,
        action_code="user.avatar.upload",
        entity_name="users",
        entity_id=current_user.user_id,
        new_value={"avatar_file_id": stored.id, "mime_type": upload.content_type, "size_bytes": len(content)},
    )
    await session.commit()
    await session.refresh(current_user.user)
    return _profile_from_user(current_user.user)


@router.get("/menu", response_model=list[MenuCardResponse])
async def get_menu(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[MenuCardResponse]:
    cards = (
        await session.scalars(
            select(MenuCard)
            .where(MenuCard.is_active.is_(True))
            .order_by(MenuCard.sort_order, MenuCard.id)
        )
    ).all()
    result = []
    for card in cards:
        roles = card.roles_json or []
        if roles and current_user.role_code not in roles:
            continue
        result.append(_menu_card(card))
    return result or _default_menu(current_user.role_code)


def _profile_from_user(user: User) -> UserProfile:
    return UserProfile(
        id=user.id,
        telegram_id=user.telegram_id or 0,
        username=user.username,
        full_name=user.full_name,
        squad_id=user.squad_id,
        avatar_file_id=user.avatar_file_id,
        role_code=user.role_code,
        status_code=user.status_code,
        birth_date=user.birth_date,
        phone=user.phone,
    )


def _menu_card(card: MenuCard) -> MenuCardResponse:
    return MenuCardResponse(
        code=card.code,
        title=card.title,
        description=card.description,
        icon_code=card.icon_code,
        color_code=card.color_code,
        route=card.route,
        sort_order=card.sort_order,
        is_required=card.is_required,
        show_badge=card.show_badge,
    )


def _default_menu(role_code: str) -> list[MenuCardResponse]:
    level = role_level(role_code)
    if level < RoleLevel.PARTICIPANT:
        return [
            MenuCardResponse(code="join", title="Вступить", route="/join", icon_code="dashboard", is_required=True),
            MenuCardResponse(code="schedule", title="Открытые события", route="/schedule", icon_code="schedule", is_required=True),
            MenuCardResponse(code="learning_public", title="Материалы", route="/learning", icon_code="learning"),
        ]

    cards = [
        MenuCardResponse(code="dashboard", title="Главная", route="/", icon_code="dashboard", is_required=True),
        MenuCardResponse(code="schedule", title="Расписание", route="/schedule", icon_code="schedule", is_required=True),
        MenuCardResponse(code="attendance", title="Посещаемость", route="/attendance", icon_code="attendance"),
        MenuCardResponse(code="normatives", title="Нормативы", route="/normatives", icon_code="normatives"),
        MenuCardResponse(code="squads", title="Состав", route="/squads", icon_code="squads"),
        MenuCardResponse(code="notifications", title="Уведомления", route="/notifications", icon_code="notifications"),
        MenuCardResponse(code="appeals", title="Обращения", route="/appeals", icon_code="appeals"),
    ]
    if level >= RoleLevel.DEPUTY_SQUAD_COMMANDER:
        cards.append(MenuCardResponse(code="announcements", title="Объявления", route="/announcements", icon_code="announcements"))
    if level >= RoleLevel.SQUAD_COMMANDER:
        cards.append(MenuCardResponse(code="reports", title="Отчёты", route="/reports", icon_code="reports"))
    if level >= RoleLevel.DEPUTY_PLATOON_COMMANDER:
        cards.append(MenuCardResponse(code="admin", title="Админка", route="/admin", icon_code="admin"))
    return cards
