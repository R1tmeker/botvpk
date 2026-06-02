// VPK Visual Test - Playwright screenshot for all roles and views
import { chromium } from "playwright";
import { mkdirSync } from "fs";
import { join } from "path";

const BASE = "http://localhost:5173";
const OUT = "C:/Users/vlad-/AppData/Local/Temp/vpk_screenshots";
mkdirSync(OUT, { recursive: true });

const ROLES = [
  { code: "PUBLIC_USER",            level: 0, label: "PUBLIC_USER" },
  { code: "PARTICIPANT",            level: 3, label: "PARTICIPANT" },
  { code: "DEPUTY_SQUAD_COMMANDER", level: 4, label: "DSC" },
  { code: "PLATOON_COMMANDER",      level: 7, label: "PC" },
  { code: "ADMIN",                  level: 8, label: "ADMIN" },
];

function makeProfile(roleCode, level) {
  return {
    id: 1, telegram_id: 795307805, username: "testuser",
    full_name: "Тест Пользователь",
    squad_id: level >= 3 ? 1 : null,
    avatar_file_id: null, role_code: roleCode, status_code: "ACTIVE",
    birth_date: "2000-05-15", phone: "+79001234567",
    city: "Новосибирск", education_place: "НГУ", group_name: null,
  };
}

const now = Date.now();

