import { CheckCircle2, AlertTriangle, Calendar, MapPin, Globe } from "lucide-react";
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
        "rounded-card border bg-surface px-4 py-3 transition-colors",
        hasConflict
          ? "border-terracotta-border bg-terracotta-tint/50"
          : "border-border",
        className
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2 pb-2.5 border-b border-border/70">
        <div className="flex items-center gap-2">
          <Calendar className="h-4 w-4 text-ink-muted" strokeWidth={1.5} />
          <span className="text-xs font-semibold uppercase tracking-wider text-ink-secondary">
            График участия по датам
          </span>
        </div>

        {hasConflict ? (
          <div className="inline-flex items-center gap-1.5 rounded-badge bg-terracotta-tint px-2.5 py-0.5 text-xs font-medium text-terracotta border border-terracotta-border">
            <AlertTriangle className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} />
            <span>{conflictDescription || "Обнаружено наложение дат"}</span>
          </div>
        ) : (
          <div className="inline-flex items-center gap-1.5 rounded-badge bg-sage-tint px-2.5 py-0.5 text-xs font-medium text-sage border border-sage-border">
            <CheckCircle2 className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} />
            <span>Календарь сверен: пересечений по срокам нет</span>
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
              className="flex items-center gap-2.5 rounded-control border border-border/80 bg-canvas/60 px-2.5 py-1.5"
            >
              <div className="flex h-9 w-11 shrink-0 flex-col items-center justify-center rounded-badge bg-pine text-white tabular-nums">
                <span className="text-[11px] font-bold leading-none">
                  {cal.dayText}
                </span>
                <span className="mt-0.5 text-[9px] font-medium uppercase tracking-wider text-white/80 leading-none">
                  {cal.monthText}
                </span>
              </div>

              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1 text-[11px] text-ink-muted">
                  <span className="font-medium text-ink-secondary">
                    Этап {index + 1}
                  </span>
                  <span>·</span>
                  {ev.is_online ? (
                    <Globe className="h-3 w-3 shrink-0" strokeWidth={1.5} />
                  ) : (
                    <MapPin className="h-3 w-3 shrink-0" strokeWidth={1.5} />
                  )}
                  <span className="truncate">{loc}</span>
                </div>
                <p className="truncate text-xs font-medium text-ink" title={ev.canonical_title}>
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

