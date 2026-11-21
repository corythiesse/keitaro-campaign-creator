import { useCallback, useEffect, useRef, useState } from "react";
import {
  addOffer,
  discardCampaignChanges,
  fetchCampaignDetail,
  loadCampaignStreams,
  pushCampaignChanges,
  updateOffer
} from "../../shared/api/campaigns";
import { getErrorMessage, isApiError } from "../../shared/api/client";
import type { CampaignEditor, Offer, OfferPatch, Stream, SyncResult } from "../../shared/api/types";
import { useLatestRequest } from "../../shared/hooks/useLatestRequest";
import { useNotice } from "../../shared/hooks/useNotice";

export type ConfirmType = "load" | "discard";

interface RunOptions<T> {
  successMessage?: string;
  onSuccess?: (data: T) => void;
  onError?: (error: unknown) => boolean;
}

export function useCampaignEditor(campaignId: string) {
  const [campaign, setCampaign] = useState<CampaignEditor | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<ConfirmType | null>(null);
  const [pushResults, setPushResults] = useState<SyncResult[]>([]);
  const [revisionConflict, setRevisionConflict] = useState(false);
  const { notice, showNotice, closeNotice } = useNotice();
  const { next, isLatest } = useLatestRequest();

  const busyRef = useRef(false);
  const confirmRef = useRef<ConfirmType | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    confirmRef.current = confirm;
  }, [confirm]);

  useEffect(
    () => () => {
      abortRef.current?.abort();
    },
    []
  );

  const load = useCallback(
    async ({ silent = false }: { silent?: boolean } = {}) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      const requestId = next();

      if (!silent) setLoading(true);
      setError(null);

      try {
        const data = await fetchCampaignDetail(campaignId, controller.signal);
        if (!isLatest(requestId)) return;
        setCampaign(data);
        setRevisionConflict(false);
      } catch (caught) {
        if (!isLatest(requestId)) return;
        if (isApiError(caught) && caught.code === "ABORTED") return;
        if (silent) {
          showNotice("error", getErrorMessage(caught, "Не удалось загрузить кампанию"));
        } else {
          setError(getErrorMessage(caught, "Не удалось загрузить кампанию"));
        }
      } finally {
        if (isLatest(requestId) && !silent) setLoading(false);
      }
    },
    [campaignId, isLatest, next, showNotice]
  );

  useEffect(() => {
    void load();
  }, [load]);

  // Reload on tab focus so a second tab's edits are picked up. Skip while a
  // mutation or a confirmation dialog is active.
  useEffect(() => {
    const onFocus = () => {
      if (busyRef.current || confirmRef.current) return;
      if (document.visibilityState !== "visible") return;
      void load({ silent: true });
    };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [load]);

  const hasChanges = Boolean(campaign?.has_local_changes);
  useEffect(() => {
    if (!hasChanges) return undefined;
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [hasChanges]);

  const runAction = useCallback(
    async <T>(
      key: string,
      action: () => Promise<T>,
      options: RunOptions<T> = {}
    ): Promise<T | null> => {
      if (busyRef.current) return null;
      busyRef.current = true;
      setBusy(key);
      try {
        const data = await action();
        if (options.successMessage) showNotice("success", options.successMessage);
        options.onSuccess?.(data);
        return data;
      } catch (caught) {
        if (options.onError?.(caught)) return null;
        if (isApiError(caught) && caught.code === "REVISION_CONFLICT") {
          setRevisionConflict(true);
        } else {
          showNotice("error", getErrorMessage(caught));
        }
        return null;
      } finally {
        busyRef.current = false;
        setBusy(null);
      }
    },
    [showNotice]
  );

  const doLoad = useCallback(
    async (force: boolean) => {
      setRevisionConflict(false);
      return runAction("load", () => loadCampaignStreams(campaignId, { force }), {
        successMessage: "Данные из Keitaro загружены",
        onSuccess: (data) => {
          setCampaign(data);
          setPushResults([]);
          if (data.warnings.length) showNotice("warning", data.warnings.join("; "));
        },
        onError: (caught) => {
          if (!force && isApiError(caught) && caught.code === "LOCAL_CHANGES_PENDING") {
            setConfirm("load");
            return true;
          }
          return false;
        }
      });
    },
    [campaignId, runAction, showNotice]
  );

  const doDiscard = useCallback(async () => {
    await runAction("discard", () => discardCampaignChanges(campaignId), {
      successMessage: "Изменения отменены",
      onSuccess: (data) => {
        setCampaign(data);
        setPushResults([]);
      }
    });
  }, [campaignId, runAction]);

  const requestLoad = useCallback(() => {
    if (campaign?.has_local_changes) setConfirm("load");
    else void doLoad(false);
  }, [campaign?.has_local_changes, doLoad]);

  const requestDiscard = useCallback(() => {
    setConfirm("discard");
  }, []);

  const closeConfirm = useCallback(() => {
    setConfirm(null);
  }, []);

  const confirmLoad = useCallback(() => {
    setConfirm(null);
    void doLoad(true);
  }, [doLoad]);

  const confirmDiscard = useCallback(() => {
    setConfirm(null);
    void doDiscard();
  }, [doDiscard]);

  const handlePush = useCallback(async () => {
    if (!campaign) return null;
    setRevisionConflict(false);
    return runAction(
      "push",
      () =>
        pushCampaignChanges(campaignId, {
          expectedRevision: campaign.revision
        }),
      {
        onSuccess: (body) => {
          setCampaign(body.campaign);
          if (body.success) {
            setPushResults([]);
            showNotice("success", "Изменения отправлены в Keitaro");
          } else {
            setPushResults(body.results);
            showNotice("warning", "Часть потоков не удалось отправить");
          }
        },
        onError: (caught) => {
          if (isApiError(caught) && caught.code === "SYNC_FAILED") {
            const detail = (caught.body as { detail?: { results?: SyncResult[] } } | undefined)
              ?.detail;
            setPushResults(detail?.results ?? []);
            showNotice("error", caught.message);
            return true;
          }
          return false;
        }
      }
    );
  }, [campaign, campaignId, runAction, showNotice]);

  const handleOfferPatch = useCallback(
    (offer: Offer, patch: OfferPatch) =>
      runAction(
        `offer:${offer.id}`,
        () => updateOffer(offer.id, patch, campaign?.revision ?? null),
        {
          onSuccess: setCampaign
        }
      ),
    [campaign?.revision, runAction]
  );

  const handleAddOffer = useCallback(
    (stream: Stream, offer: { offer_id: number; name?: string }) =>
      runAction(
        `add:${stream.id}`,
        () =>
          addOffer(stream.id, {
            ...offer,
            expectedRevision: campaign?.revision ?? null
          }),
        {
          onSuccess: setCampaign,
          successMessage: "Предложение добавлено"
        }
      ),
    [campaign?.revision, runAction]
  );

  const showError = useCallback(
    (message: string, _code?: string) => {
      showNotice("error", message);
    },
    [showNotice]
  );

  const retryLoad = useCallback(() => {
    void load();
  }, [load]);

  const refreshAfterConflict = useCallback(() => {
    void load({ silent: true });
  }, [load]);

  return {
    campaign,
    loading,
    error,
    busy,
    confirm,
    pushResults,
    revisionConflict,
    notice,
    closeNotice,
    requestLoad,
    handlePush,
    requestDiscard,
    handleOfferPatch,
    handleAddOffer,
    confirmLoad,
    confirmDiscard,
    closeConfirm,
    retryLoad,
    refreshAfterConflict,
    showError
  };
}
