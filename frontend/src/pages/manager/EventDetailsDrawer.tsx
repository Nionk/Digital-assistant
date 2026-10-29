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
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import type { CatalogEventItemOut } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  FORMAT_LABELS,
  ROLE_BADGE_LABELS,
  formatCalendarBadge,
  formatDateShort,
  formatDateRange,
  formatRub,
} from "@/lib/formatters";

interface EventDetailsDrawerProps {
  event: CatalogEventItemOut | null;
  isOpen: boolean;
  onClose: () => void;
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

  React.useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!event) return null;

  const cal = formatCalendarBadge(event.start_date, event.end_date);
  const formatLabel = FORMAT_LABELS[event.event_format] || event.event_format;
  const locationLabel = event.is_online ? "Онлайн" : event.city || "Россия";

  const minPrice = event.tariffs.reduce<number | null>((acc, t) => {
    if (t.actual_price === null) return acc;
    if (acc === null) return t.actual_price;
    return Math.min(acc, t.actual_price);
  }, null);

  const maxSavings = Math.max(0, ...event.tariffs.map((t) => t.savings || 0));

  const handleCopySummary = () => {
    const text = `${event.canonical_title}\nДаты: ${formatDateRange(event.start_date, event.end_date)}\nФормат: ${formatLabel} (${locationLabel})\n${event.venue ? `Площадка: ${event.venue}\n` : ""}Тарифы: от ${minPrice ? formatRub(minPrice) : "По запросу"}\n\nОписание:\n${event.summary}`;
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (typeof document === "undefined") return null;

  return createPortal(
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-[9999] flex justify-end">
          {/* Полупрозрачный матовый фон */}
          <motion.div
            key="drawer-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18, ease: "easeOut" }}
            onClick={onClose}
            className="fixed inset-0 bg-black/75 backdrop-blur-sm"
          />

          {/* Панель шторки */}
          <motion.aside
            key="drawer-panel"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
            className="relative z-10 flex h-full w-full max-w-[540px] flex-col border-l border-[#7C5A20]/60 bg-[#161B22] text-white shadow-2xl"
          >
            {/* 1. Шапка шторки */}
            <div className="border-b border-[#21262F] bg-[#12161A] p-5">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-2 text-xs">
                  <span className="font-serif italic text-[#E5C378]">✦ Паспорт площадки</span>
                  <span className="text-[#3A4553]">·</span>
                  <span className="font-medium text-[#D1D5DB]">{formatLabel}</span>
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
                  <span className="mt-1 text-[10px] font-semibold uppercase tracking-wider text-white/85 leading-none">
                    {cal.monthText}
                  </span>
                  <span className="mt-1 text-[9px] text-[#8E95A0] leading-none">
                    {cal.durationText}
                  </span>
                </div>

                <div className="min-w-0 flex-1">
                  <h2 className="font-serif text-base sm:text-lg font-bold leading-snug text-white">
                    {event.canonical_title}
                  </h2>
                  <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-[#8E95A0]">
                    <span className="inline-flex items-center gap-1 font-medium text-[#D1D5DB]">
                      {event.is_online ? (
                        <Globe className="h-3.5 w-3.5 text-[#529E85]" strokeWidth={1.5} />
                      ) : (
                        <MapPin className="h-3.5 w-3.5 text-[#8E95A0]" strokeWidth={1.5} />
                      )}
                      <span>{locationLabel}</span>
                    </span>
                    {event.venue && (
                      <>
                        <span>·</span>
                        <span className="inline-flex items-center gap-1 truncate max-w-[260px] text-[#D1D5DB]">
                          <Building className="h-3.5 w-3.5 shrink-0 opacity-70" strokeWidth={1.5} />
                          <span className="truncate">{event.venue}</span>
                        </span>
                      </>
                    )}
                  </div>
                </div>
              </div>

              {/* Экспресс-сводка по стоимости и выгоде */}
              <div className="mt-4 flex flex-wrap items-center gap-2 pt-3 border-t border-[#21262F] text-xs">
                <div className="inline-flex items-center gap-1.5 rounded-[6px] border border-[#262D35] bg-[#161B21] px-2.5 py-1 text-[11px] text-[#8E95A0]">
                  <Layers className="h-3.5 w-3.5 text-[#E5C378]" strokeWidth={1.5} />
                  <span>Тарифов:</span>
                  <strong className="text-white font-bold tabular-nums">{event.tariffs.length}</strong>
                </div>
                <div className="inline-flex items-center gap-1.5 rounded-[6px] border border-[#262D35] bg-[#161B21] px-2.5 py-1 text-[11px] text-[#8E95A0]">
                  <span>Входной порог:</span>
                  <strong className="text-white font-bold tabular-nums">
                    {minPrice !== null ? `от ${formatRub(minPrice)}` : "По запросу"}
                  </strong>
                </div>
                {maxSavings > 0 && (
                  <Badge variant="ebEmerald" className="text-[10px]">
                    Выгода до {formatRub(maxSavings)}
                  </Badge>
                )}
              </div>
            </div>

            {/* 2. Тело шторки (скроллируемая область) */}
            <div className="flex-1 space-y-5 overflow-y-auto p-5 scrollbar-thin">
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
                  <span className="font-serif italic text-[11px] text-[#8E95A0]">
                    Цены организатора без наценок
                  </span>
                </div>

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
                            Роль: {ROLE_BADGE_LABELS[t.participation_role] || t.participation_role}
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
                          className="text-[9px] shrink-0"
                        >
                          {ROLE_BADGE_LABELS[t.participation_role] || t.participation_role}
                        </Badge>
                      </div>

                      {/* Цены и спецтарифы Early Bird */}
                      <div className="mt-2.5 flex flex-wrap items-baseline justify-between gap-2 border-t border-[#1F252D] pt-2 tabular-nums">
                        <div className="flex items-baseline gap-2">
                          <span className="font-sans text-base font-bold text-white">
                            {formatRub(t.actual_price)}
                          </span>
                          {t.savings > 0 && t.base_price && (
                            <span className="text-xs text-[#727985] line-through">
                              {formatRub(t.base_price)}
                            </span>
                          )}
                        </div>

                        {t.savings > 0 ? (
                          <Badge variant="ebEmerald" className="text-[10px]">
                            Выгода {formatRub(t.savings)}
                            {t.early_bird_deadline
                              ? ` до ${formatDateShort(t.early_bird_deadline)}`
                              : ""}
                          </Badge>
                        ) : (
                          <span className="text-xs text-[#727985] font-serif italic">
                            Базовый тариф
                          </span>
                        )}
                      </div>

                      {/* Что входит в тариф */}
                      {t.included_benefits && (
                        <div className="mt-2.5 rounded-[4px] border border-[#262D35]/70 bg-[#161B21] p-2 text-xs text-[#8E95A0] leading-relaxed">
                          <div className="flex items-center gap-1 font-semibold text-[#D1D5DB] text-[11px] mb-0.5">
                            <Check className="h-3 w-3 text-[#34D399]" strokeWidth={2} />
                            <span>Включено в пакет:</span>
                          </div>
                          <p>{t.included_benefits}</p>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* 3. Подвал шторки: лаконичное целевое действие */}
            <div className="border-t border-[#21262F] bg-[#12161A] p-4 flex items-center justify-center">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleCopySummary}
                className="w-full h-9 border-[#7C5A20]/60 bg-[#1E190E] text-xs font-serif italic text-[#E5C378] hover:border-[#E5C378] hover:bg-[#261E0F] hover:text-white hover:shadow-[0_0_10px_rgba(229,195,120,0.2)] transition-all"
              >
                {copied ? (
                  <>
                    <Check className="h-3.5 w-3.5 text-[#34D399]" />
                    <span>Описание скопировано в буфер</span>
                  </>
                ) : (
                  <>
                    <Copy className="h-3.5 w-3.5 text-[#E5C378]" />
                    <span>Скопировать описание площадки и тарифов</span>
                  </>
                )}
              </Button>
            </div>
          </motion.aside>
        </div>
      )}
    </AnimatePresence>,
    document.body
  );
}
