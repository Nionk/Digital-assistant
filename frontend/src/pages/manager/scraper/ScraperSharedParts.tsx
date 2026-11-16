import * as React from "react";
import {
  AlertCircle,
  Calendar,
  CheckCircle2,
  ChevronRight,
  ExternalLink,
  Link2,
  Loader2,
  MapPin,
} from "lucide-react";
import type {
  ScraperRunDetailOut,
  ScraperRunSavedEventOut,
  ScraperRunSourceLogOut,
  ScraperRunStatus,
} from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import {
  formatShortDateRu,
  getRunStatusMeta,
  getTriggerLabel,
} from "./scraperFormatters";

export function RunStatusBadge({ status }: { status: ScraperRunStatus }) {
  const meta = getRunStatusMeta(status);
  return (
    <Badge
      variant={meta.badgeVariant}
      asSlanted={false}
      className="text-[11px] font-sans not-italic"
    >
      {meta.isActive && <Loader2 className="h-3 w-3 animate-spin" />}
      <span>{meta.label}</span>
    </Badge>
  );
}

export function RunTriggerBadges({
  triggeredBy,
  dryRun,
}: {
  triggeredBy: string;
  dryRun: boolean;
}) {
  const trigger = getTriggerLabel(triggeredBy, dryRun);
  return (
    <div className="inline-flex flex-wrap items-center gap-1.5">
      {dryRun ? (
        <Badge
          variant="ebTeal"
          asSlanted={false}
          className="text-[11px] font-sans not-italic"
        >
          Пробный (Dry Run)
        </Badge>
      ) : (
        <Badge
          variant={trigger.badgeVariant}
          asSlanted={false}
          className="text-[11px] font-sans not-italic"
        >
          {trigger.label}
        </Badge>
      )}
    </div>
  );
}

export function RunMetricsStrip({ run }: { run: ScraperRunDetailOut }) {
  const metrics = [
    {
      label: "Найдено URL",
      value: run.urls_discovered,
      accent: "text-white",
    },
    {
      label: "Создано",
      value: run.events_created,
      accent: "text-[#34D399]",
    },
    {
      label: "Обновлено",
      value: run.events_updated,
      accent: "text-[#60A5FA]",
    },
    {
      label: "Отсеяно B2C",
      value: run.rejected_b2c,
      accent: "text-[#D1D5DB]",
    },
    {
      label: "Не РФ / онлайн",
      value: run.rejected_geo,
      accent: "text-[#D1D5DB]",
    },
    {
      label: "Прошедших",
      value: run.rejected_past,
      accent: "text-[#D1D5DB]",
    },
    {
      label: "Ошибок",
      value: run.errors_count,
      accent: run.errors_count > 0 ? "text-[#FCA5A5]" : "text-[#8E95A0]",
    },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2">
      {metrics.map((m) => (
        <div
          key={m.label}
          className="rounded-[6px] border border-[#21262F] bg-[#0E1116] px-2.5 py-2"
        >
          <div className="text-[10px] leading-tight text-[#8E95A0] truncate">
            {m.label}
          </div>
          <div
            className={cn(
              "mt-0.5 text-sm font-semibold tabular-nums",
              m.accent
            )}
          >
            {m.value}
          </div>
        </div>
      ))}
    </div>
  );
}

