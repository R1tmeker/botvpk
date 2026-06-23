import { describe, expect, it } from "vitest";

import { applyPhoneMask, formatPhoneDisplay, formatUnreadCount, phoneInputToRaw } from "./format";

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
});
