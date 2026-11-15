import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, apiClient } from "./client";
import type {
  AskRegulationQuestionIn,
  CatalogEventsFilterParams,
  ClientReactionIn,
  EscalateQuestionIn,
  EventUploadIn,
  LoginRequestIn,
  ManagerReplyIn,
  MatchRequestIn,
  PublishSelectionIn,
  ScraperRunIn,
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
  managerEventsRoot: ["manager", "events"] as const,
  managerEvents: (filters?: CatalogEventsFilterParams) =>
    filters ? (["manager", "events", filters] as const) : (["manager", "events"] as const),
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

export function useUploadEventPdfMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: EventUploadIn) => apiClient.uploadEventPdf(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.managerEventsRoot });
    },
  });
}

export function useRunScraperMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ScraperRunIn) => apiClient.runScraper(payload),
    onSuccess: () => {
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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.managerDashboard });
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
      queryClient.invalidateQueries({
        queryKey: queryKeys.selectionActivity(data.selection_id),
      });
      queryClient.invalidateQueries({
        queryKey: queryKeys.showcase(data.magic_token),
      });
    },
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
