import * as React from "react";
import { AlertCircle, ChevronDown, ChevronUp, History, Loader2 } from "lucide-react";
import type { ScraperRunDetailOut, ScraperSourceOut } from "@/api/types";
import { cn } from "@/lib/utils";
import {
  formatDateTimeRu,
  formatDurationLabel,
  resolveSourceTitle,
} from "./scraperFormatters";
import {
  RunMetricsStrip,
  RunStatusBadge,
  RunTriggerBadges,
  SourceLogsBreakdown,
} from "./ScraperSharedParts";

interface ScraperHistoryTabProps {
  runs: ScraperRunDetailOut[];
  isLoading: boolean;
  sources: ScraperSourceOut[];
  onOpenEventDetails?: (eventId: number) => void;
}

export function ScraperHistoryTab({
  runs,
  isLoading,
  sources,
  onOpenEventDetails,
}: ScraperHistoryTabProps) {
  const [expandedRunId, setExpandedRunId] = React.useState<number | null>(null);

  const sourcesByKey = React.useMemo(
    () => new Map(sources.map((src) => [src.source_key, src])),
    [sources]
  );

  if (isLoading && runs.length === 0) {
    return (
      <div className="flex items-center justify-center gap-2 py-8 text-xs text-[#8E95A0]">
        <Loader2 className="h-4 w-4 animate-spin text-[#E5C378]" />
        <span>Загрузка истории прогонов...</span>
      </div>
    );
  }

  if (runs.length === 0) {
    return (
      <div className="rounded-[8px] border border-[#21262F] bg-[#12161A] px-4 py-8 text-center">
        <History className="mx-auto h-7 w-7 text-[#8E95A0]" strokeWidth={1.5} />
        <p className="mt-2 text-xs text-[#8E95A0]">
          История прогонов пока пуста. Запустите мониторинг на первой вкладке.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-2.5">
      {runs.map((run) => {
        const isExpanded = expandedRunId === run.id;
        const duration = formatDurationLabel(run.started_at, run.finished_at);

        return (
          <div
            key={run.id}
            className="rounded-[8px] border border-[#21262F] bg-[#12161A] overflow-hidden"
          >
            <button
              type="button"
              onClick={() =>
                setExpandedRunId((prev) => (prev === run.id ? null : run.id))
              }
              aria-expanded={isExpanded}
              className={cn(
                "w-full flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 px-3.5 py-2.5 text-left transition-colors cursor-pointer",
                isExpanded ? "bg-[#161B22]" : "hover:bg-[#161B22]/70"
              )}
            >
              <div className="min-w-0 space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs font-semibold text-[#E5C378]">
                    #{run.id}
                  </span>
                  <span className="text-xs font-medium text-white truncate">
                    {resolveSourceTitle(run.target_source_key, sourcesByKey)}
                  </span>
                  <RunStatusBadge status={run.status} />
                  <RunTriggerBadges
                    triggeredBy={run.triggered_by}
                    dryRun={run.dry_run}
                  />
                </div>

                <div className="text-[11px] text-[#8E95A0] tabular-nums">
                  <span>{formatDateTimeRu(run.started_at)}</span>
                  {run.finished_at && (
                    <span>
                      {" "}
                      → {formatDateTimeRu(run.finished_at)}
                      {duration ? ` (${duration})` : ""}
                    </span>
                  )}
                </div>
              </div>

              <div className="flex items-center justify-between sm:justify-end gap-3 shrink-0">
                <div className="flex items-center gap-2.5 text-xs tabular-nums">
                  <span className="text-[#34D399]" title="Создано событий">
                    +{run.events_created}
                  </span>
                  <span className="text-[#60A5FA]" title="Обновлено событий">
                    ~{run.events_updated}
                  </span>
                  <span
                    className={
                      run.errors_count > 0 ? "text-[#FCA5A5]" : "text-[#8E95A0]"
                    }
                    title="Ошибки"
                  >
                    ош: {run.errors_count}
                  </span>
                </div>

                {isExpanded ? (
                  <ChevronUp className="h-4 w-4 text-[#E5C378]" />
                ) : (
                  <ChevronDown className="h-4 w-4 text-[#8E95A0]" />
                )}
              </div>
            </button>

            {isExpanded && (
              <div className="border-t border-[#21262F] bg-[#0E1116]/60 p-3 space-y-3">
                {run.error_message && (
                  <div className="flex items-start gap-2 rounded-[6px] border border-[#EA4335]/50 bg-[#EA4335]/10 p-2.5 text-xs text-[#FCA5A5]">
                    <AlertCircle className="h-4 w-4 shrink-0 mt-0.5 text-[#F87171]" />
                    <span className="break-words">{run.error_message}</span>
                  </div>
                )}

                <RunMetricsStrip run={run} />

                <SourceLogsBreakdown
                  logs={run.source_logs}
                  isRunning={run.status === "queued" || run.status === "running"}
                  onOpenEventDetails={onOpenEventDetails}
                />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
