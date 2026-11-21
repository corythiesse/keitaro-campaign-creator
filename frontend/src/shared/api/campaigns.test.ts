import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  addOffer,
  discardCampaignChanges,
  fetchCampaignDetail,
  fetchCampaigns,
  loadCampaignStreams,
  pushCampaignChanges,
  updateOffer
} from "./campaigns";

function response(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => body
  } as unknown as Response;
}

describe("campaigns API", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    fetchMock.mockReset();
  });

  it("passes pagination, search and state to the list endpoint", async () => {
    fetchMock.mockResolvedValue(response([]));

    await fetchCampaigns({ limit: 20, offset: 40, q: "sale", state: "active" });

    const url = String(fetchMock.mock.calls[0]?.[0]);
    expect(url).toContain("/api/campaigns?");
    expect(url).toContain("limit=20");
    expect(url).toContain("offset=40");
    expect(url).toContain("q=sale");
    expect(url).toContain("state=active");
  });

  it("sends expected_revision when adding an offer", async () => {
    fetchMock.mockResolvedValue(response({ id: 1 }));

    await addOffer(10, { offer_id: 44, name: "Offer D", expectedRevision: 3 });

    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(JSON.parse(String(init.body))).toEqual({
      offer_id: 44,
      name: "Offer D",
      expected_revision: 3
    });
  });

  it("sends expected_revision when patching an offer", async () => {
    fetchMock.mockResolvedValue(response({ id: 1 }));

    await updateOffer(100, { is_pinned: true, pinned_share: 60 }, 3);

    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(JSON.parse(String(init.body))).toEqual({
      is_pinned: true,
      pinned_share: 60,
      expected_revision: 3
    });
  });

  it("uses the detail, load, push and discard endpoints", async () => {
    fetchMock.mockResolvedValue(response({ id: 1 }));

    await fetchCampaignDetail(1);
    await loadCampaignStreams(1, { force: true });
    await pushCampaignChanges(1, { expectedRevision: 4 });
    await discardCampaignChanges(1);

    expect(String(fetchMock.mock.calls[0]?.[0])).toBe("/api/campaigns/1");
    expect(String(fetchMock.mock.calls[1]?.[0])).toBe("/api/campaigns/1/sync/load");
    expect(JSON.parse(String((fetchMock.mock.calls[1]?.[1] as RequestInit).body))).toEqual({
      force: true
    });
    expect(String(fetchMock.mock.calls[2]?.[0])).toBe("/api/campaigns/1/sync/push");
    expect(JSON.parse(String((fetchMock.mock.calls[2]?.[1] as RequestInit).body))).toEqual({
      expected_revision: 4,
      force: false
    });
    expect(String(fetchMock.mock.calls[3]?.[0])).toBe("/api/campaigns/1/sync/discard");
    expect((fetchMock.mock.calls[3]?.[1] as RequestInit).method).toBe("POST");
  });
});
