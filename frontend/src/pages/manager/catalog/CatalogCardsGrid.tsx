import type * as React from "react";
import { motion } from "framer-motion";
import {
  MapPin,
  Globe,
  Building,
  ChevronRight,
  Copy,
  Check,
} from "lucide-react";
import type { CatalogEventItemOut } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import {
  FORMAT_LABELS,
  formatCalendarBadge,
  formatRub,
} from "@/lib/formatters";
import { cn } from "@/lib/utils";
import {
  CATALOG_ROLE_LABELS,
  CATALOG_ROLE_PILL_CLASSES,
  getEventPriceSummary,
  getEventMaxSavings,
  getEventRoles,
  isPastEvent,
} from "./catalogUtils";
import { CatalogWarningsBadge } from "./CatalogWarningsBadge";

interface CatalogCardsGridProps {
  events: CatalogEventItemOut[];
  todayIso: string;
  selectedEventId: number | null;
  copiedEventId: number | null;
  onSelectEvent: (eventId: number) => void;
  onCopyLocation: (e: React.MouseEvent, ev: CatalogEventItemOut) => void;
}

export function CatalogCardsGrid({
  events,
  todayIso,
  selectedEventId,
  copiedEventId,
  onSelectEvent,
  onCopyLocation,
}: CatalogCardsGridProps) {
  return (
    <motion.div
      key="catalog-cards"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.15, ease: "easeOut" }}
      className="grid grid-cols-1 gap-3.5 lg:grid-cols-2"
    >
      {events.map((ev) => {
        const cal = formatCalendarBadge(ev.start_date, ev.end_date);
        const formatLabel = FORMAT_LABELS[ev.event_format] || ev.event_format;
        const locationLabel = ev.is_online ? "Онлайн" : ev.city || "Россия";
        const priceSummary = getEventPriceSummary(ev);
        const { savings } = getEventMaxSavings(ev);
        const roles = getEventRoles(ev);
        const isPast = isPastEvent(ev, todayIso);
        const isSelected = selectedEventId === ev.event_id;

        return (
          <div
            key={ev.event_id}
            onClick={() => onSelectEvent(ev.event_id)}
            className={cn(
              "group flex flex-col justify-between rounded-[10px] border p-4 shadow-sm transition-all duration-150 active:scale-[0.995] cursor-pointer",
              isSelected
                ? "border-[#E5C378] bg-[#1E190E] shadow-[0_0_12px_rgba(229,195,120,0.18)]"
                : isPast
                  ? "border-[#21262F] bg-[#12161A]/80 opacity-75 hover:opacity-100 hover:border-[#7C5A20] hover:bg-[#181D24]"
                  : "border-[#262D35] bg-[#161B22] hover:border-[#7C5A20] hover:bg-[#181D24]"
            )}
          >
            <div>
              <div className="flex items-start gap-3">
                {/* Календарный листок даты */}
                <div className="flex min-h-[58px] min-w-[56px] shrink-0 flex-col items-center justify-center rounded-[6px] border border-[#7C5A20]/50 bg-[#12161A] px-2 py-1.5 tabular-nums shadow-inner transition-colors group-hover:border-[#E5C378]">
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

                {/* Информация о мероприятии */}
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-[#8E95A0]">
                    <span className="font-semibold text-[#D1D5DB]">
                      {formatLabel}
                    </span>
                    <span>·</span>
                    <button
                      type="button"
                      onClick={(e) => onCopyLocation(e, ev)}
                      title={`Клик — скопировать адрес: ${ev.is_online ? "Онлайн" : `${ev.city || ""}${ev.venue ? `, ${ev.venue}` : ""}`}`}
                      className="group/loc inline-flex items-center gap-1 rounded-[4px] border border-transparent px-1 py-0.5 font-medium text-[#D1D5DB] hover:border-[#7C5A20]/60 hover:bg-[#1E2530] hover:text-[#E5C378] transition-all cursor-pointer"
                    >
                      {ev.is_online ? (
                        <Globe className="h-3 w-3 text-[#529E85]" strokeWidth={1.5} />
                      ) : (
                        <MapPin className="h-3 w-3 text-[#8E95A0] group-hover/loc:text-[#E5C378]" strokeWidth={1.5} />
                      )}
                      <span>{locationLabel}</span>
                      {copiedEventId === ev.event_id ? (
                        <Check className="h-3 w-3 text-[#34D399] shrink-0" />
                      ) : (
                        <Copy className="h-2.5 w-2.5 opacity-0 group-hover/loc:opacity-100 text-[#E5C378] shrink-0 transition-opacity" />
                      )}
                    </button>
                    {ev.venue && (
                      <>
                        <span>·</span>
                        <button
                          type="button"
                          onClick={(e) => onCopyLocation(e, ev)}
                          title={`Клик — скопировать адрес площадки: ${ev.city || ""}, ${ev.venue}`}
                          className="inline-flex items-center gap-1 rounded-[4px] border border-transparent px-1 py-0.5 hover:border-[#7C5A20]/60 hover:bg-[#1E2530] hover:text-[#E5C378] transition-all cursor-pointer text-[#D1D5DB] leading-tight truncate max-w-[220px]"
                        >
                          <Building className="h-3 w-3 shrink-0 opacity-70" strokeWidth={1.5} />
                          <span className="truncate">{ev.venue}</span>
                        </button>
                      </>
                    )}
                    <div className="ml-auto flex items-center gap-1.5 shrink-0">
                      {isPast && (
                        <span className="inline-flex items-center rounded-[4px] border border-[#2A313C] bg-[#12161A] px-1.5 py-0.5 text-[11px] font-medium text-[#8E95A0]">
                          Прошло
                        </span>
                      )}
                      {ev.data_status === "ready" ? (
                        <Badge variant="ebEmerald" asSlanted={false} className="text-[11px]">
                          Готово к КП
                        </Badge>
                      ) : ev.data_status === "needs_enrichment" ? (
                        <Badge variant="ebAmber" asSlanted={false} className="text-[11px]">
                          Требует обогащения
                        </Badge>
                      ) : null}
                    </div>
                  </div>

                  <h3
                    title={ev.canonical_title}
                    className="mt-1 font-serif text-sm sm:text-[15px] font-semibold leading-snug text-white group-hover:text-[#E5C378] transition-colors line-clamp-1"
                  >
                    {ev.canonical_title}
                  </h3>

                  <p
                    title={ev.summary}
                    className="mt-1 text-xs text-[#8E95A0] line-clamp-1 leading-relaxed"
                  >
                    {ev.summary}
                  </p>

                  {ev.missing_data_warnings.length > 0 && (
                    <div className="mt-1.5">
                      <CatalogWarningsBadge warnings={ev.missing_data_warnings} />
                    </div>
                  )}
                </div>
              </div>

              {/* Роли участия и тематические теги */}
              {(roles.length > 0 || ev.themes.length > 0) && (
                <div className="mt-2.5 flex flex-wrap gap-1">
                  {roles.map((role) => (
                    <span
                      key={role}
                      className={cn(
                        "inline-flex items-center rounded-[4px] border px-1.5 py-0.5 text-[11px] font-medium leading-tight",
                        CATALOG_ROLE_PILL_CLASSES[role]
                      )}
                    >
                      {CATALOG_ROLE_LABELS[role]}
                    </span>
                  ))}
                  {ev.themes.slice(0, 4).map((t) => (
                    <span
                      key={t}
                      title={t}
                      className="rounded-[3px] border border-[#262D35] bg-[#12161A] px-1.5 py-0.5 text-[11px] font-serif italic text-[#8E95A0] hover:text-[#E5C378] transition-colors"
                    >
                      {t}
                    </span>
                  ))}
                  {ev.themes.length > 4 && (
                    <span
                      title={ev.themes.slice(4).join(", ")}
                      className="rounded-[3px] border border-[#262D35] bg-[#12161A] px-1.5 py-0.5 text-[11px] font-serif italic text-[#E5C378]/90 cursor-help"
                    >
                      +{ev.themes.length - 4}
                    </span>
                  )}
                </div>
              )}
            </div>

            {/* Нижняя лаконичная сводка: стоимость + Early Bird + кнопка Подробнее */}
            <div className="mt-3 flex items-center justify-between gap-2 border-t border-[#21262F] pt-2.5 text-xs">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-sans font-bold text-white tabular-nums">
                  {priceSummary.label}
                </span>
                {priceSummary.subLabel && (
                  <span className="text-[11px] text-[#E5C378]/85">
                    · {priceSummary.subLabel}
                  </span>
                )}
                {savings > 0 && (
                  <Badge variant="ebEmerald" asSlanted={false} className="text-[11px]">
                    Выгода {formatRub(savings)}
                  </Badge>
                )}
              </div>

              <span className="inline-flex items-center gap-1 text-[11px] font-serif italic text-[#8E95A0] group-hover:text-[#E5C378] group-hover:translate-x-0.5 transition-all">
                <span>Тарифы ({ev.tariffs.length})</span>
                <ChevronRight className="h-3 w-3 text-inherit shrink-0" strokeWidth={2} />
              </span>
            </div>
          </div>
        );
      })}
    </motion.div>
  );
}
