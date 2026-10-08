import type { ScheduleEvent } from "../../types/api";

export function responseIsOpen(event: ScheduleEvent, level: number, now = Date.now()): boolean {
  return event.requires_response && event.status_code !== "CANCELLED"
    && new Date(event.start_datetime).getTime() > now
    && (level >= 4 || !event.response_deadline_at || new Date(event.response_deadline_at).getTime() >= now);
}

export function needsFinalResponse(event: ScheduleEvent): boolean {
  return !event.my_response_code || event.my_response_code === "MAYBE";
}

export function checkInIsOpen(event: ScheduleEvent, now = Date.now()): boolean {
  const start = new Date(event.start_datetime).getTime();
  const opens = event.self_checkin_opens_at ? new Date(event.self_checkin_opens_at).getTime() : start - 15 * 60_000;
  const closes = event.self_checkin_closes_at ? new Date(event.self_checkin_closes_at).getTime() : start + 20 * 60_000;
  return event.self_checkin_enabled && event.status_code !== "CANCELLED" && now >= opens && now <= closes;
}

export function eventIsArchived(event: ScheduleEvent, now = Date.now()): boolean {
  const start = new Date(event.start_datetime).getTime();
  const end = event.end_datetime ? new Date(event.end_datetime).getTime() : start;
  const checkInEnd = event.self_checkin_enabled
    ? event.self_checkin_closes_at ? new Date(event.self_checkin_closes_at).getTime() : start + 20 * 60_000 : start;
  return event.status_code === "CANCELLED" || Math.max(start, end, checkInEnd) < now;
}

export function sameDayInTimezone(value: string, now: number, timezone: string): boolean {
  const formatter = new Intl.DateTimeFormat("en-CA", { timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit" });
  return formatter.format(new Date(value)) === formatter.format(new Date(now));
}

export type SchedulePeriod = "today" | "week" | "month";

// Compare calendar dates in the club's timezone, independent of the device's
// timezone and of 23/25-hour days at daylight-saving transitions.
export function schedulePeriod(period: SchedulePeriod, now: number, timezone: string, offset = 0) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(new Date(now));
  const part = (name: string) => Number(parts.find((item) => item.type === name)!.value);
  const start = new Date(Date.UTC(part("year"), part("month") - 1, part("day")));
  if (period === "week") start.setUTCDate(start.getUTCDate() - (start.getUTCDay() + 6) % 7 + offset * 7);
  else if (period === "month") { start.setUTCDate(1); start.setUTCMonth(start.getUTCMonth() + offset); }
  const end = new Date(start);
  if (period === "month") end.setUTCMonth(end.getUTCMonth() + 1);
  else end.setUTCDate(end.getUTCDate() + (period === "week" ? 7 : 1));
  const last = new Date(end.getTime() - 86_400_000);
  const format = (date: Date) => new Intl.DateTimeFormat("ru-RU", {
    timeZone: "UTC", day: "numeric", month: "long", year: "numeric",
  }).format(date);
  const weekStartLabel = new Intl.DateTimeFormat("ru-RU", {
    timeZone: "UTC", day: "numeric",
    ...(start.getUTCMonth() !== last.getUTCMonth() ? { month: "long" as const } : {}),
    ...(start.getUTCFullYear() !== last.getUTCFullYear() ? { year: "numeric" as const } : {}),
  }).format(start);
  return {
    from: start.toISOString().slice(0, 10), to: end.toISOString().slice(0, 10),
    label: period === "month"
      ? new Intl.DateTimeFormat("ru-RU", { timeZone: "UTC", month: "long", year: "numeric" }).format(start)
      : period === "week" ? `${weekStartLabel} – ${format(last)}` : format(start),
  };
}

export function eventInPeriod(event: ScheduleEvent, range: { from: string; to: string }, timezone: string): boolean {
  const day = new Intl.DateTimeFormat("sv-SE", { timeZone: timezone }).format(new Date(event.start_datetime));
  return day >= range.from && day < range.to;
}

export function recordId(search: string, parameter: string): number | null {
  const value = new URLSearchParams(search).get(parameter);
  if (!value || !/^[1-9]\d*$/.test(value)) return null;
  const id = Number(value);
  return Number.isSafeInteger(id) ? id : null;
}
