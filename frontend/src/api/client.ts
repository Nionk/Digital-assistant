import type {
  AskRegulationQuestionIn,
  AskRegulationQuestionOut,
  CatalogEventsFilterParams,
  ClientCreateIn,
  ClientReactionIn,
  ClientReactionOut,
  ClientSummaryOut,
  ClientUpdateIn,
  ClientWorkspaceOut,
  EscalateQuestionIn,
  EscalateQuestionOut,
  EventUploadIn,
  EventUploadOut,
  GeneratePitchIn,
  GeneratePitchOut,
  LoginRequestIn,
  ManagerDashboardOut,
  ManagerEventsCatalogOut,
  ManagerReplyIn,
  ManagerReplyOut,
  MatchRequestIn,
  MatchResponseOut,
  PublishSelectionIn,
  PublishSelectionOut,
  ScraperRunIn,
  ScraperRunOut,
  SelectionActivityOut,
  ShowcaseViewOut,
  TokenOut,
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

const DEFAULT_TIMEOUT_MS = 15_000;
const LLM_TIMEOUT_MS = 90_000;

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export interface ApiAuthConfig {
  getAccessToken: () => string | null;
  onUnauthorized?: (status: 401 | 403, path: string) => void;
}

let authConfig: ApiAuthConfig = {
  getAccessToken: () => null,
};

/**
 * Подключает провайдер JWT-токена и обработчик 401/403 (вызывается при инициализации auth-стора).
 */
export function configureApiAuth(config: ApiAuthConfig): void {
  authConfig = config;
}

interface RequestOptions extends RequestInit {
  timeoutMs?: number;
  requiresAuth?: boolean;
}

function buildTimedSignal(
  timeoutMs: number,
  externalSignal?: AbortSignal | null
): { signal: AbortSignal; cleanup: () => void } {
  const timeoutSignal =
    typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function"
      ? AbortSignal.timeout(timeoutMs)
      : null;

  if (timeoutSignal && !externalSignal) {
    return { signal: timeoutSignal, cleanup: () => {} };
  }

  if (
    timeoutSignal &&
    externalSignal &&
    typeof AbortSignal.any === "function"
  ) {
    return {
      signal: AbortSignal.any([timeoutSignal, externalSignal]),
      cleanup: () => {},
    };
  }

  const controller = new AbortController();
  const timerId = window.setTimeout(() => {
    controller.abort(new DOMException("Превышен таймаут запроса", "TimeoutError"));
  }, timeoutMs);

  const onExternalAbort = () => {
    controller.abort(externalSignal?.reason);
  };

  if (externalSignal) {
    if (externalSignal.aborted) {
      controller.abort(externalSignal.reason);
    } else {
      externalSignal.addEventListener("abort", onExternalAbort, { once: true });
    }
  }

  return {
    signal: controller.signal,
    cleanup: () => {
      window.clearTimeout(timerId);
      externalSignal?.removeEventListener("abort", onExternalAbort);
    },
  };
}

async function requestJson<T>(
  path: string,
  options: RequestOptions = {}
): Promise<T> {
  const {
    timeoutMs = DEFAULT_TIMEOUT_MS,
    requiresAuth = path.startsWith("/api/manager"),
    headers: customHeaders,
    signal: externalSignal,
    ...restOptions
  } = options;

  const isFormData =
    typeof FormData !== "undefined" && restOptions.body instanceof FormData;

  const headers = new Headers(customHeaders);
  if (!isFormData && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  if (requiresAuth && !headers.has("Authorization")) {
    const token = authConfig.getAccessToken();
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
  }

  const { signal, cleanup } = buildTimedSignal(timeoutMs, externalSignal);

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...restOptions,
      headers,
      signal,
    });
  } catch (err) {
    if (externalSignal?.aborted) {
      throw err;
    }
    if (err instanceof DOMException && (err.name === "TimeoutError" || err.name === "AbortError")) {
      throw new ApiError(
        408,
        "Сервер не ответил вовремя. Пожалуйста, повторите попытку."
      );
    }
    throw err;
  } finally {
    cleanup();
  }

  if (!response.ok) {
    let detail = `Ошибка сервера (HTTP ${response.status})`;
    try {
      const errBody = await response.json();
      if (typeof errBody?.detail === "string") {
        detail = errBody.detail;
      } else if (Array.isArray(errBody?.detail)) {
        detail = errBody.detail
          .map((e: { msg?: string }) => e.msg || "")
          .filter(Boolean)
          .join("; ");
      }
    } catch {
      // Игнорируем ошибку парсинга JSON при нестандартном ответе
    }

    if (requiresAuth && (response.status === 401 || response.status === 403)) {
      authConfig.onUnauthorized?.(response.status, path);
    }

    throw new ApiError(response.status, detail);
  }

  return response.json() as Promise<T>;
}

