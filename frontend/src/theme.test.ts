import { describe, expect, it } from "vitest";

import { isAppTheme, resolveInitialTheme } from "./theme";

describe("theme resolution", () => {
  it("prefers a stored theme over Telegram and system values", () => {
    expect(resolveInitialTheme({ storedTheme: "dark", telegramColorScheme: "light", prefersDark: false })).toBe("dark");
  });

  it("uses Telegram color scheme when there is no stored preference", () => {
    expect(resolveInitialTheme({ storedTheme: null, telegramColorScheme: "dark", prefersDark: false })).toBe("dark");
  });

  it("falls back to system preference and rejects unknown values", () => {
    expect(isAppTheme("contrast")).toBe(false);
    expect(resolveInitialTheme({ storedTheme: "contrast", telegramColorScheme: "system", prefersDark: true })).toBe("dark");
    expect(resolveInitialTheme({ storedTheme: null, telegramColorScheme: null, prefersDark: false })).toBe("light");
  });
});
