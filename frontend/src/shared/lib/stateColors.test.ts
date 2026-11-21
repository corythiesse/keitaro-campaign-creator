import { describe, expect, it } from "vitest";
import { stateColor, stateLabel } from "./stateColors";

describe("state presentation", () => {
  it("maps campaign and offer states independently", () => {
    expect(stateColor("campaign", "active")).toBe("success");
    expect(stateColor("campaign", "suspended")).toBe("warning");
    expect(stateColor("offer", "disabled")).toBe("default");
    expect(stateColor("offer", "deleted")).toBe("error");
  });

  it("labels known states and keeps unknown values", () => {
    expect(stateLabel("campaign", "active")).toBe("Активна");
    expect(stateLabel("offer", "deleted")).toBe("Удалён");
    expect(stateLabel("stream", "deleted")).toBe("Удалён");
    expect(stateLabel("stream", "custom")).toBe("custom");
    expect(stateLabel("stream", null)).toBe("Неизвестно");
  });
});
