import { describe, expect, it } from "vitest";

import { actionItemLabel } from "./ActionCenter";

describe("actionItemLabel", () => {
  it("localizes known command actions", () => {
    expect(actionItemLabel("send_reminder")).toBe("Напомнить всем");
    expect(actionItemLabel("retry_delivery")).toBe("Повторить доставку");
  });

  it("keeps an unknown server action visible", () => {
    expect(actionItemLabel("custom_action")).toBe("custom_action");
  });
});
