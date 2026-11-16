import * as React from "react";
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Loader2,
  Play,
  Radar,
  Settings2,
} from "lucide-react";
import { toast } from "sonner";
import { ApiError } from "@/api/client";
import { useRunScraperMutation } from "@/api/queries";
import type {
  ScraperRunDetailOut,
  ScraperRunOut,
  ScraperSourceKey,
  ScraperSourceOut,
} from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  CustomSelect,
  type CustomSelectOption,
} from "@/components/ui/custom-select";
import { cn } from "@/lib/utils";
import {
  formatDateTimeRu,
  formatDurationLabel,
  formatSourceSubLabel,
  resolveSourceTitle,
} from "./scraperFormatters";
import {
  RunMetricsStrip,
  RunStatusBadge,
  RunTriggerBadges,
  SourceLogsBreakdown,
} from "./ScraperSharedParts";

interface ScraperRunTabProps {
  sources: ScraperSourceOut[];
  isLoadingSources: boolean;
  selectedSource: ScraperSourceKey;
  onSelectSource: (key: ScraperSourceKey) => void;
  latestRun: ScraperRunDetailOut | null | undefined;
  isLoadingLatestRun: boolean;
  onSwitchToSourcesTab: () => void;
  onOpenEventDetails?: (eventId: number) => void;
}

interface ScraperFeedbackState {
  tone: "success" | "warning" | "error";
  title: string;
  message: string;
  statusBadge?: string;
}

function isAlreadyRunningResponse(res: ScraperRunOut): boolean {
  const lower = res.message.toLowerCase();
  return (
    lower.includes("уже выполняется") ||
    lower.includes("повторный запуск отклонен")
  );
}

