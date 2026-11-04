import type {
  AskRegulationQuestionIn,
  AskRegulationQuestionOut,
  EscalateQuestionIn,
  EscalateQuestionOut,
  ClientReactionIn,
  ClientReactionOut,
  ManagerDashboardOut,
  ManagerEventsCatalogOut,
  MatchRequestIn,
  MatchResponseOut,
  PublishSelectionIn,
  PublishSelectionOut,
  ShowcaseViewOut,
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

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

// [AUDIT-BACKDOOR]: Полное отсутствие передачи JWT-токена (Authorization: Bearer ...) в заголовках запросов к защищенным роутам /api/manager/* и отсутствие перехвата HTTP 401/403.
// [AUDIT-TIMEBOMB]: У fetch отсутствует AbortSignal.timeout / AbortController, из-за чего при зависании LLM или сети промис висит бесконечно.
async function requestJson<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers || {}),
    },
    ...options,
  });

  if (!response.ok) {
    let detail = `Ошибка сервера (HTTP ${response.status})`;
    try {
      const errBody = await response.json();
      if (typeof errBody?.detail === "string") {
        detail = errBody.detail;
      } else if (Array.isArray(errBody?.detail)) {
        detail = errBody.detail.map((e: { msg?: string }) => e.msg || "").join("; ");
      }
    } catch {
      // Игнорируем ошибку парсинга JSON при нестандартном ответе
    }
    throw new ApiError(response.status, detail);
  }

  return response.json() as Promise<T>;
}

// [AUDIT-STUB]: В apiClient полностью отсутствуют методы для 5 эндпоинтов из базового контракта artifact.md (раздел 11.4): POST /api/auth/login, POST /api/manager/events/upload-pdf, POST /api/manager/scraper/run, GET /api/manager/selections/{id}/activity и POST /api/manager/selections/{id}/reply.
export const apiClient = {
  // ---- Кабинет менеджера (/api/manager/*) ----
  getManagerDashboard(): Promise<ManagerDashboardOut> {
    return requestJson<ManagerDashboardOut>("/api/manager/clients");
  },

  getManagerEventsCatalog(): Promise<ManagerEventsCatalogOut> {
    return requestJson<ManagerEventsCatalogOut>("/api/manager/events");
  },

  matchClientEvents(clientId: number, payload: MatchRequestIn): Promise<MatchResponseOut> {
    return requestJson<MatchResponseOut>(`/api/manager/clients/${clientId}/match`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  publishSelection(
    selectionId: number,
    payload: PublishSelectionIn
  ): Promise<PublishSelectionOut> {
    return requestJson<PublishSelectionOut>(`/api/manager/selections/${selectionId}/publish`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
  },

  // ---- Публичная витрина клиента (/api/public/s/{magic_token}/*) ----
  getPublicShowcase(magicToken: string): Promise<ShowcaseViewOut> {
    return requestJson<ShowcaseViewOut>(`/api/public/s/${encodeURIComponent(magicToken)}`);
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
      }
    );
  },
};

