import { expect, test } from "@playwright/test";
import { mockApp } from "./fixtures/app";

test.use({ locale: "ru-RU", timezoneId: "America/New_York" });

for (const theme of ["dark", "light"]) {
  test(`announcement clears after photo send and blocks repeated clicks ${theme}`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await mockApp(page, "SUPER_ADMIN", theme);
    const payloads: Record<string, unknown>[] = [];
    let sent = 0;
    let release!: () => void;
    const blocked = new Promise<void>((resolve) => { release = resolve; });
    await page.route("**/api/files/upload", (route) => route.fulfill({ json: { id: 42, original_name: "long-photo-attachment-name.png" } }));
    await page.route("**/api/announcements**", async (route) => {
      if (route.request().method() === "GET") return route.fulfill({ json: payloads.length && sent ? [{ id: 8, ...payloads[0], status_code: "SENT" }] : [] });
      if (route.request().url().endsWith("/send")) { sent++; return route.fulfill({ json: { detail: "Queued" } }); }
      payloads.push(route.request().postDataJSON());
      await blocked;
      await route.fulfill({ json: { id: 8, ...payloads[0] } });
    });
    await page.goto("/announcements");
    await page.getByLabel("Заголовок", { exact: true }).fill("Проверка объявления");
    await page.getByLabel("Текст", { exact: true }).fill("Текст с фотографией");
    await page.locator('input[type="file"]').setInputFiles({ name: "photo.png", mimeType: "image/png", buffer: Buffer.from("photo") });
    await expect(page.getByText("long-photo-attachment-name.png")).toBeVisible();
    const submit = page.getByRole("button", { name: "Отправить объявление", exact: true });
    await submit.evaluate((button: HTMLButtonElement) => { button.click(); button.click(); });
    await expect.poll(() => payloads.length).toBe(1);
    await expect(page.getByRole("button", { name: "Отправляем...", exact: true })).toBeDisabled();
    release();
    await expect(page.getByRole("status").filter({ hasText: "Можно создать новое" })).toBeVisible();
    await expect(page.getByLabel("Заголовок", { exact: true })).toHaveValue("");
    await expect(page.getByLabel("Текст", { exact: true })).toHaveValue("");
    await expect(page.getByText("long-photo-attachment-name.png")).toHaveCount(0);
    await expect(submit).toBeDisabled();
    expect(payloads[0].file_id).toBe(42);
    expect(payloads[0].client_request_id).toMatch(/^[a-f0-9-]{36}$/);
    expect(sent).toBe(1);
  });
}

test("announcement retry preserves draft and uses the same request identifier", async ({ page }) => {
  await mockApp(page, "SUPER_ADMIN", "dark");
  const ids: string[] = [];
  let sends = 0;
  await page.route("**/api/announcements**", (route) => {
    if (route.request().method() === "GET") return route.fulfill({ json: [] });
    if (route.request().url().endsWith("/send")) return route.fulfill({ status: ++sends === 1 ? 503 : 200, json: { detail: "Delivery" } });
    const payload = route.request().postDataJSON();
    ids.push(payload.client_request_id);
    return route.fulfill({ json: { id: 9, ...payload } });
  });
  await page.goto("/announcements");
  await page.getByLabel("Заголовок", { exact: true }).fill("Сохранённый черновик");
  await page.getByLabel("Текст", { exact: true }).fill("Сохранённый текст");
  const submit = page.getByRole("button", { name: "Отправить объявление", exact: true });
  await submit.click();
  await expect(page.getByRole("status").filter({ hasText: "Данные сохранены" })).toBeVisible();
  await expect(page.getByLabel("Заголовок", { exact: true })).toHaveValue("Сохранённый черновик");
  await submit.click();
  await expect(page.getByRole("status").filter({ hasText: "Можно создать новое" })).toBeVisible();
  expect(ids).toHaveLength(2);
  expect(ids[0]).toBe(ids[1]);
});

