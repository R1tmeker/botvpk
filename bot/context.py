from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from logging import Logger

from aiogram import Bot

from .config_loader import BotConfig
from .services.broadcast import BroadcastService
from .services.importer import SheetImporter
from .services.polls import PollService
from .services.roster import RosterService
from .services.birthdays import BirthdayService
from .services.attendance import AttendanceService
from .services.notifications import NotificationsService
from .services.normatives import NormativesService
from .schedulers.poll_scheduler import PollScheduler
from .schedulers.birthdays import BirthdayScheduler


@dataclass
class BotContext:
    bot: Bot
    config: BotConfig
    config_path: Path
    logger: Logger
    roster_service: RosterService
    poll_service: PollService
    broadcast_service: BroadcastService
    sheet_importer: SheetImporter
    birthday_service: BirthdayService
    attendance_service: AttendanceService
    notifications_service: NotificationsService
    normatives_service: NormativesService
    poll_scheduler: PollScheduler
    birthday_scheduler: BirthdayScheduler
