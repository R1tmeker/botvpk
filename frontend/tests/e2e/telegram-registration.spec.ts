import { expect, test } from "@playwright/test";

test("Telegram Mini App logs in automatically and shows newcomer registration", async ({ page }) => {
  let telegramAuthCalls = 0;

  await page.addInitScript(() => {
    const noop = () => undefined;
    Object.defineProperty(window, "Telegram", {
      configurable: true,
      value: {
        WebApp: {
          initData: "query_id=test&user=%7B%22id%22%3A777001%7D&hash=test",
          initDataUnsafe: { user: { id: 777001, first_name: "Новый" } },
          ready: noop,
          expand: noop,
          BackButton: { show: noop, hide: noop, onClick: noop, offClick: noop },
          HapticFeedback: { impactOccurred: noop, notificationOccurred: noop },
        },
      },
    });
  });

  await page.route("http://127.0.0.1:5173/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/telegram") {
      telegramAuthCalls += 1;
      expect(route.request().postDataJSON()).toEqual({
        init_data: "query_id=test&user=%7B%22id%22%3A777001%7D&hash=test",
      });
      await route.fulfill({
        json: {
          authenticated: true,
          app_timezone: "Asia/Novosibirsk",
          profile: {
            id: 77,
            telegram_id: 777001,
            username: null,
            full_name: "Новый участник",
            squad_id: null,
            avatar_file_id: null,
            role_code: "PUBLIC_USER",
            status_code: "ACTIVE",
            birth_date: null,
            phone: null,
            city: null,
            education_place: null,
            version: null,
          },
        },
      });
      return;
    }
    if (path === "/api/public/content") {
      await route.fulfill({ json: { promo_blocks: [], materials: [] } });
      return;
    }
    if (path === "/api/public/events") {
      await route.fulfill({ json: [] });
      return;
    }
    await route.fulfill({ json: [] });
  });

  const initData = "query_id=test&user=%7B%22id%22%3A777001%7D&hash=test";
  await page.goto(`/?tgWebAppData=${encodeURIComponent(initData)}`);

  await expect(page.getByRole("heading", { name: "Вход на сайт" })).toHaveCount(0);
  await expect(page.getByText("Анкета вступления", { exact: true }).first()).toBeVisible();
  await page.getByRole("button", { name: "Заполнить", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Анкета вступления" })).toBeVisible();
  await expect(page.getByText("ФИО *", { exact: true })).toBeVisible();
  expect(telegramAuthCalls).toBe(1);
});