const MOCK_SCHEDULE = [
  { id: 10, title: "Строевая подготовка", description: "Площадка", start_datetime: new Date(now + 86400000).toISOString(), end_datetime: new Date(now + 90000000).toISOString(), place: "ул. Ленина 1", type_code: "TRAINING", status_code: "SCHEDULED", week_type: "A", squad_id: null, requires_response: true, my_response_code: null, response_deadline: null },
  { id: 11, title: "Огневая подготовка", description: null, start_datetime: new Date(now + 172800000).toISOString(), end_datetime: new Date(now + 176400000).toISOString(), place: "Тир №3", type_code: "TRAINING", status_code: "SCHEDULED", week_type: "B", squad_id: 1, requires_response: true, my_response_code: "COMING", response_deadline: null },
  { id: 12, title: "Физическая подготовка", description: null, start_datetime: new Date(now - 604800000).toISOString(), end_datetime: new Date(now - 601200000).toISOString(), place: "Спортзал", type_code: "TRAINING", status_code: "SCHEDULED", week_type: "A", squad_id: null, requires_response: false, my_response_code: null, response_deadline: null },
];
const MOCK_ATTENDANCE = [
  { id: 1, event_id: 10, status_code: "PRESENT", marked_at: new Date(now - 604800000).toISOString() },
  { id: 2, event_id: 11, status_code: "ABSENT", marked_at: new Date(now - 1209600000).toISOString() },
  { id: 3, event_id: 12, status_code: "PRESENT", marked_at: new Date(now - 1814400000).toISOString() },
];
const MOCK_STATS = { present: 8, absent: 2, late: 0, total: 10, percent: 80, avg_grade: 4.2 };
const MOCK_STREAK = { current_streak: 3, best_streak: 7, total_events: 10, present_count: 8, percent: 80 };
const MOCK_NORMATIVES = [
  { id: 1, title: "Бег 3км", description: "Норматив: < 14:00", deadline_at: new Date(now + 2592000000).toISOString(), type_code: "PHYSICAL", target_audience: "CANDIDATE", squad_id: null, instruction_video_file_id: null, instruction_video_url: null, is_active: true },
  { id: 2, title: "Подтягивания", description: "Мин. 8 раз", deadline_at: new Date(now + 5184000000).toISOString(), type_code: "PHYSICAL", target_audience: "PARTICIPANTS", squad_id: null, instruction_video_file_id: null, instruction_video_url: null, is_active: true },
];
const MOCK_SUBMISSIONS = [
  { id: 1, normative_id: 1, status_code: "ACCEPTED", submitted_at: new Date(now - 259200000).toISOString(), reviewer_comment: "Отлично", grade_value: "5", comment: "13:45", user_id: 1, file_id: null, file_ids: [] },
];
const MOCK_PENDING = [
  { id: 2, normative_id: 2, status_code: "PENDING", submitted_at: new Date(now - 86400000).toISOString(), reviewer_comment: null, grade_value: null, comment: "9 раз", user_id: 2, file_id: null, file_ids: [] },
];
const MOCK_NOTIFICATIONS = [
  { id: 1, title: "Добро пожаловать!", body: "Вы авторизовались", is_read: false, created_at: new Date().toISOString(), type_code: "INFO" },
  { id: 2, title: "Занятие завтра", body: "Строевая в 14:00", is_read: true, created_at: new Date(now - 3600000).toISOString(), type_code: "REMINDER" },
];
const MOCK_ANNOUNCEMENTS = [
  { id: 1, title: "Общее собрание", body: "В пятницу в 18:00", importance_code: "NORMAL", target_type: "ALL", target_squad_id: null, target_role_code: null, file_id: null, send_to_tg: true, send_to_app: true, require_read_confirm: false, status_code: "SENT", sent_at: new Date(now - 86400000).toISOString(), created_at: new Date(now - 86400000).toISOString() },
];
const MOCK_SQUAD = {
  squad: { id: 1, name: "Отделение Альфа", commander_id: 3 },
  members: [
    { id: 1, full_name: "Тест Пользователь", role_code: "PARTICIPANT", status_code: "ACTIVE", username: "testuser" },
    { id: 2, full_name: "Иванов Иван", role_code: "PARTICIPANT", status_code: "ACTIVE", username: null },
    { id: 3, full_name: "Сидоров Сидор", role_code: "SQUAD_COMMANDER", status_code: "ACTIVE", username: "sidorov" },
  ],
};
const MOCK_USERS = [
  { id: 1, telegram_id: 795307805, full_name: "Тест Пользователь", role_code: "PARTICIPANT", status_code: "ACTIVE", username: "testuser", squad_id: 1, birth_date: "2000-05-15", phone: "+79001234567" },
  { id: 2, telegram_id: 795307806, full_name: "Иванов Иван", role_code: "PARTICIPANT", status_code: "ACTIVE", username: null, squad_id: 1, birth_date: null, phone: null },
  { id: 3, telegram_id: 795307807, full_name: "Сидоров Сидор", role_code: "SQUAD_COMMANDER", status_code: "ACTIVE", username: "sidorov", squad_id: 1, birth_date: null, phone: null },
];
const MOCK_SQUADS = [
  { id: 1, name: "Отделение Альфа", commander_id: 3 },
  { id: 2, name: "Отделение Бета", commander_id: null },
];
const MOCK_PROMO = [
  { id: 1, title: "Турнир по стрельбе", body: "Запись до 10 июня!", button_text: "Записаться", button_url: null, action_type_code: "OPEN_FORM", style_code: "PROMO", is_active: true, sort_order: 1 },
];
const MOCK_DASHBOARD_SETTINGS = [
  { code: "next_event", sort_order: 1, is_visible: true },
  { code: "personal_stats", sort_order: 2, is_visible: true },
  { code: "normatives", sort_order: 3, is_visible: true },
  { code: "notifications", sort_order: 4, is_visible: true },
  { code: "commander_summary", sort_order: 5, is_visible: true },
  { code: "promo", sort_order: 6, is_visible: true },
];
const MOCK_ATTENDANCE_REPORT = { items: [
  { user_id: 1, user_name: "Тест Пользователь", present: 8, absent: 2, total: 10, percent: 80 },
  { user_id: 2, user_name: "Иванов Иван", present: 6, absent: 4, total: 10, percent: 60 },
]};
const MOCK_GRADES_REPORT = { items: [
  { user_id: 1, user_name: "Тест Пользователь", avg_score: 4.5, total_submissions: 3 },
]};
const MOCK_NORMATIVES_REPORT = { items: [
  { normative_id: 1, normative_title: "Бег 3км", submitted: 5, accepted: 4, pending: 1, rejected: 0 },
]};
const MOCK_LEARNING = [
  { id: 1, title: "Устав ВС РФ", description: "Основные положения", type_code: "PDF", file_id: 1, mime_type: "application/pdf", is_viewed: false, course_id: 1 },
  { id: 2, title: "Строевой устав", description: "Правила строевой", type_code: "PDF", file_id: 2, mime_type: "application/pdf", is_viewed: true, course_id: 1 },
];
const MOCK_COURSES = [
  { id: 1, title: "Базовая подготовка", description: "Основы ВПК", materials_count: 2 },
];
const MOCK_APPEALS = [
  { id: 1, subject: "Вопрос по расписанию", description: "Уточнить расписание", category_code: "QUESTION", urgency_code: "NORMAL", is_anonymous: false, status_code: "OPEN", created_at: new Date(now - 86400000).toISOString(), user_id: 1 },
];
const MOCK_ACTIVITY_FEED = [
  { type: "response", user_name: "Иванов Иван", event_title: "Строевая", response: "COMING", created_at: new Date(now - 3600000).toISOString() },
  { type: "normative_submission", user_name: "Тест Пользователь", normative_title: "Бег 3км", status: "ACCEPTED", created_at: new Date(now - 7200000).toISOString() },
];
const MOCK_ADMIN_APPLICATIONS = [
  { id: 1, full_name: "Новиков Алексей", status_code: "NEW", created_at: new Date(now - 86400000).toISOString(), phone: "+79001111111", consent_given: true },
];
const MOCK_ADMIN_AUDIT = [
  { id: 1, user_id: 1, user_name: "Тест Пользователь", action_code: "USER_LOGIN", entity_name: "users", entity_id: 1, old_value: null, new_value: "{}", created_at: new Date().toISOString() },
];
const MOCK_ABSENCE_REASONS = [
  { id: 1, label: "Болезнь", is_active: true, requires_comment: false },
  { id: 2, label: "Работа", is_active: true, requires_comment: false },
  { id: 3, label: "Другое", is_active: true, requires_comment: true },
];

