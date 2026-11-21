import { describe, expect, it } from "vitest";
import { parseGeoCodes, validateCampaignForm } from "./campaignFormValidation";

const offer = { id: 44, name: "Offer D" };

describe("validateCampaignForm", () => {
  it("requires name, geo and offer", () => {
    expect(validateCampaignForm({ name: "", geo: "", offer: null })).toEqual({
      name: "Введите название кампании",
      geo: "Укажите хотя бы одну страну",
      offer: "Выберите оффер из списка"
    });
  });

  it("rejects non-ISO geo codes", () => {
    expect(validateCampaignForm({ name: "Test", geo: "MX, MEX", offer }).geo).toBe(
      "Используйте ISO-коды через запятую, например MX, AU, RO"
    );
  });

  it("rejects duplicate geo codes", () => {
    expect(validateCampaignForm({ name: "Test", geo: "MX, mx", offer }).geo).toBe(
      "Удалите повторяющиеся GEO-коды"
    );
  });

  it("accepts valid values", () => {
    expect(validateCampaignForm({ name: " Test ", geo: "MX, AU; RO", offer })).toEqual({});
  });

  it("parses codes case-insensitively with all supported separators", () => {
    expect(parseGeoCodes("mx, au; ro")).toEqual(["MX", "AU", "RO"]);
  });
});
