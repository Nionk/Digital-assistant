import { create } from "zustand";
import { createJSONStorage, persist, type StateStorage } from "zustand/middleware";
import type {
  ClientQueryExtracted,
  ClientWorkspaceOut,
  MatchResponseOut,
  ShowcaseViewOut,
} from "@/api/types";
import {
  bonusItemKey,
  computeClientFinancialSummary,
  normalizeBundleGroup,
  resolveSlotKeyForActiveEvent,
  variantItemKey,
  type ComputedBundleItem,
  type ComputedFinancialSummary,
} from "@/lib/bundleMath";
import { formatDateShort, formatNumberCompact } from "@/lib/formatters";
import { useAuthStore } from "@/store/useAuthStore";

export type { ComputedBundleItem, ComputedFinancialSummary };
export { computeClientFinancialSummary };

export type ManagerWorkspaceMode = "matching" | "catalog";

export interface PublishedSelectionInfo {
  selectionId?: number | null;
  magicToken: string;
  publicUrl: string;
  totalPrice: number;
  totalSavings: number;
}

interface ManagerState {
  // Модалка профиля текущей JWT-сессии
  isProducerModalOpen: boolean;

  // Навигация и поиск клиентов
  workspaceMode: ManagerWorkspaceMode;
  isSidebarCollapsed: boolean;
  selectedClientId: number | null;
  clientSearchQuery: string;

  // Черновики заметок и свернутость конспекта по клиентам
  notesByClient: Record<number, string>;
  isNotesCollapsed: boolean;

  // Результаты последнего подбора по каждому client_id
  matchResultByClient: Record<number, MatchResponseOut>;
  editableProfileByClient: Record<number, ClientQueryExtracted>;

  // Выбранный вариант пакета (1 или 2) и тонкая настройка конструктора
  selectedVariantGroupByClient: Record<number, 1 | 2>;
  includedEventsByClient: Record<number, Record<number, boolean>>;
  // Ключ вида `${bundleGroup}:${eventId}` или `bonus:${eventId}` исключает затирание Варианта 1 Вариантом 2
  selectedTariffByClient: Record<number, Record<string, number>>;
  customRationaleByClient: Record<number, Record<string, string>>;
  pitchTextByClient: Record<number, string>;
  publishedInfoByClient: Record<number, PublishedSelectionInfo>;

  // Неперсистируемая защита сессии от перезаписи несохраненного локального черновика
  sessionMatchedSelectionByClient: Record<number, number>;
  sessionDirtyDraftByClient: Record<number, boolean>;

  // Целевое мероприятие для перехода в Базу площадок
  catalogTargetEventId: number | null;

  // Действия
  setWorkspaceMode: (mode: ManagerWorkspaceMode) => void;
  navigateToCatalogEvent: (eventId: number) => void;
  setCatalogTargetEventId: (eventId: number | null) => void;
  toggleSidebar: () => void;
  selectClient: (clientId: number, initialNotes?: string) => void;
  clearSelectedClient: () => void;
  removeClientWorkspace: (clientId: number) => void;
  setClientSearchQuery: (q: string) => void;
  setClientNotes: (clientId: number, notes: string) => void;
  syncClientNotes: (clientId: number, notes: string) => void;
  setNotesCollapsed: (collapsed: boolean) => void;

  hydrateMatchResponse: (clientId: number, response: MatchResponseOut) => void;
  hydrateServerWorkspace: (
    clientId: number,
    workspace: ClientWorkspaceOut
  ) => void;
  hydratePublishedShowcase: (
    clientId: number,
    magicToken: string,
    showcase: ShowcaseViewOut
  ) => void;
  updateEditableProfile: (
    clientId: number,
    updater: (prev: ClientQueryExtracted) => ClientQueryExtracted
  ) => void;
  selectVariantGroup: (clientId: number, group: number) => void;
  toggleEventIncluded: (clientId: number, eventId: number) => void;
  changeEventTariff: (clientId: number, eventId: number, tariffId: number) => void;
  updateEventRationale: (
    clientId: number,
    eventId: number,
    rationale: string
  ) => void;
  setPitchText: (clientId: number, text: string) => void;
  syncPitchNumbersWithPackage: (clientId: number, companyName: string) => void;
  setPublishedInfo: (clientId: number, info: PublishedSelectionInfo) => void;
  setProducerModalOpen: (open: boolean) => void;
  resetWorkspaceMemory: () => void;
}

