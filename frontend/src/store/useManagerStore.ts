import { create } from "zustand";
import type {
  BundleEventItemOut,
  ClientQueryExtracted,
  MatchResponseOut,
  SelectedEventTariffPairIn,
  TariffOptionOut,
} from "@/api/types";
import { checkDateConflicts, formatDateShort, formatNumberCompact } from "@/lib/formatters";

export type ManagerWorkspaceMode = "matching" | "catalog";

export interface ProducerProfile {
  id: string;
  name: string;
  role: string;
  department: string;
  avatarText: string;
  avatarBg: string;
  dealsCount: number;
}

export const PRODUCER_PROFILES: ProducerProfile[] = [
  {
    id: "ekaterina",
    name: "Екатерина Смирнова",
    role: "Старший продюсер проектов",
    department: "Девелопмент, КРТ и Урбанистика",
    avatarText: "ЕС",
    avatarBg: "bg-pine",
    dealsCount: 5,
  },
  {
    id: "alexey",
    name: "Алексей Морозов",
    role: "Head of B2B Partnerships",
    department: "IT, FinTech & Инженерия",
    avatarText: "АМ",
    avatarBg: "bg-novel-slate",
    dealsCount: 3,
  },
  {
    id: "guest",
    name: "Куратор (Демо-доступ)",
    role: "Ознакомительный доступ",
    department: "Все отраслевые направления",
    avatarText: "СК",
    avatarBg: "bg-novel-dark",
    dealsCount: 8,
  },
];

export interface ComputedBundleItem {
  item: BundleEventItemOut;
  isBonusSlot: boolean;
  isIncluded: boolean;
  selectedTariff: TariffOptionOut;
  rationale: string;
}

export interface ComputedFinancialSummary {
  rows: ComputedBundleItem[];
  includedRows: ComputedBundleItem[];
  totalActualPrice: number;
  totalBasePrice: number;
  totalSavings: number;
  earliestDeadline: string | null;
  hasOnRequestIncluded: boolean;
  hasDateConflict: boolean;
  conflictDescription: string | null;
  budgetMax: number;
  isOverBudget: boolean;
  isWithinTolerance10Pct: boolean;
  finalItemsPayload: SelectedEventTariffPairIn[];
}

interface ManagerState {
  // Профиль активного куратора (Терминал продюсера)
  currentProducer: ProducerProfile;
  isProducerModalOpen: boolean;

  // Навигация и сайдбар
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
  selectedVariantGroupByClient: Record<number, number>;
  includedEventsByClient: Record<number, Record<number, boolean>>;
  selectedTariffByClient: Record<number, Record<number, number>>;
  customRationaleByClient: Record<number, Record<number, string>>;
  pitchTextByClient: Record<number, string>;
  publishedInfoByClient: Record<
    number,
    { magicToken: string; publicUrl: string; totalPrice: number; totalSavings: number }
  >;

  // Действия
  setWorkspaceMode: (mode: ManagerWorkspaceMode) => void;
  toggleSidebar: () => void;
  selectClient: (clientId: number, initialNotes?: string) => void;
  setClientSearchQuery: (q: string) => void;
  setClientNotes: (clientId: number, notes: string) => void;
  setNotesCollapsed: (collapsed: boolean) => void;

  hydrateMatchResponse: (clientId: number, response: MatchResponseOut) => void;
  updateEditableProfile: (
    clientId: number,
    updater: (prev: ClientQueryExtracted) => ClientQueryExtracted
  ) => void;
  selectVariantGroup: (clientId: number, group: number) => void;
  toggleEventIncluded: (clientId: number, eventId: number) => void;
  changeEventTariff: (clientId: number, eventId: number, tariffId: number) => void;
  updateEventRationale: (clientId: number, eventId: number, rationale: string) => void;
  setPitchText: (clientId: number, text: string) => void;
  syncPitchNumbersWithPackage: (clientId: number, companyName: string) => void;
  setPublishedInfo: (
    clientId: number,
    info: { magicToken: string; publicUrl: string; totalPrice: number; totalSavings: number }
  ) => void;
  setProducer: (producer: ProducerProfile) => void;
  setProducerModalOpen: (open: boolean) => void;
}

