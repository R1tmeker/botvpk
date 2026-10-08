import { type Page } from "@playwright/test";

export const longName = "Константинопольский Владислав Владимирович";
const description = "Подготовка участников, расписание занятий и важные сведения для командования. ".repeat(5);
export const user = {
  id: 1, telegram_id: 990000001, username: "long_username_for_testing",
  full_name: longName, squad_id: 1, avatar_file_id: null,
  role_code: "PARTICIPANT", status_code: "ACTIVE", birth_date: "2006-04-11",
  phone: "+79990001122", city: "Барнаул", education_place: "1ИСП-42",
  version: "2026-10-08T00:00:00Z",
};
const squad = { id: 1, name: "Первое учебное отделение с длинным названием", commander_id: 1 };
export const events = [1, 2, 3].map((id) => ({
  id, title: `Занятие ${id}: подготовка участников военно-патриотического клуба`,
  description, start_datetime: new Date(Date.now() + 86400000 * id).toISOString(),
  end_datetime: null, place: "Учебный корпус, кабинет 123", status_code: "PLANNED",
  type_code: "TRAINING", squad_id: null, requires_response: true,
  my_response_code: null, self_checkin_enabled: false,
}));

export async function mockApp(page: Page, role: string, theme: string) {
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
