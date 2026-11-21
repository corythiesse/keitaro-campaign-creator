import { request } from "./client";
import type { OfferOption } from "./types";

const OFFERS_REMOTE_PATH = "/api/offers-remote";

export async function searchOffers(
  query: string,
  { signal }: { signal?: AbortSignal } = {}
): Promise<OfferOption[]> {
  const params = new URLSearchParams({ q: query });
  const body = await request<OfferOption[]>(`${OFFERS_REMOTE_PATH}?${params.toString()}`, {
    fallback: "Не удалось загрузить офферы",
    signal
  });
  return Array.isArray(body) ? body : [];
}
