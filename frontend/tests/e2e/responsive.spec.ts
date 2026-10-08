import { expect, test, type Page } from "@playwright/test";

const longName = "Константинопольский Владислав Владимирович";
const description = "Подготовка участников, расписание занятий и важные сведения для командования. ".repeat(5);
const user = {
  id: 1, telegram_id: 990000001, username: "long_username_for_testing",
  full_name: longName, squad_id: 1, avatar_file_id: null,
  role_code: "PARTICIPANT", status_code: "ACTIVE", birth_date: "2006-04-11",
  phone: "+79990001122", city: "Барнаул", education_place: "1ИСП-42",
  version: "2026-10-08T00:00:00Z",
};
const squad = { id: 1, name: "Первое учебное отделение с длинным названием", commander_id: 1 };
const events = [1, 2, 3].map((id) => ({
  id, title: `Занятие ${id}: подготовка участников военно-патриотического клуба`,
  description, start_datetime: new Date(Date.now() + 86400000 * id).toISOString(),
  end_datetime: null, place: "Учебный корпус, кабинет 123", status_code: "PLANNED",
  type_code: "TRAINING", squad_id: null, requires_response: true,
  my_response_code: null, self_checkin_enabled: false,
}));

async function mockApp(page: Page, role: string, theme: string) {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.addInitScript((value) => localStorage.setItem("vpk_theme", value), theme);
  await page.route("http://127.0.0.1:5173/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api/, "");
    let json: unknown = [];
    if (path === "/auth/session") json = { authenticated: true, app_timezone: "Asia/Barnaul", profile: { ...user, role_code: role } };
    else if (path === "/events/stream") {
      await route.fulfill({ contentType: "text/event-stream", body: "event: connected\ndata: {}\n\n" }); return;
    } else if (path === "/dashboard/bootstrap") json = { settings: [], promo: [], action_items: [] };
    else if (path === "/schedule" || path === "/admin/schedule") json = events;
    else if (path === "/schedule/current-week-type") json = { parity: "A", week_a_start: "2026-10-05" };
    else if (path === "/users" || path === "/admin/users") json = [user, { ...user, id: 2, telegram_id: 990000002, full_name: "Иванов Иван Иванович", username: null }];
    else if (path === "/squads" || path === "/admin/squads") json = [squad];
    else if (path === "/squads/my") json = { squad, members: [user] };
    else if (path === "/attendance/stats/my" || path.startsWith("/reports/")) json = { title: "Посещаемость", items: [{ status_code: "PRESENT", count: 12 }, { status_code: "ABSENT", count: 3 }] };
    else if (path === "/attendance/streak/my") json = { current_streak: 0, best_streak: 3, total_events: 15, present_count: 12, percent: 80 };
    else if (path === "/attendance/my") json = [{ id: 1, event_id: 1, user_id: 1, status_code: "PRESENT", marked_at: "2026-10-07T12:00:00Z" }];
    else if (path === "/normatives" || path === "/admin/normatives") json = [1, 2].map((id) => ({ id, title: `Норматив ${id}: физическая подготовка участников`, description, is_active: true, deadline_at: null, type_code: "VIDEO", instruction_video_url: "https://www.youtube.com/watch?v=dQw4w9WgXcQ" }));
    else if (path === "/notifications/summary") json = { total: 1, unread: 1 };
    else if (path === "/notifications") json = [{ id: 1, title: "Обновление расписания занятий", body: description, type_code: "INFO", is_read: false, created_at: "2026-10-08T00:00:00Z" }];
    else if (path === "/announcements") json = [{ id: 1, title: "Объявление для участников клуба", body: description, status_code: "PUBLISHED", created_at: "2026-10-08T00:00:00Z", author_name: longName }];
    else if (path === "/learning/materials") json = [{ id: 1, title: "Учебный материал с длинным названием", description, type_code: "TEXT", is_active: true, is_viewed: false, course_id: null }];
    else if (path === "/me/progress") json = { attendance_percent: 80, attendance_total: 15, normatives_accepted: 0, current_streak: 0, periods: [], achievements: [] };
    else if (path === "/join/me") json = null;
    await route.fulfill({ json });
  });
}