export function ScraperRunTab({
  sources,
  isLoadingSources,
  selectedSource,
  onSelectSource,
  latestRun,
  isLoadingLatestRun,
  onSwitchToSourcesTab,
  onOpenEventDetails,
}: ScraperRunTabProps) {
  const runScraperMutation = useRunScraperMutation();

  const [dryRun, setDryRun] = React.useState(false);
  const [maxUrlsInput, setMaxUrlsInput] = React.useState("");
  const [feedback, setFeedback] = React.useState<ScraperFeedbackState | null>(
    null
  );

  const sourcesByKey = React.useMemo(
    () => new Map(sources.map((src) => [src.source_key, src])),
    [sources]
  );

  const enabledAutoSources = React.useMemo(
    () =>
      sources.filter(
        (src) => src.is_enabled && src.adapter_type !== "manual_only"
      ),
    [sources]
  );

  const selectOptions = React.useMemo<CustomSelectOption<ScraperSourceKey>[]>(
    () => [
      {
        value: "all",
        label: "Все активные площадки (кроме отключенных и ручных)",
        subLabel: `${enabledAutoSources.length} акт.`,
      },
      ...sources.map((src) => ({
        value: src.source_key,
        label: src.display_name,
        subLabel: formatSourceSubLabel(src),
      })),
    ],
    [sources, enabledAutoSources.length]
  );

  const selectedSourceObj =
    selectedSource === "all" ? null : sourcesByKey.get(selectedSource) ?? null;

  const blockedReason = React.useMemo(() => {
    if (selectedSource === "all") {
      if (!isLoadingSources && sources.length > 0 && enabledAutoSources.length === 0) {
        return "Нет активных автоматических площадок. Включите хотя бы одну площадку на вкладке «Площадки и настройки».";
      }
      return null;
    }
    if (!selectedSourceObj) {
      return isLoadingSources ? null : "Выбранная площадка не найдена в списке.";
    }
    if (selectedSourceObj.adapter_type === "manual_only") {
      return "Площадка работает только в режиме ручного импорта PDF/URL. Автоматический обход каталога недоступен.";
    }
    if (!selectedSourceObj.is_enabled) {
      return "Эта площадка отключена в настройках. Включите её на вкладке «Площадки и настройки», чтобы запустить мониторинг.";
    }
    return null;
  }, [
    selectedSource,
    selectedSourceObj,
    isLoadingSources,
    sources.length,
    enabledAutoSources.length,
  ]);

  const parsedMaxUrls = React.useMemo<{
    valid: boolean;
    value: number | null;
    error: string | null;
  }>(() => {
    const trimmed = maxUrlsInput.trim();
    if (!trimmed) return { valid: true, value: null, error: null };
    if (!/^\d+$/.test(trimmed)) {
      return {
        valid: false,
        value: null,
        error: "Укажите целое число от 1 до 50.",
      };
    }
    const num = Number(trimmed);
    if (num < 1 || num > 50) {
      return {
        valid: false,
        value: null,
        error: "Лимит новых URL должен быть в диапазоне от 1 до 50.",
      };
    }
    return { valid: true, value: num, error: null };
  }, [maxUrlsInput]);

  const isLatestActive =
    latestRun?.status === "queued" || latestRun?.status === "running";

  const canLaunch =
    !runScraperMutation.isPending &&
    !isLatestActive &&
    !blockedReason &&
    parsedMaxUrls.valid;

  const handleRun = async () => {
    setFeedback(null);
    if (!parsedMaxUrls.valid) {
      toast.error(parsedMaxUrls.error || "Некорректный лимит URL.");
      return;
    }

    try {
      const res = await runScraperMutation.mutateAsync({
        source_key: selectedSource,
        dry_run: dryRun,
        max_urls_per_source: parsedMaxUrls.value,
      });

      if (res.status === "failed") {
        setFeedback({
          tone: "error",
          title: "Запуск парсера завершился ошибкой",
          message: res.message,
          statusBadge: "Ошибка",
        });
        toast.error(res.message);
        return;
      }

      if (res.status === "queued" && isAlreadyRunningResponse(res)) {
        setFeedback({
          tone: "warning",
          title: "Мониторинг уже выполняется",
          message: res.message,
          statusBadge: "В работе",
        });
        toast.warning(res.message);
        return;
      }

      setFeedback({
        tone: "success",
        title: dryRun
          ? "Пробный прогон (Dry Run) поставлен в очередь"
          : "Задача мониторинга поставлена в очередь",
        message: res.message,
        statusBadge: "В очереди",
      });
      toast.success(res.message);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        const detail =
          err.detail ||
          "Задача мониторинга уже выполняется в фоне. Дождитесь её завершения.";
        setFeedback({
          tone: "warning",
          title: "Конфликт запуска (409 Conflict)",
          message: detail,
          statusBadge: "Уже запущен",
        });
        toast.warning(detail);
        return;
      }

      const message =
        err instanceof Error
          ? err.message
          : "Не удалось поставить задачу парсинга в очередь.";
      setFeedback({
        tone: "error",
        title: "Ошибка запуска скрейпера",
        message,
      });
      toast.error(message);
    }
  };

  const progressPercent = React.useMemo(() => {
    if (!latestRun || latestRun.sources_total <= 0) return 0;
    return Math.min(
      100,
      Math.round((latestRun.sources_done / latestRun.sources_total) * 100)
    );
  }, [latestRun]);

  const durationText = latestRun
    ? formatDurationLabel(latestRun.started_at, latestRun.finished_at)
    : null;

  return (
    <div className="space-y-4">
      <div className="rounded-[8px] border border-[#21262F] bg-[#12161A] p-3.5 space-y-3.5">
        <div className="grid grid-cols-1 md:grid-cols-[1fr_200px] gap-3 items-start">
          <div>
            <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-[#8E95A0]">
              Цель мониторинга
            </span>
            <CustomSelect<ScraperSourceKey>
              value={selectedSource}
              onChange={onSelectSource}
              options={selectOptions}
              disabled={runScraperMutation.isPending || isLoadingSources}
              className="w-full"
              buttonClassName="w-full h-9 px-3 text-xs"
              menuClassName="w-full"
            />
          </div>

          <div>
            <label
              htmlFor="scraper-max-urls-input"
              className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-[#8E95A0]"
            >
              Лимит URL (1–50)
            </label>
            <input
              id="scraper-max-urls-input"
              type="number"
              min={1}
              max={50}
              step={1}
              placeholder={
                selectedSourceObj
                  ? `По умолчанию: ${selectedSourceObj.max_urls_per_run}`
                  : "По настройкам"
              }
              value={maxUrlsInput}
              onChange={(e) => setMaxUrlsInput(e.target.value)}
              disabled={runScraperMutation.isPending}
              className={cn(
                "h-9 w-full rounded-[6px] border bg-[#0E1116] px-3 text-xs text-white placeholder:text-[#6B7280] tabular-nums outline-none transition-colors",
                parsedMaxUrls.valid
                  ? "border-[#262D35] focus:border-[#E5C378]"
                  : "border-[#F87171] focus:border-[#F87171]"
              )}
            />
            {parsedMaxUrls.error && (
              <p className="mt-1 text-[11px] text-[#FCA5A5]">
                {parsedMaxUrls.error}
              </p>
            )}
          </div>
        </div>

        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pt-1">
          <label className="inline-flex items-start gap-2.5 cursor-pointer select-none group">
            <input
              type="checkbox"
              checked={dryRun}
              onChange={(e) => setDryRun(e.target.checked)}
              disabled={runScraperMutation.isPending}
              className="mt-0.5 h-4 w-4 rounded border-[#7C5A20] bg-[#0E1116] accent-[#E5C378] cursor-pointer"
            />
            <span className="text-xs leading-snug text-[#D1D5DB] group-hover:text-white transition-colors">
              <span className="font-medium text-white">
                Пробный запуск (Dry Run)
              </span>
              <span className="block text-[11px] text-[#8E95A0]">
                Только поиск ссылок, 0 токенов LLM и без сохранения событий в БД
              </span>
            </span>
          </label>

          <Button
            type="button"
            variant="monolith"
            size="sm"
            disabled={!canLaunch}
            onClick={handleRun}
            className="h-9 px-4 text-xs font-semibold shrink-0 cursor-pointer"
          >
            {runScraperMutation.isPending ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin text-[#E5C378]" />
                <span>Запуск...</span>
              </>
            ) : isLatestActive ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin text-[#E5C378]" />
                <span>Мониторинг в работе...</span>
              </>
            ) : (
              <>
                <Play className="h-3.5 w-3.5 text-[#E5C378] monolith-icon" />
                <span>
                  {dryRun ? "Запустить пробный поиск" : "Запустить парсер"}
                </span>
              </>
            )}
          </Button>
        </div>

        {blockedReason && (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-[6px] border border-[#7C4A19] bg-[#22160C] px-3 py-2 text-xs text-[#E59837]">
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              <span>{blockedReason}</span>
            </div>
            {selectedSourceObj &&
              selectedSourceObj.adapter_type !== "manual_only" &&
              !selectedSourceObj.is_enabled && (
                <button
                  type="button"
                  onClick={onSwitchToSourcesTab}
                  className="inline-flex items-center gap-1 rounded-[4px] border border-[#7C5A20]/70 bg-[#1E190E] px-2 py-1 text-[11px] font-medium text-[#E5C378] hover:border-[#E5C378] hover:text-white transition-colors cursor-pointer"
                >
                  <Settings2 className="h-3 w-3" />
                  <span>К настройкам площадок</span>
                </button>
              )}
          </div>
        )}

        {feedback && (
          <div
            role="status"
            className={
              feedback.tone === "success"
                ? "rounded-[8px] border border-[#1E5241] bg-[#0E241E]/90 p-3 text-xs space-y-1"
                : feedback.tone === "warning"
                  ? "rounded-[8px] border border-[#7C4A19] bg-[#22160C] p-3 text-xs space-y-1"
                  : "rounded-[8px] border border-[#EA4335]/40 bg-[#EA4335]/10 p-3 text-xs space-y-1"
            }
          >
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-1.5 font-semibold">
                {feedback.tone === "success" ? (
                  <CheckCircle2 className="h-4 w-4 shrink-0 text-[#34D399]" />
                ) : feedback.tone === "warning" ? (
                  <AlertTriangle className="h-4 w-4 shrink-0 text-[#E59837]" />
                ) : (
                  <AlertCircle className="h-4 w-4 shrink-0 text-[#F87171]" />
                )}
                <span
                  className={
                    feedback.tone === "success"
                      ? "text-[#34D399]"
                      : feedback.tone === "warning"
                        ? "text-[#E59837]"
                        : "text-[#FCA5A5]"
                  }
                >
                  {feedback.title}
                </span>
              </div>
              {feedback.statusBadge && (
                <Badge
                  variant={
                    feedback.tone === "success"
                      ? "ebEmerald"
                      : feedback.tone === "warning"
                        ? "ebAmber"
                        : "ebRose"
                  }
                  asSlanted={false}
                  className="text-[11px] shrink-0 font-sans not-italic"
                >
                  {feedback.statusBadge}
                </Badge>
              )}
            </div>
            <p className="text-[#D1D5DB] leading-relaxed">{feedback.message}</p>
          </div>
        )}
      </div>

      {/* Live-панель последнего/текущего прогона */}
      <div className="rounded-[8px] border border-[#21262F] bg-[#12161A] p-3.5 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#21262F] pb-2.5">
          <div className="flex items-center gap-2">
            {isLatestActive ? (
              <span className="relative flex h-2.5 w-2.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#34D399] opacity-75" />
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-[#34D399]" />
              </span>
            ) : (
              <Radar className="h-4 w-4 text-[#E5C378]" strokeWidth={1.75} />
            )}
            <h3 className="font-serif italic text-sm font-semibold text-[#E5C378]">
              {isLatestActive
                ? "Текущий прогон (live-обновление)"
                : "Последний прогон парсера"}
            </h3>
          </div>

          {latestRun && (
            <div className="flex flex-wrap items-center gap-1.5">
              <RunStatusBadge status={latestRun.status} />
              <RunTriggerBadges
                triggeredBy={latestRun.triggered_by}
                dryRun={latestRun.dry_run}
              />
            </div>
          )}
        </div>

        {isLoadingLatestRun && latestRun === undefined ? (
          <div className="flex items-center justify-center gap-2 py-6 text-xs text-[#8E95A0]">
            <Loader2 className="h-4 w-4 animate-spin text-[#E5C378]" />
            <span>Загрузка статуса прогона...</span>
          </div>
        ) : !latestRun ? (
          <div className="rounded-[6px] border border-[#21262F] bg-[#0E1116] px-4 py-6 text-center text-xs text-[#8E95A0]">
            Запусков мониторинга ещё не было. Выберите площадку и запустите
            первый обход.
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-[#D1D5DB]">
              <div>
                <span className="text-[#8E95A0]">Цель: </span>
                <span className="font-medium text-white">
                  {resolveSourceTitle(
                    latestRun.target_source_key,
                    sourcesByKey
                  )}
                </span>
                <span className="mx-2 text-[#262D35]">|</span>
                <span className="text-[#8E95A0]">ID прогона: </span>
                <span className="font-mono text-[#E5C378]">#{latestRun.id}</span>
              </div>

              <div className="text-[11px] text-[#8E95A0] tabular-nums">
                <span>Старт: {formatDateTimeRu(latestRun.started_at)}</span>
                {latestRun.finished_at && (
                  <span>
                    {" "}
                    · Финиш: {formatDateTimeRu(latestRun.finished_at)}
                    {durationText ? ` (${durationText})` : ""}
                  </span>
                )}
              </div>
            </div>

            {isLatestActive && (
              <div className="space-y-1.5 rounded-[6px] border border-[#262D35] bg-[#0E1116] p-2.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-[#D1D5DB]">
                    Прогресс по площадкам:{" "}
                    <strong className="text-white tabular-nums">
                      {latestRun.sources_done} /{" "}
                      {latestRun.sources_total > 0
                        ? latestRun.sources_total
                        : "—"}
                    </strong>
                  </span>
                  {latestRun.sources_total > 0 && (
                    <span className="text-[11px] font-semibold text-[#E5C378] tabular-nums">
                      {progressPercent}%
                    </span>
                  )}
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-[#1E252E]">
                  <div
                    className={cn(
                      "h-full rounded-full transition-all duration-300",
                      latestRun.sources_total > 0
                        ? "bg-gradient-to-r from-[#7C5A20] to-[#E5C378]"
                        : "w-1/3 animate-pulse bg-[#E5C378]/70"
                    )}
                    style={
                      latestRun.sources_total > 0
                        ? { width: `${progressPercent}%` }
                        : undefined
                    }
                  />
                </div>
              </div>
            )}

            {latestRun.status === "failed" && latestRun.error_message && (
              <div className="flex items-start gap-2 rounded-[6px] border border-[#EA4335]/50 bg-[#EA4335]/10 p-3 text-xs text-[#FCA5A5]">
                <AlertCircle className="h-4 w-4 shrink-0 mt-0.5 text-[#F87171]" />
                <div className="space-y-0.5">
                  <div className="font-semibold text-[#FCA5A5]">
                    Причина сбоя прогона
                  </div>
                  <div className="text-[#FECACA] break-words">
                    {latestRun.error_message}
                  </div>
                </div>
              </div>
            )}

            <RunMetricsStrip run={latestRun} />

            <div className="space-y-1.5">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-[#8E95A0]">
                Детализация по площадкам ({latestRun.source_logs.length})
              </div>
              <SourceLogsBreakdown
                logs={latestRun.source_logs}
                isRunning={isLatestActive}
                onOpenEventDetails={onOpenEventDetails}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
