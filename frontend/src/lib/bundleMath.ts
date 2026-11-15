import type {
  BundleEventItemOut,
  ClientQueryExtracted,
  MatchResponseOut,
  SelectedEventTariffPairIn,
  TariffOptionOut,
} from "@/api/types";
import { checkDateConflicts } from "@/lib/formatters";

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

export interface BundleCalculationState {
  matchResultByClient: Record<number, MatchResponseOut>;
  selectedVariantGroupByClient: Record<number, 1 | 2>;
  includedEventsByClient: Record<number, Record<number, boolean>>;
  selectedTariffByClient: Record<number, Record<string, number>>;
  customRationaleByClient: Record<number, Record<string, string>>;
  editableProfileByClient: Record<number, ClientQueryExtracted>;
}

/** Ключ слота для основного мероприятия варианта (изолирует Вариант 1 и Вариант 2). */
export function variantItemKey(group: 1 | 2, eventId: number): string {
  return `${group}:${eventId}`;
}

/** Ключ слота для бонусного мероприятия по запросу. */
export function bonusItemKey(eventId: number): string {
  return `bonus:${eventId}`;
}

/** Нормализация номера группы варианта пакета к 1 | 2. */
export function normalizeBundleGroup(group: number): 1 | 2 {
  return group === 2 ? 2 : 1;
}

function resolveActiveVariant(
  matchRes: MatchResponseOut,
  requestedGroup: number
) {
  const activeVariant =
    matchRes.bundle_variants.find((v) => v.bundle_group === requestedGroup) ||
    matchRes.bundle_variants[0];
  const resolvedGroup = normalizeBundleGroup(
    activeVariant?.bundle_group ?? requestedGroup
  );
  return { activeVariant, resolvedGroup };
}

/** Определяет ключ слота (вариант или бонус) для мероприятия в активной подборке клиента. */
export function resolveSlotKeyForActiveEvent(
  state: Pick<
    BundleCalculationState,
    "matchResultByClient" | "selectedVariantGroupByClient"
  >,
  clientId: number,
  eventId: number
): string {
  const activeGroup = state.selectedVariantGroupByClient[clientId] ?? 1;
  const matchRes = state.matchResultByClient[clientId];
  if (!matchRes) {
    return bonusItemKey(eventId);
  }
  const { activeVariant, resolvedGroup } = resolveActiveVariant(
    matchRes,
    activeGroup
  );
  const inVariant = activeVariant?.items.some((i) => i.event_id === eventId);
  return inVariant
    ? variantItemKey(resolvedGroup, eventId)
    : bonusItemKey(eventId);
}

function buildComputedBundleRow(
  item: BundleEventItemOut,
  slotKey: string,
  isBonusSlot: boolean,
  defaultIncluded: boolean,
  includedMap: Record<number, boolean>,
  tariffMap: Record<string, number>,
  rationaleMap: Record<string, string>
): ComputedBundleItem {
  const chosenTariffId = tariffMap[slotKey] ?? item.recommended_tariff.tariff_id;
  const selectedTariff =
    item.available_tariffs.find((t) => t.tariff_id === chosenTariffId) ||
    item.recommended_tariff;

  return {
    item,
    isBonusSlot,
    isIncluded: includedMap[item.event_id] ?? defaultIncluded,
    selectedTariff,
    rationale: rationaleMap[slotKey] ?? item.ai_rationale,
  };
}

/**
 * Чистая детерминированная функция расчета бюджета, экономии Early Bird и проверки календаря
 * по текущему состоянию конструктора менеджера.
 */
export function computeClientFinancialSummary(
  state: BundleCalculationState,
  clientId: number | null
): ComputedFinancialSummary | null {
  if (!clientId) return null;
  const matchRes = state.matchResultByClient[clientId];
  if (!matchRes) return null;

  const requestedGroup = state.selectedVariantGroupByClient[clientId] ?? 1;
  const { activeVariant, resolvedGroup } = resolveActiveVariant(
    matchRes,
    requestedGroup
  );

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
      const slotKey = variantItemKey(resolvedGroup, item.event_id);
      rows.push(
        buildComputedBundleRow(
          item,
          slotKey,
          false,
          true,
          includedMap,
          tariffMap,
          rationaleMap
        )
      );
    }
  }

  for (const bonus of matchRes.bonus_on_request_items) {
    if (seenEventIds.has(bonus.event_id)) continue;
    const bKey = bonusItemKey(bonus.event_id);
    rows.push(
      buildComputedBundleRow(
        bonus,
        bKey,
        true,
        false,
        includedMap,
        tariffMap,
        rationaleMap
      )
    );
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

  const finalItemsPayload: SelectedEventTariffPairIn[] = includedRows.map(
    (r) => ({
      event_id: r.item.event_id,
      tariff_id: r.selectedTariff.tariff_id,
      ai_rationale: r.rationale,
    })
  );

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