for (const width of [320, 390]) {
  test(`template chooses weekdays, previews, creates and edits at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 844 });
    await mockApp(page, "SUPER_ADMIN", "dark");
    let templates: Record<string, unknown>[] = [];
    let created = 0, updated = 0;
    await page.route("**/api/schedule/templates**", async (route) => {
      const request = route.request(), url = new URL(request.url());
      if (request.method() === "GET") return route.fulfill({ json: templates });
      const payload = request.postDataJSON();
      if (url.pathname.endsWith("/preview")) {
        expect(payload.week_days).toBe("1,3");
        return route.fulfill({ json: { dates: ["2026-10-12", "2026-10-14"], days: 60, timezone: "Asia/Barnaul" } });
      }
      if (request.method() === "POST") { created++; expect(url.searchParams.get("generate_days")).toBe("60"); }
      else { updated++; expect(url.searchParams.get("apply_to_future")).toBe("true"); }
      templates = [{ id: 5, ...payload, start_time: `${payload.start_time}:00`, sync_summary: { created: created === 1 && !updated ? 2 : 0, updated, cancelled: 0, preserved: 0 } }];
      return route.fulfill({ json: templates[0] });
    });
    await page.goto("/admin");
    await page.getByRole("button", { name: "Расписание", exact: true }).click();
    const title = page.getByLabel("Название шаблона *", { exact: true });
    await title.fill("Строевая подготовка");
    const create = page.getByRole("button", { name: "Создать шаблон и занятия" });
    await expect(create).toBeDisabled();
    await page.getByRole("button", { name: "Понедельник", exact: true }).click();
    await page.getByRole("button", { name: "Среда", exact: true }).click();
    await expect(page.getByRole("button", { name: "Среда", exact: true })).toHaveAttribute("aria-pressed", "true");
    const colors = await page.locator('[class*="weekdayGrid"] button').evaluateAll((buttons) => buttons.map((button) => ({ color: getComputedStyle(button).backgroundColor, wraps: button.scrollWidth > button.clientWidth })));
    expect(colors[0].color).not.toBe(colors[1].color);
    expect(colors.some((item) => item.wraps)).toBe(false);
    await page.getByRole("button", { name: "Показать даты занятий" }).click();
    await expect(page.getByText("По шаблону: 2 занятий")).toBeVisible();
    await create.click();
    await expect(title).toHaveValue("");
    await expect(page.getByText("Пн, Ср · 16:00", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Редактировать шаблон" }).click();
    await expect(title).toHaveValue("Строевая подготовка");
    await expect(page.getByRole("button", { name: "Понедельник", exact: true })).toHaveAttribute("aria-pressed", "true");
    await title.fill("Подготовка обновлена");
    await page.getByLabel("Начало занятия *", { exact: true }).fill("17:00");
    await page.getByRole("button", { name: "Показать даты занятий" }).click();
    await page.getByRole("button", { name: "Сохранить изменения", exact: true }).click();
    await expect(page.getByText("Пн, Ср · 17:00", { exact: true })).toBeVisible();
    expect(created).toBe(1); expect(updated).toBe(1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
    await page.getByRole("button", { name: "Редактировать шаблон" }).click();
    await page.locator('[class*="templateDays"]').screenshot({ path: info.outputPath("weekday-picker.png") });
    await page.screenshot({ path: info.outputPath("schedule-editor.png"), fullPage: true });
  });
}

test("participant can open an announcement and its attachment without composer controls", async ({ page }) => {
  await mockApp(page, "PARTICIPANT", "dark");
  const body = "Полное объявление с вложением. ".repeat(20);
  await page.route("**/api/announcements**", (route) => route.fulfill({ json: [{ id: 4, title: "Сообщение клуба", body, status_code: "SENT", file_id: 42 }] }));
  await page.goto("/announcements?id=4");
  await expect(page.locator("#announcement-4")).toBeFocused();
  await expect(page.getByText(body, { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Открыть вложение" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Отправить объявление" })).toHaveCount(0);
});
