import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as offersApi from "../api/offers";
import { useOfferSearch } from "./useOfferSearch";

vi.mock("../api/offers", () => ({
  searchOffers: vi.fn()
}));

const searchOffers = vi.mocked(offersApi.searchOffers);

beforeEach(() => {
  searchOffers.mockResolvedValue([{ id: 1, name: "Offer A" }]);
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useOfferSearch", () => {
  it("debounces the request and exposes offers", async () => {
    const { result } = renderHook(() => useOfferSearch());

    await act(async () => {
      await vi.advanceTimersByTimeAsync(249);
    });
    expect(searchOffers).not.toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });

    expect(searchOffers).toHaveBeenCalledWith("", { signal: expect.any(AbortSignal) });
    expect(result.current.offers).toEqual([{ id: 1, name: "Offer A" }]);
  });

  it("does not search until enabled", async () => {
    const { rerender } = renderHook(({ enabled }) => useOfferSearch({ enabled }), {
      initialProps: { enabled: false }
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
    expect(searchOffers).not.toHaveBeenCalled();

    rerender({ enabled: true });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(250);
    });
    expect(searchOffers).toHaveBeenCalledTimes(1);
  });

  it("reports a search error through onError", async () => {
    const onError = vi.fn();
    searchOffers.mockRejectedValueOnce(new Error("Не удалось загрузить офферы"));

    renderHook(() => useOfferSearch({ onError }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(250);
    });

    expect(onError).toHaveBeenCalledWith("Не удалось загрузить офферы", undefined);
  });
});
