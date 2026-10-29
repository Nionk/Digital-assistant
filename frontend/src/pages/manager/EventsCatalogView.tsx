import * as React from "react";
import {
  Search,
  MapPin,
  Globe,
  Building,
  Compass,
  Sparkles,
  X,
  RotateCcw,
  LayoutList,
  LayoutGrid,
  ChevronRight,
} from "lucide-react";
import { useManagerEventsCatalog } from "@/api/queries";
import type { CatalogEventItemOut } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { CustomSelect } from "@/components/ui/custom-select";
import { EventDetailsDrawer } from "./EventDetailsDrawer";
import {
  FORMAT_LABELS,
  formatCalendarBadge,
  formatDateShort,
  formatRub,
} from "@/lib/formatters";
import { cn } from "@/lib/utils";

const FORMAT_OPTIONS = [
  { value: "all", label: "Все форматы" },
  { value: "forum", label: "Форумы" },
  { value: "conference", label: "Конференции" },
  { value: "roundtable", label: "Круглые столы" },
  { value: "business_breakfast", label: "Деловые завтраки" },
  { value: "session", label: "Сессии" },
];

/**
 * База площадок (реестр отраслевых мероприятий) в кабинете менеджера.
 * Организована по принципу Progressive Disclosure:
 * 1. Легковесный, неутомительный реестр (таблица / карточки) для быстрого сканирования.
 * 2. Детальная боковая шторка по клику на событие для углубленного изучения тарифов.
 */
