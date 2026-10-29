import { create } from "zustand";
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
}

interface ShowcaseState {
  layoutMode: ShowcaseLayoutMode;
  roleFilter: ShowcaseRoleFilter;

  // Выдвижная панель «Паспорт участия и ИИ-консультант по регламенту»
  activeDrawerEventId: number | null;
  drawerInitialTab: "regulation" | "benefits";

  // Сохраненная история вопросов/ответов по каждому event_id (не теряется при закрытии Drawer)
  chatByEventId: Record<number, RegulationChatExchange[]>;

  // Выбранные услуги сопровождения агентства (Этап 09) по каждому selection_item_id
  selectedAgencyServicesByItem: Record<number, string[]>;

  setLayoutMode: (mode: ShowcaseLayoutMode) => void;
  setRoleFilter: (role: ShowcaseRoleFilter) => void;
  openEventDrawer: (eventId: number, tab?: "regulation" | "benefits") => void;
  closeEventDrawer: () => void;

  startQuestionExchange: (eventId: number, id: string, questionText: string) => void;
  completeQuestionExchange: (
    eventId: number,
    id: string,
    response: AskRegulationQuestionOut
  ) => void;
  failQuestionExchange: (eventId: number, id: string, errorMsg: string) => void;

  toggleAgencyServiceForItem: (selectionItemId: number, serviceTag: string) => void;
}

export const useShowcaseStore = create<ShowcaseState>((set) => ({
  layoutMode: "carousel",
  roleFilter: "all",
  activeDrawerEventId: null,
  drawerInitialTab: "regulation",
  chatByEventId: {},
  selectedAgencyServicesByItem: {},

  setLayoutMode: (mode) => set({ layoutMode: mode }),
  setRoleFilter: (role) => set({ roleFilter: role }),

  openEventDrawer: (eventId, tab = "regulation") =>
    set({ activeDrawerEventId: eventId, drawerInitialTab: tab }),

  closeEventDrawer: () => set({ activeDrawerEventId: null }),

  startQuestionExchange: (eventId, id, questionText) =>
    set((state) => {
      const prev = state.chatByEventId[eventId] || [];
      return {
        chatByEventId: {
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
        },
      };
    }),

  completeQuestionExchange: (eventId, id, response) =>
    set((state) => {
      const prev = state.chatByEventId[eventId] || [];
      return {
        chatByEventId: {
          ...state.chatByEventId,
          [eventId]: prev.map((item) =>
            item.id === id ? { ...item, response, isLoading: false, error: null } : item
          ),
        },
      };
    }),

  failQuestionExchange: (eventId, id, errorMsg) =>
    set((state) => {
      const prev = state.chatByEventId[eventId] || [];
      return {
        chatByEventId: {
          ...state.chatByEventId,
          [eventId]: prev.map((item) =>
            item.id === id ? { ...item, isLoading: false, error: errorMsg } : item
          ),
        },
      };
    }),

  toggleAgencyServiceForItem: (selectionItemId, serviceTag) =>
    set((state) => {
      const current = state.selectedAgencyServicesByItem[selectionItemId] || [];
      const exists = current.includes(serviceTag);
      const next = exists
        ? current.filter((t) => t !== serviceTag)
        : [...current, serviceTag];
      return {
        selectedAgencyServicesByItem: {
          ...state.selectedAgencyServicesByItem,
          [selectionItemId]: next,
        },
      };
    }),
}));

