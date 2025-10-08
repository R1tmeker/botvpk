from __future__ import annotations

import logging
from datetime import datetime, time

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiogram import Bot

from ..services.birthdays import BirthdayService
from ..services.roster import RosterService


class BirthdayScheduler:
    def __init__(
        self,
        scheduler: AsyncIOScheduler,
        service: BirthdayService,
        roster: RosterService,
        bot: Bot,
        timezone: str,
        runtime: time,
        chat_id: int | None,
        thread_id: int | None,
        dryrun: bool,
        leap_policy: str,
    ):
        self.scheduler = scheduler
        self.service = service
        self.roster = roster
        self.bot = bot
        self.timezone_name = timezone
        self.runtime = runtime
        self.chat_id = chat_id
        self.thread_id = thread_id
        self.dryrun = dryrun
        self.leap_policy = leap_policy
        self.logger = logging.getLogger("vpk_bot.birthdays")
        self.job_id = "birthdays_job"

    async def refresh(self) -> None:
        job = self.scheduler.get_job(self.job_id)
        if job:
            job.remove()
        tz = pytz.timezone(self.timezone_name)
        trigger = CronTrigger(
            hour=self.runtime.hour,
            minute=self.runtime.minute,
            timezone=tz,
        )
        self.scheduler.add_job(
            self._run,
            trigger=trigger,
            id=self.job_id,
            replace_existing=True,
        )
        self.logger.info(
            "Birthday job scheduled at %02d:%02d %s",
            self.runtime.hour,
            self.runtime.minute,
            self.timezone_name,
        )

    def update_settings(
        self,
        *,
        timezone: str | None = None,
        runtime: time | None = None,
        chat_id: int | None = None,
        thread_id: int | None = None,
        dryrun: bool | None = None,
        leap_policy: str | None = None,
    ) -> None:
        if timezone:
            self.timezone_name = timezone
        if runtime:
            self.runtime = runtime
        if chat_id is not None:
            self.chat_id = chat_id
        if thread_id is not None:
            self.thread_id = thread_id
        if dryrun is not None:
            self.dryrun = dryrun
        if leap_policy:
            self.leap_policy = leap_policy

    async def _run(self) -> None:
        tz = pytz.timezone(self.timezone_name)
        today = datetime.now(tz).date()
        members = self.roster.birthdays_on_date(today, self.leap_policy)
        if not members:
            self.logger.debug("No birthdays today.")
            return
        if not self.chat_id:
            self.logger.warning("Birthdays chat is not configured.")
            return
        messages = self.service.build_messages(members)
        if not messages:
            self.logger.warning("No greetings templates available.")
            return
        text = "\n".join(messages)
        if self.dryrun:
            self.logger.info("DRYRUN birthdays message:\n%s", text)
            return
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                message_thread_id=self.thread_id,
            )
            self.logger.info("Birthday message sent to chat %s", self.chat_id)
        except Exception as exc:  # pylint: disable=broad-except
            self.logger.exception("Failed to send birthday message: %s", exc)
