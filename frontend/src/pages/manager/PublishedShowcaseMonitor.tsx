import {
  ThumbsUp,
  RefreshCcw,
  Clock,
  ExternalLink,
  Copy,
  Check,
  MessageSquare,
} from "lucide-react";
import * as React from "react";
import { usePublicShowcase } from "@/api/queries";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  ROLE_BADGE_LABELS,
  formatDateRange,
  formatRub,
} from "@/lib/formatters";

interface PublishedShowcaseMonitorProps {
  magicToken: string;
  onCopyLink: (url: string) => void;
}

/**
 * Панель живого мониторинга опубликованной витрины клиента (TanStack Query Polling 10s).
 * Позволяет менеджеру сразу видеть статус согласования (Шаг 07) и запрошенные услуги подготовки (Шаг 09).
 */
export function PublishedShowcaseMonitor({
  magicToken,
  onCopyLink,
}: PublishedShowcaseMonitorProps) {
  const { data: showcase, isLoading } = usePublicShowcase(magicToken, 10000);
  const [copied, setCopied] = React.useState(false);

  const relativeUrl = `/s/${magicToken}`;

  const handleCopy = () => {
    onCopyLink(relativeUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (isLoading || !showcase) {
    return null;
  }

  const approvedCount = showcase.items.filter(
    (i) => i.client_reaction === "interested"
  ).length;
  const rejectedCount = showcase.items.filter(
    (i) => i.client_reaction === "rejected"
  ).length;

  return (
    <section className="rounded-card border border-sage-border bg-surface p-4 shadow-card">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-3">
        <div className="flex items-center gap-2.5">
          <span className="h-2.5 w-2.5 rounded-full bg-sage animate-pulse" />
          <div>
            <div className="flex items-center gap-2">
              <span className="rounded-tag bg-pine text-white px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider">
                LIVE СТАТУС
              </span>
              <h3 className="font-serif text-sm font-semibold text-ink">
                Мониторинг согласования витрины
              </h3>
              <Badge variant="novelSand" className="text-[9px]">
                ОПУБЛИКОВАНО
              </Badge>
            </div>
            <p className="mt-0.5 text-xs text-ink-muted tabular-nums">
              Площадок в КП: {showcase.total_events_count} · Взносы:{" "}
              <strong className="text-ink">{formatRub(showcase.total_actual_price)}</strong>
              {showcase.total_savings > 0 && (
                <>
                  {" "}
                  · Выгода по спецтарифам:{" "}
                  <strong className="text-sage">
                    {formatRub(showcase.total_savings)}
                  </strong>
                </>
              )}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <div className="hidden sm:flex items-center gap-1.5 mr-2 text-xs tabular-nums">
            <Badge variant="novelSand" className="text-[9px]">
              ОДОБРЕНО: {approvedCount}
            </Badge>
            {rejectedCount > 0 && (
              <Badge variant="novelWine" className="text-[9px]">
                ЗАПРОС ЗАМЕНЫ: {rejectedCount}
              </Badge>
            )}
          </div>

          <Button type="button" variant="outline" size="sm" onClick={handleCopy}>
            {copied ? (
              <>
                <Check className="h-3.5 w-3.5 text-sage" />
                <span>Ссылка скопирована</span>
              </>
            ) : (
              <>
                <Copy className="h-3.5 w-3.5" strokeWidth={1.5} />
                <span>Скопировать ссылку</span>
              </>
            )}
          </Button>

          <a
            href={relativeUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex h-8 items-center gap-1.5 rounded-control bg-pine px-3 text-xs font-medium text-white transition-colors hover:bg-pine-hover"
          >
            <ExternalLink className="h-3.5 w-3.5" strokeWidth={1.5} />
            <span>Витрина клиента</span>
          </a>
        </div>
      </div>

      {/* Статусы и комментарии клиента по каждому мероприятию опубликованного пакета */}
      <div className="mt-3 grid grid-cols-1 gap-2.5 md:grid-cols-3">
        {showcase.items.map((item) => {
          const isInterested = item.client_reaction === "interested";
          const isRejected = item.client_reaction === "rejected";

          return (
            <div
              key={item.selection_item_id}
              className="flex flex-col justify-between rounded-control border border-border bg-canvas/50 p-3"
            >
              <div>
                <div className="flex items-center justify-between gap-2">
                  <Badge variant="neutral">
                    {ROLE_BADGE_LABELS[item.participation_role]}
                  </Badge>

                  {isInterested ? (
                    <span className="inline-flex items-center gap-1 rounded-badge bg-sage-tint px-2 py-0.5 text-[11px] font-semibold text-sage border border-sage-border">
                      <ThumbsUp className="h-3 w-3" strokeWidth={1.75} />
                      Интересно
                    </span>
                  ) : isRejected ? (
                    <span className="inline-flex items-center gap-1 rounded-badge bg-terracotta-tint px-2 py-0.5 text-[11px] font-semibold text-terracotta border border-terracotta-border">
                      <RefreshCcw className="h-3 w-3" strokeWidth={1.75} />
                      Запрошена замена
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 rounded-badge bg-surface px-2 py-0.5 text-[11px] text-ink-muted border border-border">
                      <Clock className="h-3 w-3" strokeWidth={1.5} />
                      Ожидает решения
                    </span>
                  )}
                </div>

                <h4 className="mt-2 text-xs font-semibold leading-snug text-ink">
                  {item.canonical_title}
                </h4>
                <p className="mt-0.5 text-[11px] text-ink-muted">
                  {item.is_online ? "Онлайн" : item.city} ·{" "}
                  {formatDateRange(item.start_date, item.end_date)} ·{" "}
                  <strong className="text-ink-secondary tabular-nums">
                    {formatRub(item.actual_price)}
                  </strong>
                </p>
              </div>

              {item.client_comment && (
                <div className="mt-2.5 rounded border border-border bg-surface p-2 text-[11px] text-ink-secondary">
                  <div className="flex items-center gap-1 font-semibold text-ink">
                    <MessageSquare className="h-3 w-3 text-pine" strokeWidth={1.5} />
                    <span>Комментарий / Запрос подготовки (Этап 09):</span>
                  </div>
                  <p className="mt-0.5 leading-relaxed">{item.client_comment}</p>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

