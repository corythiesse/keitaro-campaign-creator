import { describe, expect, it } from "vitest";
import { theme } from "./theme";

describe("theme", () => {
  it("exposes the brand palette and shape", () => {
    expect(theme.palette.primary.main).toBe("#315fba");
    expect(theme.shape.borderRadius).toBe(8);
  });
});
