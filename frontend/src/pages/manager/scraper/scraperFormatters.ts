import type {
  ScraperAdapterType,
  ScraperRunStatus,
  ScraperSourceOut,
} from "@/api/types";
import type { CustomSelectOption } from "@/components/ui/custom-select";

export const ADAPTER_LABELS: Record<ScraperAdapterType, string> = {
  html_list: "HTML-список",
  rss: "RSS",
  html_digest: "Дайджест",
  manual_only: "Ручной PDF/URL",
};

export const ADAPTER_OPTIONS: CustomSelectOption<ScraperAdapterType>[] = [
  {
    value: "html_list",
    label: "HTML-список",
    subLabel: "Каталог карточек",
  },
  {
    value: "rss",
    label: "RSS",
    subLabel: "XML/Atom-лента",
  },
  {
    value: "html_digest",
    label: "Дайджест",
    subLabel: "Сводная страница",
  },
  {
    value: "manual_only",
    label: "Ручной PDF/URL",
    subLabel: "Без автосбора",
  },
];

export function extractHostLabel(url: string | undefined): string {
  if (!url) return "";
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export function formatSourceSubLabel(source: ScraperSourceOut): string {
  const host = extractHostLabel(source.catalog_urls[0]) || source.source_key;
  if (source.adapter_type === "manual_only") {
    return `${host} · только ручной импорт PDF/URL`;
  }
  if (!source.is_enabled) {
    return `${host} · откл.`;
  }
  return host;
}

export function resolveSourceTitle(
  sourceKey: string,
  sourcesByKey: Map<string, ScraperSourceOut>
): string {
  if (sourceKey === "all") return "Все площадки";
  return sourcesByKey.get(sourceKey)?.display_name || sourceKey;
}

export function formatDateTimeRu(iso: string | null | undefined): string {
  if (!iso) return "—";
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function formatShortDateRu(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const match = iso.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (match) {
    return `${match[3]}.${match[2]}.${match[1]}`;
  }
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toLocaleDateString("ru-RU");
}

export function formatDurationLabel(
  startedAt: string,
  finishedAt: string | null
): string | null {
  if (!finishedAt) return null;
  const startMs = new Date(startedAt).getTime();
  const endMs = new Date(finishedAt).getTime();
  if (Number.isNaN(startMs) || Number.isNaN(endMs) || endMs < startMs) {
    return null;
  }
  const totalSec = Math.round((endMs - startMs) / 1000);
  if (totalSec < 60) return `${totalSec} сек.`;
  const mins = Math.floor(totalSec / 60);
  const secs = totalSec % 60;
  return `${mins} мин ${secs} сек.`;
}

export function getRunStatusMeta(status: ScraperRunStatus): {
  label: string;
  badgeVariant: "ebEmerald" | "ebAmber" | "ebRose" | "ebBlue";
  isActive: boolean;
} {
  switch (status) {
    case "queued":
      return {
        label: "В очереди",
        badgeVariant: "ebAmber",
        isActive: true,
      };
    case "running":
      return {
        label: "Выполняется",
        badgeVariant: "ebBlue",
        isActive: true,
      };
    case "completed":
      return {
        label: "Завершён",
        badgeVariant: "ebEmerald",
        isActive: false,
      };
    case "failed":
      return {
        label: "Ошибка",
        badgeVariant: "ebRose",
        isActive: false,
      };
  }
}

export function getTriggerLabel(triggeredBy: string, dryRun: boolean): {
  label: string;
  badgeVariant: "ebTeal" | "ebGold" | "surface";
} {
  if (dryRun || triggeredBy === "manual_dry_run") {
    return { label: "Пробный", badgeVariant: "ebTeal" };
  }
  if (triggeredBy === "scheduler") {
    return { label: "Ночной авто", badgeVariant: "ebGold" };
  }
  return { label: "Ручной", badgeVariant: "surface" };
}

export function parseMultilineValues(raw: string): string[] {
  return raw
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}