const INITIAL_MANAGER_PERSISTED_DATA = {
  workspaceMode: "matching" as ManagerWorkspaceMode,
  isSidebarCollapsed: true,
  selectedClientId: null as number | null,
  notesByClient: {} as Record<number, string>,
  isNotesCollapsed: false,
  matchResultByClient: {} as Record<number, MatchResponseOut>,
  editableProfileByClient: {} as Record<number, ClientQueryExtracted>,
  selectedVariantGroupByClient: {} as Record<number, 1 | 2>,
  includedEventsByClient: {} as Record<number, Record<number, boolean>>,
  selectedTariffByClient: {} as Record<number, Record<string, number>>,
  customRationaleByClient: {} as Record<number, Record<string, string>>,
  pitchTextByClient: {} as Record<number, string>,
  publishedInfoByClient: {} as Record<number, PublishedSelectionInfo>,
};

function buildHydratedSelectionMaps(response: MatchResponseOut): {
  defaultGroup: 1 | 2;
  includedMap: Record<number, boolean>;
  tariffMap: Record<string, number>;
  rationaleMap: Record<string, string>;
} {
  const defaultGroup = normalizeBundleGroup(
    response.bundle_variants[0]?.bundle_group ?? 1
  );
  const activeVariant =
    response.bundle_variants.find((v) => v.bundle_group === defaultGroup) ||
    response.bundle_variants[0];

  const includedMap: Record<number, boolean> = {};
  const tariffMap: Record<string, number> = {};
  const rationaleMap: Record<string, string> = {};

  for (const variant of response.bundle_variants) {
    const vGroup = normalizeBundleGroup(variant.bundle_group);
    for (const item of variant.items) {
      const key = variantItemKey(vGroup, item.event_id);
      tariffMap[key] = item.recommended_tariff.tariff_id;
      rationaleMap[key] = item.ai_rationale;
    }
  }

  if (activeVariant) {
    for (const item of activeVariant.items) {
      includedMap[item.event_id] = true;
    }
  }

  for (const bonus of response.bonus_on_request_items) {
    if (includedMap[bonus.event_id] === undefined) {
      includedMap[bonus.event_id] = false;
    }
    const bKey = bonusItemKey(bonus.event_id);
    tariffMap[bKey] = bonus.recommended_tariff.tariff_id;
    rationaleMap[bKey] = bonus.ai_rationale;
  }

  return { defaultGroup, includedMap, tariffMap, rationaleMap };
}

function omitClientKey<T>(
  record: Record<number, T>,
  clientId: number
): Record<number, T> {
  if (!(clientId in record)) return record;
  const next = { ...record };
  delete next[clientId];
  return next;
}

function buildFallbackProfileFromWorkspace(
  workspace: ClientWorkspaceOut
): ClientQueryExtracted {
  const sel = workspace.selection;
  const itemCount = sel?.bundle_variants[0]?.items.length || 3;
  return {
    cities: [],
    include_online: true,
    date_from: null,
    date_to: null,
    total_budget_max:
      sel && sel.total_budget_limit > 0 ? sel.total_budget_limit : 300000,
    target_events_count: Math.max(1, Math.min(10, itemCount)),
    preferred_formats: [],
    required_roles: ["delegate"],
    min_speaker_events: 0,
    themes_keywords: [],
    semantic_search_query:
      workspace.raw_manager_notes.trim() || "деловые мероприятия",
    budget_is_assumed: true,
    profile_source: "heuristic",
  };
}

