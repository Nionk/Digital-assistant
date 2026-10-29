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
    <section className="rounded-[12px] border border-[#262D35] bg-[#161B22] p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#21262F] pb-3">
        <div className="flex items-center gap-2.5">
          <span className="h-2.5 w-2.5 rounded-full bg-[#34D399] animate-pulse" />
          <div>
            <div className="flex items-center gap-2">
              <span className="rounded-[4px] border border-[#2B3545] bg-[#12161A] text-[#D1D5DB] px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider tabular-nums font-serif italic">
                LIVE СТАТУС
              </span>
              <h3 className="font-serif text-sm font-semibold text-white">
                Мониторинг согласования витрины
              </h3>
              <Badge variant="ebEmerald" className="text-[9px]">
                ОПУБЛИКОВАНО
              </Badge>
            </div>
            <p className="mt-0.5 text-xs text-[#8E95A0] tabular-nums">
              Площадок в КП: {showcase.total_events_count} · Взносы:{" "}
              <strong className="text-white">{formatRub(showcase.total_actual_price)}</strong>
              {showcase.total_savings > 0 && (
                <>
                  {" "}
                  · Выгода по спецтарифам:{" "}
                  <strong className="text-[#34D399]">
                    {formatRub(showcase.total_savings)}
                  </strong>
                </>
              )}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <div className="hidden sm:flex items-center gap-1.5 mr-2 text-xs tabular-nums">
            <Badge variant="ebTeal" className="text-[9px]">
              ОДОБРЕНО: {approvedCount}
            </Badge>
            {rejectedCount > 0 && (
              <Badge variant="ebRose" className="text-[9px]">
                ЗАПРОС ЗАМЕНЫ: {rejectedCount}
              </Badge>
            )}
          </div>

          <Button type="button" variant="outline" size="sm" onClick={handleCopy} className="border-[#262D35] bg-[#12161A] text-white hover:bg-[#1A2128]">
            {copied ? (
              <>
                <Check className="h-3.5 w-3.5 text-[#34D399]" />
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
            className="inline-flex h-8 items-center gap-1.5 rounded-[6px] border border-[#38BDF8]/40 bg-[#121E2C] px-3 text-xs font-medium text-[#60A5FA] transition-colors hover:bg-[#1A2D44] hover:text-white"
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
              className="flex flex-col justify-between rounded-[8px] border border-[#262C35] bg-[#1A1E24] p-3"
            >
              <div>
                <div className="flex items-center justify-between gap-2">
                  <Badge
                    variant={
                      item.participation_role === "speaker"
                        ? "ebGold"
                        : item.participation_role === "sponsor"
                          ? "ebRose"
                          : "ebBlue"
                    }
                  >
                    {ROLE_BADGE_LABELS[item.participation_role]}
                  </Badge>

                  {isInterested ? (
                    <span className="inline-flex items-center gap-1 rounded-[4px] bg-[#0B2528] px-2 py-0.5 text-[10px] font-bold text-[#2DD4BF] border border-[#165057] uppercase tracking-wider font-serif italic">
                      <ThumbsUp className="h-3 w-3" strokeWidth={1.75} />
                      ИНТЕРЕСНО
                    </span>
                  ) : isRejected ? (
                    <span className="inline-flex items-center gap-1 rounded-[4px] bg-[#28131E] px-2 py-0.5 text-[10px] font-bold text-[#F472B6] border border-[#5E2242] uppercase tracking-wider font-serif italic">
                      <RefreshCcw className="h-3 w-3" strokeWidth={1.75} />
                      ЗАПРОС ЗАМЕНЫ
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 rounded-[4px] bg-[#161B21] px-2 py-0.5 text-[10px] text-[#8E95A0] border border-[#2B3545] uppercase tracking-wider font-serif italic">
                      <Clock className="h-3 w-3" strokeWidth={1.5} />
                      ОЖИДАЕТ РЕШЕНИЯ
                    </span>
                  )}
                </div>

                <h4 className="mt-2 text-xs font-semibold leading-snug text-white">
                  {item.canonical_title}
                </h4>
                <p className="mt-0.5 text-[11px] text-[#8E95A0]">
                  {item.is_online ? "Онлайн" : item.city} ·{" "}
                  {formatDateRange(item.start_date, item.end_date)} ·{" "}
                  <strong className="text-[#D1D5DB] tabular-nums">
                    {formatRub(item.actual_price)}
                  </strong>
                </p>
              </div>

              {item.client_comment && (
                <div className="mt-2.5 rounded-[6px] border border-[#262C35] bg-[#12161A] p-2 text-[11px] text-[#D1D5DB]">
                  <div className="flex items-center gap-1 font-semibold text-white">
                    <MessageSquare className="h-3 w-3 text-[#38BDF8]" strokeWidth={1.5} />
                    <span>Комментарий клиента:</span>
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

