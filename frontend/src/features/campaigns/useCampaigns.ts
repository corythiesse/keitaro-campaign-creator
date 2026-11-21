import { useCallback, useEffect, useRef, useState } from "react";
import { CAMPAIGNS_PAGE_SIZE, fetchCampaigns } from "../../shared/api/campaigns";
import { getErrorMessage, isApiError } from "../../shared/api/client";
import type { CampaignSummary } from "../../shared/api/types";
import { useLatestRequest } from "../../shared/hooks/useLatestRequest";
import { CAMPAIGNS_SEARCH_DEBOUNCE_MS } from "../../shared/lib/constants";

interface LoadOptions {
  silent?: boolean;
}

export function useCampaigns() {
  const [campaigns, setCampaigns] = useState<CampaignSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [stateFilter, setStateFilter] = useState("");
  const [hasMore, setHasMore] = useState(false);

  const firstRequest = useLatestRequest();
  const moreRequest = useLatestRequest();
  const abortRef = useRef<AbortController | null>(null);
  const campaignsRef = useRef<CampaignSummary[]>([]);

  useEffect(() => {
    campaignsRef.current = campaigns;
  }, [campaigns]);

  useEffect(
    () => () => {
      abortRef.current?.abort();
    },
    []
  );

  const loadFirst = useCallback(
    async ({ silent = false }: LoadOptions = {}) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      const requestId = firstRequest.next();

      if (silent) setRefreshing(true);
      else setLoading(true);
      setError(null);

      try {
        const data = await fetchCampaigns({
          limit: CAMPAIGNS_PAGE_SIZE,
          offset: 0,
          q: query,
          state: stateFilter || null,
          signal: controller.signal
        });
        if (!firstRequest.isLatest(requestId)) return;
        setCampaigns(data);
        setHasMore(data.length === CAMPAIGNS_PAGE_SIZE);
      } catch (caught) {
        if (!firstRequest.isLatest(requestId)) return;
        if (isApiError(caught) && caught.code === "ABORTED") return;
        setError(getErrorMessage(caught, "Не удалось загрузить кампании"));
      } finally {
        if (firstRequest.isLatest(requestId)) {
          if (silent) setRefreshing(false);
          else setLoading(false);
        }
      }
    },
    [firstRequest, query, stateFilter]
  );

  useEffect(() => {
    const timer = setTimeout(
      () => {
        void loadFirst();
      },
      query ? CAMPAIGNS_SEARCH_DEBOUNCE_MS : 0
    );
    return () => clearTimeout(timer);
  }, [loadFirst, query]);

  const loadMore = useCallback(async () => {
    if (loading || refreshing || loadingMore || !hasMore) return;
    const requestId = moreRequest.next();
    setLoadingMore(true);
    setError(null);
    try {
      const data = await fetchCampaigns({
        limit: CAMPAIGNS_PAGE_SIZE,
        offset: campaignsRef.current.length,
        q: query,
        state: stateFilter || null
      });
      if (!moreRequest.isLatest(requestId)) return;
      setCampaigns((previous) => [...previous, ...data]);
      setHasMore(data.length === CAMPAIGNS_PAGE_SIZE);
    } catch (caught) {
      if (!moreRequest.isLatest(requestId)) return;
      if (isApiError(caught) && caught.code === "ABORTED") return;
      setError(getErrorMessage(caught, "Не удалось загрузить кампании"));
    } finally {
      if (moreRequest.isLatest(requestId)) setLoadingMore(false);
    }
  }, [hasMore, loading, loadingMore, moreRequest, query, refreshing, stateFilter]);

  const retry = useCallback(() => {
    void loadFirst();
  }, [loadFirst]);

  const refresh = useCallback(() => {
    void loadFirst({ silent: true });
  }, [loadFirst]);

  const hasFilters = query.trim().length > 0 || stateFilter.length > 0;

  return {
    campaigns,
    loading,
    refreshing,
    loadingMore,
    error,
    hasMore,
    query,
    setQuery,
    stateFilter,
    setStateFilter,
    hasFilters,
    retry,
    refresh,
    loadMore
  };
}
