import { Calendar, MapPin, Globe } from "lucide-react";
import {
  checkDateConflicts,
  formatCalendarBadge,
  type DateSpanItem,
} from "@/lib/formatters";
import { cn } from "@/lib/utils";

interface CalendarTimelineProps {
  items: (DateSpanItem & { city?: string | null; roleLabel?: string })[];
  className?: string;
  compact?: boolean;
}

/**
 * Наглядный индикатор и хронологическая шкала «Календарь без пересечений по срокам»
 * (Слайды 02, 03, 04 и Шаг 06 схемы заказчика).
 */
export function CalendarTimeline({
  items,
  className,
  compact = false,
}: CalendarTimelineProps) {
  if (items.length === 0) return null;

  const sorted = [...items].sort((a, b) =>
    a.start_date.localeCompare(b.start_date)
  );
  const { hasConflict, conflictDescription } = checkDateConflicts(sorted);

  return (
    <div
      className={cn(
        "rounded-[12px] border px-4 py-3 transition-colors shadow-sm",
        hasConflict
          ? "border-[#7C4A19] bg-[#22160C]"
          : "border-[#262D35] bg-[#161B22]",
        className
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2 pb-2.5 border-b border-[#21262F]">
        <div className="flex items-center gap-2">
          <Calendar className="h-4 w-4 text-[#E5C378]" strokeWidth={1.5} />
          <span className="font-serif italic text-xs font-semibold tracking-wide text-[#E5C378]">
            График участия по датам
          </span>
        </div>

        {hasConflict ? (
          <div className="inline-flex items-center gap-2 rounded-full border border-[#6E2A34] bg-[#2A151C]/80 px-2.5 py-0.5 text-xs select-none">
            <span className="relative flex h-2 w-2 shrink-0 items-center justify-center">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#FB7185] opacity-75" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-[#FB7185]" />
            </span>
            <span className="font-serif italic text-[11px] font-medium text-[#FDA4AF]">
              {conflictDescription || "Обнаружено наложение дат"}
            </span>
          </div>
        ) : (
          <div className="inline-flex items-center gap-2 rounded-full border border-[#1E5241]/80 bg-[#0E241E]/80 px-2.5 py-0.5 text-xs select-none shadow-[0_0_10px_rgba(52,211,153,0.12)]">
            <span className="relative flex h-2 w-2 shrink-0 items-center justify-center">
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-[#34D399] shadow-[0_0_8px_rgba(52,211,153,0.9)]" />
            </span>
            <span className="font-serif italic text-[11px] font-medium text-[#6EE7B7]">
              Календарь сверен · без накладок
            </span>
          </div>
        )}
      </div>

      <div
        className={cn(
          "mt-2.5 grid gap-2",
          compact
            ? "grid-cols-1 sm:grid-cols-3"
            : "grid-cols-1 md:grid-cols-3 lg:grid-cols-4"
        )}
      >
        {sorted.map((ev, index) => {
          const cal = formatCalendarBadge(ev.start_date, ev.end_date);
          const loc = ev.is_online ? "Онлайн" : ev.city || "Россия";

          return (
            <div
              key={ev.event_id}
              className="flex items-center gap-2.5 rounded-[6px] border border-[#262C35] bg-[#1A1E24] px-2.5 py-1.5 transition-colors duration-150 hover:border-[#38414F]"
            >
              <div className="flex h-9 w-11 shrink-0 flex-col items-center justify-center rounded-[4px] border border-[#7C5A20]/50 bg-[#161B21] text-white tabular-nums">
                <span className="text-[11px] font-bold leading-none">
                  {cal.dayText}
                </span>
                <span className="mt-0.5 text-[9px] font-medium uppercase tracking-wider text-white/80 leading-none">
                  {cal.monthText}
                </span>
              </div>

              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1 text-[11px] text-[#8E95A0]">
                  <span className="font-medium text-[#D1D5DB]">
                    Этап {index + 1}
                  </span>
                  <span>·</span>
                  {ev.is_online ? (
                    <Globe className="h-3 w-3 shrink-0 text-[#38BDF8]" strokeWidth={1.5} />
                  ) : (
                    <MapPin className="h-3 w-3 shrink-0 text-[#8E95A0]" strokeWidth={1.5} />
                  )}
                  <span className="truncate">{loc}</span>
                </div>
                <p className="truncate text-xs font-medium text-white" title={ev.canonical_title}>
                  {ev.canonical_title}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

