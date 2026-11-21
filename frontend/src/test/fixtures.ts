import type { CampaignEditor, CampaignSummary, Offer, Stream } from "../shared/api/types";

export function makeOffer(overrides: Partial<Offer> = {}): Offer {
  return {
    id: 100,
    keitaro_id: 42,
    keitaro_offer_stream_id: 555,
    campaign_id: 1,
    stream_id: 10,
    keitaro_stream_id: 9002,
    name: "Offer A",
    state: "active",
    share: 60,
    is_deleted: false,
    is_pinned: false,
    pinned_share: null,
    origin: "keitaro",
    ...overrides
  };
}

export function makeStream(overrides: Partial<Stream> = {}): Stream {
  return {
    id: 10,
    keitaro_id: 9002,
    campaign_id: 1,
    name: "Default - Offer",
    type: "default",
    schema: "landings",
    position: 1,
    state: "active",
    comments: null,
    is_deleted: false,
    origin: "keitaro",
    offers: [makeOffer(), makeOffer({ id: 101, keitaro_id: 43, name: "Offer B", share: 40 })],
    ...overrides
  };
}

export function makeCampaign(overrides: Partial<CampaignEditor> = {}): CampaignEditor {
  return {
    id: 1,
    keitaro_id: 456,
    keitaro_campaign_url: "https://keitaro.test/admin/#!/campaign/456/main",
    name: "Test campaign",
    alias: "test_alias",
    state: "active",
    has_local_changes: false,
    last_loaded_at: "2026-11-20T10:00:00Z",
    last_pushed_at: null,
    last_sync_error: null,
    revision: 3,
    warnings: [],
    streams: [
      makeStream(),
      makeStream({
        id: 11,
        keitaro_id: 9001,
        name: "GEO - Google",
        type: "regular",
        schema: "redirect",
        offers: []
      })
    ],
    ...overrides
  };
}

export function makeCampaignSummary(overrides: Partial<CampaignSummary> = {}): CampaignSummary {
  return {
    id: 1,
    keitaro_id: 456,
    name: "Test campaign",
    alias: "test_alias",
    state: "active",
    created_at: "2026-11-20T10:00:00Z",
    ...overrides
  };
}
