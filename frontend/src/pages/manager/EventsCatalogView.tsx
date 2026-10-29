import * as React from "react";
import {
  Search,
  MapPin,
  Globe,
  Building,
  Calendar,
} from "lucide-react";
import { useManagerEventsCatalog } from "@/api/queries";
import { Badge } from "@/components/ui/badge";
import {
  FORMAT_LABELS,
  ROLE_BADGE_LABELS,
  formatCalendarBadge,
  formatDateShort,
  formatRub,
} from "@/lib/formatters";
import { cn } from "@/lib/utils";

/**
 * Вкладка «База площадок» в кабинете менеджера (GET /api/manager/events).
 * Позволяет просматривать весь отслеживаемый календарь отраслевых мероприятий и тарифов.
 */
export function EventsCatalogView() {
  const { data, isLoading } = useManagerEventsCatalog(true);
  const [searchQuery, setSearchQuery] = React.useState("");
  const [selectedFormat, setSelectedFormat] = React.useState<string>("all");
  const [selectedCity, setSelectedCity] = React.useState<string>("all");

  const events = data?.events || [];

  const uniqueCities = React.useMemo(() => {
    const set = new Set<string>();
    for (const ev of events) {
      if (ev.city) set.add(ev.city);
    }
    return Array.from(set);
  }, [events]);

  const filteredEvents = events.filter((ev) => {
    if (selectedFormat !== "all" && ev.event_format !== selectedFormat) {
      return false;
    }
    if (selectedCity === "online" && !ev.is_online) {
      return false;
    }
    if (
      selectedCity !== "all" &&
      selectedCity !== "online" &&
      ev.city !== selectedCity
    ) {
      return false;
    }
    const q = searchQuery.trim().toLowerCase();
    if (!q) return true;
    return (
      ev.canonical_title.toLowerCase().includes(q) ||
      ev.summary.toLowerCase().includes(q) ||
      ev.themes.some((t) => t.toLowerCase().includes(q))
    );
  });

  return (
    <div className="mx-auto max-w-[1440px] p-5 space-y-4">
      {/* Панель фильтрации каталога */}
      <div className="rounded-card border border-border bg-surface p-4 shadow-card">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="font-serif text-base font-semibold text-ink sm:text-lg">
              Отслеживаемый календарь отраслевых площадок
            </h1>
            <p className="text-xs text-ink-muted">
              Форумы, закрытые деловые завтраки, круглые столы и конференции с актуальными тарифами организаторов
            </p>
          </div>

          <div className="relative w-full md:w-80">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-faint"
              strokeWidth={1.5}
            />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Поиск по названию, КРТ, ИЖС, BIM..."
              className="h-9 w-full rounded-control border border-border bg-canvas pl-9 pr-3 text-xs text-ink placeholder:text-ink-faint focus:border-pine focus:bg-surface focus:outline-none"
            />
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-border/70 pt-3">
          {/* Фильтр по формату */}
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="mr-1 text-[11px] font-medium text-ink-muted">
              Формат:
            </span>
            {[
              { id: "all", label: "Все форматы" },
              { id: "forum", label: "Форумы" },
              { id: "conference", label: "Конференции" },
              { id: "roundtable", label: "Круглые столы" },
              { id: "business_breakfast", label: "Деловые завтраки" },
              { id: "session", label: "Сессии" },
            ].map((fmt) => (
              <button
                key={fmt.id}
                type="button"
                onClick={() => setSelectedFormat(fmt.id)}
                className={cn(
                  "rounded-badge border px-2.5 py-1 text-xs font-medium transition-colors",
                  selectedFormat === fmt.id
                    ? "border-pine bg-pine text-white"
                    : "border-border bg-canvas text-ink-secondary hover:bg-surface-muted"
                )}
              >
                {fmt.label}
              </button>
            ))}
          </div>

          {/* Фильтр по локации */}
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-medium text-ink-muted">
              Локация:
            </span>
            <select
              value={selectedCity}
              onChange={(e) => setSelectedCity(e.target.value)}
              className="h-7 rounded-badge border border-border bg-canvas px-2 text-xs text-ink focus:border-pine focus:outline-none"
            >
              <option value="all">Все города ({events.length})</option>
              {uniqueCities.map((city) => (
                <option key={city} value={city}>
                  {city}
                </option>
              ))}
              <option value="online">Только Онлайн</option>
            </select>
          </div>
        </div>
      </div>

      {/* Сетка площадок */}
      {isLoading ? (
        <div className="rounded-card border border-border bg-surface p-12 text-center text-sm text-ink-muted">
          Загрузка базы отраслевых мероприятий...
        </div>
      ) : filteredEvents.length === 0 ? (
        <div className="rounded-card border border-border bg-surface p-12 text-center text-sm text-ink-muted">
          По выбранным фильтрам мероприятия не найдены
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {filteredEvents.map((ev) => {
            const cal = formatCalendarBadge(ev.start_date, ev.end_date);
            return (
              <div
                key={ev.event_id}
                className="flex flex-col justify-between rounded-card border border-border bg-surface p-4 shadow-card transition-colors hover:border-border-strong"
              >
                <div>
                  <div className="flex items-start gap-3">
                    <div className="flex h-12 w-14 shrink-0 flex-col items-center justify-center rounded-control bg-pine text-white tabular-nums">
                      <span className="text-xs font-bold leading-none">
                        {cal.dayText}
                      </span>
                      <span className="mt-0.5 text-[10px] font-semibold uppercase">
                        {cal.monthText}
                      </span>
                      <span className="mt-0.5 text-[9px] opacity-75">
                        {cal.durationText}
                      </span>
                    </div>

                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-ink-muted">
                        <span className="font-semibold text-ink-secondary">
                          {FORMAT_LABELS[ev.event_format] || ev.event_format}
                        </span>
                        <span>·</span>
                        <span className="inline-flex items-center gap-1 font-medium text-ink-secondary">
                          {ev.is_online ? (
                            <Globe className="h-3 w-3 text-sage" strokeWidth={1.5} />
                          ) : (
                            <MapPin className="h-3 w-3" strokeWidth={1.5} />
                          )}
                          {ev.is_online ? "Онлайн" : ev.city}
                        </span>
                        {ev.venue && (
                          <>
                            <span>·</span>
                            <span className="inline-flex items-center gap-1 truncate">
                              <Building className="h-3 w-3 shrink-0" strokeWidth={1.5} />
                              {ev.venue}
                            </span>
                          </>
                        )}
                      </div>

                      <h3 className="mt-1 font-serif text-[15px] font-semibold leading-snug text-ink">
                        {ev.canonical_title}
                      </h3>
                    </div>
                  </div>

                  <p className="mt-2.5 text-xs leading-relaxed text-ink-secondary">
                    {ev.summary}
                  </p>

                  {ev.themes.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {ev.themes.map((t) => (
                        <Badge key={t} variant="neutral">
                          {t}
                        </Badge>
                      ))}
                    </div>
                  )}
                </div>

                {/* Тарифная сетка события */}
                <div className="mt-3.5 border-t border-border/80 pt-3">
                  <div className="mb-1.5 flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
                    <span>Доступные тарифы организатора</span>
                    <span className="inline-flex items-center gap-1 font-normal normal-case">
                      <Calendar className="h-3 w-3" strokeWidth={1.5} />
                      {formatDateShort(ev.start_date)}
                    </span>
                  </div>

                  <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
                    {ev.tariffs.map((t) => (
                      <div
                        key={t.tariff_id}
                        className="flex items-center justify-between rounded-control border border-border/80 bg-canvas/60 px-2.5 py-1.5 text-xs tabular-nums"
                      >
                        <div className="min-w-0 pr-2">
                          <span className="block truncate font-medium text-ink">
                            {t.tariff_name}
                          </span>
                          <span className="text-[10px] text-ink-muted">
                            {ROLE_BADGE_LABELS[t.participation_role]}
                          </span>
                        </div>
                        <div className="text-right shrink-0">
                          <span className="block font-semibold text-ink">
                            {formatRub(t.actual_price)}
                          </span>
                          {t.savings > 0 && (
                            <span className="text-[10px] font-medium text-sage">
                              −{formatRub(t.savings)}
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

