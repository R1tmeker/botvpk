import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { mockApp, user } from "./fixtures/app";

test.use({ locale: "ru-RU", timezoneId: "America/New_York" });

const catalog = [
  [99, "Архивная тренировка", "2025-06-01T10:00:00Z"],
  [98, "Завершённое занятие недели", "2026-10-06T10:00:00Z"],
  [1, "Занятие этой недели", "2026-10-09T10:00:00Z"],
  [2, "Занятие следующей недели", "2026-10-12T10:00:00Z"],
  [3, "Занятие следующего месяца", "2026-11-02T10:00:00Z"],
].map(([id, title, start_datetime]) => ({
  id, title, start_datetime, end_datetime: null, status_code: "PLANNED",
  squad_id: null, requires_response: true, self_checkin_enabled: false,
}));
const history = [{ id: 7, event_id: 99, user_id: 1, status_code: "PRESENT",
  event_title: "Архивная тренировка", event_start_datetime: "2025-06-01T10:00:00Z",
  marked_at: "2026-10-08T10:00:00Z" }];

async function setup(page: Page, theme = "dark") {
  await page.clock.setFixedTime(new Date("2026-10-08T12:00:00Z"));
  await mockApp(page, "SUPER_ADMIN", theme);
  await page.route("**/api/schedule", (route) => route.fulfill({ json: catalog }));
  await page.route("**/api/attendance/my?**", (route) => route.fulfill({ json: history }));
  await page.route("**/api/attendance/streak/my", (route) => route.fulfill({ json: {
    current_streak: 2, best_streak: 2, total_events: 2, present_count: 2, percent: 100,
  } }));
  await page.route("**/api/admin/audit?**", (route) => route.fulfill({ json: [{
    id: 1, action_code: "schedule.event.update", entity_name: "schedule_events",
    entity_id: 99, user_id: 1, created_at: "2026-10-08T12:00:00Z", new_value: { title: "Название занятия" },
  }] }));
  await page.route("**/api/admin/settings", (route) => route.fulfill({ json: [
    { key: "birthday_enabled", value: "true" }, { key: "birthday_time", value: "09:00" },
    { key: "schedule_week_a_start", value: "2026-06-01" },
  ] }));
  await page.route("**/api/admin/users?**", (route) => route.fulfill({ json: Array.from({ length: 13 }, (_, index) => ({ ...user, id: index + 1 })) }));
}

async function contained(page: Page) {
  const failures = await page.locator('main input:not([type="hidden"]), main select, main textarea').evaluateAll((items) => items.flatMap((item) => {
    const rect = item.getBoundingClientRect();
    const panel = item.closest('[class*="_panel_"]')?.getBoundingClientRect();
    if (!rect.width || !panel) return [];
    return rect.right > panel.right + 1 || rect.left < panel.left - 1 ? [item.outerHTML] : [];
  }));
  expect(failures).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
}

async function contrast(page: Page, selector: string) {
  const results = await new AxeBuilder({ page }).include(selector).withRules(["color-contrast"]).analyze();
  expect(results.violations.map((item) => ({ id: item.id, nodes: item.nodes.map((node) => ({ html: node.html, summary: node.failureSummary })) }))).toEqual([]);
}

for (const theme of ["dark", "light"]) {
  for (const width of [320, 390, 768]) {
    test(`reported visual defects ${theme} ${width}px`, async ({ page }, info) => {
      test.setTimeout(90_000);
      await page.setViewportSize({ width, height: 844 });
      await setup(page, theme);
      const capture = async (name: string) => {
        if (width === 390 && theme === "dark") await page.screenshot({ path: info.outputPath(`${name}.png`), fullPage: true });
      };
      await page.goto("/schedule");
      await expect(page.getByText("Тип 1", { exact: true })).toBeVisible();
      await contrast(page, '[class*="weekBadge"] b, [class*="_row_"] strong');
      await capture("schedule");

      await page.goto("/attendance");
      await page.getByRole("button", { name: "История", exact: true }).click();
      await expect(page.getByText("Архивная тренировка", { exact: true })).toBeVisible();
      await expect(page.getByText("Присутствовал · 01.06.2025, 17:00", { exact: true })).toBeVisible();
      await contrast(page, '[class*="_row_"] strong, [class*="_row_"] span');
      await capture("history");

      await page.goto("/profile");
      await expect(page.locator('[class*="streakBadge"] strong')).toBeVisible();
      await contrast(page, '[class*="streakBadge"] strong, [class*="rosterTable"] a');
      await capture("profile");

      await page.goto("/notifications");
      await expect(page.getByText("Обновление расписания занятий", { exact: true })).toBeVisible();
      await contrast(page, '[class*="_row_"] strong');
      await capture("notifications");

      await page.goto("/admin");
      await page.getByRole("button", { name: "Логи", exact: true }).click();
      await expect(page.getByText("schedule.event.update", { exact: true })).toBeVisible();
      await contained(page);
      await contrast(page, '[class*="_row_"] strong, [class*="adminTabGroups"] strong');
      if (theme === "dark") expect(await page.locator('section[data-system="true"]').evaluate((item) => getComputedStyle(item).backgroundColor)).not.toBe("rgb(238, 243, 251)");
      await capture("logs");

      await page.getByRole("button", { name: "Настройки", exact: true }).click();
      const checked = page.getByRole("checkbox", { name: "Включить поздравления" });
      await expect(checked).toBeChecked();
      const colors = await checked.evaluate((item) => ({ fill: getComputedStyle(item).backgroundColor, tick: getComputedStyle(item, "::after").borderBottomColor }));
      expect(colors.fill).not.toBe(colors.tick);
      await expect(page.getByLabel("Время отправки (HH:MM)")).toHaveAttribute("type", "time");
      await contained(page);
      await contrast(page, '[class*="tokenBar"] button');
      await capture("settings");

      await page.getByRole("button", { name: "Заявки", exact: true }).click();
      const counts = page.locator('[class*="pipelineStageCount"]');
      await expect(counts).toHaveCount(4);
      for (const count of await counts.all()) expect((await count.boundingBox())!.width).toBeGreaterThanOrEqual(24);
      await contrast(page, '[class*="pipelineStageCount"]');
      await capture("applications");

      await page.getByRole("button", { name: "События канд.", exact: true }).click();
      await expect(page.getByLabel("Название события для кандидатов")).toBeVisible();
      await contained(page);
      await capture("candidate-event");
    });
  }
}