function SavedEventRow({
  event,
  onOpenEventDetails,
}: {
  event: ScraperRunSavedEventOut;
  onOpenEventDetails?: (eventId: number) => void;
}) {
  const isCreated = event.action === "created";
  const isNeedsEnrichment = event.data_status === "needs_enrichment";
  const formattedDate = formatShortDateRu(event.start_date);
  const canOpenDrawer = Boolean(event.event_id && onOpenEventDetails);

  return (
    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 rounded-[6px] border border-[#21262F] bg-[#12161A] px-2.5 py-2 transition-colors hover:border-[#7C5A20]/60">
      <div className="min-w-0 space-y-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge
            variant={isCreated ? "ebEmerald" : "ebBlue"}
            asSlanted={false}
            className="text-[10px] font-sans not-italic"
          >
            {isCreated ? "Создано" : "Обновлено"}
          </Badge>
          {isNeedsEnrichment && (
            <Badge
              variant="ebAmber"
              asSlanted={false}
              className="text-[10px] font-sans not-italic"
            >
              Дозаполнить
            </Badge>
          )}
          {canOpenDrawer ? (
            <button
              type="button"
              onClick={() => onOpenEventDetails?.(event.event_id!)}
              title="Открыть карточку мероприятия в каталоге"
              className="inline-flex items-center gap-1 text-left text-xs font-medium text-white hover:text-[#E5C378] transition-colors cursor-pointer min-w-0"
            >
              <span className="break-words">{event.title}</span>
              <ChevronRight className="h-3.5 w-3.5 shrink-0 text-[#E5C378]" />
            </button>
          ) : (
            <span className="text-xs font-medium text-white break-words">
              {event.title}
            </span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-[#8E95A0]">
          {formattedDate && (
            <span className="inline-flex items-center gap-1 tabular-nums">
              <Calendar className="h-3 w-3 text-[#7C5A20]" />
              <span>{formattedDate}</span>
            </span>
          )}
          {event.city && (
            <span className="inline-flex items-center gap-1">
              <MapPin className="h-3 w-3 text-[#7C5A20]" />
              <span>{event.city}</span>
            </span>
          )}
          {event.url && (
            <a
              href={event.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 font-mono text-[10px] text-[#E5C378]/90 hover:text-[#E5C378] hover:underline truncate max-w-[300px]"
            >
              <span className="truncate">{event.url}</span>
              <ExternalLink className="h-2.5 w-2.5 shrink-0" />
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

function CandidateUrlsPreview({ urls }: { urls: string[] }) {
  const [expanded, setExpanded] = React.useState(false);
  const visibleUrls = expanded ? urls : urls.slice(0, 5);
  const hiddenCount = Math.max(0, urls.length - 5);

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2 text-[10px] font-semibold uppercase tracking-wider text-[#8E95A0]">
        <span className="inline-flex items-center gap-1">
          <Link2 className="h-3 w-3 text-[#E5C378]" />
          <span>Отобранные URL ({urls.length})</span>
        </span>
        {hiddenCount > 0 && (
          <button
            type="button"
            onClick={() => setExpanded((prev) => !prev)}
            className="text-[10px] font-medium normal-case text-[#E5C378] hover:underline cursor-pointer"
          >
            {expanded ? "Свернуть" : `Показать все (+${hiddenCount})`}
          </button>
        )}
      </div>

      <div className="flex flex-wrap gap-1.5">
        {visibleUrls.map((url, idx) => (
          <a
            key={`${url}-${idx}`}
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 rounded-[4px] border border-[#21262F] bg-[#12161A] px-2 py-1 font-mono text-[10px] text-[#E5C378]/90 hover:border-[#7C5A20] hover:text-[#E5C378] transition-colors max-w-full"
          >
            <span className="truncate max-w-[280px]">{url}</span>
            <ExternalLink className="h-2.5 w-2.5 shrink-0" />
          </a>
        ))}
      </div>
    </div>
  );
}

export function SourceLogsBreakdown({
  logs,
  isRunning,
  onOpenEventDetails,
}: {
  logs: ScraperRunSourceLogOut[];
  isRunning?: boolean;
  onOpenEventDetails?: (eventId: number) => void;
}) {
  if (logs.length === 0) {
    return (
      <div className="rounded-[6px] border border-[#21262F] bg-[#0E1116] px-3 py-2.5 text-xs text-[#8E95A0]">
        {isRunning
          ? "Ожидаем завершения обработки первой площадки..."
          : "Детализация по площадкам отсутствует."}
      </div>
    );
  }

  return (
    <div className="space-y-2.5">
      {logs.map((log, idx) => {
        const rejectedTotal =
          log.rejected_b2c + log.rejected_geo + log.rejected_past;
        const savedEvents = log.saved_events ?? [];
        const candidateUrls = log.candidate_urls ?? [];
        const hasDetails = savedEvents.length > 0 || candidateUrls.length > 0;

        return (
          <div
            key={`${log.source_key}-${idx}`}
            className="rounded-[8px] border border-[#21262F] bg-[#0E1116] overflow-hidden"
          >
            {/* Сводная строка площадки */}
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 px-3 py-2.5 bg-[#12161A]/75">
              <div className="min-w-0">
                <div className="text-xs font-semibold text-white truncate">
                  {log.display_name || log.source_key}
                </div>
                <div className="text-[10px] font-mono text-[#8E95A0]">
                  {log.source_key}
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs tabular-nums">
                <span className="text-[#8E95A0]">
                  Найдено:{" "}
                  <strong className="text-[#D1D5DB]">{log.discovered_total}</strong>
                  {" / "}
                  <strong className="text-[#E5C378]" title="Новых отобрано">
                    {log.selected_new_count}
                  </strong>
                </span>

                <span>
                  <span className="text-[#34D399]">+{log.events_created}</span>
                  <span className="text-[#8E95A0]"> / </span>
                  <span className="text-[#60A5FA]">~{log.events_updated}</span>
                </span>

                <span
                  className="text-[#8E95A0]"
                  title={`B2C: ${log.rejected_b2c}, Гео: ${log.rejected_geo}, Прошедшие: ${log.rejected_past}`}
                >
                  Отсеяно:{" "}
                  <strong className="text-[#D1D5DB]">{rejectedTotal}</strong>
                  {rejectedTotal > 0 && (
                    <span className="ml-1 text-[10px]">
                      ({log.rejected_b2c}/{log.rejected_geo}/{log.rejected_past})
                    </span>
                  )}
                </span>

                {log.error ? (
                  <span className="inline-flex items-center gap-1 text-[11px] text-[#FCA5A5]">
                    <AlertCircle className="h-3.5 w-3.5 shrink-0 text-[#F87171]" />
                    <span className="break-words max-w-[260px]">{log.error}</span>
                  </span>
                ) : log.errors_count > 0 ? (
                  <span className="text-[11px] text-[#E59837]">
                    Ошибок карточек: {log.errors_count}
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-[11px] text-[#34D399]">
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    <span>ОК</span>
                  </span>
                )}
              </div>
            </div>

            {/* Конкретные спарсенные мероприятия или отобранные ссылки */}
            {hasDetails && (
              <div className="border-t border-[#21262F] px-3 py-2.5 space-y-2">
                {savedEvents.length > 0 ? (
                  <div className="space-y-1.5">
                    <div className="text-[10px] font-semibold uppercase tracking-wider text-[#8E95A0]">
                      Обработанные мероприятия ({savedEvents.length})
                    </div>
                    <div className="space-y-1.5">
                      {savedEvents.map((ev, evIdx) => (
                        <SavedEventRow
                          key={`${ev.event_id ?? "ev"}-${evIdx}`}
                          event={ev}
                          onOpenEventDetails={onOpenEventDetails}
                        />
                      ))}
                    </div>
                  </div>
                ) : (
                  <CandidateUrlsPreview urls={candidateUrls} />
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
