import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const roles = [
  ["PARTICIPANT", "Участник"],
  ["SQUAD_COMMANDER", "Командир отделения"],
  ["ADMIN", "Администратор"],
] as const;
const viewports = [
  { width: 320, height: 720 },
  { width: 390, height: 844 },
  { width: 768, height: 1024 },
  { width: 1280, height: 900 },
];

for (const [roleCode, roleLabel] of roles) {
  for (const theme of ["light", "dark"] as const) {
    for (const viewport of viewports) {
      test(`${roleCode} ${theme} ${viewport.width}px dashboard`, async ({ page }) => {
        const pageErrors: string[] = [];
        const initialApiRequests: string[] = [];
        page.on("pageerror", (error) => pageErrors.push(error.message));
        await page.setViewportSize(viewport);
        await page.emulateMedia({ reducedMotion: "reduce" });
        await page.addInitScript((selectedTheme) => localStorage.setItem("vpk_theme", selectedTheme), theme);
        await page.route("http://127.0.0.1:5173/api/**", async (route) => {
          const path = new URL(route.request().url()).pathname;
          initialApiRequests.push(path);
          if (path === "/api/auth/session") {
            await route.fulfill({
              json: {
                authenticated: true,
                app_timezone: "Asia/Novosibirsk",
                profile: {
                  id: 1,
                  telegram_id: 990000001,
                  username: "test_user",
                  full_name: "Тестовый Пользователь",
                  squad_id: 1,
                  avatar_file_id: null,
                  role_code: roleCode,
                  status_code: "ACTIVE",
                  birth_date: null,
                  phone: null,
                  city: null,
                  education_place: null,
                  version: "2026-07-10T00:00:00Z",
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
          await route.fulfill({ json: [] });
        });

        await page.goto("/");
        await expect.poll(() => pageErrors).toEqual([]);
        await expect(page.getByText(roleLabel, { exact: true }).first()).toBeVisible();
        await expect(page.getByRole("navigation", { name: "Основная навигация" })).toBeVisible();
        await page.waitForTimeout(500);
        expect(initialApiRequests.length, initialApiRequests.join("\n")).toBeLessThanOrEqual(8);
        await expect(page.locator("body")).toHaveCSS("overflow-x", "hidden");
        const accessibility = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
        expect(accessibility.violations.filter((item) => ["critical", "serious"].includes(item.impact ?? ""))).toEqual([]);
      });
    }
  }
}