function mockJson(body, status = 200) {
  return { status, contentType: "application/json", body: JSON.stringify(body) };
}

// Single catch-all route handler — avoids Playwright glob matching Vite paths
async function setupRoutes(page, roleCode, level) {
  const authResponse = {
    access_token: "mock_token_" + roleCode,
    token_type: "bearer",
    profile: makeProfile(roleCode, level),
    app_timezone: "Asia/Novosibirsk",
  };

  await page.route("**/*", async (route) => {
    const url = route.request().url();
    const method = route.request().method();

    // Only intercept backend API calls
    if (!url.includes("localhost:8000")) {
      return route.continue();
    }

    const path = new URL(url).pathname.replace(/^\/api\//, "").replace(/\/$/, "");

    // Log
    if (process.env.DEBUG) console.log(`  API ${method} /${path}`);

    if (path === "auth/telegram") return route.fulfill(mockJson(authResponse));
    if (path === "menu") return route.fulfill(mockJson([]));

    // Schedule (exact paths from queries.ts)
    if (path === "schedule/current-week-type") return route.fulfill(mockJson({ parity: "A", week_a_start: new Date(now - 86400000).toISOString() }));
    if (path === "schedule/absence-reasons") return route.fulfill(mockJson(MOCK_ABSENCE_REASONS));
    if (path.startsWith("schedule/events/")) return route.fulfill(mockJson([]));
    if (path === "schedule/templates") return route.fulfill(mockJson([]));
    if (path === "schedule") return route.fulfill(mockJson(MOCK_SCHEDULE));

    // Attendance
    if (path === "attendance/stats/my") return route.fulfill(mockJson(MOCK_STATS));
    if (path === "attendance/streak/my") return route.fulfill(mockJson(MOCK_STREAK));
    if (path === "attendance/my") return route.fulfill(mockJson(MOCK_ATTENDANCE));
    if (path.startsWith("attendance/events/")) return route.fulfill(mockJson([]));
    if (path.startsWith("attendance")) return route.fulfill(mockJson([]));

    // Normatives submissions live at /submissions/* (not /normatives/submissions/*)
    if (path === "submissions/my") return route.fulfill(mockJson(MOCK_SUBMISSIONS));
    if (path === "submissions/pending") return route.fulfill(mockJson(MOCK_PENDING));
    if (path.startsWith("submissions/")) return route.fulfill(mockJson([]));

    // Normatives
    if (path === "normatives") return route.fulfill(mockJson(MOCK_NORMATIVES));
    if (path.startsWith("normatives/")) return route.fulfill(mockJson({}));

    if (path === "notifications") return route.fulfill(mockJson(MOCK_NOTIFICATIONS));
    if (path.startsWith("notifications/")) return route.fulfill(mockJson({}));

    if (path === "announcements") return route.fulfill(mockJson(MOCK_ANNOUNCEMENTS));

    if (path === "dashboard/settings") return route.fulfill(mockJson(MOCK_DASHBOARD_SETTINGS));
    if (path.startsWith("dashboard")) return route.fulfill(mockJson([]));

    // Promo uses /promo/active (not /promo)
    if (path === "promo/active") return route.fulfill(mockJson(MOCK_PROMO));
    if (path.startsWith("promo")) return route.fulfill(mockJson(MOCK_PROMO));

    // Learning uses /learning/materials and /learning/courses
    if (path === "learning/courses") return route.fulfill(mockJson(MOCK_COURSES));
    if (path === "learning/materials") return route.fulfill(mockJson(MOCK_LEARNING));
    if (path.startsWith("learning")) return route.fulfill(mockJson([]));

    if (path.match(/^appeals\/\d+\/messages/)) return route.fulfill(mockJson([]));
    if (path === "appeals") return route.fulfill(mockJson(MOCK_APPEALS));
    if (path.startsWith("appeals")) return route.fulfill(mockJson(MOCK_APPEALS));

    if (path === "squads/my") return route.fulfill(mockJson(MOCK_SQUAD));
    if (path === "squads") return route.fulfill(mockJson(MOCK_SQUADS));
    if (path.startsWith("squads")) return route.fulfill(mockJson(MOCK_SQUADS));

    if (path === "users") return route.fulfill(mockJson(MOCK_USERS));
    if (path.startsWith("users")) return route.fulfill(mockJson(MOCK_USERS));

    if (path === "reports/activity-feed") return route.fulfill(mockJson(MOCK_ACTIVITY_FEED));
    if (path === "activity-feed") return route.fulfill(mockJson(MOCK_ACTIVITY_FEED));

    if (path === "join/me") return route.fulfill(mockJson(null));
    if (path === "join/me/history") return route.fulfill(mockJson([]));
    if (path === "join/events") return route.fulfill(mockJson([]));
    if (path === "join/applications") return route.fulfill(mockJson(null));
    if (path.startsWith("join")) return route.fulfill(mockJson(null));

    if (path === "public/events") return route.fulfill(mockJson([]));
    if (path.startsWith("public")) return route.fulfill(mockJson({ description: "Добро пожаловать!", requirements: "16+ лет" }));

    // Reports (actual paths from queries.ts)
    if (path === "reports/attendance") return route.fulfill(mockJson(MOCK_ATTENDANCE_REPORT));
    if (path === "reports/grades") return route.fulfill(mockJson(MOCK_GRADES_REPORT));
    if (path === "reports/normatives") return route.fulfill(mockJson(MOCK_NORMATIVES_REPORT));
    if (path.startsWith("reports")) return route.fulfill(mockJson({}));

    // Admin (admin/join/* not admin/join-events)
    if (path === "admin/users") return route.fulfill(mockJson(MOCK_USERS));
    if (path === "admin/join/applications") return route.fulfill(mockJson(MOCK_ADMIN_APPLICATIONS));
    if (path === "admin/join/events") return route.fulfill(mockJson([]));
    if (path === "admin/promo") return route.fulfill(mockJson(MOCK_PROMO));
    if (path === "admin/menu") return route.fulfill(mockJson([]));
    if (path === "admin/squads") return route.fulfill(mockJson(MOCK_SQUADS));
    if (path === "admin/audit") return route.fulfill(mockJson(MOCK_ADMIN_AUDIT));
    if (path === "admin/settings") return route.fulfill(mockJson({ timezone: "Asia/Novosibirsk" }));
    if (path.startsWith("admin/normatives")) return route.fulfill(mockJson(MOCK_NORMATIVES));
    if (path.startsWith("admin/learning")) return route.fulfill(mockJson([]));
    if (path.startsWith("admin/appeals")) return route.fulfill(mockJson(MOCK_APPEALS));
    if (path.startsWith("admin")) return route.fulfill(mockJson([]));

    if (path === "me") return route.fulfill(mockJson(makeProfile("PARTICIPANT", 3)));
    if (path.startsWith("files")) return route.fulfill(mockJson({}));

    // Fallback
    console.log(`  [WARN] UNHANDLED ${method} /${path}`);
    return route.fulfill(mockJson([]));
  });
}

// The @twa-dev/sdk reads initData from location.hash (#tgWebAppData=...).
// We must NOT override window.Telegram.WebApp — the SDK replaces it anyway.
// Instead, we pass the initData via URL hash so the SDK picks it up.
const TG_INIT_DATA = encodeURIComponent(
  "user=%7B%22id%22%3A795307805%2C%22first_name%22%3A%22Test%22%7D&auth_date=9999999999&hash=testhash"
);
const APP_URL = `${BASE}/#tgWebAppData=${TG_INIT_DATA}&tgWebAppVersion=7.0&tgWebAppPlatform=web`;

const roleExpectedText = {
  PUBLIC_USER: "Новый пользователь",
  CANDIDATE: "Кандидат",
  PARTICIPANT: "Участник",
  DEPUTY_SQUAD_COMMANDER: "Зам. командира отделения",
  SQUAD_COMMANDER: "Командир отделения",
  DEPUTY_PLATOON_COMMANDER: "Зам. командира взвода",
  PLATOON_COMMANDER: "Командир взвода",
  ADMIN: "Администратор",
};

async function waitForAuth(page, roleCode) {
  const expected = roleExpectedText[roleCode] ?? roleCode;
  // Wait until the header shows the expected role label
  await page.waitForFunction(
    (exp) => {
      const spans = document.querySelectorAll("header span");
      return Array.from(spans).some(s => s.textContent === exp);
    },
    expected,
    { timeout: 8000 }
  ).catch(() => {
    console.log(`  [WARN] Auth timeout — role label "${expected}" not found in header`);
  });
  await page.waitForTimeout(600);
}

async function shot(page, filename) {
  await page.waitForTimeout(300);
  await page.screenshot({ path: join(OUT, filename), fullPage: false });
  console.log("  [SHOT]", filename);
}

// Navigate by clicking the nav button (bottom nav)
async function nav(page, label) {
  // Nav buttons are inside <nav> element, contain a span with the label
  const btn = page.locator("nav button").filter({ hasText: label });
  const count = await btn.count();
  if (count === 0) {
    console.log(`  [WARN] Nav "${label}" not in nav bar`);
    return false;
  }
  await btn.first().click();
  await page.waitForTimeout(500);
  return true;
}

// Click any button anywhere by visible text
async function click(page, text, context = "button") {
  const btn = page.locator(context).filter({ hasText: text });
  const count = await btn.count();
  if (count === 0) {
    console.log(`  [WARN] "${text}" button not found`);
    return false;
  }
  await btn.first().click();
  await page.waitForTimeout(400);
  return true;
}

// Click a card in the menu grid
async function clickCard(page, text) {
  // Cards are button elements with class containing "menuCard" or similar
  // Try section buttons first, then any button
  let btn = page.locator("section button").filter({ hasText: text });
  if (await btn.count() === 0) {
    btn = page.locator("button").filter({ hasText: text });
  }
  if (await btn.count() === 0) {
    console.log(`  [WARN] Card "${text}" not found`);
    return false;
  }
  await btn.first().click();
  await page.waitForTimeout(600);
  return true;
}

async function runRole(browser, role) {
  console.log(`\n═══ ${role.label} (level ${role.level}) ═══`);
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await context.newPage();

  page.on("pageerror", e => console.log("  [PAGE ERR]", e.message.slice(0, 80)));

  await setupRoutes(page, role.code, role.level);
  await page.goto(APP_URL);

  // Wait for header to appear
  await page.waitForSelector("header", { timeout: 10000 });
  // Wait for auth to complete (role label in header)
  await waitForAuth(page, role.code);

  const p = role.label;

  // ── Dashboard ──
  await shot(page, `${p}__01_dashboard.png`);
  await page.evaluate(() => window.scrollTo(0, 600));
  await page.waitForTimeout(200);
  await shot(page, `${p}__01b_dashboard_bottom.png`);
  await page.evaluate(() => window.scrollTo(0, 0));

  if (role.level < 3) {
    // PUBLIC_USER — limited nav: Главная, План, Нормы, Профиль
    await nav(page, "План");
    await shot(page, `${p}__02_schedule_public.png`);
    await nav(page, "Нормы");
    await shot(page, `${p}__03_normatives_public.png`);
    await nav(page, "Профиль");
    await shot(page, `${p}__04_profile.png`);
    // Menu card Материалы
    await nav(page, "Главная");
    if (await clickCard(page, "Материалы")) await shot(page, `${p}__05_learning.png`);
    await context.close();
    return;
  }

  // ── PARTICIPANT+ nav: Главная, План, Явка, Нормы, Профиль [, Админка] ──

  // Schedule
  await nav(page, "План");
  await shot(page, `${p}__02_schedule.png`);

  // Attendance
  await nav(page, "Явка");
  await shot(page, `${p}__03_attendance.png`);
  if (await click(page, "Календарь")) await shot(page, `${p}__03b_attendance_cal.png`);
  if (await click(page, "История")) await shot(page, `${p}__03c_attendance_hist.png`);

  // Normatives
  await nav(page, "Нормы");
  await shot(page, `${p}__04_normatives.png`);
  if (await click(page, "Мои сдачи")) await shot(page, `${p}__04b_norm_my.png`);
  if (role.level >= 4 && await click(page, "На проверке")) await shot(page, `${p}__04c_norm_review.png`);
  if (await click(page, "Принятые")) await shot(page, `${p}__04d_norm_accepted.png`);

  // Profile
  await nav(page, "Профиль");
  await shot(page, `${p}__05_profile.png`);
  await page.evaluate(() => window.scrollTo(0, 500));
  await page.waitForTimeout(200);
  await shot(page, `${p}__05b_profile_scroll.png`);
  await page.evaluate(() => window.scrollTo(0, 0));

  // ── Menu cards from dashboard ──
  await nav(page, "Главная");
  await page.waitForTimeout(300);

  if (await clickCard(page, "Состав")) await shot(page, `${p}__06_people.png`);
  await nav(page, "Главная");
  if (await clickCard(page, "Уведомления")) await shot(page, `${p}__07_notifications.png`);
  await nav(page, "Главная");
  if (await clickCard(page, "Нужна помощь?")) await shot(page, `${p}__08_appeals.png`);
  await nav(page, "Главная");
  if (await clickCard(page, "Материалы")) await shot(page, `${p}__09_learning.png`);

  // Announcements (level 4+)
  if (role.level >= 4) {
    await nav(page, "Главная");
    if (await clickCard(page, "Объявления")) await shot(page, `${p}__10_announcements.png`);
  }

  // Reports (level 5+)
  if (role.level >= 5) {
    await nav(page, "Главная");
    if (await clickCard(page, "Отчёты")) {
      await shot(page, `${p}__11_reports.png`);
      if (await click(page, "Оценки")) await shot(page, `${p}__11b_grades.png`);
      if (await click(page, "Нормативы")) await shot(page, `${p}__11c_norms.png`);
      if (await click(page, "Экспорт")) await shot(page, `${p}__11d_export.png`);
    }
  }

  // Admin (level 6+)
  if (role.level >= 6) {
    await nav(page, "Админка");
    await shot(page, `${p}__12_admin.png`);
    await page.evaluate(() => window.scrollTo(0, 600));
    await shot(page, `${p}__12b_admin_scroll.png`);
    await page.evaluate(() => window.scrollTo(0, 0));

    const adminTabs = [
      "Люди", "Заявки", "Расписание", "Промо", "Меню", "Нормативы", "Материалы", "Связь",
      ...(role.level >= 8 ? ["Логи"] : []),
    ];
    for (const tab of adminTabs) {
      if (await click(page, tab, '[class*="adminTabGroups"] button')) await shot(page, `${p}__admin_${tab}.png`);
    }
  }

  await context.close();
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    for (const role of ROLES) {
      await runRole(browser, role);
    }
    console.log(`\n[DONE] ${OUT}`);
  } catch (e) {
    console.error("FATAL:", e.message);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
