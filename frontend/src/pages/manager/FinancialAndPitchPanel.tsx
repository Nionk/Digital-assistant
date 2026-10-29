import {
  Copy,
  ExternalLink,
  RefreshCw,
  Send,
  ShieldCheck,
  AlertTriangle,
  Sparkles,
  Check,
  Layers,
} from "lucide-react";
import * as React from "react";
import type { ComputedFinancialSummary } from "@/store/useManagerStore";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
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
    <div className="sticky top-[80px] space-y-3">
      {/* 1. Финансовый блок коммерческого предложения */}
      <div className="rounded-[12px] border border-[#262D35] bg-[#161B22] p-4 text-white shadow-sm">
        <div className="flex items-center justify-between border-b border-[#21262F] pb-2.5">
          <div>
            <span className="font-serif italic font-semibold text-xs tracking-wide text-[#E5C378]">
              Сводка коммерческого предложения
            </span>
            <h3 className="font-serif text-base font-semibold text-white mt-0.5">
              {companyName}
            </h3>
          </div>
          <div className="inline-flex items-center gap-1.5 rounded-[6px] border border-[#262D35] bg-[#12161A] px-2 py-0.5 select-none">
            <Layers className="h-3.5 w-3.5 text-[#E5C378]" strokeWidth={1.5} />
            <span className="font-serif italic text-[11px] text-[#8E95A0]">Площадок:</span>
            <span className="rounded-[4px] border border-[#2D3642] bg-[#1E252E] px-1.5 py-0.5 font-sans font-bold text-xs text-white tabular-nums leading-none">
              {summary.includedRows.length}
            </span>
          </div>
        </div>

        {/* Основная сумма внешних расходов */}
        <div className="mt-3.5">
          <div className="flex items-baseline justify-between">
            <span className="text-xs text-[#8E95A0]">
              Организационные взносы площадок:
            </span>
            {summary.totalSavings > 0 && (
              <span className="text-xs text-[#727985] line-through tabular-nums">
                {formatRub(summary.totalBasePrice)}
              </span>
            )}
          </div>

          <div className="mt-1 flex items-baseline justify-between gap-2 tabular-nums">
            <span className="text-2xl font-bold tracking-tight text-white">
              {formatRub(summary.totalActualPrice)}
            </span>
            {summary.hasOnRequestIncluded && (
              <span className="text-[11px] font-medium text-[#2DD4BF]">
                + спецпроект по запросу
              </span>
            )}
          </div>
        </div>

        {/* Выгода Early Bird / спецтарифы */}
        {summary.totalSavings > 0 && (
          <div className="mt-3 rounded-[8px] border border-[#1E5241] bg-[#0E241E]/90 p-2.5">
            <div className="flex items-center justify-between tabular-nums">
              <span className="font-serif italic text-xs font-semibold text-[#D1D5DB]">
                Выгода по спецтарифам:
              </span>
              <Badge variant="ebEmerald">
                −{formatRub(summary.totalSavings)}{" "}
                {savingsPct > 0 ? `(${savingsPct}%)` : ""}
              </Badge>
            </div>
            {summary.earliestDeadline && (
              <p className="mt-1 text-[11px] text-[#8E95A0] tabular-nums">
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
          <div className="mt-3 pt-2.5 border-t border-[#21262F]">
            <div className="flex items-center justify-between text-[11px] text-[#8E95A0] tabular-nums">
              <span>Целевой лимит клиента:</span>
              <span className="text-white">{formatRub(summary.budgetMax)}</span>
            </div>
            <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-[#12161A]">
              <div
                className={cn(
                  "h-full transition-all duration-300",
                  summary.isOverBudget ? "bg-[#EF4444]" : "bg-[#34D399]"
                )}
                style={{ width: `${budgetRatioPct}%` }}
              />
            </div>

            {summary.isOverBudget && (
              <div className="mt-2 flex items-start gap-1.5 rounded-[4px] border border-[#7C4A19] bg-[#22160C] px-2.5 py-1.5 text-[11px] text-[#E59837]">
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

        {/* Пояснение по Слайду 10 */}
        <p className="mt-3 text-[11px] leading-relaxed text-[#727985]">
          Сопровождение агентства (подготовка спикера, целевые встречи, интерактив на стенде) рассчитывается отдельно под выбранные клиентом задачи на витрине.
        </p>
      </div>

      {/* 2. Редактор сопроводительного письма и кнопка публикации (Шаг 06–07) */}
      <div className="rounded-[12px] border border-[#262D35] bg-[#161B22] p-4 shadow-sm">
        <div className="flex items-center justify-between gap-2 pb-2 border-b border-[#21262F]">
          <div className="flex items-baseline gap-2">
            <span className="font-serif italic font-bold text-base sm:text-lg text-[#E5C378] select-none">
              03
            </span>
            <h2 className="font-serif italic text-sm sm:text-[15px] font-semibold tracking-tight text-[#E5C378]">
              Персональное обращение к клиенту
            </h2>
          </div>

          <button
            type="button"
            onClick={onSyncPitchNumbers}
            title="Автоматически подставить пересчитанную сумму, выгоду и список площадок в текст письма"
            className="group relative inline-flex items-center gap-1.5 rounded-[6px] border border-[#262D35] bg-[#12161A] px-2.5 py-1 text-[11px] font-medium text-[#D1D5DB] select-none cursor-pointer overflow-hidden shadow-sm transition-all duration-150 hover:border-[#E5C378] hover:bg-[#1E252E] hover:text-white hover:shadow-[0_0_10px_rgba(229,195,120,0.2)]"
          >
            <RefreshCw className="h-3 w-3 shrink-0 text-inherit transition-colors duration-150 group-hover:text-[#E5C378]" strokeWidth={2} />
            <span className="transition-colors duration-150">Синхронизировать цифры</span>
          </button>
        </div>

        <textarea
          rows={7}
          value={pitchText}
          onChange={(e) => onPitchChange(e.target.value)}
          className="mt-2.5 w-full rounded-[8px] border border-[#262D35] bg-[#12161A] p-3 text-xs leading-relaxed text-white [color-scheme:dark] outline-none focus:outline-none focus-visible:outline-none active:outline-none focus:border-[#E5C378] focus:shadow-[0_0_0_1px_rgba(229,195,120,0.25)] transition-colors duration-150 scrollbar-thin"
        />

        <div className="mt-3 space-y-2">
          <Button
            type="button"
            variant="primary"
            size="lg"
            disabled={isPublishing || summary.includedRows.length === 0}
            onClick={onPublish}
            className="w-full bg-gradient-to-r from-[#D4AF37] via-[#E5C378] to-[#D4AF37] text-[#0E1215] font-semibold hover:shadow-[0_0_12px_rgba(229,195,120,0.35)] active:scale-[0.98] active:brightness-150 transition-all duration-100 ease-out"
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
            <div className="rounded-[8px] border border-[#1E5241] bg-[#0E241E]/90 p-2.5">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5 min-w-0">
                  <ShieldCheck className="h-4 w-4 shrink-0 text-[#34D399]" strokeWidth={1.75} />
                  <span className="truncate text-xs font-semibold text-[#34D399]">
                    Персональная витрина активна
                  </span>
                </div>
                <span className="text-[10px] font-mono text-[#8E95A0] truncate max-w-[130px]">
                  {publishedUrl}
                </span>
              </div>

              <div className="mt-2 grid grid-cols-2 gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => handleCopy(publishedUrl)}
                  className="border-[#262D35] bg-[#12161A] text-xs text-white hover:border-[#E5C378] hover:text-[#E5C378] hover:bg-[#1A2128] transition-colors"
                >
                  {copied ? (
                    <>
                      <Check className="h-3.5 w-3.5 text-[#34D399]" />
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
                  className="inline-flex h-8 items-center justify-center gap-1.5 rounded-[6px] border border-[#38BDF8]/50 bg-[#121E2C] px-3 text-xs font-medium text-[#60A5FA] transition-all duration-200 hover:bg-[#1E3A5F] hover:text-[#BAE6FD] hover:border-[#38BDF8] hover:shadow-[0_0_12px_rgba(56,189,248,0.25)]"
                >
                  <ExternalLink className="h-3.5 w-3.5" strokeWidth={1.75} />
                  <span>Открыть витрину</span>
                </a>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Памятка по циклу согласования (Шаг 07 -> Шаг 09) */}
      <div className="rounded-[8px] border border-[#262D35] bg-[#161B22]/70 px-3.5 py-2.5 flex items-start gap-2.5">
        <Sparkles className="h-4 w-4 shrink-0 text-[#E5C378] mt-0.5" strokeWidth={1.5} />
        <p className="text-[11px] leading-relaxed text-[#8E95A0]">
          После отправки ссылки все отклики клиента (<strong className="font-bold text-inherit">Утверждение плана</strong>, <strong className="font-bold text-inherit">Запрос правок</strong>, выбор <strong className="font-bold text-inherit">Подготовки спикера / Целевых встреч</strong> и вопросы по регламенту) приходят в Telegram и синхронизируются на этом экране каждые 10 секунд.
        </p>
      </div>
    </div>
  );
}

