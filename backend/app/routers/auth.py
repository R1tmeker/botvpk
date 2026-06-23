from __future__ import annotations

import logging
from datetime import datetime, timezone

import pyotp
from fastapi import APIRouter, Depends, File as UploadParam, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..database import get_db_session
from ..dependencies.auth import CurrentUser, get_current_user
from ..models import File as StoredFile
from ..models import JoinApplication, MenuCard, User
from ..ratelimit import limiter
from ..roles import RoleCode, RoleLevel, role_level
from ..schemas.auth import (
    AuthResponse,
    MenuCardResponse,
    PasswordLoginRequest,
    PasswordResetRequest,
    PasswordSetRequest,
    PasswordStatusResponse,
    TelegramAuthRequest,
    TwoFactorCodeRequest,
    TwoFactorSetupResponse,
    TwoFactorStatusResponse,
    UserProfile,
)
from ..schemas.core import UserSelfUpdate
from ..services.auth_security import (
    PasswordPolicyError,
    bump_token_version,
    password_lockout_state,
    register_failed_password_login,
    register_successful_password_login,
    validate_password_policy,
)
from ..services.uploads import IMAGE_MIME_TYPES, UploadValidationError, build_upload_path, prepare_upload
from ..utils.audit import record_audit
from ..utils.channel_link import redeem_link_code_for_user
from ..utils.jwt import create_access_token
from ..utils.password import hash_password, verify_password
from ..utils.telegram_auth import TelegramInitDataError, validate_init_data

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])


