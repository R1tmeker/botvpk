from __future__ import annotations

import asyncio
import time
from threading import Thread
from pathlib import Path


async def heartbeat_loop(path: str | Path, *, interval_seconds: float = 15.0) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    while True:
        target.write_text(str(time.time()), encoding="utf-8")
        await asyncio.sleep(interval_seconds)


def heartbeat_is_fresh(path: str | Path, *, max_age_seconds: float = 60.0) -> bool:
    target = Path(path)
    if not target.exists():
        return False
    return (time.time() - target.stat().st_mtime) <= max_age_seconds


def start_heartbeat_thread(path: str | Path, *, interval_seconds: float = 15.0) -> Thread:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    def _run() -> None:
        while True:
            target.write_text(str(time.time()), encoding="utf-8")
            time.sleep(interval_seconds)

    thread = Thread(target=_run, name=f"heartbeat:{target}", daemon=True)
    thread.start()
    return thread
