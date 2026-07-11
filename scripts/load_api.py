from __future__ import annotations

import asyncio
import os
import statistics
import time

import httpx

BASE_URL = os.getenv("APP_URL", "http://127.0.0.1:8082")
SESSION_COOKIE = os.getenv("VPK_SESSION", "")
RATE = int(os.getenv("LOAD_RPS", "20"))
DURATION = int(os.getenv("LOAD_DURATION_SECONDS", "60"))


async def main() -> None:
    latencies: list[float] = []
    failures = 0
    cookies = {"vpk_session": SESSION_COOKIE} if SESSION_COOKIE else None
    async with httpx.AsyncClient(base_url=BASE_URL, cookies=cookies, timeout=5) as client:
        started = time.perf_counter()
        while time.perf_counter() - started < DURATION:
            batch_started = time.perf_counter()
            responses = await asyncio.gather(
                *(client.get("/api/schedule/today") for _ in range(RATE)),
                return_exceptions=True,
            )
            for response in responses:
                if isinstance(response, Exception) or response.status_code >= 500:
                    failures += 1
                elif response.status_code < 400:
                    latencies.append(response.elapsed.total_seconds() * 1000)
            await asyncio.sleep(max(0, 1 - (time.perf_counter() - batch_started)))
    if not latencies:
        raise SystemExit("No successful requests. Set VPK_SESSION to a valid preprod session cookie.")
    p95 = statistics.quantiles(latencies, n=100)[94]
    error_rate = failures / (len(latencies) + failures)
    print(f"requests={len(latencies) + failures} p95_ms={p95:.1f} error_rate={error_rate:.3%}")
    if p95 >= 300 or error_rate >= 0.01:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
