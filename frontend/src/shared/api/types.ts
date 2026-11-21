export interface CampaignSummary {
  id: number;
  keitaro_id: number;
  name: string;
  alias?: string | null;
  state?: string | null;
  type?: string | null;
  domain_id?: number | null;
  group_id?: string | null;
  traffic_source_id?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface Offer {
  id: number;
  keitaro_id: number;
  keitaro_offer_stream_id?: number | null;
  campaign_id: number;
  stream_id: number;
  keitaro_stream_id?: number | null;
  name?: string | null;
  state?: string | null;
  share?: number | null;
  is_deleted: boolean;
  is_pinned: boolean;
  pinned_share?: number | null;
  origin?: string;
  created_at?: string | null;
}

export interface Stream {
  id: number;
  keitaro_id: number;
  campaign_id: number;
  name: string;
  type?: string | null;
  schema?: string | null;
  position?: number | null;
  state?: string | null;
  action_type?: string | null;
  action_payload?: string | null;
  comments?: string | null;
  weight?: number | null;
  is_deleted: boolean;
  origin?: string;
  offers: Offer[];
}

export interface CampaignEditor extends CampaignSummary {
  keitaro_campaign_url?: string | null;
  streams: Stream[];
  has_local_changes: boolean;
  last_loaded_at?: string | null;
  last_pushed_at?: string | null;
  last_sync_error?: string | null;
  revision: number;
  warnings: string[];
}

export interface CreatedCampaign {
  id: number;
  name: string;
  alias?: string | null;
}

export interface CreatedStream {
  id: number;
  name: string;
}

export interface CreateCampaignResponse {
  success: boolean;
  campaign: CreatedCampaign;
  streams: CreatedStream[];
}

export interface SyncResult {
  stream_id?: number | null;
  keitaro_id?: number | null;
  status: string;
  action?: string | null;
  code?: string | null;
  message?: string | null;
}

export interface SyncPushResponse {
  success: boolean;
  code?: string | null;
  message?: string | null;
  campaign: CampaignEditor;
  results: SyncResult[];
}

export interface OfferOption {
  id: number;
  name: string;
}

export interface CampaignCreateInput {
  name: string;
  geo: string;
  offer_id: number;
}

export interface OfferPatch {
  is_deleted?: boolean;
  is_pinned?: boolean;
  pinned_share?: number;
  state?: string;
}
