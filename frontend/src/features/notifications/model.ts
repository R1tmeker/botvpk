import type { Notification } from "../../types/api";

export const notificationCategories = [
  ["", "Все категории"], ["SCHEDULE", "Расписание"], ["ATTENDANCE", "Посещаемость"],
  ["NORMATIVES", "Нормативы"], ["ANNOUNCEMENTS", "Объявления"], ["APPEALS", "Обращения"], ["SYSTEM", "Система"],
] as const;

export function safeAppLink(value?: string | null): string | null {
  if (!value?.startsWith("/") || value.startsWith("//") || value.includes("\\")) return null;
  try {
    const url = new URL(value, "https://app.local");
    const allowed = ["/", "/schedule", "/attendance", "/normatives", "/learning", "/appeals", "/people", "/announcements", "/notifications", "/profile", "/admin", "/admin/applications"];
    return url.origin === "https://app.local" && allowed.includes(url.pathname)
      ? `${url.pathname}${url.search}${url.hash}` : null;
  } catch {
    return null;
  }
}

export function notificationDestination(item: Notification): string | null {
  if (item.entity_name === "normative_submissions") return "/normatives";
  const explicit = safeAppLink(item.deep_link);
  if (explicit) return explicit;
  const id = item.entity_id;
  if (!id || id < 1) return null;
  const links: Record<string, string> = {
    schedule_events: `/schedule?event=${id}`, normatives: `/normatives?id=${id}`,
    appeals: `/appeals?id=${id}`, attendance: "/attendance", join_applications: "/admin/applications",
  };
  return links[item.entity_name ?? ""] ?? null;
}
