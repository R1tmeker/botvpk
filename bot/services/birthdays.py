from __future__ import annotations

import random
from datetime import date
from typing import Iterable

from ..storage.greetings import GreetingsStorage
from ..storage.members import Member
from .roster import RosterService


class BirthdayService:
    def __init__(self, roster: RosterService, greetings: GreetingsStorage):
        self.roster = roster
        self.greetings = greetings

    def birthday_members(self, target_date: date, leap_policy: str) -> list[Member]:
        return self.roster.birthdays_on_date(target_date, leap_policy)

    def build_messages(self, members: Iterable[Member]) -> list[str]:
        greetings = self.greetings.list_greetings()
        if not greetings:
            return []
        templates = greetings.copy()
        messages: list[str] = []
        for member in members:
            if not templates:
                templates = greetings.copy()
            template = random.choice(templates)
            mention = f"@{member.tg_username}" if member.tg_username else member.fio
            messages.append(template.replace("{name}", mention))
        return messages
