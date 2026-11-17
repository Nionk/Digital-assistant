import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, apiClient } from "./client";
import type {
  AskRegulationQuestionIn,
  CatalogEventsFilterParams,
  ClientCreateIn,
  ClientReactionIn,
  ClientUpdateIn,
  EscalateQuestionIn,
  EventRefreshIn,
  EventUploadIn,
  GeneratePitchIn,
  LoginRequestIn,
  ManagerDashboardOut,
  ManagerReplyIn,
  MatchRequestIn,
  PublishSelectionIn,
  ScraperRunIn,
  ScraperSourceCreateIn,
  ScraperSourcePreviewIn,
  ScraperSourceUpdateIn,
  ShowcaseViewOut,
} from "./types";

const TERMINAL_HTTP_STATUSES = new Set([401, 403, 404, 422]);

function isTerminalPollingError(error: unknown): boolean {
  return error instanceof ApiError && TERMINAL_HTTP_STATUSES.has(error.status);
}

/**
 * Ключи кэша TanStack Query.
 * Поллинг 10 секунд обеспечивает синхронизацию реакций клиента,
 * чата и дашборда менеджера без WebSockets.
 */
export const queryKeys = {
  managerDashboard: ["manager", "dashboard"] as const,
  clientWorkspaceRoot: ["manager", "clientWorkspace"] as const,
  clientWorkspace: (clientId: number) =>
    ["manager", "clientWorkspace", clientId] as const,
  managerEventsRoot: ["manager", "events"] as const,
  managerEvents: (filters?: CatalogEventsFilterParams) =>
    filters ? (["manager", "events", filters] as const) : (["manager", "events"] as const),
  scraperSources: ["manager", "scraper", "sources"] as const,
  scraperRunsRoot: ["manager", "scraper", "runs"] as const,
  scraperRuns: (limit: number) =>
    ["manager", "scraper", "runs", limit] as const,
  scraperLatestRun: ["manager", "scraper", "runs", "latest"] as const,
  selectionActivity: (selectionId: number) =>
    ["manager", "selectionActivity", selectionId] as const,
  showcase: (magicToken: string) => ["public", "showcase", magicToken] as const,
};

export function useLoginMutation() {
  return useMutation({
    mutationFn: (payload: LoginRequestIn) => apiClient.login(payload),
  });
}

export function useManagerDashboard() {
  return useQuery({
    queryKey: queryKeys.managerDashboard,
    queryFn: () => apiClient.getManagerDashboard(),
    refetchInterval: (query) =>
      isTerminalPollingError(query.state.error) ? false : 10_000,
    refetchIntervalInBackground: false,
    staleTime: 5_000,
  });
}

export function useClientWorkspace(
  clientId: number | null | undefined,
  enabled = true
) {
  return useQuery({
    queryKey: queryKeys.clientWorkspace(clientId || 0),
    queryFn: () => apiClient.getClientWorkspace(clientId!),
    enabled: Boolean(clientId) && enabled,
    staleTime: 15_000,
  });
}

export function useCreateClientMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ClientCreateIn) => apiClient.createClient(payload),
    onSuccess: (created) => {
      queryClient.setQueryData<ManagerDashboardOut>(
        queryKeys.managerDashboard,
        (prev) => {
          if (!prev) return prev;
          const exists = prev.clients.some((c) => c.id === created.id);
          return exists
            ? prev
            : { ...prev, clients: [...prev.clients, created] };
        }
      );
      queryClient.invalidateQueries({ queryKey: queryKeys.managerDashboard });
    },
  });
}

export function useUpdateClientMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      clientId,
      payload,
    }: {
      clientId: number;
      payload: ClientUpdateIn;
    }) => apiClient.updateClient(clientId, payload),
    onSuccess: (updated) => {
      queryClient.setQueryData<ManagerDashboardOut>(
        queryKeys.managerDashboard,
        (prev) => {
          if (!prev) return prev;
          return {
            ...prev,
            clients: updated.is_active
              ? prev.clients.map((c) => (c.id === updated.id ? updated : c))
              : prev.clients.filter((c) => c.id !== updated.id),
          };
        }
      );
      queryClient.invalidateQueries({ queryKey: queryKeys.managerDashboard });
      if (updated.is_active) {
        queryClient.invalidateQueries({
          queryKey: queryKeys.clientWorkspace(updated.id),
        });
      } else {
        queryClient.removeQueries({
          queryKey: queryKeys.clientWorkspace(updated.id),
        });
      }
    },
  });
}

