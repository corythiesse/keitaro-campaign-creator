import type { OfferOption } from "../../shared/api/types";

export interface CampaignFormValues {
  name: string;
  geo: string;
  offer: OfferOption | null;
}

export interface CampaignFormErrors {
  name?: string;
  geo?: string;
  offer?: string;
}

export function parseGeoCodes(geo: string): string[] {
  return geo
    .toUpperCase()
    .split(/[,\s;]+/)
    .filter(Boolean);
}

export function validateCampaignForm(values: CampaignFormValues): CampaignFormErrors {
  const errors: CampaignFormErrors = {};

  if (!values.name.trim()) {
    errors.name = "Введите название кампании";
  }

  const geo = values.geo.trim();
  if (!geo) {
    errors.geo = "Укажите хотя бы одну страну";
  } else {
    const codes = parseGeoCodes(geo);
    if (codes.some((code) => !/^[A-Z]{2}$/.test(code))) {
      errors.geo = "Используйте ISO-коды через запятую, например MX, AU, RO";
    } else if (new Set(codes).size !== codes.length) {
      errors.geo = "Удалите повторяющиеся GEO-коды";
    }
  }

  if (!values.offer) {
    errors.offer = "Выберите оффер из списка";
  }

  return errors;
}

export function hasFormErrors(errors: CampaignFormErrors): boolean {
  return Object.keys(errors).length > 0;
}
