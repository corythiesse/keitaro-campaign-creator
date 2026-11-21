import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { searchOffers } from "./offers";

function response(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => body
  } as unknown as Response;
}

describe("searchOffers", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    fetchMock.mockReset();
  });

  it("encodes the query and returns an array", async () => {
    fetchMock.mockResolvedValue(response([{ id: 44, name: "Offer D" }]));

    await expect(searchOffers("Offer D & Co")).resolves.toEqual([{ id: 44, name: "Offer D" }]);
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("q=Offer+D+%26+Co");
  });

  it("normalizes a non-array response to an empty list", async () => {
    fetchMock.mockResolvedValue(response({ items: [] }));

    await expect(searchOffers("")).resolves.toEqual([]);
  });
});