export const useManagerStore = create<ManagerState>((set, get) => ({
  currentProducer: PRODUCER_PROFILES[0],
  isProducerModalOpen: false,
  workspaceMode: "matching",
  isSidebarCollapsed: false,
  selectedClientId: null,
  clientSearchQuery: "",

  notesByClient: {},
  isNotesCollapsed: false,

  matchResultByClient: {},
  editableProfileByClient: {},
  selectedVariantGroupByClient: {},
  includedEventsByClient: {},
  selectedTariffByClient: {},
  customRationaleByClient: {},
  pitchTextByClient: {},
  publishedInfoByClient: {},

  setProducer: (producer) => set({ currentProducer: producer }),
  setProducerModalOpen: (open) => set({ isProducerModalOpen: open }),

  setWorkspaceMode: (mode) => set({ workspaceMode: mode }),
  toggleSidebar: () => set((s) => ({ isSidebarCollapsed: !s.isSidebarCollapsed })),

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

  setClientSearchQuery: (q) => set({ clientSearchQuery: q }),

  setClientNotes: (clientId, notes) =>
    set((state) => ({
      notesByClient: { ...state.notesByClient, [clientId]: notes },
    })),

  setNotesCollapsed: (collapsed) => set({ isNotesCollapsed: collapsed }),

  hydrateMatchResponse: (clientId, response) =>
    set((state) => {
      const defaultGroup = response.bundle_variants[0]?.bundle_group ?? 1;
      const activeVariant =
        response.bundle_variants.find((v) => v.bundle_group === defaultGroup) ||
        response.bundle_variants[0];

      const includedMap: Record<number, boolean> = {};
      const tariffMap: Record<number, number> = {};
      const rationaleMap: Record<number, string> = {};

      for (const variant of response.bundle_variants) {
        for (const item of variant.items) {
          tariffMap[item.event_id] = item.recommended_tariff.tariff_id;
          rationaleMap[item.event_id] = item.ai_rationale;
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
        tariffMap[bonus.event_id] = bonus.recommended_tariff.tariff_id;
        rationaleMap[bonus.event_id] = bonus.ai_rationale;
      }

      return {
        isNotesCollapsed: true,
        matchResultByClient: { ...state.matchResultByClient, [clientId]: response },
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
      };
    }),

  selectVariantGroup: (clientId, group) =>
    set((state) => {
      const matchRes = state.matchResultByClient[clientId];
      if (!matchRes) return state;
      const targetVariant = matchRes.bundle_variants.find((v) => v.bundle_group === group);
      if (!targetVariant) return state;

      const newIncluded: Record<number, boolean> = {};
      const newTariffs: Record<number, number> = {
        ...(state.selectedTariffByClient[clientId] || {}),
      };

      for (const item of targetVariant.items) {
        newIncluded[item.event_id] = true;
        newTariffs[item.event_id] = item.recommended_tariff.tariff_id;
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
          [clientId]: group,
        },
        includedEventsByClient: {
          ...state.includedEventsByClient,
          [clientId]: newIncluded,
        },
        selectedTariffByClient: {
          ...state.selectedTariffByClient,
          [clientId]: newTariffs,
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
      };
    }),

  changeEventTariff: (clientId, eventId, tariffId) =>
    set((state) => {
      const currentMap = state.selectedTariffByClient[clientId] || {};
      return {
        selectedTariffByClient: {
          ...state.selectedTariffByClient,
          [clientId]: {
            ...currentMap,
            [eventId]: tariffId,
          },
        },
      };
    }),

  updateEventRationale: (clientId, eventId, rationale) =>
    set((state) => {
      const currentMap = state.customRationaleByClient[clientId] || {};
      return {
        customRationaleByClient: {
          ...state.customRationaleByClient,
          [clientId]: {
            ...currentMap,
            [eventId]: rationale,
          },
        },
      };
    }),

  setPitchText: (clientId, text) =>
    set((state) => ({
      pitchTextByClient: {
        ...state.pitchTextByClient,
        [clientId]: text,
      },
    })),

  syncPitchNumbersWithPackage: (clientId, companyName) => {
    const state = get();
    const summary = computeClientFinancialSummary(state, clientId);
    if (!summary) return;

    const matchRes = state.matchResultByClient[clientId];
    const profile = state.editableProfileByClient[clientId] || matchRes?.extracted_profile;
    const themesStr =
      profile?.themes_keywords && profile.themes_keywords.length > 0
        ? profile.themes_keywords.slice(0, 3).join(", ")
        : "ключевым отраслевым направлениям";

    const titles = summary.includedRows
      .map((r) => `«${r.item.canonical_title}» (${r.selectedTariff.tariff_name})`)
      .join(", ");

    const priceStr = formatNumberCompact(summary.totalActualPrice);
    const budgetStr = formatNumberCompact(summary.budgetMax);

    let updatedPitch =
      `Добрый день! По итогам установочной встречи подготовили для компании ${companyName} ` +
      `рекомендованный календарь профильных мероприятий по направлениям: ${themesStr}.\n\n` +
      `В согласованный план без пересечений по срокам вошли (${summary.includedRows.length}): ${titles}.\n\n` +
      `Расчет внешних расходов (взносы организаторов по выбранным тарифам) составляет ${priceStr} ₽ (с НДС) ` +
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
      `подготовку экспертного выступления спикера и организацию целевых деловых знакомств на площадках.`;

    set((s) => ({
      pitchTextByClient: {
        ...s.pitchTextByClient,
        [clientId]: updatedPitch,
      },
    }));
  },

  setPublishedInfo: (clientId, info) =>
    set((state) => ({
      publishedInfoByClient: {
        ...state.publishedInfoByClient,
        [clientId]: info,
      },
    })),
}));

/**
 * Чистая детерминированная функция расчета бюджета, экономии Early Bird и проверки календаря
 * по текущему состоянию конструктора менеджера.
 */
export function computeClientFinancialSummary(
  state: ManagerState,
  clientId: number | null
): ComputedFinancialSummary | null {
  if (!clientId) return null;
  const matchRes = state.matchResultByClient[clientId];
  if (!matchRes) return null;

  const group = state.selectedVariantGroupByClient[clientId] ?? 1;
  const activeVariant =
    matchRes.bundle_variants.find((v) => v.bundle_group === group) ||
    matchRes.bundle_variants[0];

  const includedMap = state.includedEventsByClient[clientId] || {};
  const tariffMap = state.selectedTariffByClient[clientId] || {};
  const rationaleMap = state.customRationaleByClient[clientId] || {};
  const profile =
    state.editableProfileByClient[clientId] || matchRes.extracted_profile;

  const rows: ComputedBundleItem[] = [];
  const seenEventIds = new Set<number>();

  if (activeVariant) {
    for (const item of activeVariant.items) {
      seenEventIds.add(item.event_id);
      const chosenTariffId =
        tariffMap[item.event_id] ?? item.recommended_tariff.tariff_id;
      const selectedTariff =
        item.available_tariffs.find((t) => t.tariff_id === chosenTariffId) ||
        item.recommended_tariff;

      rows.push({
        item,
        isBonusSlot: false,
        isIncluded: includedMap[item.event_id] ?? true,
        selectedTariff,
        rationale: rationaleMap[item.event_id] ?? item.ai_rationale,
      });
    }
  }

  for (const bonus of matchRes.bonus_on_request_items) {
    if (seenEventIds.has(bonus.event_id)) continue;
    const chosenTariffId =
      tariffMap[bonus.event_id] ?? bonus.recommended_tariff.tariff_id;
    const selectedTariff =
      bonus.available_tariffs.find((t) => t.tariff_id === chosenTariffId) ||
      bonus.recommended_tariff;

    rows.push({
      item: bonus,
      isBonusSlot: true,
      isIncluded: includedMap[bonus.event_id] ?? false,
      selectedTariff,
      rationale: rationaleMap[bonus.event_id] ?? bonus.ai_rationale,
    });
  }

  const includedRows = rows.filter((r) => r.isIncluded);

  let totalActualPrice = 0;
  let totalBasePrice = 0;
  let totalSavings = 0;
  let earliestDeadline: string | null = null;
  let hasOnRequestIncluded = false;

  for (const row of includedRows) {
    const t = row.selectedTariff;
    if (t.actual_price === null) {
      hasOnRequestIncluded = true;
    } else {
      totalActualPrice += t.actual_price;
      totalBasePrice += t.base_price ?? t.actual_price;
      totalSavings += t.savings || 0;
      if (t.savings > 0 && t.early_bird_deadline) {
        if (!earliestDeadline || t.early_bird_deadline < earliestDeadline) {
          earliestDeadline = t.early_bird_deadline;
        }
      }
    }
  }

  const conflictCheck = checkDateConflicts(
    includedRows.map((r) => ({
      event_id: r.item.event_id,
      canonical_title: r.item.canonical_title,
      start_date: r.item.start_date,
      end_date: r.item.end_date,
      is_online: r.item.is_online,
    }))
  );

  const budgetMax = profile.total_budget_max || 0;
  const isOverBudget = budgetMax > 0 && totalActualPrice > budgetMax;
  const isWithinTolerance10Pct =
    isOverBudget && totalActualPrice <= budgetMax * 1.1;

  const finalItemsPayload: SelectedEventTariffPairIn[] = includedRows.map((r) => ({
    event_id: r.item.event_id,
    tariff_id: r.selectedTariff.tariff_id,
    ai_rationale: r.rationale,
  }));

  return {
    rows,
    includedRows,
    totalActualPrice: Math.round(totalActualPrice),
    totalBasePrice: Math.round(totalBasePrice),
    totalSavings: Math.round(totalSavings),
    earliestDeadline,
    hasOnRequestIncluded,
    hasDateConflict: conflictCheck.hasConflict,
    conflictDescription: conflictCheck.conflictDescription,
    budgetMax,
    isOverBudget,
    isWithinTolerance10Pct,
    finalItemsPayload,
  };
}

