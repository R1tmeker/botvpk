from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..database import get_db_session
from ..dependencies.auth import CurrentUser, get_current_user
from ..models import JoinApplication, MenuCard, User
from ..roles import RoleCode
from ..schemas.auth import AuthResponse, MenuCardResponse, TelegramAuthRequest, UserProfile
from ..utils.jwt import create_access_token
from ..utils.telegram_auth import TelegramInitDataError, validate_init_data

router = APIRouter(tags=["auth"])


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
        if application and user.role_code == RoleCode.PUBLIC_USER.value:
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
    base = [
        MenuCardResponse(code="dashboard", title="Главная", route="/", icon_code="dashboard", is_required=True),
        MenuCardResponse(code="schedule", title="Расписание", route="/schedule", icon_code="schedule", is_required=True),
        MenuCardResponse(code="appeals", title="Обращения", route="/appeals", icon_code="appeals", is_required=True),
    ]
    if role_code in {RoleCode.PUBLIC_USER.value, RoleCode.CANDIDATE.value}:
        return base + [
            MenuCardResponse(code="join", title="Вступить", route="/join", icon_code="join", is_required=True),
            MenuCardResponse(code="learning_public", title="Материалы", route="/learning", icon_code="learning"),
        ]
    return base + [
        MenuCardResponse(code="attendance", title="Посещаемость", route="/attendance", icon_code="attendance"),
        MenuCardResponse(code="normatives", title="Нормативы", route="/normatives", icon_code="normatives"),
        MenuCardResponse(code="squads", title="Состав", route="/squads", icon_code="squads"),
        MenuCardResponse(code="notifications", title="Уведомления", route="/notifications", icon_code="notifications"),
    ]
