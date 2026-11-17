import * as React from "react";
import { createPortal } from "react-dom";
import {
  X,
  MapPin,
  Globe,
  Building,
  Check,
  Copy,
  Layers,
  ExternalLink,
  AlertTriangle,
  Upload,
  RefreshCw,
  Archive,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "sonner";
import type { CatalogEventItemOut } from "@/api/types";
import {
  useArchiveEventMutation,
  useRefreshEventMutation,
} from "@/api/queries";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EventImportModal } from "./EventImportModal";
import { copyTextToClipboard } from "@/lib/clipboard";
import {
  FORMAT_LABELS,
  ROLE_BADGE_LABELS,
  formatCalendarBadge,
  formatDateShort,
  formatDateRange,
  formatRub,
} from "@/lib/formatters";
import { humanizeMissingDataWarnings } from "@/lib/warnings";
import { getEventPriceSummary } from "./catalog/catalogUtils";

interface EventDetailsDrawerProps {
  event: CatalogEventItemOut | null;
  isOpen: boolean;
  onClose: () => void;
}

function getSafeHttpUrl(rawUrl: string | null | undefined): string | null {
  if (!rawUrl) return null;
  const trimmed = rawUrl.trim();
  if (!trimmed) return null;
  try {
    const parsed = new URL(trimmed);
    if (parsed.protocol === "http:" || parsed.protocol === "https:") {
      return parsed.toString();
    }
    return null;
  } catch {
    return null;
  }
}

/**
 * Выдвижная шторка детального просмотра мероприятия (Slide-over Drawer 520px).
 * Позволяет менеджеру глубоко изучить тарифы, концепцию и дедлайны без захламления каталога.
 */