@router.post("/auth/telegram", response_model=AuthResponse)
async def auth_telegram(
    payload: TelegramAuthRequest,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> AuthResponse:
    try:
        init_data = validate_init_data(
            payload.init_data,
            settings.bot_token,
            max_age_seconds=settings.telegram_init_data_max_age_seconds,
        )
    except TelegramInitDataError as exc:
        logger.warning(
            "Telegram auth failed: reason=%s init_data_len=%s",
            exc,
            len(payload.init_data),
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    user = await session.scalar(select(User).where(User.telegram_id == init_data.user.telegram_id))
    application = await session.scalar(
        select(JoinApplication)
        .where(
            JoinApplication.telegram_id == init_data.user.telegram_id,
            JoinApplication.status_code.notin_(["ACCEPTED", "REJECTED", "ARCHIVED"]),
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

    token = create_access_token(_token_payload(user), settings)
    return AuthResponse(access_token=token, profile=profile, app_timezone=settings.timezone)


# ──────────────────────── website password auth ────────────────────────────
# Telegram remains the primary identity. Password is set from inside the Mini App
# (where the member is already verified) and only lets confirmed members log in on
# the plain website. Login = Telegram ID + password.


@router.get("/auth/password/status", response_model=PasswordStatusResponse)
async def password_status(
    current_user: CurrentUser = Depends(get_current_user),
) -> PasswordStatusResponse:
    user = current_user.user
    if user is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User profile is required.")
    return PasswordStatusResponse(has_password=bool(user.password_hash), password_set_at=user.password_set_at)


@router.post("/auth/password/set", response_model=PasswordStatusResponse)
async def set_password(
    payload: PasswordSetRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PasswordStatusResponse:
    user = current_user.user
    if user is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User profile is required.")
    if current_user.role_level < RoleLevel.PARTICIPANT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password login is available only to confirmed members.",
        )
    # Changing an existing password requires the current one.
    if user.password_hash and not (
        payload.current_password and verify_password(payload.current_password, user.password_hash)
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Current password is incorrect.")
    try:
        validate_password_policy(payload.new_password, telegram_id=user.telegram_id)
    except PasswordPolicyError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    user.password_hash = hash_password(payload.new_password)
    user.password_set_at = datetime.now(timezone.utc)
    user.updated_at = datetime.now(timezone.utc)
    user.failed_login_count = 0
    user.locked_until = None
    bump_token_version(user)
    await record_audit(
        session,
        user_id=user.id,
        action_code="auth.password.set",
        entity_name="users",
        entity_id=user.id,
    )
    await session.commit()
    await session.refresh(user)
    return PasswordStatusResponse(has_password=True, password_set_at=user.password_set_at)


@router.delete("/auth/password", response_model=PasswordStatusResponse)
async def delete_password(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PasswordStatusResponse:
    user = current_user.user
    if user is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User profile is required.")
    user.password_hash = None
    user.password_set_at = None
    user.updated_at = datetime.now(timezone.utc)
    user.failed_login_count = 0
    user.locked_until = None
    bump_token_version(user)
    await record_audit(
        session,
        user_id=user.id,
        action_code="auth.password.delete",
        entity_name="users",
        entity_id=user.id,
    )
    await session.commit()
    return PasswordStatusResponse(has_password=False, password_set_at=None)


@router.post("/auth/password/reset", response_model=PasswordStatusResponse)
async def reset_password(
    payload: PasswordResetRequest,
    session: AsyncSession = Depends(get_db_session),
) -> PasswordStatusResponse:
    invalid = HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset code.")
    user = await session.scalar(select(User).where(User.telegram_id == payload.telegram_id))
    if user is None or user.status_code != "ACTIVE" or role_level(user.role_code) < RoleLevel.PARTICIPANT:
        raise invalid
    consumed = await redeem_link_code_for_user(
        session,
        user_id=user.id,
        code=payload.code,
        channel="PASSWORD_RESET",
    )
    if not consumed:
        await session.rollback()
        raise invalid
    try:
        validate_password_policy(payload.new_password, telegram_id=user.telegram_id)
    except PasswordPolicyError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    user.password_hash = hash_password(payload.new_password)
    user.password_set_at = datetime.now(timezone.utc)
    user.updated_at = datetime.now(timezone.utc)
    user.failed_login_count = 0
    user.locked_until = None
    bump_token_version(user)
    await record_audit(
        session,
        user_id=user.id,
        action_code="auth.password.reset",
        entity_name="users",
        entity_id=user.id,
    )
    await session.commit()
    return PasswordStatusResponse(has_password=True, password_set_at=user.password_set_at)


@router.post("/auth/password/login", response_model=AuthResponse)
@limiter.limit("5/minute")
async def password_login(
    request: Request,
    payload: PasswordLoginRequest,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> AuthResponse:
    # Single generic error for "no such id" and "wrong password" to avoid
    # leaking which Telegram IDs exist (IDs are enumerable).
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Telegram ID or password."
    )
    user = await session.scalar(select(User).where(User.telegram_id == payload.telegram_id))
    if user is not None:
        lockout = password_lockout_state(user)
        if lockout.locked:
            await record_audit(
                session,
                user_id=user.id,
                action_code="auth.password.login_locked",
                entity_name="users",
                entity_id=user.id,
                new_value={"seconds_left": lockout.seconds_left},
            )
            await session.commit()
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed login attempts. Try again later.",
            )
    if user is None or not user.password_hash or not verify_password(payload.password, user.password_hash):
        if user is not None:
            lockout = await register_failed_password_login(session, user)
            await record_audit(
                session,
                user_id=user.id,
                action_code="auth.password.login_failed",
                entity_name="users",
                entity_id=user.id,
                new_value={"failed_login_count": user.failed_login_count, "locked": lockout.locked},
            )
            await session.commit()
        raise invalid
    if user.status_code != "ACTIVE" or role_level(user.role_code) < RoleLevel.PARTICIPANT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Website access is available only to confirmed active members.",
        )
    if user.totp_enabled_at is not None:
        if not payload.totp_code:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Two-factor code is required.")
        if not pyotp.TOTP(user.totp_secret or "").verify(payload.totp_code, valid_window=1):
            await record_audit(
                session,
                user_id=user.id,
                action_code="auth.password.totp_failed",
                entity_name="users",
                entity_id=user.id,
            )
            await session.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid two-factor code.")
    register_successful_password_login(user)
    token = create_access_token(_token_payload(user), settings)
    await record_audit(
        session,
        user_id=user.id,
        action_code="auth.password.login",
        entity_name="users",
        entity_id=user.id,
    )
    await session.commit()
    return AuthResponse(access_token=token, profile=_profile_from_user(user), app_timezone=settings.timezone)


@router.get("/auth/2fa/status", response_model=TwoFactorStatusResponse)
async def two_factor_status(current_user: CurrentUser = Depends(get_current_user)) -> TwoFactorStatusResponse:
    user = current_user.user
    if user is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User profile is required.")
    available = current_user.role_level >= RoleLevel.DEPUTY_SQUAD_COMMANDER
    return TwoFactorStatusResponse(available=available, enabled=bool(user.totp_enabled_at))


@router.post("/auth/2fa/setup", response_model=TwoFactorSetupResponse)
async def two_factor_setup(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> TwoFactorSetupResponse:
    user = current_user.user
    if user is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User profile is required.")
    if current_user.role_level < RoleLevel.DEPUTY_SQUAD_COMMANDER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Two-factor auth is for commanders and admins.")
    if not user.totp_secret:
        user.totp_secret = pyotp.random_base32()
        user.updated_at = datetime.now(timezone.utc)
        await session.commit()
    issuer = "ВПК Звезда"
    name = str(user.telegram_id or user.id)
    provisioning_uri = pyotp.TOTP(user.totp_secret).provisioning_uri(name=name, issuer_name=issuer)
    return TwoFactorSetupResponse(secret=user.totp_secret, provisioning_uri=provisioning_uri)


@router.post("/auth/2fa/enable", response_model=TwoFactorStatusResponse)
async def two_factor_enable(
    payload: TwoFactorCodeRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> TwoFactorStatusResponse:
    user = current_user.user
    if user is None or current_user.role_level < RoleLevel.DEPUTY_SQUAD_COMMANDER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Two-factor auth is for commanders and admins.")
    if not user.totp_secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Start 2FA setup first.")
    if not pyotp.TOTP(user.totp_secret).verify(payload.code, valid_window=1):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid two-factor code.")
    user.totp_enabled_at = datetime.now(timezone.utc)
    user.updated_at = datetime.now(timezone.utc)
    bump_token_version(user)
    await record_audit(session, user_id=user.id, action_code="auth.2fa.enable", entity_name="users", entity_id=user.id)
    await session.commit()
    return TwoFactorStatusResponse(available=True, enabled=True)


@router.post("/auth/2fa/disable", response_model=TwoFactorStatusResponse)
async def two_factor_disable(
    payload: TwoFactorCodeRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> TwoFactorStatusResponse:
    user = current_user.user
    if user is None or current_user.role_level < RoleLevel.DEPUTY_SQUAD_COMMANDER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Two-factor auth is for commanders and admins.")
    if user.totp_enabled_at and not pyotp.TOTP(user.totp_secret or "").verify(payload.code, valid_window=1):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid two-factor code.")
    user.totp_secret = None
    user.totp_enabled_at = None
    user.updated_at = datetime.now(timezone.utc)
    bump_token_version(user)
    await record_audit(session, user_id=user.id, action_code="auth.2fa.disable", entity_name="users", entity_id=user.id)
    await session.commit()
    return TwoFactorStatusResponse(available=True, enabled=False)


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


@router.patch("/me", response_model=UserProfile)
async def update_me(
    payload: UserSelfUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> UserProfile:
    if current_user.user is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User profile is required.")
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(current_user.user, field, value or None)
    current_user.user.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(current_user.user)
    return _profile_from_user(current_user.user)


@router.post("/me/avatar", response_model=UserProfile)
async def upload_my_avatar(
    upload: UploadFile = UploadParam(...),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> UserProfile:
    if current_user.user is None or current_user.user_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User profile is required.")
    content = await upload.read()
    try:
        prepared = prepare_upload(
            content,
            max_size_bytes=settings.max_upload_size_bytes,
            allowed_mime_types=IMAGE_MIME_TYPES,
            image_max_side=512,
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
    target = build_upload_path(
        settings.uploads_dir,
        "avatars",
        str(now.year),
        f"{now.month:02d}",
        extension=prepared.extension,
    )
    target.write_bytes(prepared.content)

    stored = StoredFile(
        file_path=str(target),
        original_name=upload.filename,
        mime_type=prepared.mime_type,
        size_bytes=prepared.size_bytes,
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
        new_value={"avatar_file_id": stored.id, "mime_type": prepared.mime_type, "size_bytes": prepared.size_bytes},
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
        city=user.city,
        education_place=user.education_place,
    )


def _token_payload(user: User) -> dict:
    return {
        "user_id": user.id,
        "telegram_id": user.telegram_id,
        "role_code": user.role_code,
        "squad_id": user.squad_id,
        "token_version": user.token_version or 0,
    }


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
