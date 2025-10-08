from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from aiogram import Bot

from ..services.polls import PollService
from ..storage.polls import Poll


class PollScheduler:
    def __init__(
        self,
        scheduler: AsyncIOScheduler,
        poll_service: PollService,
        bot: Bot,
        timezone: str,
        dryrun: bool,
    ):
        self.scheduler = scheduler
        self.poll_service = poll_service
        self.bot = bot
        self.timezone_name = timezone
        self.dryrun = dryrun
        self.logger = logging.getLogger("vpk_bot.polls")
        self.jobs: Dict[int, str] = {}

    async def refresh(self) -> None:
        for job_id in list(self.jobs.values()):
            job = self.scheduler.get_job(job_id)
            if job:
                job.remove()
        self.jobs.clear()

        for poll in self.poll_service.list_polls():
            if poll.is_active:
                self._schedule_poll(poll)

    def update_settings(self, *, timezone: str | None = None, dryrun: bool | None = None) -> None:
        if timezone:
            self.timezone_name = timezone
        if dryrun is not None:
            self.dryrun = dryrun

    def _schedule_poll(self, poll: Poll) -> None:
        tz = pytz.timezone(self.timezone_name)
        if poll.schedule_type == "weekly":
            trigger = CronTrigger(
                day_of_week=",".join(day.lower() for day in poll.days),
                hour=poll.time_local.hour,
                minute=poll.time_local.minute,
                timezone=tz,
            )
        elif poll.schedule_type == "daily":
            trigger = CronTrigger(
                hour=poll.time_local.hour,
                minute=poll.time_local.minute,
                timezone=tz,
            )
        elif poll.schedule_type == "once":
            run_date = self._next_run_for_once(poll, tz)
            trigger = DateTrigger(run_date=run_date)
        else:
            self.logger.warning("Unknown schedule type for poll %s", poll.poll_id)
            return

        job = self.scheduler.add_job(
            self._send_poll,
            trigger=trigger,
            args=[poll.poll_id],
            id=f"poll_{poll.poll_id}",
            replace_existing=True,
        )
        self.jobs[poll.poll_id] = job.id
        self.logger.info("Scheduled poll %s with trigger %s", poll.poll_id, trigger)

    def _next_run_for_once(self, poll: Poll, tz: pytz.BaseTzInfo) -> datetime:
        now = datetime.now(tz)
        candidate = tz.localize(datetime.combine(now.date(), poll.time_local))
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate

    async def _send_poll(self, poll_id: int) -> None:
        poll = self.poll_service.get_poll(poll_id)
        if not poll or not poll.is_active:
            self.logger.info("Poll %s is inactive, skip.", poll_id)
            return

        if self.dryrun:
            self.logger.info("DRYRUN: would send poll %s to chat %s", poll_id, poll.target_chat_id)
        else:
            try:
                await self.bot.send_poll(
                    chat_id=poll.target_chat_id,
                    question=poll.question,
                    options=poll.options,
                    is_anonymous=poll.is_anonymous,
                    allows_multiple_answers=poll.allows_multiple_answers,
                    message_thread_id=poll.message_thread_id,
                )
                self.logger.info("Poll %s sent", poll_id)
            except Exception as exc:  # pylint: disable=broad-except
                self.logger.exception("Failed to send poll %s: %s", poll_id, exc)

        if poll.schedule_type == "once":
            self.poll_service.toggle_poll(poll_id, False)
            await self.refresh()

