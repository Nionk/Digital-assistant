import {
  Copy,
  ExternalLink,
  RefreshCw,
  Send,
  ShieldCheck,
  AlertTriangle,
  Sparkles,
  Check,
} from "lucide-react";
import * as React from "react";
import type { ComputedFinancialSummary } from "@/store/useManagerStore";
import { Button } from "@/components/ui/button";
import { formatDateShort, formatRub } from "@/lib/formatters";
import { cn } from "@/lib/utils";

interface FinancialAndPitchPanelProps {
  companyName: string;
  summary: ComputedFinancialSummary;
  pitchText: string;
  onPitchChange: (text: string) => void;
  onSyncPitchNumbers: () => void;
  onPublish: () => void;
  isPublishing: boolean;
  publishedUrl: string | null;
  onCopyLink: (url: string) => void;
}

export function FinancialAndPitchPanel({
  companyName,
  summary,
  pitchText,
  onPitchChange,
  onSyncPitchNumbers,
  onPublish,
  isPublishing,
  publishedUrl,
  onCopyLink,
}: FinancialAndPitchPanelProps) {
  const [copied, setCopied] = React.useState(false);

  const budgetRatioPct =
    summary.budgetMax > 0
      ? Math.min(100, Math.round((summary.totalActualPrice / summary.budgetMax) * 100))
      : 0;

  const savingsPct =
    summary.totalBasePrice > 0 && summary.totalSavings > 0
      ? Math.round((summary.totalSavings / summary.totalBasePrice) * 100)
      : 0;

  const handleCopy = (url: string) => {
    onCopyLink(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="sticky top-[72px] space-y-3">
      {/* 1. Темно-хвойный финансовый блок (в стиле Фото 3 «You've saved...» + Слайд 05 и 10) */}
      <div className="rounded-card bg-pine p-4 text-white shadow-elevated">
        <div className="flex items-center justify-between border-b border-white/15 pb-2.5">
          <div>
            <span className="text-[10px] font-bold uppercase tracking-widest text-white/70">
              Сводка коммерческого предложения
            </span>
            <h3 className="font-serif text-base font-semibold text-white">
              {companyName}
            </h3>
          </div>
          <span className="rounded-tag bg-white/20 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white tabular-nums">
            Площадок: {summary.includedRows.length}
          </span>
        </div>

        {/* Основная сумма внешних расходов */}
        <div className="mt-3.5">
          <div className="flex items-baseline justify-between">
            <span className="text-xs text-white/75">
              Организационные взносы площадок:
            </span>
            {summary.totalSavings > 0 && (
              <span className="text-xs text-white/50 line-through tabular-nums">
                {formatRub(summary.totalBasePrice)}
              </span>
            )}
          </div>

          <div className="mt-1 flex items-baseline justify-between gap-2 tabular-nums">
            <span className="text-2xl font-bold tracking-tight text-white">
              {formatRub(summary.totalActualPrice)}
            </span>
            {summary.hasOnRequestIncluded && (
              <span className="text-[11px] font-medium text-sage-border">
                + спецпроект по запросу
              </span>
            )}
          </div>
        </div>

        {/* Выгода Early Bird / спецтарифы */}
        {summary.totalSavings > 0 && (
          <div className="mt-3 rounded-control border border-white/15 bg-white/10 p-2.5">
            <div className="flex items-center justify-between tabular-nums">
              <span className="text-xs font-medium text-white/90">
                Выгода по спецтарифам:
              </span>
              <span className="rounded-tag bg-novel-gold px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-[#1F1808]">
                −{formatRub(summary.totalSavings)}{" "}
                {savingsPct > 0 ? `(${savingsPct}%)` : ""}
              </span>
            </div>
            {summary.earliestDeadline && (
              <p className="mt-1 text-[11px] text-white/75 tabular-nums">
                Фиксация льготных условий при бронировании до{" "}
                <strong className="text-white">
                  {formatDateShort(summary.earliestDeadline)}
                </strong>
              </p>
            )}
          </div>
        )}

        {/* Контроль лимита бюджета клиента */}
        {summary.budgetMax > 0 && (
          <div className="mt-3 pt-2.5 border-t border-white/15">
            <div className="flex items-center justify-between text-[11px] text-white/80 tabular-nums">
              <span>Целевой лимит клиента:</span>
              <span>{formatRub(summary.budgetMax)}</span>
            </div>
            <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-white/15">
              <div
                className={cn(
                  "h-full transition-all duration-300",
                  summary.isOverBudget ? "bg-terracotta" : "bg-sage-border"
                )}
                style={{ width: `${budgetRatioPct}%` }}
              />
            </div>

            {summary.isOverBudget && (
              <div className="mt-2 flex items-start gap-1.5 rounded-badge bg-terracotta/90 px-2.5 py-1.5 text-[11px] text-white">
                <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" strokeWidth={1.75} />
                <span>
                  {summary.isWithinTolerance10Pct
                    ? "Превышение бюджета в пределах допустимых +10% (требует согласования с клиентом)"
                    : `Пакет превышает ориентир бюджета на ${formatRub(
                        summary.totalActualPrice - summary.budgetMax
                      )}`}
                </span>
              </div>
            )}
          </div>
        )}

        {/* Пояснение по Слайду 10 (разделение взносов и сопровождения агентства) */}
        <p className="mt-3 text-[11px] leading-relaxed text-white/65">
          Сопровождение агентства (подготовка спикера, целевые встречи, интерактив на стенде) рассчитывается отдельно под выбранные клиентом задачи на витрине.
        </p>
      </div>

      {/* 2. Редактор сопроводительного письма и кнопка публикации (Шаг 06–07) */}
      <div className="rounded-card border border-border bg-surface p-4 shadow-card">
        <div className="flex items-center justify-between gap-2 pb-2 border-b border-border/80">
          <div className="flex items-center gap-2">
            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-pine text-[10px] font-bold text-white tabular-nums">
              03
            </span>
            <span className="text-xs font-semibold uppercase tracking-wider text-ink">
              Персональное обращение к клиенту
            </span>
          </div>

          <button
            type="button"
            onClick={onSyncPitchNumbers}
            title="Автоматически подставить пересчитанную сумму, выгоду и список площадок в текст письма"
            className="inline-flex items-center gap-1 rounded-badge border border-border bg-canvas px-2 py-1 text-[11px] font-medium text-ink-secondary transition-colors hover:border-pine hover:text-pine"
          >
            <RefreshCw className="h-3 w-3" strokeWidth={1.5} />
            <span>Синхронизировать цифры</span>
          </button>
        </div>

        <textarea
          rows={7}
          value={pitchText}
          onChange={(e) => onPitchChange(e.target.value)}
          className="mt-2.5 w-full rounded-control border border-border bg-canvas/50 p-3 text-xs leading-relaxed text-ink focus:border-pine focus:bg-surface focus:outline-none scrollbar-thin"
        />

        <div className="mt-3 space-y-2">
          <Button
            type="button"
            variant="primary"
            size="lg"
            disabled={isPublishing || summary.includedRows.length === 0}
            onClick={onPublish}
            className="w-full"
          >
            {isPublishing ? (
              <span>Публикация витрины...</span>
            ) : (
              <>
                <Send className="h-4 w-4" strokeWidth={1.75} />
                <span>Опубликовать витрину и скопировать ссылку</span>
              </>
            )}
          </Button>

          {publishedUrl && (
            <div className="rounded-control border border-sage-border bg-sage-tint/70 p-2.5">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5 min-w-0">
                  <ShieldCheck className="h-4 w-4 shrink-0 text-sage" strokeWidth={1.75} />
                  <span className="truncate text-xs font-semibold text-sage">
                    Персональная витрина активна
                  </span>
                </div>
                <span className="text-[10px] font-mono text-ink-muted truncate max-w-[130px]">
                  {publishedUrl}
                </span>
              </div>

              <div className="mt-2 grid grid-cols-2 gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => handleCopy(publishedUrl)}
                  className="bg-surface text-xs"
                >
                  {copied ? (
                    <>
                      <Check className="h-3.5 w-3.5 text-sage" />
                      <span>Скопировано</span>
                    </>
                  ) : (
                    <>
                      <Copy className="h-3.5 w-3.5" strokeWidth={1.5} />
                      <span>Скопировать</span>
                    </>
                  )}
                </Button>

                <a
                  href={publishedUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex h-8 items-center justify-center gap-1.5 rounded-control bg-pine px-3 text-xs font-medium text-white transition-colors hover:bg-pine-hover"
                >
                  <ExternalLink className="h-3.5 w-3.5" strokeWidth={1.5} />
                  <span>Открыть витрину</span>
                </a>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Памятка по циклу согласования (Шаг 07 -> Шаг 09) */}
      <div className="rounded-card border border-border bg-surface/70 px-3.5 py-2.5 flex items-start gap-2.5">
        <Sparkles className="h-4 w-4 shrink-0 text-sage mt-0.5" strokeWidth={1.5} />
        <p className="text-[11px] leading-relaxed text-ink-muted">
          После отправки ссылки все отклики клиента (<strong className="text-ink-secondary">Утверждение плана</strong>, <strong className="text-ink-secondary">Запрос правок</strong>, выбор <strong className="text-ink-secondary">Подготовки спикера / Целевых встреч</strong> и вопросы по регламенту) приходят в Telegram и синхронизируются на этом экране каждые 10 секунд.
        </p>
      </div>
    </div>
  );
}

