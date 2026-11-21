import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as campaignsApi from "../../shared/api/campaigns";
import { useCreateCampaign } from "./useCreateCampaign";

vi.mock("../../shared/api/campaigns", () => ({
  createCampaign: vi.fn()
}));

const createCampaign = vi.mocked(campaignsApi.createCampaign);
const input = { name: "Test", geo: "MX", offer_id: 44 };

beforeEach(() => {
  createCampaign.mockResolvedValue({
    success: true,
    campaign: { id: 1, name: "Test" },
    streams: []
  });
});

describe("useCreateCampaign", () => {
  it("creates a campaign and resets submitting", async () => {
    const { result } = renderHook(() => useCreateCampaign());

    let response: Awaited<ReturnType<typeof result.current.submit>> | undefined;
    await act(async () => {
      response = await result.current.submit(input);
    });

    expect(createCampaign).toHaveBeenCalledWith(input);
    expect(response?.success).toBe(true);
    expect(result.current.submitting).toBe(false);
  });

  it("prevents a parallel submit and propagates errors", async () => {
    const { result } = renderHook(() => useCreateCampaign());
    let rejectFirst: (error: Error) => void = () => undefined;
    createCampaign.mockImplementationOnce(
      () =>
        new Promise((_resolve, reject) => {
          rejectFirst = reject;
        })
    );

    let first: Promise<unknown> | undefined;
    act(() => {
      first = result.current.submit(input);
    });

    await expect(result.current.submit(input)).rejects.toThrow("уже выполняется");
    await act(async () => {
      rejectFirst(new Error("boom"));
      await expect(first).rejects.toThrow("boom");
    });

    expect(result.current.submitting).toBe(false);
  });
});
