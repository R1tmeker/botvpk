import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("commander mobile navigation stays accessible with 44px touch targets", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.setViewportSize({ width: 320, height: 720 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.addInitScript(() => localStorage.setItem("vpk_theme", "dark"));
  await page.route("http://127.0.0.1:5173/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/session") {
      await route.fulfill({
        json: {
          authenticated: true,
          app_timezone: "Asia/Novosibirsk",
          profile: {
            id: 1,
            telegram_id: 990000001,
            username: "commander",
            full_name: "Тестовый Командир",
            squad_id: 1,
            avatar_file_id: null,
            role_code: "SQUAD_COMMANDER",
            status_code: "ACTIVE",
            birth_date: null,
            phone: null,
            city: null,
            education_place: null,
            version: "2026-07-14T00:00:00Z",
          },
        },
      });
      return;
    }
    if (path === "/api/events/stream") {
      await route.fulfill({ status: 200, contentType: "text/event-stream", body: "event: connected\ndata: {}\n\n" });
      return;
    }
    if (path === "/api/attendance/stats/my") {
      await route.fulfill({ json: { title: "Моя посещаемость", items: [] } });
      return;
    }
    if (path === "/api/attendance/streak/my") {
      await route.fulfill({ json: { current_streak: 0, best_streak: 0, total_events: 0, present_count: 0, percent: 0 } });
      return;
    }
    if (path === "/api/dashboard/bootstrap") {
      await route.fulfill({ json: { settings: [], promo: [], action_items: [] } });
      return;
    }
    if (path === "/api/me/progress") {
      await route.fulfill({
        json: {
          attendance_percent: 0,
          attendance_total: 0,
          normatives_accepted: 0,
          current_streak: 0,
          periods: [],
          achievements: [],
        },
      });
      return;
    }
    await route.fulfill({ json: [] });
  });

  await page.goto("/");
  const navigation = page.getByRole("navigation", { name: "Основная навигация" });
  await expect(navigation).toBeVisible();

  const destinations = [
    ["Главная", "/"],
    ["План", "/schedule"],
    ["Явка", "/attendance"],
    ["Нормы", "/normatives"],
    ["Ещё", "/profile"],
  ] as const;
  for (const [label, path] of destinations) {
    const button = navigation.getByRole("button", { name: label });
    const box = await button.boundingBox();
    expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
    expect(box?.width ?? 0).toBeGreaterThanOrEqual(44);
    await button.click();
    await expect(page).toHaveURL(new RegExp(`${path === "/" ? "/$" : `${path}$`}`));
    await page.waitForTimeout(100);
    const accessibility = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
    expect(accessibility.violations.filter((item) => ["critical", "serious"].includes(item.impact ?? ""))).toEqual([]);
    expect(pageErrors).toEqual([]);
  }
});
