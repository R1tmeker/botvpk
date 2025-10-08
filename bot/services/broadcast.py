from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable, Iterable, Optional

from ..storage.members import Member
from .roster import RosterService


@dataclass
class BroadcastResult:
    member: Member
    success: bool
    error: Optional[str] = None


class BroadcastService:
    def __init__(self, roster: RosterService, limit_per_minute: int = 20):
        self.roster = roster
        self.limit_per_minute = limit_per_minute

    def eligible_members(
        self,
        *,
        department: Optional[str] = None,
        role: Optional[str] = None,
        only_active: bool = True,
    ) -> list[Member]:
        members = self.roster.list_members()
        result: list[Member] = []
        for member in members:
            if only_active and member.status != "active":
                continue
            if not member.tg_user_id:
                continue
            if department and member.department != department:
                continue
            if role and member.role != role:
                continue
            result.append(member)
        return result

    async def broadcast(
        self,
        members: Iterable[Member],
        sender: Callable[[Member], Awaitable[None]],
        *,
        dryrun: bool = False,
    ) -> list[BroadcastResult]:
        delay = 60 / self.limit_per_minute if self.limit_per_minute > 0 else 0
        results: list[BroadcastResult] = []
        for member in members:
            if dryrun:
                results.append(BroadcastResult(member=member, success=True))
                continue
            try:
                await sender(member)
                results.append(BroadcastResult(member=member, success=True))
            except Exception as exc:  # pylint: disable=broad-except
                results.append(BroadcastResult(member=member, success=False, error=str(exc)))
            if delay:
                await asyncio.sleep(delay)
        return results

