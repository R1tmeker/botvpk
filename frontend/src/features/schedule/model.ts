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

export function recordId(search: string, parameter: string): number | null {
  const value = new URLSearchParams(search).get(parameter);
  if (!value || !/^[1-9]\d*$/.test(value)) return null;
  const id = Number(value);
  return Number.isSafeInteger(id) ? id : null;
}
