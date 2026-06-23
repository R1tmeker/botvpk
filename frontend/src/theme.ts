export type AppTheme = "light" | "dark";

const STORAGE_KEY = "vpk_theme";

export function isAppTheme(value: unknown): value is AppTheme {
  return value === "light" || value === "dark";
}

export function resolveInitialTheme(options: {
  storedTheme?: string | null;
  telegramColorScheme?: string | null;
  prefersDark?: boolean;
}): AppTheme {
  if (isAppTheme(options.storedTheme)) {
    return options.storedTheme;
  }
  if (isAppTheme(options.telegramColorScheme)) {
    return options.telegramColorScheme;
  }
  return options.prefersDark ? "dark" : "light";
}

export function readStoredTheme(): AppTheme | null {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return isAppTheme(value) ? value : null;
  } catch {
    return null;
  }
}

export function applyTheme(theme: AppTheme) {
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
}

export function saveTheme(theme: AppTheme) {
  try {
    window.localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // Theme persistence is an enhancement; applying it for this session is enough.
  }
  applyTheme(theme);
}

export function applyInitialTheme(telegramColorScheme?: string | null) {
  const prefersDark =
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches;
  applyTheme(
    resolveInitialTheme({
      storedTheme: readStoredTheme(),
      telegramColorScheme,
      prefersDark,
    }),
  );
}
