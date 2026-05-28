from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from ..context import BotContext
from ..services.exceptions import LinkAmbiguityError, NotFoundError, ValidationServiceError

router = Router(name="link")


class LinkStates(StatesGroup):
    waiting_fio = State()
    waiting_id = State()


@router.message(Command("link"))
async def command_link(message: Message, state: FSMContext, context: BotContext, member) -> None:
    if member:
        await message.answer("Вы уже привязаны к реестру.")
        return
    await message.answer("Введите своё ФИО точно как в реестре (Фамилия Имя Отчество).")
    await state.set_state(LinkStates.waiting_fio)


@router.message(LinkStates.waiting_fio)
async def process_fio(message: Message, state: FSMContext, context: BotContext) -> None:
    fio = message.text.strip()
    try:
        result = context.roster_service.link_member(
            fio=fio,
            tg_user_id=message.from_user.id,
            tg_username=message.from_user.username,
        )
        await state.clear()
        suffix = " Роль обновлена до «Участник»." if result.newly_confirmed else ""
        await message.answer(f"Привязка успешна. Добро пожаловать!{suffix}")
    except LinkAmbiguityError as exc:
        await state.update_data(candidates=exc.candidates)
        await state.update_data(fio=fio)
        lines = ["Найдено несколько совпадений:"]
        for candidate_id in exc.candidates:
            member = context.roster_service.get_member_by_id(candidate_id)
            lines.append(f"{member.id} — {member.fio} ({member.department})")
        lines.append("Отправьте id нужного участника.")
        await message.answer("\n".join(lines))
        await state.set_state(LinkStates.waiting_id)
    except NotFoundError:
        await message.answer("ФИО не найдено. Проверьте написание или обратитесь к администратору.")
        await state.clear()
    except ValidationServiceError as exc:
        await message.answer(str(exc))
        await state.clear()


@router.message(LinkStates.waiting_id)
async def process_id(message: Message, state: FSMContext, context: BotContext) -> None:
    data = await state.get_data()
    candidates = data.get("candidates", [])
    try:
        member_id = int(message.text.strip())
    except ValueError:
        await message.answer("Введите числовой id.")
        return
    if member_id not in candidates:
        await message.answer("Этот id не в списке кандидатов.")
        return
    try:
        result = context.roster_service.link_member_by_id(
            member_id,
            tg_user_id=message.from_user.id,
            tg_username=message.from_user.username,
        )
        await message.answer("Привязка подтверждена.")
        await state.clear()
    except ValidationServiceError as exc:
        await message.answer(str(exc))
        await state.clear()

