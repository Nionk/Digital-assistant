import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "./client";
import type {
  AskRegulationQuestionIn,
  EscalateQuestionIn,
  ClientReactionIn,
  MatchRequestIn,
  PublishSelectionIn,
  ShowcaseViewOut,
} from "./types";

/**
 * Ключи кэша TanStack Query.
 * Поллинг 10 секунд (refetchInterval: 10000) обеспечивает синхронизацию
 * реакций клиента и дашборда менеджера строго без WebSockets (.cursorrules п. 1.4).
 */
export const queryKeys = {
  managerDashboard: ["manager", "dashboard"] as const,
  managerEvents: ["manager", "events"] as const,
  showcase: (magicToken: string) => ["public", "showcase", magicToken] as const,
};

export function useManagerDashboard() {
  return useQuery({
    queryKey: queryKeys.managerDashboard,
    queryFn: () => apiClient.getManagerDashboard(),
    refetchInterval: 10000,
    staleTime: 5000,
  });
}

export function useManagerEventsCatalog(enabled = true) {
  return useQuery({
    queryKey: queryKeys.managerEvents,
    queryFn: () => apiClient.getManagerEventsCatalog(),
    enabled,
    staleTime: 30000,
  });
}

export function useMatchClientMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ clientId, payload }: { clientId: number; payload: MatchRequestIn }) =>
      apiClient.matchClientEvents(clientId, payload),
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
        queryKey: queryKeys.showcase(data.magic_token),
      });
    },
  });
}

export function usePublicShowcase(magicToken: string | null | undefined, pollInterval = 10000) {
  return useQuery({
    queryKey: queryKeys.showcase(magicToken || ""),
    queryFn: () => apiClient.getPublicShowcase(magicToken!),
    enabled: Boolean(magicToken),
    refetchInterval: pollInterval,
    staleTime: 4000,
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
      await queryClient.cancelQueries({ queryKey: queryKeys.showcase(magicToken) });
      const previous = queryClient.getQueryData<ShowcaseViewOut>(
        queryKeys.showcase(magicToken)
      );

      if (previous) {
        queryClient.setQueryData<ShowcaseViewOut>(queryKeys.showcase(magicToken), {
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
        });
      }

      return { previous };
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKeys.showcase(magicToken), context.previous);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.showcase(magicToken) });
    },
  });
}

export function useAskRegulationMutation(magicToken: string) {
  return useMutation({
    mutationFn: ({
      eventId,
      payload,
    }: {
      eventId: number;
      payload: AskRegulationQuestionIn;
    }) => apiClient.askRegulationQuestion(magicToken, eventId, payload),
  });
}

export function useEscalateQuestionMutation(magicToken: string) {
  return useMutation({
    mutationFn: ({
      eventId,
      payload,
    }: {
      eventId: number;
      payload: EscalateQuestionIn;
    }) => apiClient.escalateQuestion(magicToken, eventId, payload),
  });
}
