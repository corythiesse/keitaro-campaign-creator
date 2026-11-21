export type HttpMethod = "GET" | "POST" | "PATCH" | "DELETE";

export interface ApiErrorOptions {
  status?: number;
  code?: string;
  body?: unknown;
  cause?: unknown;
}

export class ApiError extends Error {
  readonly status?: number;
  readonly code?: string;
  readonly body?: unknown;

  constructor(message: string, options: ApiErrorOptions = {}) {
    super(message, options.cause === undefined ? undefined : { cause: options.cause });
    this.name = "ApiError";
    this.status = options.status;
    this.code = options.code;
    this.body = options.body;
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

function detailOf(body: unknown): unknown {
  if (body && typeof body === "object" && "detail" in body) {
    return (body as { detail?: unknown }).detail;
  }
  return undefined;
}

const MAX_DETAIL_LENGTH = 500;

function formatDetail(value: unknown): string | undefined {
  if (typeof value === "string") {
    const text = value.trim();
    return text ? text.slice(0, MAX_DETAIL_LENGTH) : undefined;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (value && typeof value === "object") {
    try {
      const text = JSON.stringify(value);
      return text && text !== "{}" ? text.slice(0, MAX_DETAIL_LENGTH) : undefined;
    } catch {
      return undefined;
    }
  }
  return undefined;
}

function withDetail(message: string, details: unknown): string {
  const text = formatDetail(details);
  if (!text || message.includes(text)) return message;
  return `${message}: ${text}`;
}

export function parseApiError(body: unknown, fallback: string): string {
  const detail = detailOf(body);
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    for (const item of detail) {
      const message = typeof item === "string" ? item : (item as { msg?: unknown })?.msg;
      if (typeof message === "string" && message.trim()) {
        // Pydantic v2 добавляет префикс "Value error, " к сообщениям валидаторов.
        return message.replace(/^Value error,\s*/i, "").trim();
      }
    }
    return fallback;
  }
  if (detail && typeof detail === "object") {
    const { message, details } = detail as { message?: unknown; details?: unknown };
    const messageText = typeof message === "string" ? message.trim() : "";
    if (messageText) return withDetail(messageText, details);
    return formatDetail(details) ?? fallback;
  }
  return fallback;
}

export function getApiErrorCode(error: unknown): string | undefined {
  return isApiError(error) ? error.code : undefined;
}

export function getErrorMessage(error: unknown, fallback = "Неизвестная ошибка"): string {
  if (error instanceof Error && error.message.trim()) return error.message;
  if (typeof error === "string" && error.trim()) return error;
  return fallback;
}

function errorCodeOf(body: unknown): string | undefined {
  const detail = detailOf(body);
  if (detail && typeof detail === "object" && "code" in detail) {
    const code = (detail as { code?: unknown }).code;
    return typeof code === "string" ? code : undefined;
  }
  return undefined;
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

export interface RequestOptions {
  method?: HttpMethod;
  body?: unknown;
  fallback: string;
  signal?: AbortSignal;
  timeoutMs?: number;
}

const DEFAULT_TIMEOUT_MS = 30_000;

export async function request<T>(url: string, options: RequestOptions): Promise<T> {
  const { method = "GET", body, fallback, signal, timeoutMs = DEFAULT_TIMEOUT_MS } = options;
  const controller = new AbortController();
  let timedOut = false;
  const timeoutId =
    timeoutMs > 0
      ? setTimeout(() => {
          timedOut = true;
          controller.abort();
        }, timeoutMs)
      : undefined;
  const onAbort = () => controller.abort();
  if (signal) {
    if (signal.aborted) controller.abort();
    else signal.addEventListener("abort", onAbort, { once: true });
  }

  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";

  try {
    const response = await fetch(url, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal
    });
    const data = await readJson(response);
    if (!response.ok) {
      throw new ApiError(parseApiError(data, fallback), {
        status: response.status,
        code: errorCodeOf(data),
        body: data
      });
    }
    return data as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (timedOut) {
      throw new ApiError("Превышено время ожидания ответа сервера", {
        code: "TIMEOUT",
        cause: error
      });
    }
    if (signal?.aborted || controller.signal.aborted) {
      throw new ApiError("Запрос отменён", { code: "ABORTED", cause: error });
    }
    throw new ApiError(fallback, { code: "NETWORK_ERROR", cause: error });
  } finally {
    if (timeoutId !== undefined) clearTimeout(timeoutId);
    signal?.removeEventListener("abort", onAbort);
  }
}