test("appeal reply survives a failed request and clears only after success", async ({ page }) => {
  await mockApp(page, "PARTICIPANT", "light");
  const appeal = { id: 7, author_user_id: 1, subject: "Ошибка посещаемости", description: "Прошу проверить отметку", category_code: "ATTENDANCE_ERROR", urgency_code: "NORMAL", status_code: "CREATED", created_at: "2026-10-08T00:00:00Z" };
  let attempts = 0;
  const thread: Array<{ id: number; appeal_id: number; author_id: number; body: string; created_at: string }> = [];
  await page.route("**/api/appeals", (route) => route.fulfill({ json: [appeal] }));
  await page.route("**/api/appeals/7/messages", async (route) => {
    if (route.request().method() === "POST") {
      attempts += 1;
      if (attempts === 1) { await route.fulfill({ status: 503, json: { detail: "Временно недоступно" } }); return; }
      thread.push({ id: 1, appeal_id: 7, author_id: 1, body: route.request().postDataJSON().body, created_at: new Date().toISOString() });
      await route.fulfill({ status: 201, json: thread[0] });
    } else await route.fulfill({ json: thread });
  });
  await page.goto("/appeals?id=7");
  const composer = page.getByRole("textbox", { name: "Сообщение в обращении" });
  await expect(composer).toBeEnabled();
  const text = "Был на занятии\nПроверьте, пожалуйста";
  await composer.fill(text);
  await page.getByRole("button", { name: "Отправить", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Временно недоступно");
  await expect(composer).toHaveValue(text);
  expect(attempts).toBe(1);
  await page.getByRole("button", { name: "Отправить", exact: true }).click();
  await expect(composer).toHaveValue("");
  await expect(page.getByText(text, { exact: true })).toBeVisible();
  expect(attempts).toBe(2);
});

test("unsent appeal reply survives reloading the conversation", async ({ page }) => {
  await mockApp(page, "PARTICIPANT", "light");
  await page.route("**/api/appeals", (route) => route.fulfill({ json: [{ id: 7, author_user_id: 1, subject: "Вопрос", description: "Подробности", category_code: "OTHER", urgency_code: "NORMAL", status_code: "CREATED", created_at: "2026-10-08T00:00:00Z" }] }));
  await page.goto("/appeals?id=7");
  const composer = page.getByRole("textbox", { name: "Сообщение в обращении" });
  await expect(composer).toBeEnabled();
  await composer.fill("Ответ, который ещё не отправлен");
  await expect(page.getByRole("status").filter({ hasText: "Черновик сохранён" })).toBeVisible();
  await page.reload();
  await expect(composer).toHaveValue("Ответ, который ещё не отправлен");
});

test("notifications load older pages and navigate to a related event", async ({ page }) => {
  await mockApp(page, "PARTICIPANT", "light");
  const inbox = Array.from({ length: 25 }, (_, index) => ({
    id: index + 1, title: `Уведомление ${index + 1}`, body: `Полный текст ${index + 1}`,
    type_code: "SCHEDULE", category_code: "SCHEDULE", is_read: false, is_pinned: false,
    created_at: "2026-10-08T00:00:00Z", deep_link: "/schedule?event=1",
  }));
  await page.route("**/api/notifications?**", async (route) => {
    const params = new URL(route.request().url()).searchParams;
    const offset = Number(params.get("offset") ?? 0);
    await route.fulfill({ json: inbox.slice(offset, offset + Number(params.get("limit") ?? 50)) });
  });
  await page.route("**/api/schedule/events/1", (route) => route.fulfill({ json: events[0] }));
  await page.route("**/api/notifications/*/read", (route) => route.fulfill({ json: { ...inbox[0], is_read: true } }));
  await page.goto("/notifications");
  await expect(page.getByText("Полный текст 1", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Загрузить ещё", exact: true }).click();
  await expect(page.getByText("Уведомление 25", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Открыть", exact: true }).first().click();
  await expect(page).toHaveURL(/\/schedule\?event=1$/);
  await expect(page.locator("#event-1")).toBeFocused();
});

test("selected event responses use one bulk request", async ({ page }) => {
  await mockApp(page, "PARTICIPANT", "light");
  let list: Array<Omit<typeof events[number], "my_response_code"> & { my_response_code: string | null }> = events.map((event) => ({ ...event }));
  await page.route("**/api/schedule?**", (route) => route.fulfill({ json: list }));
  await page.route("**/api/schedule/events/respond-bulk", async (route) => {
    const payload = route.request().postDataJSON();
    expect(payload.event_ids).toEqual([1, 2, 3]);
    expect(payload.response_code).toBe("COMING");
    list = list.map((event) => ({ ...event, my_response_code: "COMING" }));
    await route.fulfill({ json: { event_ids: [1, 2, 3], response_code: "COMING", count: 3 } });
  });
  await page.goto("/schedule");
  await page.getByRole("button", { name: "Выбрать без окончательного ответа" }).click();
  await page.getByRole("button", { name: "Приду на выбранные (3)", exact: true }).click();
  await expect(page.getByRole("button", { name: "Изменить ответ", exact: true })).toHaveCount(3);
});

test("old linked event opens in the archive and receives focus", async ({ page }) => {
  await mockApp(page, "PARTICIPANT", "light");
  await page.route("**/api/schedule/events/99", (route) => route.fulfill({ json: {
    ...events[0], id: 99, title: "Занятие из старого архива", start_datetime: "2025-01-01T10:00:00Z",
  } }));
  await page.goto("/schedule?event=99");
  await expect(page.locator("#event-99")).toBeVisible();
  await expect(page.locator("#event-99")).toBeFocused();
  await expect(page.locator("#event-99").getByRole("button", { name: "Приду", exact: true })).toHaveCount(0);
});

async function expectContained(page: Page) {
  const overflow = await page.evaluate(() => {
    const width = document.documentElement.clientWidth;
    return {
      page: document.documentElement.scrollWidth - width,
      controls: [...document.querySelectorAll<HTMLElement>('main button, main input, main select, main textarea, nav')]
        .filter((element) => {
          const rect = element.getBoundingClientRect();
          if (!rect.width || !rect.height) return false;
          // Explicit local scrollers may have offscreen children by design.
          let parent = element.parentElement;
          while (parent && parent.tagName !== "MAIN") {
            const style = getComputedStyle(parent);
            if (["auto", "scroll"].includes(style.overflowX) && parent.scrollWidth > parent.clientWidth) return false;
            parent = parent.parentElement;
          }
          return rect.left < -1 || rect.right > width + 1;
        }).map((element) => element.outerHTML.slice(0, 200)),
    };
  });
  expect(overflow.page).toBeLessThanOrEqual(1);
  expect(overflow.controls).toEqual([]);
}

const viewports = [
  { width: 320, height: 568 }, { width: 390, height: 844 },
  { width: 844, height: 390 }, { width: 768, height: 1024 },
  { width: 1280, height: 800 }, { width: 1920, height: 1080 },
];
for (const role of ["PARTICIPANT", "SQUAD_COMMANDER", "ADMIN"]) {
  for (const theme of ["light", "dark"]) {
    for (const viewport of viewports) {
      test(`responsive ${role} ${theme} ${viewport.width}x${viewport.height}`, async ({ page }) => {
        test.setTimeout(90_000);
        const errors: string[] = [];
        page.on("pageerror", (error) => errors.push(error.message));
        await page.setViewportSize(viewport);
        await mockApp(page, role, theme);
        const paths = ["/", "/schedule", "/attendance", "/normatives", "/people", "/profile", "/learning", "/notifications", "/appeals"];
        if (role !== "PARTICIPANT") paths.push("/announcements", "/reports");
        if (role === "ADMIN") paths.push("/admin");
        for (const path of paths) {
          await page.goto(path);
          const nav = page.getByRole("navigation", { name: "Основная навигация" });
          await expect(nav).toBeVisible();
          await expect(page.locator("#app-content")).toBeVisible();
          await expect(page.locator('[class*="skeletonCard"]')).toHaveCount(0);
          await expectContained(page);
          const navBox = await nav.boundingBox();
          if (viewport.width >= 1024) {
            expect(navBox!.width).toBeLessThan(220);
            expect(await page.locator("main").evaluate((el) => el.getBoundingClientRect().width)).toBeGreaterThan(1000);
          } else expect(navBox!.y + navBox!.height).toBeGreaterThanOrEqual(viewport.height - 2);
          for (const button of await nav.getByRole("button").all()) {
            const box = await button.boundingBox();
            expect(box!.width).toBeGreaterThanOrEqual(44);
            expect(box!.height).toBeGreaterThanOrEqual(44);
          }
          expect(errors, path).toEqual([]);
        }
        await page.screenshot({ path: test.info().outputPath("responsive.png"), fullPage: true });
      });
    }
  }
}

for (const width of [320, 768, 1280]) {
  test(`member dialog focus, scroll and mobile roster at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 720 });
    await mockApp(page, "ADMIN", "dark");
    await page.goto("/people");
    const nameButton = page.getByRole("button", { name: longName, exact: true });
    await nameButton.click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    const box = (await dialog.boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(width + 1);
    expect(box.y + box.height).toBeLessThanOrEqual(721);
    expect(await page.locator("#root").evaluate((root) => (root as HTMLElement).inert)).toBe(true);
    await page.keyboard.press("Tab");
    await expect(dialog.getByRole("button", { name: "Закрыть" })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(nameButton).toBeFocused();
    expect(await page.locator("#root").evaluate((root) => (root as HTMLElement).inert)).toBe(false);
    if (width < 600) {
      expect(await page.locator('td[data-label="Телефон"]').first().evaluate((el) => getComputedStyle(el).display)).toBe("grid");
    }
  });
}

test("layout changes when the viewport is resized without reloading", async ({ page }) => {
  await mockApp(page, "ADMIN", "light");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  const nav = page.getByRole("navigation", { name: "Основная навигация" });
  await expect(nav).toBeVisible();
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect.poll(async () => (await nav.boundingBox())?.width).toBe(192);
  await expectContained(page);
  await page.setViewportSize({ width: 320, height: 568 });
  await expect.poll(async () => (await nav.boundingBox())?.width).toBe(320);
  await expectContained(page);
});

test("login remains usable on a short mobile viewport and allows zoom", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 400 });
  await page.route("**/api/auth/session", (route) => route.fulfill({ json: { authenticated: false } }));
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Войти", exact: true })).toBeVisible();
  await expectContained(page);
  const viewport = await page.locator('meta[name="viewport"]').getAttribute("content");
  expect(viewport).not.toContain("user-scalable=no");
  expect(viewport).not.toContain("maximum-scale=1");
});

for (const width of [320, 768, 1280]) {
  test(`all administration and profile sections fit at ${width}px`, async ({ page }) => {
    test.setTimeout(90_000);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.setViewportSize({ width, height: 800 });
    await mockApp(page, "SUPER_ADMIN", "dark");
    await page.goto("/admin");
    const tabs = page.locator('[class*="adminTabGroups"] button');
    await expect(tabs.first()).toBeVisible();
    for (let index = 0; index < await tabs.count(); index++) {
      await tabs.nth(index).click();
      await expectContained(page);
      expect(errors).toEqual([]);
    }
    await page.goto("/profile");
    for (const label of ["Данные", "Безопасность", "Интеграции", "Уведомления"]) {
      await page.locator('[class*="tabs"]').first().getByRole("button", { name: label, exact: true }).click();
      await expectContained(page);
      expect(errors).toEqual([]);
    }
  });

  for (const role of ["PUBLIC_USER", "CANDIDATE", "USER_PENDING"]) {
    test(`onboarding ${role} fits at ${width}px`, async ({ page }) => {
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.setViewportSize({ width, height: 720 });
      await mockApp(page, role, "light");
      for (const path of ["/", "/schedule", "/normatives", "/profile"]) {
        await page.goto(path);
        await expect(page.getByRole("navigation", { name: "Основная навигация" })).toBeVisible();
        await expectContained(page);
        expect(errors).toEqual([]);
      }
    });
  }
}

test("learning completion persists and can be reset", async ({ page }) => {
  await mockApp(page, "PARTICIPANT", "light");
  let viewed = false;
  await page.route("**/api/learning/materials", (route) => route.fulfill({ json: [{
    id: 1, title: "Первая помощь", description: "Порядок действий\nПроверка состояния",
    type_code: "TEXT", is_active: true, audience_code: "ALL", course_id: null, is_viewed: viewed,
  }] }));
  await page.route("**/api/learning/materials/1/view", async (route) => {
    viewed = route.request().method() === "POST";
    await route.fulfill({ json: { detail: "Saved" } });
  });
  await page.goto("/learning");
  await page.getByRole("button", { name: "Отметить изученным", exact: true }).click();
  await expect(page.getByText("Изучено 1 из 1 · 100%", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("button", { name: "Снять отметку", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Снять отметку", exact: true }).click();
  await expect(page.getByText("Изучено 0 из 1 · 0%", { exact: true })).toBeVisible();
  await page.getByRole("combobox", { name: "Статус изучения" }).selectOption("viewed");
  await expect(page.getByText("Материалы по выбранным условиям не найдены")).toBeVisible();
});
