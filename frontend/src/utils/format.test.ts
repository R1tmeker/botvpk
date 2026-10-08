import { describe, expect, it } from "vitest";

import { applyPhoneMask, dateTimeLocalToUtc, formatPhoneDisplay, formatUnreadCount, phoneInputToRaw, setAppTimezone, toDateTimeLocal } from "./format";

describe("format helpers", () => {
  it("normalizes and displays Russian phone numbers", () => {
    expect(applyPhoneMask("89991234567")).toBe("+7 999 123 45 67");
    expect(phoneInputToRaw("+7 999 123 45 67")).toBe("+79991234567");
    expect(formatPhoneDisplay("+79991234567")).toBe("+7 999 123 45 67");
  });

  it("formats unread notification counts", () => {
    expect(formatUnreadCount(1)).toBe("1 новое");
    expect(formatUnreadCount(11)).toBe("11 новых");
    expect(formatUnreadCount(22)).toBe("22 новых");
  });

  it("uses the club timezone when saving date inputs", () => {
    setAppTimezone("Asia/Novosibirsk");
    expect(dateTimeLocalToUtc("2026-10-08T20:00")).toBe("2026-10-08T13:00:00.000Z");
    expect(toDateTimeLocal(dateTimeLocalToUtc("2026-10-08T20:00"))).toBe("2026-10-08T20:00");
  });

  it("handles DST offsets and rejects nonexistent wall times", () => {
    expect(dateTimeLocalToUtc("2026-01-15T12:00", "Europe/Berlin")).toBe("2026-01-15T11:00:00.000Z");
    expect(dateTimeLocalToUtc("2026-07-15T12:00", "Europe/Berlin")).toBe("2026-07-15T10:00:00.000Z");
    expect(dateTimeLocalToUtc("2026-03-29T02:30", "Europe/Berlin")).toBe("");
    for (const value of ["", "invalid", "2026-02-30T12:00"]) expect(dateTimeLocalToUtc(value)).toBe("");
  });
});