export function useManagerEventsCatalog(
  enabled = true,
  filters?: CatalogEventsFilterParams
) {
  return useQuery({
    queryKey: queryKeys.managerEvents(filters),
    queryFn: () => apiClient.getManagerEventsCatalog(filters),
    enabled,
    staleTime: 30_000,
  });
}

export function useArchiveEventMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (eventId: number) => apiClient.archiveEvent(eventId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.managerEventsRoot });
      queryClient.invalidateQueries({ queryKey: queryKeys.managerDashboard });
      queryClient.invalidateQueries({ queryKey: queryKeys.scraperLatestRun });
    },
  });
}

export function useRefreshEventMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      eventId,
      payload,
    }: {
      eventId: number;
      payload?: EventRefreshIn;
    }) => apiClient.refreshEvent(eventId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.managerEventsRoot });
      queryClient.invalidateQueries({ queryKey: queryKeys.managerDashboard });
      queryClient.invalidateQueries({ queryKey: queryKeys.scraperLatestRun });
    },
  });
}

export function useUploadEventPdfMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: EventUploadIn) => apiClient.uploadEventPdf(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.managerEventsRoot });
    },
  });
}

export function useScraperSources(enabled = true) {
  return useQuery({
    queryKey: queryKeys.scraperSources,
    queryFn: () => apiClient.getScraperSources(),
    enabled,
    staleTime: 30_000,
  });
}

export function useCreateScraperSourceMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ScraperSourceCreateIn) =>
      apiClient.createScraperSource(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.scraperSources });
    },
  });
}

export function useUpdateScraperSourceMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      sourceKey,
      payload,
    }: {
      sourceKey: string;
      payload: ScraperSourceUpdateIn;
    }) => apiClient.updateScraperSource(sourceKey, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.scraperSources });
    },
  });
}

export function useDeleteScraperSourceMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sourceKey: string) =>
      apiClient.deleteScraperSource(sourceKey),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.scraperSources });
    },
  });
}

export function usePreviewScraperSourceMutation() {
  return useMutation({
    mutationFn: (payload: ScraperSourcePreviewIn) =>
      apiClient.previewScraperSource(payload),
  });
}

export function useScraperRuns(limit = 15, enabled = true) {
  return useQuery({
    queryKey: queryKeys.scraperRuns(limit),
    queryFn: () => apiClient.getScraperRuns(limit),
    enabled,
    staleTime: 5_000,
  });
}

export function useLatestScraperRun(enabled = true) {
  const queryClient = useQueryClient();
  const prevRunRef = React.useRef<{ id: number; status: string } | null>(null);

  const query = useQuery({
    queryKey: queryKeys.scraperLatestRun,
    queryFn: () => apiClient.getLatestScraperRun(),
    enabled,
    refetchInterval: (q) => {
      if (!enabled || isTerminalPollingError(q.state.error)) {
        return false;
      }
      const status = q.state.data?.status;
      return status === "queued" || status === "running" ? 2_500 : false;
    },
    refetchIntervalInBackground: false,
    staleTime: 2_000,
  });

  React.useEffect(() => {
    const current = query.data;
    const prev = prevRunRef.current;

    if (current) {
      const wasActive =
        prev !== null &&
        prev.id === current.id &&
        (prev.status === "queued" || prev.status === "running");

      if (wasActive && current.status === "completed") {
        queryClient.invalidateQueries({ queryKey: queryKeys.managerEventsRoot });
        queryClient.invalidateQueries({ queryKey: queryKeys.scraperRunsRoot });
      } else if (wasActive && current.status === "failed") {
        queryClient.invalidateQueries({ queryKey: queryKeys.scraperRunsRoot });
      }
      prevRunRef.current = { id: current.id, status: current.status };
    } else if (current === null) {
      prevRunRef.current = null;
    }
  }, [query.data, queryClient]);

  return query;
}