test("schedule uses calendar periods, retains completed classes, and opens the full archive", async ({ page }) => {
  await setup(page);
  await page.goto("/schedule");
  await expect(page.locator("#event-98")).toBeVisible();
  expect((await page.locator("#event-98 > span").boundingBox())!.width).toBeGreaterThan(100);
  await expect(page.getByText("Занятие этой недели", { exact: true })).toBeVisible();
  await expect(page.getByText("Занятие следующей недели", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Следующая неделя" }).click();
  await expect(page.getByText("Занятие следующей недели", { exact: true })).toBeVisible();
  await expect(page.getByText("Занятие этой недели", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Месяц", exact: true }).click();
  await expect(page.getByText("Занятие следующей недели", { exact: true })).toBeVisible();
  await expect(page.getByText("Занятие следующего месяца", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Следующий месяц" }).click();
  await expect(page.getByText("Занятие следующего месяца", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Архив", exact: true }).click();
  await expect(page.locator("#event-99")).toBeVisible();
});

test("journal waits for existing marks and submits only changes without hiding other people", async ({ page }) => {
  await setup(page);
  const existing = [1, 2].map((id) => ({ id, event_id: 99, user_id: id, status_code: "PRESENT" }));
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  await page.route("**/api/attendance/events/99?**", async (route) => { await gate; await route.fulfill({ json: existing }); });
  await page.route("**/api/attendance/events/99/bulk", async (route) => {
    expect(route.request().postDataJSON()).toEqual({ items: [{ user_id: 2, status_code: "ABSENT" }] });
    existing[1].status_code = "ABSENT";
    await route.fulfill({ json: [existing[1]] });
  });
  await page.goto("/attendance");
  await page.getByRole("button", { name: "Журнал", exact: true }).click();
  await page.getByLabel("Событие для отметки посещаемости").selectOption("99");
  const save = page.getByRole("button", { name: "Сохранить отметки", exact: true });
  await expect(save).toBeDisabled();
  release();
  const first = page.getByLabel(`Статус явки: ${user.full_name}`);
  const second = page.getByLabel("Статус явки: Иванов Иван Иванович");
  await expect(first).toHaveValue("PRESENT");
  await expect(second).toBeEnabled();
  await second.selectOption("ABSENT");
  await page.getByRole("button", { name: "Сохранить отметки (1)", exact: true }).click();
  await expect(save).toBeDisabled();
  await expect(first).toHaveValue("PRESENT");
  await expect(second).toHaveValue("ABSENT");
});

test("empty journal explains missing events and notification filters can be reset", async ({ page }) => {
  await setup(page);
  await page.route("**/api/schedule", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/notifications?**", (route) => route.fulfill({ json: [] }));
  await page.goto("/attendance");
  await page.getByRole("button", { name: "Журнал", exact: true }).click();
  await expect(page.getByLabel("Событие для отметки посещаемости")).toBeDisabled();
  await expect(page.getByText("Занятий для отметки пока нет. Добавьте занятие в расписание.")).toBeVisible();
  await expect(page.getByText("Выберите событие для отметки", { exact: true })).toHaveCount(0);
  await page.goto("/notifications");
  await page.getByLabel("Поиск по уведомлениям").fill("несуществующее");
  await page.getByRole("button", { name: "Сбросить поиск и категорию" }).click();
  await expect(page.getByLabel("Поиск по уведомлениям")).toHaveValue("");
});

test("candidate date is saved in the club timezone even on a device in another timezone", async ({ page }) => {
  await setup(page);
  await page.route("**/api/admin/join/events", async (route) => {
    if (route.request().method() === "POST") expect(route.request().postDataJSON().start_datetime).toBe("2026-10-10T13:00:00.000Z");
    await route.fulfill({ json: route.request().method() === "POST" ? { id: 1 } : [] });
  });
  await page.goto("/admin");
  await page.getByRole("button", { name: "События канд.", exact: true }).click();
  await page.getByLabel("Название события для кандидатов").fill("Встреча кандидатов");
  await page.locator('input[type="datetime-local"]').fill("2026-10-10T20:00");
  await page.getByRole("button", { name: "Создать событие для кандидатов", exact: true }).click();
  await expect(page.getByText("Событие создано", { exact: true })).toBeVisible();
});
