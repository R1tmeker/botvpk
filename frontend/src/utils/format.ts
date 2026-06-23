let appTimezone = "Asia/Novosibirsk";

export function setAppTimezone(timezone: string) {
  appTimezone = timezone || "Asia/Novosibirsk";
}

export function getAppTimezone(): string {
  return appTimezone;
}

export function formatPhoneDisplay(raw: string | null | undefined): string {
  if (!raw) {
    return "—";
  }
  const digits = raw.replace(/\D/g, "");
  const local = digits.startsWith("7") || digits.startsWith("8") ? digits.slice(1) : digits;
  if (local.length !== 10) {
    return raw;
  }
  return `+7 ${local.slice(0, 3)} ${local.slice(3, 6)} ${local.slice(6, 8)} ${local.slice(8, 10)}`;
}

export function phoneInputToRaw(display: string): string {
  const digits = display.replace(/\D/g, "");
  const local = digits.startsWith("7") || digits.startsWith("8") ? digits.slice(1) : digits;
  return local.length > 0 ? "+7" + local.slice(0, 10) : "";
}

export function applyPhoneMask(value: string): string {
  const digits = value.replace(/\D/g, "");
  const local = digits.startsWith("7") || digits.startsWith("8") ? digits.slice(1) : digits;
  const d = local.slice(0, 10);
  let result = "+7";
  if (d.length > 0) result += " " + d.slice(0, 3);
  if (d.length > 3) result += " " + d.slice(3, 6);
  if (d.length > 6) result += " " + d.slice(6, 8);
  if (d.length > 8) result += " " + d.slice(8, 10);
  return result;
}

export function formatDate(value: string | null) {
  if (!value) return "без даты";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: appTimezone,
  }).format(new Date(value));
}

export function toDateTimeLocal(value: string | null) {
  if (!value) return "";
  const parts = new Intl.DateTimeFormat("sv-SE", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: appTimezone,
    hour12: false,
  }).formatToParts(new Date(value));
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? "00";
  return `${get("year")}-${get("month")}-${get("day")}T${get("hour")}:${get("minute")}`;
}

export function formatDateFull(value: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "long",
    year: "numeric",
    timeZone: appTimezone,
  }).format(new Date(value));
}

export function formatUnreadCount(count: number) {
  const mod10 = count % 10;
  const mod100 = count % 100;
  const word = mod10 === 1 && mod100 !== 11 ? "новое" : "новых";
  return `${count} ${word}`;
}
