import { expect, test } from "@playwright/test";

test("web login exposes password reset flow", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Вход на сайт" })).toBeVisible();
  await expect(page.getByLabel("Telegram ID")).toBeVisible();
  await expect(page.locator('input[autocomplete="current-password"]')).toBeVisible();

  await page.getByRole("button", { name: "Забыли пароль?" }).click();

  await expect(page.getByRole("heading", { name: "Сброс пароля" })).toBeVisible();
  await expect(page.getByLabel("Код из Telegram")).toBeVisible();
  await expect(page.getByLabel("Новый пароль")).toBeVisible();
  await expect(page.getByLabel("Повтор пароля")).toBeVisible();

  await page.getByRole("button", { name: "Вернуться ко входу" }).click();
  await expect(page.getByRole("heading", { name: "Вход на сайт" })).toBeVisible();
});
