import { request } from "./client";
import type {
  CampaignCreateInput,
  CampaignEditor,
  CampaignSummary,
  CreateCampaignResponse,
  OfferPatch,
  SyncPushResponse
} from "./types";

const CAMPAIGNS_PATH = "/api/campaigns";

export const CAMPAIGNS_PAGE_SIZE = 50;

export interface FetchCampaignsParams {
  limit?: number;
  offset?: number;
  q?: string;
  state?: string | null;
  signal?: AbortSignal;
}

export async function fetchCampaigns({
  limit = CAMPAIGNS_PAGE_SIZE,
  offset = 0,
  q = "",
  state = null,
  signal
}: FetchCampaignsParams = {}): Promise<CampaignSummary[]> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset)
  });
  if (q.trim()) params.set("q", q.trim());
  if (state) params.set("state", state);

  const body = await request<CampaignSummary[]>(`${CAMPAIGNS_PATH}?${params.toString()}`, {
    fallback: "Не удалось загрузить кампании",
    signal
  });
  return Array.isArray(body) ? body : [];
}

export function createCampaign(input: CampaignCreateInput): Promise<CreateCampaignResponse> {
  return request<CreateCampaignResponse>(`${CAMPAIGNS_PATH}/create`, {
    method: "POST",
    body: input,
    fallback: "Не удалось создать кампанию"
  });
}

export function fetchCampaignDetail(
  id: string | number,
  signal?: AbortSignal
): Promise<CampaignEditor> {
  return request<CampaignEditor>(`${CAMPAIGNS_PATH}/${id}`, {
    fallback: "Не удалось загрузить кампанию",
    signal
  });
}

export function loadCampaignStreams(
  id: string | number,
  { force = false, signal }: { force?: boolean; signal?: AbortSignal } = {}
): Promise<CampaignEditor> {
  return request<CampaignEditor>(`${CAMPAIGNS_PATH}/${id}/sync/load`, {
    method: "POST",
    body: { force },
    fallback: "Не удалось загрузить данные из Keitaro",
    signal
  });
}

export function pushCampaignChanges(
  id: string | number,
  {
    expectedRevision = null,
    force = false
  }: { expectedRevision?: number | null; force?: boolean } = {}
): Promise<SyncPushResponse> {
  return request<SyncPushResponse>(`${CAMPAIGNS_PATH}/${id}/sync/push`, {
    method: "POST",
    body: { expected_revision: expectedRevision, force },
    fallback: "Не удалось отправить изменения в Keitaro"
  });
}

export function discardCampaignChanges(id: string | number): Promise<CampaignEditor> {
  return request<CampaignEditor>(`${CAMPAIGNS_PATH}/${id}/sync/discard`, {
    method: "POST",
    fallback: "Не удалось отменить изменения"
  });
}

interface AddOfferInput {
  offer_id: number;
  name?: string;
  expectedRevision?: number | null;
}

export function addOffer(streamId: number, input: AddOfferInput): Promise<CampaignEditor> {
  const body: Record<string, unknown> = { offer_id: input.offer_id };
  if (input.name) body.name = input.name;
  if (input.expectedRevision != null) body.expected_revision = input.expectedRevision;
  return request<CampaignEditor>(`/api/streams/${streamId}/offers`, {
    method: "POST",
    body,
    fallback: "Не удалось добавить предложение"
  });
}

export function updateOffer(
  offerId: number,
  patch: OfferPatch,
  expectedRevision: number | null = null
): Promise<CampaignEditor> {
  const body: Record<string, unknown> = { ...patch };
  if (expectedRevision != null) body.expected_revision = expectedRevision;
  return request<CampaignEditor>(`/api/offers/${offerId}`, {
    method: "PATCH",
    body,
    fallback: "Не удалось изменить предложение"
  });
}