function buildCatalogQuery(filters?: CatalogEventsFilterParams): string {
  if (!filters) return "";
  const params = new URLSearchParams();
  if (filters.city?.trim()) params.set("city", filters.city.trim());
  if (filters.event_format) params.set("event_format", filters.event_format);
  if (filters.data_status) params.set("data_status", filters.data_status);
  if (filters.date_from) params.set("date_from", filters.date_from);
  if (filters.date_to) params.set("date_to", filters.date_to);
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export const apiClient = {
  // ---- Авторизация (/api/auth/*) ----
  login(payload: LoginRequestIn): Promise<TokenOut> {
    return requestJson<TokenOut>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify(payload),
      requiresAuth: false,
      timeoutMs: DEFAULT_TIMEOUT_MS,
    });
  },

  // ---- Кабинет менеджера (/api/manager/*) ----
  getManagerDashboard(includeArchived = false): Promise<ManagerDashboardOut> {
    const qs = includeArchived ? "?include_archived=true" : "";
    return requestJson<ManagerDashboardOut>(`/api/manager/clients${qs}`, {
      timeoutMs: DEFAULT_TIMEOUT_MS,
    });
  },

  createClient(payload: ClientCreateIn): Promise<ClientSummaryOut> {
    return requestJson<ClientSummaryOut>("/api/manager/clients", {
      method: "POST",
      body: JSON.stringify({
        company_name: payload.company_name,
        contact_person: payload.contact_person ?? null,
        raw_manager_notes: payload.raw_manager_notes ?? "",
      }),
      timeoutMs: DEFAULT_TIMEOUT_MS,
    });
  },

  updateClient(
    clientId: number,
    payload: ClientUpdateIn
  ): Promise<ClientSummaryOut> {
    return requestJson<ClientSummaryOut>(`/api/manager/clients/${clientId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
      timeoutMs: DEFAULT_TIMEOUT_MS,
    });
  },

  getClientWorkspace(clientId: number): Promise<ClientWorkspaceOut> {
    return requestJson<ClientWorkspaceOut>(
      `/api/manager/clients/${clientId}/workspace`,
      { timeoutMs: DEFAULT_TIMEOUT_MS }
    );
  },

  getManagerEventsCatalog(
    filters?: CatalogEventsFilterParams
  ): Promise<ManagerEventsCatalogOut> {
    return requestJson<ManagerEventsCatalogOut>(
      `/api/manager/events${buildCatalogQuery(filters)}`,
      { timeoutMs: DEFAULT_TIMEOUT_MS }
    );
  },

  uploadEventPdf(payload: EventUploadIn): Promise<EventUploadOut> {
    const formData = new FormData();
    if (payload.file) {
      formData.append("file", payload.file);
    }
    if (payload.raw_text?.trim()) {
      formData.append("raw_text", payload.raw_text.trim());
    }
    if (payload.source_url?.trim()) {
      formData.append("source_url", payload.source_url.trim());
    }
    return requestJson<EventUploadOut>("/api/manager/events/upload-pdf", {
      method: "POST",
      body: formData,
      timeoutMs: LLM_TIMEOUT_MS,
    });
  },

  runScraper(payload: ScraperRunIn): Promise<ScraperRunOut> {
    return requestJson<ScraperRunOut>("/api/manager/scraper/run", {
      method: "POST",
      body: JSON.stringify(payload),
      timeoutMs: DEFAULT_TIMEOUT_MS,
    });
  },

  matchClientEvents(
    clientId: number,
    payload: MatchRequestIn
  ): Promise<MatchResponseOut> {
    return requestJson<MatchResponseOut>(
      `/api/manager/clients/${clientId}/match`,
      {
        method: "POST",
        body: JSON.stringify(payload),
        timeoutMs: LLM_TIMEOUT_MS,
      }
    );
  },

  publishSelection(
    selectionId: number,
    payload: PublishSelectionIn
  ): Promise<PublishSelectionOut> {
    return requestJson<PublishSelectionOut>(
      `/api/manager/selections/${selectionId}/publish`,
      {
        method: "PUT",
        body: JSON.stringify(payload),
        timeoutMs: DEFAULT_TIMEOUT_MS,
      }
    );
  },

  generateSelectionPitch(
    selectionId: number,
    payload: GeneratePitchIn
  ): Promise<GeneratePitchOut> {
    return requestJson<GeneratePitchOut>(
      `/api/manager/selections/${selectionId}/pitch`,
      {
        method: "POST",
        body: JSON.stringify(payload),
        timeoutMs: LLM_TIMEOUT_MS,
      }
    );
  },

  getSelectionActivity(selectionId: number): Promise<SelectionActivityOut> {
    return requestJson<SelectionActivityOut>(
      `/api/manager/selections/${selectionId}/activity`,
      { timeoutMs: DEFAULT_TIMEOUT_MS }
    );
  },

  replyToSelectionMessage(
    selectionId: number,
    payload: ManagerReplyIn
  ): Promise<ManagerReplyOut> {
    return requestJson<ManagerReplyOut>(
      `/api/manager/selections/${selectionId}/reply`,
      {
        method: "POST",
        body: JSON.stringify(payload),
        timeoutMs: DEFAULT_TIMEOUT_MS,
      }
    );
  },

  // ---- Публичная витрина клиента (/api/public/s/{magic_token}/*) ----
  getPublicShowcase(magicToken: string): Promise<ShowcaseViewOut> {
    return requestJson<ShowcaseViewOut>(
      `/api/public/s/${encodeURIComponent(magicToken)}`,
      { requiresAuth: false, timeoutMs: DEFAULT_TIMEOUT_MS }
    );
  },

  sendClientReaction(
    magicToken: string,
    selectionItemId: number,
    payload: ClientReactionIn
  ): Promise<ClientReactionOut> {
    return requestJson<ClientReactionOut>(
      `/api/public/s/${encodeURIComponent(magicToken)}/items/${selectionItemId}/react`,
      {
        method: "POST",
        body: JSON.stringify(payload),
        requiresAuth: false,
        timeoutMs: DEFAULT_TIMEOUT_MS,
      }
    );
  },

  askRegulationQuestion(
    magicToken: string,
    eventId: number,
    payload: AskRegulationQuestionIn
  ): Promise<AskRegulationQuestionOut> {
    return requestJson<AskRegulationQuestionOut>(
      `/api/public/s/${encodeURIComponent(magicToken)}/events/${eventId}/ask`,
      {
        method: "POST",
        body: JSON.stringify(payload),
        requiresAuth: false,
        timeoutMs: LLM_TIMEOUT_MS,
      }
    );
  },

  escalateQuestion(
    magicToken: string,
    eventId: number,
    payload: EscalateQuestionIn
  ): Promise<EscalateQuestionOut> {
    return requestJson<EscalateQuestionOut>(
      `/api/public/s/${encodeURIComponent(magicToken)}/events/${eventId}/escalate-question`,
      {
        method: "POST",
        body: JSON.stringify(payload),
        requiresAuth: false,
        timeoutMs: DEFAULT_TIMEOUT_MS,
      }
    );
  },
};
