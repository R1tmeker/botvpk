type TelegramInitSource = { initData?: string | null };

function launchParam(href: string, name: string): string {
  try {
    const url = new URL(href);
    const direct = url.searchParams.get(name);
    if (direct) return direct;
    const hash = url.hash.replace(/^#/, "");
    return new URLSearchParams(hash.includes("?") ? hash.split("?", 2)[1] : hash).get(name) ?? "";
  } catch {
    return "";
  }
}

export function resolveTelegramInitData(
  sdk: TelegramInitSource,
  href = typeof window === "undefined" ? "" : window.location.href,
  globalSdk: TelegramInitSource | undefined = typeof window === "undefined"
    ? undefined
    : (window as unknown as { Telegram?: { WebApp?: TelegramInitSource } }).Telegram?.WebApp,
): string {
  const launchData = launchParam(href, "tgWebAppData");
  return [sdk.initData, globalSdk?.initData, launchData]
    .map((value) => value?.trim() ?? "")
    .find(Boolean) ?? "";
}

export async function waitForTelegramInitData(
  read: () => string,
  attempts = 16,
  delayMs = 100,
): Promise<string> {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const value = read();
    if (value) return value;
    if (attempt < attempts - 1) {
      await new Promise((resolve) => setTimeout(resolve, delayMs));
    }
  }
  return "";
}
