from __future__ import annotations

import asyncio
from pathlib import Path

import pytz
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.config_loader import load_config
from bot.context import BotContext
from bot.handlers import ALL_ROUTERS
from bot.middlewares.context_middleware import ContextMiddleware
from bot.middlewares.member_loader import MemberLoaderMiddleware
from bot.schedulers.poll_scheduler import PollScheduler
from bot.schedulers.birthdays import BirthdayScheduler
from bot.services.broadcast import BroadcastService
from bot.services.birthdays import BirthdayService
from bot.services.importer import SheetImporter
from bot.services.polls import PollService
from bot.services.roster import RosterService
from bot.storage.greetings import GreetingsStorage
from bot.storage.members import MembersStorage
from bot.storage.polls import PollsStorage
from bot.storage.sheet_url import SheetUrlStorage
from bot.utils.logging_setup import setup_logging


async def main() -> None:
    root = Path(__file__).resolve().parent
    data_dir = root / "data"
    backups_dir = root / "backups"
    logs_dir = root / "logs"

    config_path = root / "config.txt"
    config = load_config(config_path)

    logger = setup_logging(logs_dir)
    logger.info("Starting VPK bot")

    members_storage = MembersStorage(data_dir / "members.csv", backups_dir / "members")
    polls_storage = PollsStorage(data_dir / "polls.csv", backups_dir / "polls")
    greetings_storage = GreetingsStorage(data_dir / "greetings.txt", backups_dir / "greetings")
    sheet_storage = SheetUrlStorage(root / "sheet_url.txt", backups_dir / "sheet")

    roster_service = RosterService(members_storage)
    poll_service = PollService(polls_storage)
    greeting_service = BirthdayService(roster_service, greetings_storage)
    broadcast_service = BroadcastService(roster_service)
    sheet_importer = SheetImporter(roster_service, sheet_storage)

    tz = pytz.timezone(config.timezone)
    scheduler = AsyncIOScheduler(timezone=tz)

    bot = Bot(token=config.bot_token, parse_mode=ParseMode.HTML)
    dispatcher = Dispatcher()

    poll_scheduler = PollScheduler(
        scheduler=scheduler,
        poll_service=poll_service,
        bot=bot,
        timezone=config.timezone,
        dryrun=config.dryrun,
    )

    birthday_scheduler = BirthdayScheduler(
        scheduler=scheduler,
        service=greeting_service,
        roster=roster_service,
        bot=bot,
        timezone=config.timezone,
        runtime=config.birthdays_time,
        chat_id=config.birthdays_chat_id,
        thread_id=config.birthdays_thread_id,
        dryrun=config.dryrun,
        leap_policy=config.leap_policy,
    )

    context = BotContext(
        bot=bot,
        config=config,
        config_path=config_path,
        logger=logger,
        roster_service=roster_service,
        poll_service=poll_service,
        broadcast_service=broadcast_service,
        sheet_importer=sheet_importer,
        birthday_service=greeting_service,
        poll_scheduler=poll_scheduler,
        birthday_scheduler=birthday_scheduler,
    )

    dispatcher.update.outer_middleware(ContextMiddleware(context))
    dispatcher.message.middleware(MemberLoaderMiddleware())
    dispatcher.callback_query.middleware(MemberLoaderMiddleware())

    for router in ALL_ROUTERS:
        dispatcher.include_router(router)

    await poll_scheduler.refresh()
    await birthday_scheduler.refresh()
    scheduler.start()

    try:
        await dispatcher.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    asyncio.run(main())