const userScopedManagerStorage: StateStorage = {
  getItem: (name) => {
    const userId = useAuthStore.getState().user?.id;
    if (!userId || typeof window === "undefined") return null;
    return window.localStorage.getItem(`${name}_u_${userId}`);
  },
  setItem: (name, value) => {
    const userId = useAuthStore.getState().user?.id;
    if (!userId || typeof window === "undefined") return;
    window.localStorage.setItem(`${name}_u_${userId}`, value);
  },
  removeItem: (name) => {
    const userId = useAuthStore.getState().user?.id;
    if (!userId || typeof window === "undefined") return;
    window.localStorage.removeItem(`${name}_u_${userId}`);
  },
};

export const useManagerStore = create<ManagerState>()(
  persist(
    (set, get) => ({
      isProducerModalOpen: false,
      clientSearchQuery: "",
      catalogTargetEventId: null,
      sessionMatchedSelectionByClient: {},
      sessionDirtyDraftByClient: {},
      ...INITIAL_MANAGER_PERSISTED_DATA,

      setProducerModalOpen: (open) => set({ isProducerModalOpen: open }),

      setWorkspaceMode: (mode) => set({ workspaceMode: mode }),
      navigateToCatalogEvent: (eventId) =>
        set({ workspaceMode: "catalog", catalogTargetEventId: eventId }),
      setCatalogTargetEventId: (eventId) =>
        set({ catalogTargetEventId: eventId }),
      toggleSidebar: () =>
        set((s) => ({ isSidebarCollapsed: !s.isSidebarCollapsed })),

      selectClient: (clientId, initialNotes) =>
        set((state) => {
          const existingNotes = state.notesByClient[clientId];
          const hasMatch = Boolean(state.matchResultByClient[clientId]);
          return {
            selectedClientId: clientId,
            isNotesCollapsed: hasMatch,
            notesByClient:
              existingNotes === undefined && initialNotes !== undefined
                ? { ...state.notesByClient, [clientId]: initialNotes }
                : state.notesByClient,
          };
        }),

      clearSelectedClient: () => set({ selectedClientId: null }),

      removeClientWorkspace: (clientId) =>
        set((state) => ({
          selectedClientId:
            state.selectedClientId === clientId ? null : state.selectedClientId,
          notesByClient: omitClientKey(state.notesByClient, clientId),
          matchResultByClient: omitClientKey(state.matchResultByClient, clientId),
          editableProfileByClient: omitClientKey(
            state.editableProfileByClient,
            clientId
          ),
          selectedVariantGroupByClient: omitClientKey(
            state.selectedVariantGroupByClient,
            clientId
          ),
          includedEventsByClient: omitClientKey(
            state.includedEventsByClient,
            clientId
          ),
          selectedTariffByClient: omitClientKey(
            state.selectedTariffByClient,
            clientId
          ),
          customRationaleByClient: omitClientKey(
            state.customRationaleByClient,
            clientId
          ),
          pitchTextByClient: omitClientKey(state.pitchTextByClient, clientId),
          publishedInfoByClient: omitClientKey(
            state.publishedInfoByClient,
            clientId
          ),
          sessionMatchedSelectionByClient: omitClientKey(
            state.sessionMatchedSelectionByClient,
            clientId
          ),
          sessionDirtyDraftByClient: omitClientKey(
            state.sessionDirtyDraftByClient,
            clientId
          ),
        })),

      setClientSearchQuery: (q) => set({ clientSearchQuery: q }),

      setClientNotes: (clientId, notes) =>
        set((state) => ({
          notesByClient: { ...state.notesByClient, [clientId]: notes },
        })),

      syncClientNotes: (clientId, notes) =>
        set((state) => ({
          notesByClient: { ...state.notesByClient, [clientId]: notes },
        })),

      setNotesCollapsed: (collapsed) => set({ isNotesCollapsed: collapsed }),

      hydrateMatchResponse: (clientId, response) =>
        set((state) => {
          const { defaultGroup, includedMap, tariffMap, rationaleMap } =
            buildHydratedSelectionMaps(response);

          return {
            isNotesCollapsed: true,
            matchResultByClient: {
              ...state.matchResultByClient,
              [clientId]: response,
            },
            editableProfileByClient: {
              ...state.editableProfileByClient,
              [clientId]: structuredClone(response.extracted_profile),
            },
            selectedVariantGroupByClient: {
              ...state.selectedVariantGroupByClient,
              [clientId]: defaultGroup,
            },
            includedEventsByClient: {
              ...state.includedEventsByClient,
              [clientId]: includedMap,
            },
            selectedTariffByClient: {
              ...state.selectedTariffByClient,
              [clientId]: tariffMap,
            },
            customRationaleByClient: {
              ...state.customRationaleByClient,
              [clientId]: rationaleMap,
            },
            pitchTextByClient: {
              ...state.pitchTextByClient,
              [clientId]: response.generated_pitch_text,
            },
            sessionMatchedSelectionByClient: {
              ...state.sessionMatchedSelectionByClient,
              [clientId]: response.selection_id,
            },
            sessionDirtyDraftByClient: {
              ...state.sessionDirtyDraftByClient,
              [clientId]: false,
            },
          };
        }),

      hydrateServerWorkspace: (clientId, workspace) =>
        set((state) => {
          if (workspace.client_id !== clientId) return state;

          const existingNotes = state.notesByClient[clientId];
          const nextNotesByClient =
            existingNotes === undefined
              ? { ...state.notesByClient, [clientId]: workspace.raw_manager_notes }
              : state.notesByClient;

          const srvSel = workspace.selection;
          if (!srvSel) {
            const shouldFillProfile =
              Boolean(workspace.extracted_profile) &&
              !state.editableProfileByClient[clientId];
            if (!shouldFillProfile && nextNotesByClient === state.notesByClient) {
              return state;
            }
            return {
              notesByClient: nextNotesByClient,
              ...(shouldFillProfile && workspace.extracted_profile
                ? {
                    editableProfileByClient: {
                      ...state.editableProfileByClient,
                      [clientId]: structuredClone(workspace.extracted_profile),
                    },
                  }
                : {}),
            };
          }

          const existingMatch = state.matchResultByClient[clientId];
          const existingPublished = state.publishedInfoByClient[clientId];
          const sessionMatchedId =
            state.sessionMatchedSelectionByClient[clientId];
          const isDirty = Boolean(state.sessionDirtyDraftByClient[clientId]);

          let shouldHydrateSelection = false;
          if (!existingMatch) {
            shouldHydrateSelection = true;
          } else if (
            sessionMatchedId === existingMatch.selection_id &&
            srvSel.selection_id <= existingMatch.selection_id
          ) {
            shouldHydrateSelection = false;
          } else if (srvSel.selection_id > existingMatch.selection_id) {
            shouldHydrateSelection = true;
          } else if (
            srvSel.selection_id === existingMatch.selection_id &&
            srvSel.status === "published" &&
            existingPublished?.selectionId !== srvSel.selection_id &&
            !isDirty
          ) {
            shouldHydrateSelection = true;
          }

          const v1 =
            srvSel.bundle_variants.find((v) => v.bundle_group === 1) ??
            srvSel.bundle_variants[0];
          const serverPublishedInfo: PublishedSelectionInfo | null =
            srvSel.status === "published" && srvSel.magic_token
              ? {
                  selectionId: srvSel.selection_id,
                  magicToken: srvSel.magic_token,
                  publicUrl: `/s/${srvSel.magic_token}`,
                  totalPrice: v1?.total_actual_price ?? 0,
                  totalSavings: v1?.total_savings ?? 0,
                }
              : null;

          if (!shouldHydrateSelection) {
            const shouldSyncPubOnly =
              serverPublishedInfo !== null &&
              existingMatch?.selection_id === srvSel.selection_id &&
              existingPublished?.selectionId !== srvSel.selection_id;
            if (!shouldSyncPubOnly && nextNotesByClient === state.notesByClient) {
              return state;
            }
            return {
              notesByClient: nextNotesByClient,
              ...(shouldSyncPubOnly && serverPublishedInfo
                ? {
                    publishedInfoByClient: {
                      ...state.publishedInfoByClient,
                      [clientId]: serverPublishedInfo,
                    },
                  }
                : {}),
            };
          }

          const resolvedProfile =
            workspace.extracted_profile ??
            buildFallbackProfileFromWorkspace(workspace);
          const matchResponse: MatchResponseOut = {
            selection_id: srvSel.selection_id,
            client_id: clientId,
            extracted_profile: resolvedProfile,
            bundle_variants: srvSel.bundle_variants,
            bonus_on_request_items: srvSel.bonus_on_request_items,
            generated_pitch_text: srvSel.generated_pitch_text,
          };
          const { defaultGroup, includedMap, tariffMap, rationaleMap } =
            buildHydratedSelectionMaps(matchResponse);

          const nextPublishedByClient = serverPublishedInfo
            ? {
                ...state.publishedInfoByClient,
                [clientId]: serverPublishedInfo,
              }
            : omitClientKey(state.publishedInfoByClient, clientId);

          return {
            isNotesCollapsed: state.selectedClientId === clientId ? true : state.isNotesCollapsed,
            notesByClient: nextNotesByClient,
            matchResultByClient: {
              ...state.matchResultByClient,
              [clientId]: matchResponse,
            },
            editableProfileByClient: {
              ...state.editableProfileByClient,
              [clientId]: structuredClone(resolvedProfile),
            },
            selectedVariantGroupByClient: {
              ...state.selectedVariantGroupByClient,
              [clientId]: defaultGroup,
            },
            includedEventsByClient: {
              ...state.includedEventsByClient,
              [clientId]: includedMap,
            },
            selectedTariffByClient: {
              ...state.selectedTariffByClient,
              [clientId]: tariffMap,
            },
            customRationaleByClient: {
              ...state.customRationaleByClient,
              [clientId]: rationaleMap,
            },
            pitchTextByClient: {
              ...state.pitchTextByClient,
              [clientId]: srvSel.generated_pitch_text,
            },
            publishedInfoByClient: nextPublishedByClient,
            sessionDirtyDraftByClient: {
              ...state.sessionDirtyDraftByClient,
              [clientId]: false,
            },
          };
        }),

      hydratePublishedShowcase: (clientId, magicToken, showcase) =>
        set((state) => {
          const existing = state.publishedInfoByClient[clientId];
          if (
            existing &&
            existing.magicToken === magicToken &&
            existing.selectionId === showcase.selection_id &&
            existing.totalPrice === showcase.total_actual_price &&
            existing.totalSavings === showcase.total_savings
          ) {
            return state;
          }
          return {
            publishedInfoByClient: {
              ...state.publishedInfoByClient,
              [clientId]: {
                selectionId: showcase.selection_id,
                magicToken,
                publicUrl: `/s/${magicToken}`,
                totalPrice: showcase.total_actual_price,
                totalSavings: showcase.total_savings,
              },
            },
          };
        }),

      updateEditableProfile: (clientId, updater) =>
        set((state) => {
          const current = state.editableProfileByClient[clientId];
          if (!current) return state;
          return {
            editableProfileByClient: {
              ...state.editableProfileByClient,
              [clientId]: updater(current),
            },
            sessionDirtyDraftByClient: {
              ...state.sessionDirtyDraftByClient,
              [clientId]: true,
            },
          };
        }),

      selectVariantGroup: (clientId, group) =>
        set((state) => {
          const normalizedGroup = normalizeBundleGroup(group);
          const matchRes = state.matchResultByClient[clientId];
          if (!matchRes) return state;
          const targetVariant = matchRes.bundle_variants.find(
            (v) => v.bundle_group === normalizedGroup
          );
          if (!targetVariant) return state;

          const newIncluded: Record<number, boolean> = {};
          for (const item of targetVariant.items) {
            newIncluded[item.event_id] = true;
          }

          // Сохраняем состояние галочек бонусных событий
          for (const bonus of matchRes.bonus_on_request_items) {
            const prevBonusIncluded =
              state.includedEventsByClient[clientId]?.[bonus.event_id] ?? false;
            newIncluded[bonus.event_id] = prevBonusIncluded;
          }

          return {
            selectedVariantGroupByClient: {
              ...state.selectedVariantGroupByClient,
              [clientId]: normalizedGroup,
            },
            includedEventsByClient: {
              ...state.includedEventsByClient,
              [clientId]: newIncluded,
            },
            sessionDirtyDraftByClient: {
              ...state.sessionDirtyDraftByClient,
              [clientId]: true,
            },
          };
        }),

      toggleEventIncluded: (clientId, eventId) =>
        set((state) => {
          const currentMap = state.includedEventsByClient[clientId] || {};
          return {
            includedEventsByClient: {
              ...state.includedEventsByClient,
              [clientId]: {
                ...currentMap,
                [eventId]: !currentMap[eventId],
              },
            },
            sessionDirtyDraftByClient: {
              ...state.sessionDirtyDraftByClient,
              [clientId]: true,
            },
          };
        }),

      changeEventTariff: (clientId, eventId, tariffId) =>
        set((state) => {
          const slotKey = resolveSlotKeyForActiveEvent(
            state,
            clientId,
            eventId
          );
          const currentMap = state.selectedTariffByClient[clientId] || {};
          return {
            selectedTariffByClient: {
              ...state.selectedTariffByClient,
              [clientId]: {
                ...currentMap,
                [slotKey]: tariffId,
              },
            },
            sessionDirtyDraftByClient: {
              ...state.sessionDirtyDraftByClient,
              [clientId]: true,
            },
          };
        }),

      updateEventRationale: (clientId, eventId, rationale) =>
        set((state) => {
          const slotKey = resolveSlotKeyForActiveEvent(
            state,
            clientId,
            eventId
          );
          const currentMap = state.customRationaleByClient[clientId] || {};
          return {
            customRationaleByClient: {
              ...state.customRationaleByClient,
              [clientId]: {
                ...currentMap,
                [slotKey]: rationale,
              },
            },
            sessionDirtyDraftByClient: {
              ...state.sessionDirtyDraftByClient,
              [clientId]: true,
            },
          };
        }),

      setPitchText: (clientId, text) =>
        set((state) => ({
          pitchTextByClient: {
            ...state.pitchTextByClient,
            [clientId]: text,
          },
          sessionDirtyDraftByClient: {
            ...state.sessionDirtyDraftByClient,
            [clientId]: true,
          },
        })),

      /**
       * Детерминированное обновление итоговых цифр и состава мероприятий в тексте КП
       * по текущему состоянию конструктора (без имитации ИИ-генерации).
       */
      syncPitchNumbersWithPackage: (clientId, companyName) => {
        const state = get();
        const summary = computeClientFinancialSummary(state, clientId);
        if (!summary) return;

        const matchRes = state.matchResultByClient[clientId];
        const profile =
          state.editableProfileByClient[clientId] ||
          matchRes?.extracted_profile;
        const cleanThemes = (profile?.themes_keywords ?? [])
          .map((t) => t.trim())
          .filter(Boolean)
          .slice(0, 3);
        const themesClause =
          cleanThemes.length > 0
            ? `по направлениям: ${cleanThemes.join(", ")}`
            : "по ключевым отраслевым направлениям";

        const titles = summary.includedRows
          .map(
            (r) =>
              `«${r.item.canonical_title}» (${r.selectedTariff.tariff_name})`
          )
          .join(", ");

        const priceStr = formatNumberCompact(summary.totalActualPrice);
        const budgetStr = formatNumberCompact(summary.budgetMax);
        const onRequestSuffix = summary.hasOnRequestIncluded
          ? " (+ спецпроект по запросу)"
          : "";

        let updatedPitch =
          `Добрый день! По итогам установочной встречи подготовили для компании ${companyName} ` +
          `рекомендованный календарь профильных мероприятий ${themesClause}.\n\n` +
          `В согласованный план вошли (${summary.includedRows.length}): ${titles}.\n\n` +
          `Расчет внешних расходов (взносы организаторов по выбранным тарифам) составляет ${priceStr} ₽ (с НДС)${onRequestSuffix} ` +
          `при ориентире бюджета ${budgetStr} ₽.`;

        if (summary.totalSavings > 0 && summary.earliestDeadline) {
          const savingsStr = formatNumberCompact(summary.totalSavings);
          const baseStr = formatNumberCompact(summary.totalBasePrice);
          const dlStr = formatDateShort(summary.earliestDeadline);
          updatedPitch +=
            ` При подтверждении участия до ${dlStr} действуют льготные условия Early Bird и партнёрские преференции — ` +
            `прямая выгода составит ${savingsStr} ₽ (базовая стоимость без скидки — ${baseStr} ₽).`;
        }

        updatedPitch +=
          `\n\nСо стороны агентства мы берем на себя согласование условий с организаторами, ` +
          `подготовку участия и организацию целевых деловых знакомств на площадках.`;

        set((s) => ({
          pitchTextByClient: {
            ...s.pitchTextByClient,
            [clientId]: updatedPitch,
          },
          sessionDirtyDraftByClient: {
            ...s.sessionDirtyDraftByClient,
            [clientId]: true,
          },
        }));
      },

      setPublishedInfo: (clientId, info) =>
        set((state) => ({
          publishedInfoByClient: {
            ...state.publishedInfoByClient,
            [clientId]: info,
          },
          sessionDirtyDraftByClient: {
            ...state.sessionDirtyDraftByClient,
            [clientId]: false,
          },
        })),

      resetWorkspaceMemory: () =>
        set({
          isProducerModalOpen: false,
          clientSearchQuery: "",
          catalogTargetEventId: null,
          sessionMatchedSelectionByClient: {},
          sessionDirtyDraftByClient: {},
          ...INITIAL_MANAGER_PERSISTED_DATA,
        }),
    }),
    {
      name: "skart_manager_workspace_v1",
      storage: createJSONStorage(() => userScopedManagerStorage),
      partialize: (state) => ({
        workspaceMode: state.workspaceMode,
        isSidebarCollapsed: state.isSidebarCollapsed,
        selectedClientId: state.selectedClientId,
        notesByClient: state.notesByClient,
        isNotesCollapsed: state.isNotesCollapsed,
        matchResultByClient: state.matchResultByClient,
        editableProfileByClient: state.editableProfileByClient,
        selectedVariantGroupByClient: state.selectedVariantGroupByClient,
        includedEventsByClient: state.includedEventsByClient,
        selectedTariffByClient: state.selectedTariffByClient,
        customRationaleByClient: state.customRationaleByClient,
        pitchTextByClient: state.pitchTextByClient,
        publishedInfoByClient: state.publishedInfoByClient,
      }),
    }
  )
);

// Изолируем стор в памяти при входе/выходе/смене JWT-пользователя
useAuthStore.subscribe((state, prevState) => {
  const nextUserId = state.user?.id ?? null;
  const prevUserId = prevState.user?.id ?? null;
  if (nextUserId === prevUserId) return;

  useManagerStore.getState().resetWorkspaceMemory();
  if (nextUserId !== null) {
    void useManagerStore.persist.rehydrate();
  }
});
