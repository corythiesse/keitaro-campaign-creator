import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { parseApiError, request } from "./client";

const FALLBACK = "Не удалось выполнить запрос";

function response(body: unknown, ok: boolean, status: number): Response {
  return {
    ok,
    status,
    json: async () => body
  } as unknown as Response;
}

describe("parseApiError", () => {
  it("uses the first validation message from a 422 detail array", () => {
    const body = {
      detail: [
        {
          loc: ["body", "geo"],
          msg: "Некорректные ISO-коды стран: ZH",
          type: "invalid_geo"
        }
      ]
    };

    expect(parseApiError(body, FALLBACK)).toBe("Некорректные ISO-коды стран: ZH");
  });

  it("strips the pydantic value-error prefix", () => {
    const body = {
      detail: [{ loc: ["body", "geo"], msg: "Value error, Укажите хотя бы одну страну" }]
    };

    expect(parseApiError(body, FALLBACK)).toBe("Укажите хотя бы одну страну");
  });

  it("reads a message from a detail object and falls back otherwise", () => {
    expect(parseApiError({ detail: { message: "Прикладная ошибка" } }, FALLBACK)).toBe(
      "Прикладная ошибка"
    );
    expect(parseApiError({ detail: [] }, FALLBACK)).toBe(FALLBACK);
    expect(parseApiError({ detail: [{}] }, FALLBACK)).toBe(FALLBACK);
    expect(parseApiError("not json", FALLBACK)).toBe(FALLBACK);
  });

  it("appends a text detail from a Keitaro error", () => {
    const body = {
      detail: {
        code: "KEITARO_API_ERROR",
        message: "Keitaro вернул HTTP 408 (POST /campaigns)",
        details: "upstream timeout"
      }
    };

    expect(parseApiError(body, FALLBACK)).toBe(
      "Keitaro вернул HTTP 408 (POST /campaigns): upstream timeout"
    );
  });

  it("serializes structured details", () => {
    const body = {
      detail: {
        code: "KEITARO_API_ERROR",
        message: "Keitaro вернул HTTP 400 (POST /campaigns)",
        details: { error: "invalid alias" }
      }
    };

    expect(parseApiError(body, FALLBACK)).toBe(
      'Keitaro вернул HTTP 400 (POST /campaigns): {"error":"invalid alias"}'
    );
  });
});

describe("request", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    fetchMock.mockReset();
  });

  it("returns parsed JSON for a successful response", async () => {
    fetchMock.mockResolvedValue(response({ ok: true }, true, 200));

    await expect(request<{ ok: boolean }>("/api/test", { fallback: FALLBACK })).resolves.toEqual({
      ok: true
    });
  });

  it("throws ApiError with status, code and body on a failed response", async () => {
    fetchMock.mockResolvedValue(
      response({ detail: { code: "REVISION_CONFLICT", message: "Данные изменились" } }, false, 409)
    );

    await expect(request("/api/test", { fallback: FALLBACK })).rejects.toMatchObject({
      name: "ApiError",
      message: "Данные изменились",
      code: "REVISION_CONFLICT",
      status: 409
    });
  });

  it("wraps network failures in ApiError", async () => {
    fetchMock.mockRejectedValue(new TypeError("network down"));

    await expect(request("/api/test", { fallback: FALLBACK })).rejects.toMatchObject({
      name: "ApiError",
      message: FALLBACK,
      code: "NETWORK_ERROR"
    });
  });

  it("reports a timeout as ApiError", async () => {
    vi.useFakeTimers();
    fetchMock.mockImplementation(
      (_url: string, options: RequestInit) =>
        new Promise((_resolve, reject) => {
          options.signal?.addEventListener("abort", () => reject(new Error("aborted")));
        })
    );

    const expectation = expect(
      request("/api/test", { fallback: FALLBACK, timeoutMs: 50 })
    ).rejects.toMatchObject({ name: "ApiError", code: "TIMEOUT" });
    await vi.advanceTimersByTimeAsync(60);
    await expectation;
    vi.useRealTimers();
  });
});
