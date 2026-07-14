import { describe, expect, it, vi } from "vitest";

import { resolveTelegramInitData, waitForTelegramInitData } from "./telegramLaunch";

describe("Telegram launch authentication", () => {
  it("prefers SDK initData and falls back to Telegram launch parameters", () => {
    expect(resolveTelegramInitData({ initData: " sdk-data " }, "https://app.example/", undefined)).toBe("sdk-data");
    expect(resolveTelegramInitData({}, "https://app.example/?tgWebAppData=query_id%3D1%26hash%3Dabc", undefined))
      .toBe("query_id=1&hash=abc");
  });

  it("waits for asynchronously initialized Telegram SDK", async () => {
    vi.useFakeTimers();
    let reads = 0;
    const pending = waitForTelegramInitData(() => (++reads >= 3 ? "telegram-data" : ""), 4, 10);
    await vi.runAllTimersAsync();
    await expect(pending).resolves.toBe("telegram-data");
    vi.useRealTimers();
  });
});