export function EventsCatalogView() {
  const { data, isLoading } = useManagerEventsCatalog(true);
  const [searchQuery, setSearchQuery] = React.useState("");
  const [selectedFormat, setSelectedFormat] = React.useState<string>("all");
  const [selectedCity, setSelectedCity] = React.useState<string>("all");
  const [onlyEarlyBird, setOnlyEarlyBird] = React.useState<boolean>(false);
  const [viewMode, setViewMode] = React.useState<"table" | "cards">("table");
  const [selectedEventForDrawer, setSelectedEventForDrawer] =
    React.useState<CatalogEventItemOut | null>(null);

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
      if (onlyEarlyBird && !ev.tariffs.some((t) => t.savings > 0)) {
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
  }, [events, selectedFormat, selectedCity, onlyEarlyBird, searchQuery]);

  const handleResetFilters = () => {
    setSearchQuery("");
    setSelectedFormat("all");
    setSelectedCity("all");
    setOnlyEarlyBird(false);
  };

  const getEventMinPrice = (ev: CatalogEventItemOut): number | null => {
    return ev.tariffs.reduce<number | null>((acc, t) => {
      if (t.actual_price === null) return acc;
      if (acc === null) return t.actual_price;
      return Math.min(acc, t.actual_price);
    }, null);
  };

  const getEventMaxSavings = (ev: CatalogEventItemOut): { savings: number; deadline: string | null } => {
    let max = 0;
    let deadline: string | null = null;
    for (const t of ev.tariffs) {
      if (t.savings > max) {
        max = t.savings;
        deadline = t.early_bird_deadline;
      }
    }
    return { savings: max, deadline };
  };

  return (
    <div className="mx-auto max-w-[1440px] p-4 lg:p-5 space-y-3.5">
      {/* 1. Компактная консоль управления: поиск, фильтры и переключатель вида */}
      <div className="rounded-[12px] border border-[#262D35] bg-[#161B22] p-3.5 sm:p-4 shadow-sm space-y-3">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h1 className="font-serif italic text-base sm:text-lg font-semibold tracking-tight text-[#E5C378]">
              Отслеживаемый реестр отраслевых площадок
            </h1>
            <p className="mt-0.5 font-serif italic text-xs leading-relaxed text-[#8E95A0]">
              Каталог конференций, форумов и круглых столов с актуальными тарифами организаторов и скидками Early Bird
            </p>
          </div>

          {/* Строка поиска */}
          <div className="relative w-full lg:w-72">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[#8E95A0]"
              strokeWidth={1.75}
            />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Поиск по названию, КРТ, BIM..."
              className="h-8 w-full rounded-[6px] border border-[#262D35] bg-[#12161A] pl-8 pr-7 text-xs text-white placeholder:text-[#6B7280] [color-scheme:dark] outline-none focus:outline-none focus:border-[#E5C378] focus:shadow-[0_0_0_1px_rgba(229,195,120,0.25)] transition-colors duration-150"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery("")}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-[#8E95A0] hover:text-[#E5C378] transition-colors"
                title="Очистить поиск"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        </div>

        {/* Интерактивная строка фильтрации: Формат, Локация, Early Bird и Вид */}
        <div className="flex flex-wrap items-center justify-between gap-2.5 border-t border-[#21262F] pt-2.5 text-xs">
          <div className="flex flex-wrap items-center gap-2">
            {/* Селектор формата */}
            <div className="flex items-center gap-1.5">
              <span className="font-serif italic text-[11px] text-[#8E95A0]">
                Формат:
              </span>
              <CustomSelect
                value={selectedFormat}
                onChange={(val) => setSelectedFormat(String(val))}
                options={FORMAT_OPTIONS}
                buttonClassName="h-7 min-w-[130px] text-xs"
              />
            </div>

            {/* Селектор города */}
            <div className="flex items-center gap-1.5">
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
                buttonClassName="h-7 min-w-[140px] text-xs"
              />
            </div>

            {/* Быстрый фильтр: Только Early Bird */}
            <button
              type="button"
              onClick={() => setOnlyEarlyBird((prev) => !prev)}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-[4px] px-2.5 py-1 text-xs font-serif italic transition-all duration-150 select-none cursor-pointer outline-none",
                onlyEarlyBird
                  ? "border border-[#E5C378] bg-[#261E0F] text-[#E5C378] font-bold shadow-[0_0_8px_rgba(229,195,120,0.2)]"
                  : "border border-[#262D35] bg-[#12161A] text-[#8E95A0] hover:border-[#38414F] hover:text-white"
              )}
            >
              <Sparkles className="h-3 w-3 text-inherit shrink-0" strokeWidth={1.75} />
              <span>Только со скидкой Early Bird</span>
              {onlyEarlyBird && (
                <span className="ml-0.5 rounded bg-[#E5C378]/20 px-1 py-0.2 text-[10px] text-[#E5C378]">
                  {metrics.earlyBird}
                </span>
              )}
            </button>
          </div>

          {/* Правая часть: счетчик и переключатель вида */}
          <div className="flex items-center gap-3">
            <span className="text-[11px] text-[#8E95A0] font-serif italic hidden sm:inline">
              Показано: <strong className="text-white font-sans font-semibold not-italic tabular-nums">{filteredEvents.length}</strong> из {events.length}
            </span>

            {/* Переключатель вида Реестр / Карточки */}
            <div className="inline-flex items-center rounded-[6px] border border-[#262D35] bg-[#12161A] p-0.5">
              <button
                type="button"
                onClick={() => setViewMode("table")}
                title="Режим реестра (таблица)"
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-[4px] px-2.5 py-1 text-xs font-serif italic transition-all duration-150",
                  viewMode === "table"
                    ? "bg-[#261E0F] text-[#E5C378] border border-[#7C5A20]/60 font-semibold shadow-xs"
                    : "text-[#8E95A0] hover:text-white"
                )}
              >
                <LayoutList className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} />
                <span className="hidden md:inline">Реестр</span>
              </button>
              <button
                type="button"
                onClick={() => setViewMode("cards")}
                title="Режим визиток (карточки)"
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-[4px] px-2.5 py-1 text-xs font-serif italic transition-all duration-150",
                  viewMode === "cards"
                    ? "bg-[#261E0F] text-[#E5C378] border border-[#7C5A20]/60 font-semibold shadow-xs"
                    : "text-[#8E95A0] hover:text-white"
                )}
              >
                <LayoutGrid className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} />
                <span className="hidden md:inline">Карточки</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* 2. Контентная область: загрузка / пусто / реестр / карточки */}
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
            Попробуйте смягчить критерии поиска (сбросить формат или отключить фильтр Early Bird)
          </p>
          <button
            type="button"
            onClick={handleResetFilters}
            className="mt-4 inline-flex items-center gap-1.5 rounded-[6px] bg-gradient-to-r from-[#D4AF37] via-[#E5C378] to-[#D4AF37] px-3.5 py-1.5 text-xs font-semibold text-[#0E1215] shadow-sm hover:shadow-[0_0_12px_rgba(229,195,120,0.35)] active:scale-[0.98] transition-all cursor-pointer"
          >
            <RotateCcw className="h-3 w-3 text-[#0E1215]" strokeWidth={2} />
            <span>Сбросить все фильтры</span>
          </button>
        </div>
      ) : viewMode === "table" ? (
        /* ========================================================================= */
        /* РЕЖИМ 1: РЕЕСТР (ТАБЛИЦА) — Высокая плотность, до 15 событий на экран    */
        /* ========================================================================= */
        <div className="rounded-[12px] border border-[#262D35] bg-[#161B22] shadow-sm overflow-hidden">
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
                {filteredEvents.map((ev) => {
                  const cal = formatCalendarBadge(ev.start_date, ev.end_date);
                  const formatLabel = FORMAT_LABELS[ev.event_format] || ev.event_format;
                  const locationLabel = ev.is_online ? "Онлайн" : ev.city || "Россия";
                  const minPrice = getEventMinPrice(ev);
                  const { savings, deadline } = getEventMaxSavings(ev);

                  return (
                    <tr
                      key={ev.event_id}
                      onClick={() => setSelectedEventForDrawer(ev)}
                      className="group cursor-pointer transition-colors duration-150 hover:bg-[#1A2128]"
                    >
                      {/* 1. Дата события */}
                      <td className="py-3 pl-4 pr-3 align-middle tabular-nums whitespace-nowrap">
                        <div className="flex items-center gap-2">
                          <span className="font-serif font-bold text-xs text-white group-hover:text-[#E5C378] transition-colors">
                            {cal.dayText}
                          </span>
                          <span className="text-[10px] font-serif uppercase tracking-wider text-[#8E95A0]">
                            {cal.monthText}
                          </span>
                        </div>
                      </td>

                      {/* 2. Название и тематика */}
                      <td className="py-3 px-3 align-middle">
                        <div className="min-w-0 max-w-lg">
                          <span className="font-serif text-[13px] font-semibold text-white group-hover:text-[#E5C378] transition-colors leading-snug line-clamp-1">
                            {ev.canonical_title}
                          </span>
                          {ev.themes.length > 0 && (
                            <p className="mt-0.5 text-[11px] text-[#727985] truncate font-serif italic">
                              {ev.themes.slice(0, 3).join(" · ")}
                            </p>
                          )}
                        </div>
                      </td>

                      {/* 3. Формат и город */}
                      <td className="py-3 px-3 align-middle whitespace-nowrap">
                        <div className="flex items-center gap-1.5 text-xs text-[#D1D5DB]">
                          {ev.is_online ? (
                            <Globe className="h-3 w-3 text-[#529E85] shrink-0" strokeWidth={1.5} />
                          ) : (
                            <MapPin className="h-3 w-3 text-[#8E95A0] shrink-0" strokeWidth={1.5} />
                          )}
                          <span className="truncate">{locationLabel}</span>
                          <span className="text-[#3A4553]">·</span>
                          <span className="text-[11px] text-[#8E95A0] font-serif italic">
                            {formatLabel}
                          </span>
                        </div>
                      </td>

                      {/* 4. Стоимость (от X) */}
                      <td className="py-3 px-3 align-middle whitespace-nowrap tabular-nums">
                        {minPrice !== null ? (
                          <div>
                            <span className="font-sans font-bold text-white text-xs">
                              от {formatRub(minPrice)}
                            </span>
                            <span className="block text-[10px] text-[#727985] font-serif italic">
                              {ev.tariffs.length} тарифа
                            </span>
                          </div>
                        ) : (
                          <span className="text-xs text-[#8E95A0] font-serif italic">
                            По запросу
                          </span>
                        )}
                      </td>

                      {/* 5. Early Bird выгода */}
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

                      {/* 6. Кнопка «Детали» */}
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
        </div>
      ) : (
        /* ========================================================================= */
        /* РЕЖИМ 2: КАРТОЧКИ (ОБЛЕГЧЕННЫЕ) — Без простыней из тарифов, высота ~140px */
        /* ========================================================================= */
        <div className="grid grid-cols-1 gap-3.5 lg:grid-cols-2">
          {filteredEvents.map((ev) => {
            const cal = formatCalendarBadge(ev.start_date, ev.end_date);
            const formatLabel = FORMAT_LABELS[ev.event_format] || ev.event_format;
            const locationLabel = ev.is_online ? "Онлайн" : ev.city || "Россия";
            const minPrice = getEventMinPrice(ev);
            const { savings } = getEventMaxSavings(ev);

            return (
              <div
                key={ev.event_id}
                onClick={() => setSelectedEventForDrawer(ev)}
                className="group flex flex-col justify-between rounded-[10px] border border-[#262D35] bg-[#161B22] p-4 shadow-sm transition-all duration-150 hover:border-[#7C5A20] hover:bg-[#181D24] cursor-pointer"
              >
                <div>
                  <div className="flex items-start gap-3">
                    {/* Календарный листок даты */}
                    <div className="flex min-h-[58px] min-w-[56px] shrink-0 flex-col items-center justify-center rounded-[6px] border border-[#7C5A20]/50 bg-[#12161A] px-2 py-1.5 tabular-nums shadow-inner transition-colors group-hover:border-[#E5C378]">
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
                            <Globe className="h-3 w-3 text-[#529E85]" strokeWidth={1.5} />
                          ) : (
                            <MapPin className="h-3 w-3 text-[#8E95A0]" strokeWidth={1.5} />
                          )}
                          {locationLabel}
                        </span>
                        {ev.venue && (
                          <>
                            <span>·</span>
                            <span className="inline-flex items-center gap-1 truncate max-w-[200px]">
                              <Building className="h-3 w-3 shrink-0 opacity-70" strokeWidth={1.5} />
                              {ev.venue}
                            </span>
                          </>
                        )}
                      </div>

                      <h3 className="mt-1 font-serif text-sm sm:text-[15px] font-semibold leading-snug text-white group-hover:text-[#E5C378] transition-colors line-clamp-1">
                        {ev.canonical_title}
                      </h3>

                      <p className="mt-1 text-xs text-[#8E95A0] line-clamp-1 leading-relaxed">
                        {ev.summary}
                      </p>
                    </div>
                  </div>

                  {/* Тематические теги */}
                  {ev.themes.length > 0 && (
                    <div className="mt-2.5 flex flex-wrap gap-1">
                      {ev.themes.slice(0, 4).map((t) => (
                        <span
                          key={t}
                          className="rounded-[3px] border border-[#262D35] bg-[#12161A] px-1.5 py-0.2 text-[10px] font-serif italic text-[#8E95A0]"
                        >
                          {t}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                {/* Нижняя лаконичная сводка: стоимость + Early Bird + кнопка Подробнее */}
                <div className="mt-3 flex items-center justify-between border-t border-[#21262F] pt-2.5 text-xs">
                  <div className="flex items-center gap-2">
                    <span className="font-sans font-bold text-white tabular-nums">
                      {minPrice !== null ? `от ${formatRub(minPrice)}` : "По запросу"}
                    </span>
                    {savings > 0 && (
                      <Badge variant="ebEmerald" className="text-[9px]">
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
        </div>
      )}

      {/* 3. Выдвижная шторка детального просмотра мероприятия (Slide-over Drawer) */}
      <EventDetailsDrawer
        event={selectedEventForDrawer}
        isOpen={Boolean(selectedEventForDrawer)}
        onClose={() => setSelectedEventForDrawer(null)}
      />
    </div>
  );
}
