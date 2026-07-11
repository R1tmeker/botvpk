from __future__ import annotations

import asyncio
import os

import aiohttp

URL = os.getenv("SSE_URL", "http://127.0.0.1:8082/api/events/stream")
SESSION_COOKIE = os.getenv("VPK_SESSION", "")
CLIENTS = int(os.getenv("SSE_CLIENTS", "200"))


async def connect(session: aiohttp.ClientSession, index: int) -> None:
    async with session.get(URL, timeout=aiohttp.ClientTimeout(total=30)) as response:
        if response.status != 200:
            raise RuntimeError(f"SSE client {index}: HTTP {response.status}")
        first_line = await response.content.readline()
        if not first_line.startswith(b"event: connected"):
            raise RuntimeError(f"SSE client {index}: invalid first event")
        await asyncio.sleep(20)


async def main() -> None:
    if not SESSION_COOKIE:
        raise SystemExit("Set VPK_SESSION to a valid preprod session cookie.")
    cookie_jar = aiohttp.CookieJar()
    cookie_jar.update_cookies({"vpk_session": SESSION_COOKIE})
    async with aiohttp.ClientSession(cookie_jar=cookie_jar) as session:
        await asyncio.gather(*(connect(session, index) for index in range(CLIENTS)))
    print(f"sse_clients={CLIENTS} status=ok")


if __name__ == "__main__":
    asyncio.run(main())
