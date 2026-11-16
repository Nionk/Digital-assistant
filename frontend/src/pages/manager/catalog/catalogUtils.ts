import type { CatalogEventItemOut } from "@/api/types";
import type { MultiSelectOption } from "@/components/ui/searchable-multi-select-popover";
import { formatMinPrice } from "@/lib/formatters";

export const FORMAT_OPTIONS = [
  { value: "all", label: "Все форматы" },
  { value: "forum", label: "Форумы" },
  { value: "conference", label: "Конференции" },
  { value: "roundtable", label: "Круглые столы" },
  { value: "business_breakfast", label: "Деловые завтраки" },
  { value: "session", label: "Сессии" },
];

export const DATA_STATUS_OPTIONS = [
  { value: "all", label: "Все статусы" },
  { value: "ready", label: "Готовы к КП" },
  { value: "needs_enrichment", label: "Требуют обогащения" },
];

export const SORT_OPTIONS = [
  { value: "date_asc", label: "Ближайшие по дате" },
  { value: "date_desc", label: "Поздние по дате" },
  { value: "price_asc", label: "Сначала доступные (по цене)" },
  { value: "price_desc", label: "Сначала премиальные (по цене)" },
  { value: "savings_desc", label: "Выгода Early Bird" },
];

export function getEventMinPrice(ev: CatalogEventItemOut): number | null {
  return ev.tariffs.reduce<number | null>((acc, t) => {
    if (t.actual_price === null) return acc;
    if (acc === null) return t.actual_price;
    return Math.min(acc, t.actual_price);
  }, null);
}

export interface EventPriceSummary {
  minPrice: number | null;
  hasFreeTariff: boolean;
  hasPaidTariff: boolean;
  hasOnRequestTariff: boolean;
  label: string;
  subLabel: string | null;
}

/**
 * Формирует честную сводку минимальной цены мероприятия, уточняя наличие платных
 * или «По запросу» тарифов, если минимальный тариф равен 0 ₽.
 */
export function getEventPriceSummary(ev: CatalogEventItemOut): EventPriceSummary {
  const minPrice = getEventMinPrice(ev);
  const hasFreeTariff = ev.tariffs.some((t) => t.actual_price === 0);
  const hasPaidTariff = ev.tariffs.some(
    (t) => t.actual_price !== null && t.actual_price > 0
  );
  const hasOnRequestTariff = ev.tariffs.some((t) => t.actual_price === null);

  if (minPrice === null) {
    return {
      minPrice,
      hasFreeTariff,
      hasPaidTariff,
      hasOnRequestTariff,
      label: "По запросу",
      subLabel: null,
    };
  }

  let subLabel: string | null = null;
  if (minPrice === 0) {
    if (hasPaidTariff && hasOnRequestTariff) {
      subLabel = "есть платные и по запросу";
    } else if (hasPaidTariff) {
      subLabel = "есть платные тарифы";
    } else if (hasOnRequestTariff) {
      subLabel = "есть тарифы по запросу";
    }
  }

  return {
    minPrice,
    hasFreeTariff,
    hasPaidTariff,
    hasOnRequestTariff,
    label: formatMinPrice(minPrice),
    subLabel,
  };
}

export function getEventMaxSavings(ev: CatalogEventItemOut): {
  savings: number;
  deadline: string | null;
} {
  let max = 0;
  let deadline: string | null = null;
  for (const t of ev.tariffs) {
    if (t.savings > max) {
      max = t.savings;
      deadline = t.early_bird_deadline;
    }
  }
  return { savings: max, deadline };
}

export function buildCityMultiOptions(
  events: CatalogEventItemOut[]
): MultiSelectOption[] {
  const counts = new Map<string, number>();
  let onlineCount = 0;
  for (const ev of events) {
    if (ev.is_online) onlineCount++;
    if (ev.city) {
      counts.set(ev.city, (counts.get(ev.city) || 0) + 1);
    }
  }
  return [
    { value: "online", label: "Онлайн", count: onlineCount },
    ...Array.from(counts.entries())
      .map(([city, count]) => ({ value: city, label: city, count }))
      .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label)),
  ];
}

export function buildThemeMultiOptions(
  events: CatalogEventItemOut[]
): MultiSelectOption[] {
  const map = new Map<string, number>();
  for (const ev of events) {
    for (const t of ev.themes) {
      map.set(t, (map.get(t) || 0) + 1);
    }
  }
  return Array.from(map.entries())
    .map(([name, count]) => ({ value: name, label: name, count }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
}

export interface CatalogFilterCriteria {
  selectedFormat: string;
  selectedCities: string[];
  selectedThemes: string[];
  onlyEarlyBird: boolean;
  searchQuery: string;
  sortBy: string;
}

export function filterAndSortCatalogEvents(
  events: CatalogEventItemOut[],
  criteria: CatalogFilterCriteria
): CatalogEventItemOut[] {
  const {
    selectedFormat,
    selectedCities,
    selectedThemes,
    onlyEarlyBird,
    searchQuery,
    sortBy,
  } = criteria;

  const list = events.filter((ev) => {
    if (selectedFormat !== "all" && ev.event_format !== selectedFormat) {
      return false;
    }
    if (selectedCities.length > 0) {
      const matchesCity = selectedCities.some((c) => {
        if (c === "online") return ev.is_online;
        return ev.city === c;
      });
      if (!matchesCity) return false;
    }
    if (selectedThemes.length > 0) {
      const matchesTheme = selectedThemes.some((t) => ev.themes.includes(t));
      if (!matchesTheme) return false;
    }
    if (onlyEarlyBird && !ev.tariffs.some((t) => t.savings > 0)) {
      return false;
    }
    const q = searchQuery.trim().toLowerCase();
    if (!q) return true;
    return (
      ev.canonical_title.toLowerCase().includes(q) ||
      ev.summary.toLowerCase().includes(q) ||
      ev.themes.some((t) => t.toLowerCase().includes(q))
    );
  });

  return list.sort((a, b) => {
    if (sortBy === "date_asc") {
      return a.start_date.localeCompare(b.start_date);
    }
    if (sortBy === "date_desc") {
      return b.start_date.localeCompare(a.start_date);
    }
    if (sortBy === "price_asc") {
      const pA = getEventMinPrice(a) ?? Infinity;
      const pB = getEventMinPrice(b) ?? Infinity;
      return pA - pB;
    }
    if (sortBy === "price_desc") {
      const pA = getEventMinPrice(a) ?? -1;
      const pB = getEventMinPrice(b) ?? -1;
      return pB - pA;
    }
    if (sortBy === "savings_desc") {
      const sA = getEventMaxSavings(a).savings;
      const sB = getEventMaxSavings(b).savings;
      return sB - sA;
    }
    return 0;
  });
}
