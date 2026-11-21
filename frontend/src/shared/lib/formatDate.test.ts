import { describe, expect, it } from "vitest";
import { formatDate } from "./formatDate";

describe("formatDate", () => {
  it("formats a valid date in ru-RU", () => {
    expect(formatDate("2026-11-20T10:00:00Z")).toMatch(/\d{2}\.\d{2}\.\d{2}/);
  });

  it("returns the fallback for empty and invalid values", () => {
    expect(formatDate(null)).toBe("—");
    expect(formatDate("not-a-date")).toBe("—");
    expect(formatDate("", "нет даты")).toBe("нет даты");
  });
});
