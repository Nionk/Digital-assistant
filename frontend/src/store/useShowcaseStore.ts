import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import type { AskRegulationQuestionOut, ParticipationRole } from "@/api/types";

export type ShowcaseLayoutMode = "carousel" | "grid";
export type ShowcaseRoleFilter = "all" | ParticipationRole;

export interface RegulationChatExchange {
  id: string;
  questionText: string;
  response: AskRegulationQuestionOut | null;
  isLoading: boolean;
  error: string | null;
  createdAt: string;
  isEscalated?: boolean;
  isEscalating?: boolean;
}

interface TokenPersistedBucket {
  chatByEventId: Record<number, RegulationChatExchange[]>;
  selectedAgencyServicesByItem: Record<number, string[]>;
}

const DEFAULT_TOKEN_KEY = "__default__";

interface ShowcaseState {
  activeMagicToken: string | null;
  persistedByToken: Record<string, TokenPersistedBucket>;

  layoutMode: ShowcaseLayoutMode;
  roleFilter: ShowcaseRoleFilter;

  // Выдвижная панель «Паспорт участия и ИИ-консультант по регламенту»
  activeDrawerEventId: number | null;
  drawerInitialTab: "regulation" | "benefits";

  // Активные проекции текущего magicToken
  chatByEventId: Record<number, RegulationChatExchange[]>;
  selectedAgencyServicesByItem: Record<number, string[]>;

  bindMagicToken: (magicToken: string) => void;
  setLayoutMode: (mode: ShowcaseLayoutMode) => void;
  setRoleFilter: (role: ShowcaseRoleFilter) => void;
  openEventDrawer: (
    eventId: number,
    tab?: "regulation" | "benefits"
  ) => void;
  closeEventDrawer: () => void;

  startQuestionExchange: (
    eventId: number,
    id: string,
    questionText: string
  ) => void;
  completeQuestionExchange: (
    eventId: number,
    id: string,
    response: AskRegulationQuestionOut
  ) => void;
  failQuestionExchange: (
    eventId: number,
    id: string,
    errorMsg: string
  ) => void;

  setExchangeEscalating: (
    eventId: number,
    exchangeId: string,
    isEscalating: boolean
  ) => void;
  setExchangeEscalated: (eventId: number, exchangeId: string) => void;

  toggleAgencyServiceForItem: (
    selectionItemId: number,
    serviceTag: string
  ) => void;
}

function sanitizeChatMap(
  chatMap: Record<number, RegulationChatExchange[]>
): Record<number, RegulationChatExchange[]> {
  const cleaned: Record<number, RegulationChatExchange[]> = {};
  for (const [eventIdStr, exchanges] of Object.entries(chatMap)) {
    cleaned[Number(eventIdStr)] = exchanges.map((ex) => ({
      ...ex,
      isLoading: false,
      isEscalating: false,
    }));
  }
  return cleaned;
}

function syncBucket(
  state: ShowcaseState,
  nextChat: Record<number, RegulationChatExchange[]>,
  nextServices: Record<number, string[]>
): Partial<ShowcaseState> {
  const tokenKey = state.activeMagicToken || DEFAULT_TOKEN_KEY;
  return {
    chatByEventId: nextChat,
    selectedAgencyServicesByItem: nextServices,
    persistedByToken: {
      ...state.persistedByToken,
      [tokenKey]: {
        chatByEventId: nextChat,
        selectedAgencyServicesByItem: nextServices,
      },
    },
  };
}