export function useRunScraperMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ScraperRunIn) => apiClient.runScraper(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.scraperLatestRun });
      queryClient.invalidateQueries({ queryKey: queryKeys.scraperRunsRoot });
      queryClient.invalidateQueries({ queryKey: queryKeys.managerEventsRoot });
    },
  });
}

export function useMatchClientMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      clientId,
      payload,
    }: {
      clientId: number;
      payload: MatchRequestIn;
    }) => apiClient.matchClientEvents(clientId, payload),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.managerDashboard });
      queryClient.invalidateQueries({
        queryKey: queryKeys.clientWorkspace(data.client_id),
      });
    },
  });
}

export function usePublishSelectionMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      selectionId,
      payload,
    }: {
      selectionId: number;
      payload: PublishSelectionIn;
    }) => apiClient.publishSelection(selectionId, payload),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.managerDashboard });
      queryClient.invalidateQueries({ queryKey: queryKeys.clientWorkspaceRoot });
      queryClient.invalidateQueries({
        queryKey: queryKeys.selectionActivity(data.selection_id),
      });
      queryClient.invalidateQueries({
        queryKey: queryKeys.showcase(data.magic_token),
      });
    },
  });
}

export function useGenerateSelectionPitchMutation() {
  return useMutation({
    mutationFn: ({
      selectionId,
      payload,
    }: {
      selectionId: number;
      payload: GeneratePitchIn;
    }) => apiClient.generateSelectionPitch(selectionId, payload),
  });
}

export function useSelectionActivity(
  selectionId: number | null | undefined,
  pollInterval = 10_000
) {
  return useQuery({
    queryKey: queryKeys.selectionActivity(selectionId || 0),
    queryFn: () => apiClient.getSelectionActivity(selectionId!),
    enabled: Boolean(selectionId),
    refetchInterval: (query) =>
      isTerminalPollingError(query.state.error) ? false : pollInterval,
    refetchIntervalInBackground: false,
    staleTime: 4_000,
  });
}

export function useManagerReplyMutation(selectionId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ManagerReplyIn) =>
      apiClient.replyToSelectionMessage(selectionId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.selectionActivity(selectionId),
      });
    },
  });
}

export function usePublicShowcase(
  magicToken: string | null | undefined,
  pollInterval = 10_000
) {
  return useQuery({
    queryKey: queryKeys.showcase(magicToken || ""),
    queryFn: () => apiClient.getPublicShowcase(magicToken!),
    enabled: Boolean(magicToken),
    refetchInterval: (query) =>
      isTerminalPollingError(query.state.error) ? false : pollInterval,
    refetchIntervalInBackground: false,
    staleTime: 4_000,
  });
}

export function useClientReactionMutation(magicToken: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      selectionItemId,
      payload,
    }: {
      selectionItemId: number;
      payload: ClientReactionIn;
    }) => apiClient.sendClientReaction(magicToken, selectionItemId, payload),

    // Оптимистичное обновление состояния карточки за 0 мс
    onMutate: async ({ selectionItemId, payload }) => {
      await queryClient.cancelQueries({
        queryKey: queryKeys.showcase(magicToken),
      });
      const previous = queryClient.getQueryData<ShowcaseViewOut>(
        queryKeys.showcase(magicToken)
      );

      if (previous) {
        queryClient.setQueryData<ShowcaseViewOut>(
          queryKeys.showcase(magicToken),
          {
            ...previous,
            items: previous.items.map((item) =>
              item.selection_item_id === selectionItemId
                ? {
                    ...item,
                    client_reaction: payload.reaction,
                    client_comment: payload.comment ?? item.client_comment,
                  }
                : item
            ),
          }
        );
      }

      return { previous };
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(
          queryKeys.showcase(magicToken),
          context.previous
        );
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.showcase(magicToken),
      });
    },
  });
}

export function useAskRegulationMutation(magicToken: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      eventId,
      payload,
    }: {
      eventId: number;
      payload: AskRegulationQuestionIn;
    }) => apiClient.askRegulationQuestion(magicToken, eventId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.showcase(magicToken),
      });
    },
  });
}

export function useEscalateQuestionMutation(magicToken: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      eventId,
      payload,
    }: {
      eventId: number;
      payload: EscalateQuestionIn;
    }) => apiClient.escalateQuestion(magicToken, eventId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.showcase(magicToken),
      });
    },
  });
}
