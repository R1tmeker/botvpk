from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from ..context import BotContext
from ..utils.access import ensure_role
from ..utils.audit import log_action
from ..utils.keyboards import BTN_NORMS
from ..utils.roles import CONFIRMED_ROLES, PLATOON_STAFF_ROLES

router = Router(name="normatives")


class SubmitNormStates(StatesGroup):
    waiting_report = State()


@router.message(Command("norms"))
@router.message(F.text.casefold() == BTN_NORMS.casefold())
async def norms_menu(message: Message, member, context: BotContext) -> None:
    if not await ensure_role(message, getattr(member, "role", None), CONFIRMED_ROLES):
        return
    norms = context.normatives_service.list_active_norms()
    lines = ["Нормативы", ""]
    if norms:
        for norm in norms:
            deadline = f" · до {norm.deadline}" if norm.deadline else ""
            lines.append(f"#{norm.norm_id} {norm.title}{deadline}\n{norm.description}")
        lines.extend(["", "Сдать отчёт: /submit_norm ID"])
    else:
        lines.append("Активных нормативов пока нет.")
    if await _can_manage_norms(message, member, silent=True):
        lines.extend(
            [
                "",
                "Для командования:",
                "• /add_norm название | описание | дедлайн",
                "• /delete_norm ID",
                "• /norm_reports",
            ]
        )
    await message.answer("\n".join(lines), parse_mode=None)


@router.message(Command("add_norm"))
async def add_norm(message: Message, member, context: BotContext, command: CommandObject) -> None:
    if not await _can_manage_norms(message, member):
        return
    args = (command.args or "").strip()
    if not args:
        await message.answer("Формат: /add_norm название | описание | дедлайн")
        return
    parts = [part.strip() for part in args.split("|")]
    title = parts[0]
    description = parts[1] if len(parts) > 1 else ""
    deadline = parts[2] if len(parts) > 2 else ""
    if not title:
        await message.answer("Название норматива не может быть пустым.")
        return
    norm = context.normatives_service.add_norm(
        title=title,
        description=description,
        deadline=deadline,
        created_by=message.from_user.id,
    )
    log_action(context, message.from_user.id, "add_norm", f"id={norm.norm_id}")
    await message.answer(f"Норматив добавлен: #{norm.norm_id} {norm.title}", parse_mode=None)


@router.message(Command("delete_norm"))
async def delete_norm(message: Message, member, context: BotContext, command: CommandObject) -> None:
    if not await _can_manage_norms(message, member):
        return
    try:
        norm_id = int((command.args or "").strip().split()[0])
    except (ValueError, IndexError):
        await message.answer("Формат: /delete_norm ID")
        return
    if not context.normatives_service.delete_norm(norm_id):
        await message.answer("Норматив не найден.")
        return
    log_action(context, message.from_user.id, "delete_norm", f"id={norm_id}")
    await message.answer("Норматив удалён.")


@router.message(Command("submit_norm"))
async def submit_norm_start(message: Message, member, context: BotContext, command: CommandObject, state: FSMContext) -> None:
    if not await ensure_role(message, getattr(member, "role", None), CONFIRMED_ROLES):
        return
    try:
        norm_id = int((command.args or "").strip().split()[0])
    except (ValueError, IndexError):
        await message.answer("Формат: /submit_norm ID. ID можно посмотреть в разделе «Нормативы».")
        return
    norm = context.normatives_service.get_norm(norm_id)
    if not norm or not norm.is_active:
        await message.answer("Норматив не найден или выключен.")
        return
    await state.update_data(norm_id=norm_id)
    await state.set_state(SubmitNormStates.waiting_report)
    await message.answer(
        f"Отправь видео, документ, фото или текстовый отчёт по нормативу #{norm.norm_id} {norm.title}.",
        parse_mode=None,
    )


@router.message(SubmitNormStates.waiting_report)
async def submit_norm_report(message: Message, member, context: BotContext, state: FSMContext) -> None:
    data = await state.get_data()
    norm_id = int(data["norm_id"])
    file_type = "text"
    file_id = ""
    comment = message.text or ""

    if message.video:
        file_type = "video"
        file_id = message.video.file_id
        comment = message.caption or ""
    elif message.document:
        file_type = "document"
        file_id = message.document.file_id
        comment = message.caption or ""
    elif message.photo:
        file_type = "photo"
        file_id = message.photo[-1].file_id
        comment = message.caption or ""

    submission = context.normatives_service.submit(
        norm_id=norm_id,
        member_id=member.id,
        file_type=file_type,
        file_id=file_id,
        comment=comment,
    )
    log_action(context, message.from_user.id, "submit_norm", f"id={submission.submission_id};norm_id={norm_id}")
    await state.clear()
    await message.answer("Отчёт по нормативу сохранён.")


@router.message(Command("norm_reports"))
async def norm_reports(message: Message, member, context: BotContext) -> None:
    if not await _can_manage_norms(message, member):
        return
    submissions = context.normatives_service.list_submissions(limit=15)
    if not submissions:
        await message.answer("Отчётов по нормативам пока нет.")
        return
    members = {item.id: item for item in context.roster_service.list_members()}
    norms = {item.norm_id: item for item in context.normatives_service.list_norms()}
    lines = ["Последние отчёты по нормативам:"]
    for item in submissions:
        target = members.get(item.member_id)
        norm = norms.get(item.norm_id)
        name = target.fio if target else f"ID {item.member_id}"
        norm_title = norm.title if norm else f"Норматив {item.norm_id}"
        lines.append(
            f"\n#{item.submission_id} · {item.submitted_at}\n"
            f"{name}\n{norm_title}\nТип: {item.file_type}"
            + (f"\nКомментарий: {item.comment}" if item.comment else "")
        )
    await message.answer("\n".join(lines), parse_mode=None)


async def _can_manage_norms(message: Message, member, silent: bool = False) -> bool:
    if silent:
        from ..utils.roles import effective_role

        current = effective_role(getattr(member, "role", None))
        return current in {effective_role(role) for role in PLATOON_STAFF_ROLES}
    return await ensure_role(message, getattr(member, "role", None), PLATOON_STAFF_ROLES)
