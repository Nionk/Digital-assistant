import type * as React from "react";
import { motion } from "framer-motion";
import {
  MapPin,
  Globe,
  ChevronRight,
  Copy,
  Check,
  AlertTriangle,
} from "lucide-react";
import type { CatalogEventItemOut } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import {
  FORMAT_LABELS,
  formatCalendarBadge,
  formatDateShort,
  formatRub,
  formatMinPrice,
  pluralizeRu,
} from "@/lib/formatters";
import { cn } from "@/lib/utils";
import { getEventMinPrice, getEventMaxSavings } from "./catalogUtils";

interface CatalogTableProps {
  events: CatalogEventItemOut[];
  selectedEventId: number | null;
  copiedEventId: number | null;
  onSelectEvent: (eventId: number) => void;
  onCopyLocation: (e: React.MouseEvent, ev: CatalogEventItemOut) => void;
}

export function CatalogTable({
  events,
  selectedEventId,
  copiedEventId,
  onSelectEvent,
  onCopyLocation,
}: CatalogTableProps) {
  return (
    <motion.div
      key="catalog-table"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.15, ease: "easeOut" }}
      className="rounded-[12px] border border-[#262D35] bg-[#161B22] shadow-sm overflow-hidden"
    >
      <div className="overflow-x-auto scrollbar-thin">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-[#21262F] bg-[#12161A] text-[11px] font-serif italic text-[#8E95A0] select-none">
              <th className="py-2.5 pl-4 pr-3 font-semibold w-28">Сроки</th>
              <th className="py-2.5 px-3 font-semibold">Мероприятие и темы</th>
              <th className="py-2.5 px-3 font-semibold w-44">Формат и город</th>
              <th className="py-2.5 px-3 font-semibold w-36">Стоимость</th>
              <th className="py-2.5 px-3 font-semibold w-48">Спецтариф Early Bird</th>
              <th className="py-2.5 pr-4 pl-2 font-semibold text-right w-24">Действие</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#21262F] text-xs">
            {events.map((ev) => {
              const cal = formatCalendarBadge(ev.start_date, ev.end_date);
              const formatLabel = FORMAT_LABELS[ev.event_format] || ev.event_format;
              const locationLabel = ev.is_online ? "Онлайн" : ev.city || "Россия";
              const minPrice = getEventMinPrice(ev);
              const { savings, deadline } = getEventMaxSavings(ev);
              const isSelected = selectedEventId === ev.event_id;

              return (
                <tr
                  key={ev.event_id}
                  onClick={() => onSelectEvent(ev.event_id)}
                  className={cn(
                    "group cursor-pointer transition-colors duration-150 active:scale-[0.998]",
                    isSelected
                      ? "bg-[#221A0E] text-[#E5C378]"
                      : "hover:bg-[#1A2128]"
                  )}
                >
                  <td className="py-3 pl-4 pr-3 align-middle tabular-nums whitespace-nowrap">
                    <div className="flex items-baseline gap-1.5 font-serif text-xs">
                      <span
                        className={cn(
                          "font-semibold transition-colors",
                          isSelected ? "text-[#E5C378]" : "text-white group-hover:text-[#E5C378]"
                        )}
                      >
                        {cal.dayText}
                      </span>
                      <span
                        className={cn(
                          "font-normal transition-colors",
                          isSelected ? "text-[#E5C378]/90" : "text-[#8E95A0] group-hover:text-[#E5C378]/80"
                        )}
                      >
                        {cal.monthShortLabel}
                      </span>
                    </div>
                  </td>

                  <td className="py-3 px-3 align-middle">
                    <div className="min-w-0 max-w-lg">
                      <div className="flex items-center gap-2 min-w-0">
                        <span
                          title={ev.canonical_title}
                          className="font-serif text-[13px] font-semibold text-white group-hover:text-[#E5C378] transition-colors leading-snug line-clamp-1 cursor-pointer"
                        >
                          {ev.canonical_title}
                        </span>
                        {ev.data_status === "needs_enrichment" && (
                          <Badge variant="ebAmber" className="text-[9px] shrink-0">
                            Требует обогащения
                          </Badge>
                        )}
                      </div>
                      {ev.missing_data_warnings.length > 0 && (
                        <p
                          title={ev.missing_data_warnings.join(" · ")}
                          className="mt-0.5 flex items-center gap-1 text-[10px] text-[#E5C378]/90 truncate"
                        >
                          <AlertTriangle className="h-3 w-3 shrink-0" strokeWidth={1.75} />
                          <span className="truncate">
                            {ev.missing_data_warnings.join(" · ")}
                          </span>
                        </p>
                      )}
                      {ev.themes.length > 0 && (
                        <p
                          title={ev.themes.join(" · ")}
                          className="mt-0.5 text-[11px] text-[#727985] truncate font-serif italic"
                        >
                          {ev.themes.slice(0, 3).join(" · ")}
                          {ev.themes.length > 3 && (
                            <span
                              className="text-[#E5C378]/80 font-normal ml-1"
                              title={ev.themes.slice(3).join(" · ")}
                            >
                              +{ev.themes.length - 3}
                            </span>
                          )}
                        </p>
                      )}
                    </div>
                  </td>

                  <td className="py-3 px-3 align-middle whitespace-nowrap">
                    <div className="flex items-center gap-1.5 text-xs text-[#D1D5DB]">
                      <button
                        type="button"
                        onClick={(e) => onCopyLocation(e, ev)}
                        title={
                          ev.is_online
                            ? "Онлайн (клик — скопировать)"
                            : `Клик — скопировать полный адрес: ${ev.city || ""}${ev.venue ? `, ${ev.venue}` : ""}`
                        }
                        className="group/loc inline-flex items-center gap-1.5 rounded-[4px] border border-transparent px-1.5 py-0.5 text-xs text-[#D1D5DB] hover:border-[#7C5A20]/60 hover:bg-[#1E2530] hover:text-[#E5C378] transition-all cursor-pointer select-none text-left"
                      >
                        {ev.is_online ? (
                          <Globe className="h-3.5 w-3.5 text-[#529E85] shrink-0" strokeWidth={1.5} />
                        ) : (
                          <MapPin className="h-3.5 w-3.5 text-[#8E95A0] group-hover/loc:text-[#E5C378] shrink-0" strokeWidth={1.5} />
                        )}
                        <span className="truncate max-w-[140px] font-medium">
                          {locationLabel}
                          {ev.venue && ` (${ev.venue})`}
                        </span>
                        {copiedEventId === ev.event_id ? (
                          <Check className="h-3 w-3 text-[#34D399] shrink-0" />
                        ) : (
                          <Copy className="h-2.5 w-2.5 opacity-0 group-hover/loc:opacity-100 text-[#E5C378] shrink-0 transition-opacity" />
                        )}
                      </button>
                      <span className="text-[#3A4553]">·</span>
                      <span className="text-[11px] text-[#8E95A0] font-serif italic">
                        {formatLabel}
                      </span>
                    </div>
                  </td>

                  <td className="py-3 px-3 align-middle whitespace-nowrap tabular-nums">
                    {minPrice !== null ? (
                      <div>
                        <span className="font-sans font-bold text-white text-xs">
                          {formatMinPrice(minPrice)}
                        </span>
                        <span className="block text-[10px] text-[#727985] font-serif italic">
                          {ev.tariffs.length}{" "}
                          {pluralizeRu(ev.tariffs.length, ["тариф", "тарифа", "тарифов"])}
                        </span>
                      </div>
                    ) : (
                      <span className="text-xs text-[#8E95A0] font-serif italic">
                        По запросу
                      </span>
                    )}
                  </td>

                  <td className="py-3 px-3 align-middle whitespace-nowrap">
                    {savings > 0 ? (
                      <Badge variant="ebEmerald" className="text-[9px]">
                        Выгода {formatRub(savings)}
                        {deadline ? ` до ${formatDateShort(deadline).slice(0, 5)}` : ""}
                      </Badge>
                    ) : (
                      <span className="text-[11px] text-[#727985] font-serif italic">
                        Базовый тариф
                      </span>
                    )}
                  </td>

                  <td className="py-3 pr-4 pl-2 align-middle text-right whitespace-nowrap">
                    <span className="inline-flex items-center gap-1 text-[11px] font-serif italic text-[#8E95A0] group-hover:text-[#E5C378] group-hover:translate-x-0.5 transition-all">
                      <span>Детали</span>
                      <ChevronRight className="h-3 w-3 text-inherit shrink-0" strokeWidth={2} />
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </motion.div>
  );
}