export function EventDetailsDrawer({
  event,
  isOpen,
  onClose,
}: EventDetailsDrawerProps) {
  const [copied, setCopied] = React.useState(false);
  const [copiedAddress, setCopiedAddress] = React.useState(false);
  const [isEnrichModalOpen, setIsEnrichModalOpen] = React.useState(false);
  const [confirmArchive, setConfirmArchive] = React.useState(false);

  const refreshMutation = useRefreshEventMutation();
  const archiveMutation = useArchiveEventMutation();

  const summaryTimerRef = React.useRef<number | null>(null);
  const addressTimerRef = React.useRef<number | null>(null);

  React.useEffect(() => {
    setCopied(false);
    setCopiedAddress(false);
    setConfirmArchive(false);
  }, [event?.event_id, isOpen]);

  React.useEffect(() => {
    return () => {
      if (summaryTimerRef.current !== null) {
        window.clearTimeout(summaryTimerRef.current);
      }
      if (addressTimerRef.current !== null) {
        window.clearTimeout(addressTimerRef.current);
      }
    };
  }, []);

  const handleCopyAddress = async (addr: string) => {
    const ok = await copyTextToClipboard(addr, {
      successMessage: `Адрес скопирован: ${addr}`,
    });
    if (!ok) return;
    setCopiedAddress(true);
    if (addressTimerRef.current !== null) {
      window.clearTimeout(addressTimerRef.current);
    }
    addressTimerRef.current = window.setTimeout(() => {
      setCopiedAddress(false);
      addressTimerRef.current = null;
    }, 2000);
  };

  React.useEffect(() => {
    if (!isOpen || isEnrichModalOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, isEnrichModalOpen, onClose]);

  if (!event) return null;

  const cal = formatCalendarBadge(event.start_date, event.end_date);
  const formatLabel = FORMAT_LABELS[event.event_format] || event.event_format;
  const locationLabel = event.is_online ? "Онлайн" : event.city || "Россия";
  const safeWebsiteUrl = getSafeHttpUrl(event.website_url);

  const priceSummary = getEventPriceSummary(event);
  const humanizedWarnings = humanizeMissingDataWarnings(
    event.missing_data_warnings
  );
  const maxSavings = Math.max(0, ...event.tariffs.map((t) => t.savings || 0));

  const handleCopySummary = async () => {
    const priceLabel = priceSummary.subLabel
      ? `${priceSummary.label} (${priceSummary.subLabel})`
      : priceSummary.label;
    const text = `${event.canonical_title}\nДаты: ${formatDateRange(event.start_date, event.end_date)}\nФормат: ${formatLabel} (${locationLabel})\n${event.venue ? `Площадка: ${event.venue}\n` : ""}${safeWebsiteUrl ? `Сайт: ${safeWebsiteUrl}\n` : ""}Тарифы: ${priceLabel}\n\nОписание:\n${event.summary}`;
    const ok = await copyTextToClipboard(text, {
      successMessage: "Описание площадки и тарифов скопировано",
    });
    if (!ok) return;
    setCopied(true);
    if (summaryTimerRef.current !== null) {
      window.clearTimeout(summaryTimerRef.current);
    }
    summaryTimerRef.current = window.setTimeout(() => {
      setCopied(false);
      summaryTimerRef.current = null;
    }, 2000);
  };

  const handleRefreshFromSite = async () => {
    try {
      const res = await refreshMutation.mutateAsync({
        eventId: event.event_id,
        payload: { force: false },
      });
      if (res.updated) {
        toast.success(res.message || "Обновлено");
      } else {
        toast.info(res.message || "На сайте изменений нет");
      }
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Не удалось обновить карточку с сайта"
      );
    }
  };

  const handleConfirmArchive = async () => {
    try {
      await archiveMutation.mutateAsync(event.event_id);
      toast.success("Мероприятие убрано в архив");
      setConfirmArchive(false);
      onClose();
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Не удалось убрать мероприятие в архив"
      );
    }
  };

  if (typeof document === "undefined") return null;

  return (
    <>
      {createPortal(
        <AnimatePresence>
          {isOpen && (
            <div className="fixed inset-0 z-[9999] flex justify-end">
              {/* Полупрозрачный матовый фон */}
              <motion.div
                key="drawer-backdrop"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.22, ease: "easeOut" }}
                onClick={onClose}
                className="fixed inset-0 bg-black/75 backdrop-blur-sm"
              />

              {/* Панель шторки */}
              <motion.aside
                key="drawer-panel"
                initial={{ x: "100%" }}
                animate={{ x: 0 }}
                exit={{ x: "100%" }}
                transition={{ duration: 0.26, ease: [0.22, 1, 0.36, 1] }}
                className="relative z-10 flex h-full w-full max-w-[540px] flex-col border-l border-[#7C5A20]/60 bg-[#161B22] text-white shadow-2xl"
              >
                <div className="border-b border-[#21262F] bg-[#12161A] p-5">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex flex-wrap items-center gap-2 text-xs">
                      <span className="inline-flex items-center gap-1.5 font-serif italic text-[#E5C378]">
                        <span
                          className="not-italic leading-none select-none shrink-0"
                          aria-hidden="true"
                        >
                          ✦
                        </span>
                        <span>Паспорт площадки</span>
                      </span>
                      <span className="text-[#3A4553]">·</span>
                      <span className="font-medium text-[#D1D5DB]">
                        {formatLabel}
                      </span>
                      {event.data_status === "needs_enrichment" ? (
                        <Badge variant="ebAmber" asSlanted={false} className="text-[11px]">
                          Требует обогащения
                        </Badge>
                      ) : event.data_status === "ready" ? (
                        <Badge variant="ebEmerald" asSlanted={false} className="text-[11px]">
                          Готово
                        </Badge>
                      ) : null}
                    </div>

                    <button
                      type="button"
                      onClick={onClose}
                      aria-label="Закрыть шторку"
                      className="rounded-[6px] border border-[#7C5A20]/40 bg-[#161B21] p-1.5 text-[#E5C378] transition-all duration-150 hover:border-[#E5C378] hover:bg-[#261E0F] hover:text-white hover:shadow-[0_0_8px_rgba(229,195,120,0.25)] outline-none"
                    >
                      <X className="h-4 w-4 stroke-[2]" />
                    </button>
                  </div>

                  <div className="mt-3 flex items-start gap-3.5">
                    {/* Календарный листок */}
                    <div className="flex min-h-[64px] min-w-[62px] shrink-0 flex-col items-center justify-center rounded-[6px] border border-[#7C5A20]/60 bg-[#161B21] px-2 py-2 tabular-nums shadow-inner">
                      <span className="text-sm font-bold leading-none text-white">
                        {cal.dayText}
                      </span>
                      <span className="mt-1 text-[11px] font-semibold uppercase tracking-wider text-white/85 leading-none">
                        {cal.monthText}
                      </span>
                      <span className="mt-1 text-[11px] text-[#8E95A0] leading-none">
                        {cal.durationText}
                      </span>
                    </div>

                    <div className="min-w-0 flex-1">
                      <h2 className="font-serif text-base sm:text-lg font-bold leading-snug text-white">
                        {event.canonical_title}
                      </h2>
                      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-[#8E95A0]">
                        <span className="inline-flex items-center gap-1 font-medium text-[#D1D5DB]">
                          {event.is_online ? (
                            <Globe
                              className="h-3.5 w-3.5 text-[#529E85]"
                              strokeWidth={1.5}
                            />
                          ) : (
                            <MapPin
                              className="h-3.5 w-3.5 text-[#8E95A0]"
                              strokeWidth={1.5}
                            />
                          )}
                          <span>{locationLabel}</span>
                        </span>
                        {event.venue && (
                          <>
                            <span>·</span>
                            <span className="inline-flex items-center gap-1 text-[#D1D5DB] leading-relaxed">
                              <Building
                                className="h-3.5 w-3.5 shrink-0 opacity-70"
                                strokeWidth={1.5}
                              />
                              <span>{event.venue}</span>
                            </span>
                          </>
                        )}
                        <button
                          type="button"
                          onClick={() =>
                            handleCopyAddress(
                              event.is_online
                                ? "Онлайн"
                                : `${event.city || ""}${event.venue ? `, ${event.venue}` : ""}`.trim()
                            )
                          }
                          className="inline-flex items-center gap-1 rounded-[4px] border border-[#7C5A20]/50 bg-[#161B21] px-2 py-0.5 text-[11px] text-[#E5C378] hover:border-[#E5C378] hover:bg-[#261E0F] hover:text-white transition-all select-none cursor-pointer"
                          title="Скопировать точный адрес площадки в буфер обмена"
                        >
                          {copiedAddress ? (
                            <>
                              <Check className="h-3 w-3 text-[#34D399]" />
                              <span className="text-[#34D399] font-medium">
                                Скопировано
                              </span>
                            </>
                          ) : (
                            <>
                              <Copy className="h-3 w-3" />
                              <span>Скопировать адрес</span>
                            </>
                          )}
                        </button>
                        {safeWebsiteUrl && (
                          <a
                            href={safeWebsiteUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 rounded-[4px] border border-[#7C5A20]/50 bg-[#161B21] px-2 py-0.5 text-[11px] text-[#E5C378] hover:border-[#E5C378] hover:bg-[#261E0F] hover:text-white transition-all select-none cursor-pointer"
                            title="Перейти на официальный сайт мероприятия в новой вкладке"
                          >
                            <ExternalLink className="h-3 w-3 stroke-[2]" />
                            <span>Сайт события</span>
                          </a>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Экспресс-сводка по стоимости и выгоде */}
                  <div className="mt-4 flex flex-wrap items-center gap-2 pt-3 border-t border-[#21262F] text-xs">
                    <div className="inline-flex items-center gap-1.5 rounded-[6px] border border-[#262D35] bg-[#161B21] px-2.5 py-1 text-[11px] text-[#8E95A0]">
                      <Layers
                        className="h-3.5 w-3.5 text-[#E5C378]"
                        strokeWidth={1.5}
                      />
                      <span>Тарифов:</span>
                      <strong className="text-white font-bold tabular-nums">
                        {event.tariffs.length}
                      </strong>
                    </div>
                    <div className="inline-flex items-center gap-1.5 rounded-[6px] border border-[#262D35] bg-[#161B21] px-2.5 py-1 text-[11px] text-[#8E95A0]">
                      <span>Входной порог:</span>
                      <strong className="text-white font-bold tabular-nums">
                        {priceSummary.label}
                      </strong>
                      {priceSummary.subLabel && (
                        <span className="text-[11px] text-[#E5C378]/90">
                          ({priceSummary.subLabel})
                        </span>
                      )}
                    </div>
                    {maxSavings > 0 && (
                      <Badge variant="ebEmerald" asSlanted={false} className="text-[11px]">
                        Выгода до {formatRub(maxSavings)}
                      </Badge>
                    )}
                  </div>
                </div>

                <div className="flex-1 space-y-5 overflow-y-auto p-5 scrollbar-thin">
                  {(event.data_status === "needs_enrichment" ||
                    humanizedWarnings.length > 0) && (
                      <div className="rounded-[8px] border border-[#7C4A19] bg-[#22160C] p-3 text-xs space-y-2">
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-1.5 font-semibold text-[#E59837]">
                            <AlertTriangle className="h-4 w-4 shrink-0" />
                            <span>Недостающие данные карточки</span>
                          </div>
                          <button
                            type="button"
                            onClick={() => setIsEnrichModalOpen(true)}
                            className="inline-flex items-center gap-1 rounded-[4px] border border-[#E5C378]/60 bg-[#1E190E] px-2 py-0.5 text-[11px] font-medium text-[#E5C378] hover:border-[#E5C378] hover:bg-[#261E0F] hover:text-white transition-colors"
                          >
                            <Upload className="h-3 w-3" />
                            <span>Дополнить из PDF / URL</span>
                          </button>
                        </div>
                        {humanizedWarnings.length > 0 ? (
                          <ul className="list-disc pl-4 space-y-0.5 text-[#FDE68A]/90">
                            {humanizedWarnings.map((w) => (
                              <li key={w}>{w}</li>
                            ))}
                          </ul>
                        ) : (
                          <p className="text-[#FDE68A]/90">
                            Загрузите PDF-брошюру или ссылку с тарифами, чтобы перевести площадку в статус «Готово».
                          </p>
                        )}
                      </div>
                    )}

                  {/* Концепция и описание площадки */}
                  <div>
                    <span className="font-serif italic text-xs font-semibold tracking-wide text-[#E5C378]">
                      Концепция и профиль аудитории
                    </span>
                    <p className="mt-1.5 text-xs leading-relaxed text-[#D1D5DB]">
                      {event.summary}
                    </p>

                    {event.themes.length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-1.5">
                        {event.themes.map((t) => (
                          <span
                            key={t}
                            className="rounded-[4px] border border-[#262D35] bg-[#12161A] px-2 py-0.5 text-[11px] font-medium text-[#8E95A0]"
                          >
                            {t}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Развернутая сетка тарифов организатора */}
                  <div className="border-t border-[#21262F] pt-4">
                    <div className="mb-3 flex items-center justify-between">
                      <span className="font-serif italic text-xs font-semibold tracking-wide text-[#E5C378]">
                        Тарифная сетка и условия участия
                      </span>
                    </div>

                    {event.tariffs.length === 0 ? (
                      <div className="rounded-[8px] border border-[#262D35] bg-[#12161A] p-4 text-center text-xs text-[#8E95A0]">
                        Тарифы ещё не извлечены. Используйте кнопку «Обогатить из PDF / ссылки» ниже.
                      </div>
                    ) : (
                      <div className="space-y-2.5">
                        {event.tariffs.map((t) => (
                          <div
                            key={t.tariff_id}
                            className="rounded-[8px] border border-[#262D35] bg-[#12161A] p-3.5 transition-colors duration-150 hover:border-[#3E4957]"
                          >
                            <div className="flex items-start justify-between gap-2">
                              <div className="min-w-0">
                                <h4 className="font-serif text-sm font-semibold text-white">
                                  {t.tariff_name}
                                </h4>
                                <span className="mt-0.5 inline-block text-[11px] text-[#8E95A0] font-serif italic">
                                  Роль:{" "}
                                  {ROLE_BADGE_LABELS[t.participation_role] ||
                                    t.participation_role}
                                </span>
                              </div>

                              <Badge
                                variant={
                                  t.participation_role === "speaker"
                                    ? "ebGold"
                                    : t.participation_role === "sponsor"
                                      ? "ebRose"
                                      : "ebBlue"
                                }
                                className="text-[11px] shrink-0"
                              >
                                {ROLE_BADGE_LABELS[t.participation_role] ||
                                  t.participation_role}
                              </Badge>
                            </div>

                            {/* Цены и спецтарифы Early Bird */}
                            <div className="mt-2.5 flex flex-wrap items-baseline justify-between gap-2 border-t border-[#1F252D] pt-2 tabular-nums">
                              <div className="flex items-baseline gap-2">
                                <span className="font-sans text-base font-bold text-white">
                                  {formatRub(t.actual_price)}
                                </span>
                                {t.savings > 0 && t.base_price && (
                                  <span className="text-xs text-[#8E95A0] line-through">
                                    {formatRub(t.base_price)}
                                  </span>
                                )}
                              </div>

                              {t.savings > 0 ? (
                                <Badge variant="ebEmerald" asSlanted={false} className="text-[11px]">
                                  Выгода {formatRub(t.savings)}
                                  {t.early_bird_deadline
                                    ? ` до ${formatDateShort(t.early_bird_deadline)}`
                                    : ""}
                                </Badge>
                              ) : (
                                <span className="text-xs text-[#8E95A0] font-serif italic">
                                  Базовый тариф
                                </span>
                              )}
                            </div>

                            {/* Что входит в тариф */}
                            {t.included_benefits && (
                              <div className="mt-2.5 rounded-[4px] border border-[#262D35]/70 bg-[#161B21] p-2 text-xs text-[#8E95A0] leading-relaxed">
                                <div className="flex items-center gap-1 font-semibold text-[#D1D5DB] text-[11px] mb-0.5">
                                  <Check
                                    className="h-3 w-3 text-[#34D399]"
                                    strokeWidth={2}
                                  />
                                  <span>Включено в пакет:</span>
                                </div>
                                <p>{t.included_benefits}</p>
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                <div className="border-t border-[#21262F] bg-[#12161A] p-4 flex flex-col gap-2">
                  <div className="flex flex-col sm:flex-row items-center gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={!safeWebsiteUrl || refreshMutation.isPending || archiveMutation.isPending}
                      onClick={handleRefreshFromSite}
                      title={
                        safeWebsiteUrl
                          ? "Проверить изменения на сайте и обновить карточку"
                          : "У мероприятия нет ссылки на сайт"
                      }
                      className="w-full sm:flex-1 h-9 border-[#262D35] bg-[#161B21] text-xs font-medium text-[#D1D5DB] hover:border-[#E5C378] hover:text-[#E5C378] hover:bg-[#1E252E] transition-all"
                    >
                      <RefreshCw
                        className={`h-3.5 w-3.5 text-[#E5C378] ${refreshMutation.isPending ? "animate-spin" : ""}`}
                      />
                      <span>
                        {refreshMutation.isPending ? "Обновление..." : "Обновить с сайта"}
                      </span>
                    </Button>

                    {confirmArchive ? (
                      <div className="w-full sm:w-auto flex items-center justify-between gap-1.5 rounded-[6px] border border-rose-500/40 bg-rose-950/30 px-2.5 h-9 text-xs shrink-0">
                        <span className="text-rose-200 whitespace-nowrap">Убрать в архив?</span>
                        <div className="flex items-center gap-1">
                          <button
                            type="button"
                            disabled={archiveMutation.isPending}
                            onClick={handleConfirmArchive}
                            className="rounded px-2 py-0.5 font-semibold bg-rose-600 text-white hover:bg-rose-500 disabled:opacity-50 transition-colors"
                          >
                            {archiveMutation.isPending ? "..." : "Да"}
                          </button>
                          <button
                            type="button"
                            disabled={archiveMutation.isPending}
                            onClick={() => setConfirmArchive(false)}
                            className="rounded px-2 py-0.5 text-[#D1D5DB] hover:bg-[#262D35] transition-colors"
                          >
                            Нет
                          </button>
                        </div>
                      </div>
                    ) : (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        disabled={refreshMutation.isPending || archiveMutation.isPending}
                        onClick={() => setConfirmArchive(true)}
                        className="w-full sm:w-auto h-9 border-[#262D35] bg-[#161B21] text-xs font-medium text-[#8E95A0] hover:border-rose-500/50 hover:text-rose-300 hover:bg-rose-950/20 transition-all shrink-0"
                      >
                        <Archive className="h-3.5 w-3.5" />
                        <span>В архив</span>
                      </Button>
                    )}
                  </div>

                  <div className="flex flex-col sm:flex-row items-center gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => setIsEnrichModalOpen(true)}
                      className="w-full sm:w-auto h-9 border-[#262D35] bg-[#161B21] text-xs font-medium text-[#D1D5DB] hover:border-[#E5C378] hover:text-[#E5C378] hover:bg-[#1E252E] transition-all shrink-0"
                    >
                      <Upload className="h-3.5 w-3.5 text-[#E5C378]" />
                      <span>Обогатить из PDF / ссылки</span>
                    </Button>

                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={handleCopySummary}
                      className="w-full flex-1 h-9 border-[#7C5A20]/60 bg-[#1E190E] text-xs font-serif italic text-[#E5C378] hover:border-[#E5C378] hover:bg-[#261E0F] hover:text-white hover:shadow-[0_0_10px_rgba(229,195,120,0.2)] transition-all"
                    >
                      {copied ? (
                        <>
                          <Check className="h-3.5 w-3.5 text-[#34D399]" />
                          <span>Описание скопировано в буфер</span>
                        </>
                      ) : (
                        <>
                          <Copy className="h-3.5 w-3.5 text-[#E5C378]" />
                          <span>Скопировать описание и тарифы</span>
                        </>
                      )}
                    </Button>
                  </div>
                </div>
              </motion.aside>
            </div>
          )}
        </AnimatePresence>,
        document.body
      )}

      <EventImportModal
        isOpen={isEnrichModalOpen}
        onClose={() => setIsEnrichModalOpen(false)}
        initialSourceUrl={safeWebsiteUrl}
        initialEventTitle={event.canonical_title}
      />
    </>
  );
}
