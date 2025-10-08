from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from ..context import BotContext
from ..services.broadcast import BroadcastResult
from ..utils.access import ensure_role
from ..utils.roles import ADMIN_ROLES
from ..utils.audit import log_action

router = Router(name="admin_broadcast")


class BroadcastStates(StatesGroup):
    message = State()
    filter = State()
    preview = State()
    mode = State()
    confirm = State()


@router.message(Command("broadcast"))
async def broadcast_start(message: Message, member, context: BotContext, state: FSMContext, command: CommandObject) -> None:
    if not await ensure_role(message, getattr(member, "role", None), ADMIN_ROLES):
        return
    args = command.args or ""
    if args.strip():
        await state.update_data(message_text=args.strip())
        await _ask_filter(message, state)
    else:
        await message.answer("Отправьте текст рассылки.")
        await state.set_state(BroadcastStates.message)


@router.message(BroadcastStates.message)
async def broadcast_message_text(message: Message, state: FSMContext) -> None:
    await state.update_data(message_text=message.text)
    await _ask_filter(message, state)


async def _ask_filter(message: Message, state: FSMContext) -> None:
    await message.answer(
        "Выберите аудиторию: отправьте 'все', 'отделение=<название>' или 'роль=<ROLE>'."
    )
    await state.set_state(BroadcastStates.filter)


@router.message(BroadcastStates.filter)
async def broadcast_filter(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    department = None
    role = None
    if text.lower() == "все":
        pass
    elif text.lower().startswith("отделение="):
        department = text.split("=", 1)[1].strip()
    elif text.lower().startswith("роль="):
        role = text.split("=", 1)[1].strip()
    else:
        await message.answer("Формат: все / отделение=<название> / роль=<ROLE>.")
        return
    await state.update_data(department_filter=department, role_filter=role)
    await message.answer("Включить предпросмотр ссылок? (да/нет)")
    await state.set_state(BroadcastStates.preview)


@router.message(BroadcastStates.preview)
async def broadcast_preview(message: Message, state: FSMContext) -> None:
    answer = message.text.strip().lower()
    if answer not in {"да", "нет"}:
        await message.answer("Ответьте 'да' или 'нет'.")
        return
    await state.update_data(disable_preview=False if answer == "да" else True)
    await message.answer("Режим: отправить всем или тест? (всем/тест)")
    await state.set_state(BroadcastStates.mode)


@router.message(BroadcastStates.mode)
async def broadcast_mode(message: Message, state: FSMContext) -> None:
    answer = message.text.strip().lower()
    if answer not in {"всем", "тест"}:
        await message.answer("Введите 'всем' или 'тест'.")
        return
    await state.update_data(test_mode=(answer == "тест"))
    data = await state.get_data()
    summary = [
        "Проверьте данные:",
        f"Текст: {data['message_text']}",
        f"Фильтр: отделение={data.get('department_filter') or '-'}, роль={data.get('role_filter') or '-'}",
        f"Предпросмотр ссылок: {'вкл' if not data['disable_preview'] else 'выкл'}",
        f"Режим: {'тест' if data['test_mode'] else 'боевой'}",
        "",
        "Отправить? (да/нет)",
    ]
    await message.answer("\n".join(summary))
    await state.set_state(BroadcastStates.confirm)


@router.message(BroadcastStates.confirm)
async def broadcast_confirm(message: Message, member, context: BotContext, state: FSMContext) -> None:
    answer = message.text.strip().lower()
    if answer not in {"да", "нет"}:
        await message.answer("Ответьте 'да' или 'нет'.")
        return
    if answer == "нет":
        await state.clear()
        await message.answer("Рассылка отменена.")
        return
    data = await state.get_data()
    department = data.get("department_filter")
    role = data.get("role_filter")
    recipients = context.broadcast_service.eligible_members(
        department=department,
        role=role,
        only_active=True,
    )
    if data["test_mode"]:
        if getattr(member, "tg_user_id", None):
            recipients = [member]
        else:
            await message.answer("Ваш аккаунт не привязан — тестовая отправка невозможна.")
            await state.clear()
            return
    if not recipients:
        await message.answer("Нет получателей по выбранным условиям.")
        await state.clear()
        return

    text = data["message_text"]
    disable_web_page_preview = data["disable_preview"]

    async def sender(target_member):
        await context.bot.send_message(
            chat_id=target_member.tg_user_id,
            text=text,
            disable_web_page_preview=disable_web_page_preview,
        )

    results = await context.broadcast_service.broadcast(
        recipients,
        sender,
        dryrun=context.config.dryrun,
    )

    summary = _format_results(results)
    await message.answer(summary)
    log_action(
        context,
        message.from_user.id,
        "broadcast",
        f"recipients={len(recipients)};success={len([r for r in results if r.success])};test={data['test_mode']}",
    )
    await state.clear()


def _format_results(results: list[BroadcastResult]) -> str:
    success = [res for res in results if res.success]
    failed = [res for res in results if not res.success]
    lines = [
        f"Успешно: {len(success)}",
        f"Ошибки: {len(failed)}",
    ]
    for res in failed[:5]:
        lines.append(f"- {res.member.fio}: {res.error}")
    if len(failed) > 5:
        lines.append("Список ошибок сокращён.")
    return "\n".join(lines)
