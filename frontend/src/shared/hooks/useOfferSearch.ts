import { useEffect, useState } from "react";
import { searchOffers } from "../api/offers";
import { getApiErrorCode, getErrorMessage } from "../api/client";
import type { OfferOption } from "../api/types";
import { OFFER_SEARCH_DEBOUNCE_MS } from "../lib/constants";

interface UseOfferSearchOptions {
  onError?: (message: string, code?: string) => void;
  enabled?: boolean;
}

export function useOfferSearch({ onError, enabled = true }: UseOfferSearchOptions = {}) {
  const [query, setQuery] = useState("");
  const [offers, setOffers] = useState<OfferOption[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return undefined;
    }

    const controller = new AbortController();
    setLoading(true);
    const timer = setTimeout(async () => {
      try {
        const data = await searchOffers(query, { signal: controller.signal });
        if (!controller.signal.aborted) setOffers(data);
      } catch (error) {
        if (!controller.signal.aborted) {
          onError?.(getErrorMessage(error, "Не удалось загрузить офферы"), getApiErrorCode(error));
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }, OFFER_SEARCH_DEBOUNCE_MS);

    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [query, onError, enabled]);

  return { query, setQuery, offers, loading };
}
