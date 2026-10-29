import * as React from "react";
import {
  Search,
  MapPin,
  Globe,
  Building,
  Calendar,
  Compass,
  Sparkles,
  X,
  RotateCcw,
} from "lucide-react";
import { useManagerEventsCatalog } from "@/api/queries";
import { Badge } from "@/components/ui/badge";
import { CustomSelect } from "@/components/ui/custom-select";
import {
  FORMAT_LABELS,
  ROLE_BADGE_LABELS,
  formatCalendarBadge,
  formatDateShort,
  formatRub,
} from "@/lib/formatters";
import { cn } from "@/lib/utils";

const FORMAT_OPTIONS = [
  { id: "all", label: "Все форматы" },
  { id: "forum", label: "Форумы" },
  { id: "conference", label: "Конференции" },
  { id: "roundtable", label: "Круглые столы" },
  { id: "business_breakfast", label: "Деловые завтраки" },
  { id: "session", label: "Сессии" },
];

/**
 * Вкладка «База площадок» в кабинете менеджера (GET /api/manager/events).
 * Реестр отраслевых мероприятий в едином тёмно-золотом литературном стиле.
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

  const metrics = React.useMemo(() => {
    const total = events.length;
    const online = events.filter((e) => e.is_online).length;
    const offline = events.filter((e) => !e.is_online).length;
    const earlyBird = events.filter((e) =>
      e.tariffs.some((t) => t.savings > 0)
    ).length;
    return { total, online, offline, earlyBird };
  }, [events]);

  const filteredEvents = React.useMemo(() => {
    return events.filter((ev) => {
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
  }, [events, selectedFormat, selectedCity, searchQuery]);

  const handleResetFilters = () => {
    setSearchQuery("");
    setSelectedFormat("all");
    setSelectedCity("all");
  };

  return (
    <div className="mx-auto max-w-[1440px] p-4 lg:p-5 space-y-4">
      {/* Главная панель фильтрации и поиска каталога */}
      <div className="rounded-[12px] border border-[#262D35] bg-[#161B22] p-4 sm:p-5 shadow-sm">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="rounded-[4px] bg-[#94A3B8] text-[#0F172A] px-1.5 py-0.5 text-[9px] font-bold font-serif italic">
                Каталог
              </span>
              <h1 className="font-serif italic text-base sm:text-lg font-semibold tracking-tight text-[#E5C378]">
                Отслеживаемый реестр отраслевых площадок
              </h1>
            </div>
            <p className="mt-1 font-serif italic text-xs leading-relaxed text-[#8E95A0]">
              Архитектурные и строительные форумы, круглые столы девелоперов и конференции с актуальной сеткой тарифов организаторов и скидок Early Bird
            </p>
          </div>

          {/* Строка поиска без белых вспышек при клике */}
          <div className="relative w-full lg:w-80">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[#8E95A0]"
              strokeWidth={1.75}
            />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Поиск по названию, КРТ, ИЖС, BIM..."
              className="h-9 w-full rounded-[8px] border border-[#262D35] bg-[#12161A] pl-9 pr-8 text-xs text-white placeholder:text-[#6B7280] [color-scheme:dark] outline-none focus:outline-none focus-visible:outline-none active:outline-none focus:border-[#E5C378] focus:shadow-[0_0_0_1px_rgba(229,195,120,0.25)] transition-colors duration-150"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery("")}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[#8E95A0] hover:text-[#E5C378] transition-colors"
                title="Очистить поиск"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        </div>

        {/* Информационные метрики реестра */}
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
          <div className="inline-flex items-center gap-1.5 rounded-[6px] border border-[#262D35] bg-[#12161A] px-2.5 py-1 text-[11px] text-[#8E95A0]">
            <span className="font-serif italic">Всего площадок:</span>
            <strong className="text-white font-semibold tabular-nums">{metrics.total}</strong>
          </div>
          <div className="inline-flex items-center gap-1.5 rounded-[6px] border border-[#262D35] bg-[#12161A] px-2.5 py-1 text-[11px] text-[#8E95A0]">
            <span className="font-serif italic">Очные события:</span>
            <strong className="text-white font-semibold tabular-nums">{metrics.offline}</strong>
          </div>
          <div className="inline-flex items-center gap-1.5 rounded-[6px] border border-[#262D35] bg-[#12161A] px-2.5 py-1 text-[11px] text-[#8E95A0]">
            <span className="font-serif italic">Онлайн площадки:</span>
            <strong className="text-white font-semibold tabular-nums">{metrics.online}</strong>
          </div>
          <div className="inline-flex items-center gap-1.5 rounded-[6px] border border-[#1E5241] bg-[#0E241E]/80 px-2.5 py-1 text-[11px] text-[#34D399]">
            <Sparkles className="h-3 w-3" strokeWidth={1.5} />
            <span className="font-serif italic">Спецтарифы Early Bird:</span>
            <strong className="font-bold tabular-nums">{metrics.earlyBird}</strong>
          </div>
        </div>

        {/* Нижняя строка: Фильтры форматов и Локация */}
        <div className="mt-3.5 flex flex-wrap items-center justify-between gap-3 border-t border-[#21262F] pt-3">
          {/* Фильтр по формату участия */}
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="mr-1 font-serif italic text-[11px] text-[#8E95A0]">
              Формат:
            </span>
            {FORMAT_OPTIONS.map((fmt) => {
              const isActive = selectedFormat === fmt.id;
              return (
                <button
                  key={fmt.id}
                  type="button"
                  onClick={() => setSelectedFormat(fmt.id)}
                  className={cn(
                    "px-2.5 py-1 text-xs font-serif italic transition-colors duration-150 select-none cursor-pointer outline-none focus-visible:outline-none active:scale-[0.98]",
                    isActive
                      ? "-skew-x-[9deg] rounded-[2px] border border-[#E5C378] bg-[#261E0F] text-[#E5C378] font-bold shadow-[0_0_8px_rgba(229,195,120,0.2)]"
                      : "rounded-[3px] border border-[#262D35] bg-[#12161A] font-medium text-[#8E95A0] hover:border-[#38414F] hover:bg-[#1A2128] hover:text-white"
                  )}
                >
                  <span className={isActive ? "inline-block skew-x-[9deg]" : ""}>
                    {fmt.label}
                  </span>
                </button>
              );
            })}
          </div>

          {/* Фильтр по локации через CustomSelect */}
          <div className="flex items-center gap-2">
            <span className="font-serif italic text-[11px] text-[#8E95A0]">
              Локация:
            </span>
            <CustomSelect
              value={selectedCity}
              onChange={(val) => setSelectedCity(String(val))}
              options={[
                { value: "all", label: `Все города (${events.length})` },
                ...uniqueCities.map((city) => ({ value: city, label: city })),
                { value: "online", label: "Только Онлайн" },
              ]}
              buttonClassName="h-7 min-w-[145px]"
            />
          </div>
        </div>
      </div>

      {/* Сетка отраслевых площадок */}
      {isLoading ? (
        <div className="rounded-[12px] border border-[#262D35] bg-[#161B22] p-12 text-center shadow-sm">
          <div className="mx-auto h-7 w-7 rounded-full border-2 border-[#262D35] border-t-[#E5C378] animate-spin" />
          <p className="mt-3 font-serif italic text-xs font-semibold text-[#E5C378]">
            Загрузка реестра отраслевых площадок и актуальных тарифов...
          </p>
        </div>
      ) : filteredEvents.length === 0 ? (
        <div className="rounded-[12px] border border-[#21262F] bg-[#0E1116] p-10 text-center shadow-sm">
          <Compass className="mx-auto h-9 w-9 text-[#E5C378]" strokeWidth={1.5} />
          <h3 className="mt-3 font-serif italic text-sm font-semibold text-[#E5C378]">
            Мероприятия по заданным фильтрам не найдены
          </h3>
          <p className="mx-auto mt-1.5 max-w-md font-serif italic text-xs leading-relaxed text-[#D4AF37]/90">
            Попробуйте смягчить критерии поиска (сбросить формат или выбрать другой город)
          </p>
          <button
            type="button"
            onClick={handleResetFilters}
            className="mt-4 inline-flex items-center gap-1.5 rounded-[6px] bg-gradient-to-r from-[#D4AF37] via-[#E5C378] to-[#D4AF37] px-3.5 py-1.5 text-xs font-semibold text-[#0E1215] shadow-sm hover:shadow-[0_0_12px_rgba(229,195,120,0.35)] active:scale-[0.98] transition-all"
          >
            <RotateCcw className="h-3 w-3 text-[#0E1215]" strokeWidth={2} />
            <span>Сбросить фильтры поиска</span>
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3.5 lg:grid-cols-2">
          {filteredEvents.map((ev) => {
            const cal = formatCalendarBadge(ev.start_date, ev.end_date);
            const formatLabel = FORMAT_LABELS[ev.event_format] || ev.event_format;
            const locationLabel = ev.is_online ? "Онлайн" : ev.city || "Россия";

            return (
              <div
                key={ev.event_id}
                className="group flex flex-col justify-between rounded-[12px] border border-[#262D35] bg-[#161B22] p-4 shadow-sm transition-all duration-200 hover:border-[#3A4553]"
              >
                <div>
                  <div className="flex items-start gap-3">
                    {/* Календарный листок даты в литературном стиле с золотистой рамкой */}
                    <div className="flex min-h-[64px] min-w-[62px] shrink-0 self-start flex-col items-center justify-center rounded-[6px] border border-[#7C5A20]/50 bg-[#161B21] px-2 py-2 tabular-nums shadow-inner transition-colors group-hover:border-[#E5C378]/60">
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

                    {/* Информация о мероприятии */}
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-[#8E95A0]">
                        <span className="font-semibold text-[#D1D5DB]">
                          {formatLabel}
                        </span>
                        <span>·</span>
                        <span className="inline-flex items-center gap-1 font-medium text-[#D1D5DB]">
                          {ev.is_online ? (
                            <Globe className="h-3 w-3 text-[#38BDF8]" strokeWidth={1.5} />
                          ) : (
                            <MapPin className="h-3 w-3 text-[#8E95A0]" strokeWidth={1.5} />
                          )}
                          {locationLabel}
                        </span>
                        {ev.venue && (
                          <>
                            <span>·</span>
                            <span className="inline-flex items-center gap-1 truncate max-w-[220px]">
                              <Building className="h-3 w-3 shrink-0 opacity-70" strokeWidth={1.5} />
                              {ev.venue}
                            </span>
                          </>
                        )}
                      </div>

                      <h3 className="mt-1 font-serif text-[15px] font-semibold leading-snug text-white group-hover:text-[#E5C378] transition-colors">
                        {ev.canonical_title}
                      </h3>
                    </div>
                  </div>

                  <p className="mt-2.5 text-xs leading-relaxed text-[#D1D5DB] line-clamp-2">
                    {ev.summary}
                  </p>

                  {/* Тематические теги */}
                  {ev.themes.length > 0 && (
                    <div className="mt-2.5 flex flex-wrap gap-1">
                      {ev.themes.map((t) => (
                        <span
                          key={t}
                          className="rounded-[4px] border border-[#262D35] bg-[#12161A] px-2 py-0.5 text-[11px] font-medium text-[#8E95A0] transition-colors hover:border-[#38414F] hover:text-[#D1D5DB]"
                        >
                          {t}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                {/* Тарифная сетка события */}
                <div className="mt-3.5 border-t border-[#21262F] pt-3">
                  <div className="mb-2 flex items-center justify-between text-[11px]">
                    <span className="font-serif italic text-[#8E95A0]">
                      Доступные тарифы организатора:
                    </span>
                    <span className="inline-flex items-center gap-1 font-serif italic text-[#8E95A0]">
                      <Calendar className="h-3 w-3 text-[#E5C378]" strokeWidth={1.5} />
                      {formatDateShort(ev.start_date)}
                    </span>
                  </div>

                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                    {ev.tariffs.map((t) => (
                      <div
                        key={t.tariff_id}
                        className="flex flex-col justify-between rounded-[6px] border border-[#262D35] bg-[#12161A] p-2.5 transition-all duration-150 hover:border-[#3A4553]"
                      >
                        <div className="flex items-center justify-between gap-1.5">
                          <span
                            className="truncate text-xs font-semibold text-white"
                            title={t.tariff_name}
                          >
                            {t.tariff_name}
                          </span>
                          <Badge
                            variant={
                              t.participation_role === "speaker"
                                ? "ebGold"
                                : t.participation_role === "sponsor"
                                  ? "ebRose"
                                  : "ebBlue"
                            }
                            className="text-[9px]"
                          >
                            {ROLE_BADGE_LABELS[t.participation_role]}
                          </Badge>
                        </div>

                        <div className="mt-1.5 flex flex-col gap-0.5 tabular-nums">
                          <div className="flex items-baseline gap-1.5">
                            <span className="text-sm font-bold text-white">
                              {formatRub(t.actual_price)}
                            </span>
                            {t.savings > 0 && t.base_price && (
                              <span className="text-xs text-[#727985] line-through">
                                {formatRub(t.base_price)}
                              </span>
                            )}
                          </div>

                          {t.savings > 0 ? (
                            <div className="flex items-center">
                              <Badge variant="ebEmerald" className="text-[10px]">
                                Выгода {formatRub(t.savings)}
                                {t.early_bird_deadline
                                  ? ` до ${formatDateShort(t.early_bird_deadline).slice(0, 5)}`
                                  : ""}
                              </Badge>
                            </div>
                          ) : (
                            <span className="text-[10px] text-[#727985]">Базовый тариф</span>
                          )}
                        </div>

                        {t.included_benefits && (
                          <p
                            className="mt-1 truncate text-[10px] text-[#8E95A0]"
                            title={t.included_benefits}
                          >
                            {t.included_benefits}
                          </p>
                        )}
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