export const useShowcaseStore = create<ShowcaseState>()(
  persist(
    (set) => ({
      activeMagicToken: null,
      persistedByToken: {},

      layoutMode: "grid",
      roleFilter: "all",
      activeDrawerEventId: null,
      drawerInitialTab: "regulation",
      chatByEventId: {},
      selectedAgencyServicesByItem: {},

      bindMagicToken: (magicToken) =>
        set((state) => {
          if (state.activeMagicToken === magicToken) return state;
          const bucket = state.persistedByToken[magicToken];
          return {
            activeMagicToken: magicToken,
            activeDrawerEventId: null,
            chatByEventId: bucket ? sanitizeChatMap(bucket.chatByEventId) : {},
            selectedAgencyServicesByItem:
              bucket?.selectedAgencyServicesByItem || {},
          };
        }),

      setLayoutMode: (mode) => set({ layoutMode: mode }),
      setRoleFilter: (role) => set({ roleFilter: role }),

      openEventDrawer: (eventId, tab = "regulation") =>
        set({ activeDrawerEventId: eventId, drawerInitialTab: tab }),

      closeEventDrawer: () => set({ activeDrawerEventId: null }),

      startQuestionExchange: (eventId, id, questionText) =>
        set((state) => {
          const prev = state.chatByEventId[eventId] || [];
          const nextChat: Record<number, RegulationChatExchange[]> = {
            ...state.chatByEventId,
            [eventId]: [
              ...prev,
              {
                id,
                questionText,
                response: null,
                isLoading: true,
                error: null,
                createdAt: new Date().toLocaleTimeString("ru-RU", {
                  hour: "2-digit",
                  minute: "2-digit",
                }),
              },
            ],
          };
          return syncBucket(state, nextChat, state.selectedAgencyServicesByItem);
        }),

      completeQuestionExchange: (eventId, id, response) =>
        set((state) => {
          const prev = state.chatByEventId[eventId] || [];
          const nextChat: Record<number, RegulationChatExchange[]> = {
            ...state.chatByEventId,
            [eventId]: prev.map((item) =>
              item.id === id
                ? { ...item, response, isLoading: false, error: null }
                : item
            ),
          };
          return syncBucket(state, nextChat, state.selectedAgencyServicesByItem);
        }),

      failQuestionExchange: (eventId, id, errorMsg) =>
        set((state) => {
          const prev = state.chatByEventId[eventId] || [];
          const nextChat: Record<number, RegulationChatExchange[]> = {
            ...state.chatByEventId,
            [eventId]: prev.map((item) =>
              item.id === id
                ? { ...item, isLoading: false, error: errorMsg }
                : item
            ),
          };
          return syncBucket(state, nextChat, state.selectedAgencyServicesByItem);
        }),

      setExchangeEscalating: (eventId, exchangeId, isEscalating) =>
        set((state) => {
          const prev = state.chatByEventId[eventId] || [];
          const nextChat: Record<number, RegulationChatExchange[]> = {
            ...state.chatByEventId,
            [eventId]: prev.map((item) =>
              item.id === exchangeId ? { ...item, isEscalating } : item
            ),
          };
          return syncBucket(state, nextChat, state.selectedAgencyServicesByItem);
        }),

      setExchangeEscalated: (eventId, exchangeId) =>
        set((state) => {
          const prev = state.chatByEventId[eventId] || [];
          const nextChat: Record<number, RegulationChatExchange[]> = {
            ...state.chatByEventId,
            [eventId]: prev.map((item) =>
              item.id === exchangeId
                ? { ...item, isEscalated: true, isEscalating: false }
                : item
            ),
          };
          return syncBucket(state, nextChat, state.selectedAgencyServicesByItem);
        }),

      toggleAgencyServiceForItem: (selectionItemId, serviceTag) =>
        set((state) => {
          const current =
            state.selectedAgencyServicesByItem[selectionItemId] || [];
          const exists = current.includes(serviceTag);
          const next = exists
            ? current.filter((t) => t !== serviceTag)
            : [...current, serviceTag];
          const nextServices: Record<number, string[]> = {
            ...state.selectedAgencyServicesByItem,
            [selectionItemId]: next,
          };
          return syncBucket(state, state.chatByEventId, nextServices);
        }),
    }),
    {
      name: "skart_showcase_state_v1",
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => {
        const sanitizedTokens: Record<string, TokenPersistedBucket> = {};
        for (const [tok, bucket] of Object.entries(state.persistedByToken)) {
          if (tok === DEFAULT_TOKEN_KEY) continue;
          sanitizedTokens[tok] = {
            chatByEventId: sanitizeChatMap(bucket.chatByEventId),
            selectedAgencyServicesByItem: bucket.selectedAgencyServicesByItem,
          };
        }
        return {
          layoutMode: state.layoutMode,
          persistedByToken: sanitizedTokens,
        };
      },
    }
  )
);
