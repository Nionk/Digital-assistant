import * as React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "sonner";
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
  ArrowUpDown,
  Copy,
  Check,
} from "lucide-react";
import { useManagerEventsCatalog } from "@/api/queries";
import type { CatalogEventItemOut } from "@/api/types";
import { useManagerStore } from "@/store/useManagerStore";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CustomSelect } from "@/components/ui/custom-select";
import {
  SearchableMultiSelectPopover,
  type MultiSelectOption,
} from "@/components/ui/searchable-multi-select-popover";
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

const SORT_OPTIONS = [
  { value: "date_asc", label: "Ближайшие по дате" },
  { value: "date_desc", label: "Поздние по дате" },
  { value: "price_asc", label: "Сначала доступные (по цене)" },
  { value: "price_desc", label: "Сначала премиальные (по цене)" },
  { value: "savings_desc", label: "Выгода Early Bird" },
];

/**
 * База площадок (реестр отраслевых мероприятий) в кабинете менеджера.
 * Организована по принципу Progressive Disclosure:
 * 1. Легковесный, неутомительный реестр (таблица / карточки) для быстрого сканирования.
 * 2. Выпадающие фильтры по формату, локации, тематике и сортировке.
 * 3. Детальная боковая шторка по клику на событие для углубленного изучения тарифов.
 */
export function EventsCatalogView() {
  const { data, isLoading } = useManagerEventsCatalog(true);
  const [searchQuery, setSearchQuery] = React.useState("");
  const [selectedFormat, setSelectedFormat] = React.useState<string>("all");
  const [selectedCities, setSelectedCities] = React.useState<string[]>([]);
  const [selectedThemes, setSelectedThemes] = React.useState<string[]>([]);
  const [sortBy, setSortBy] = React.useState<string>("date_asc");
  const [onlyEarlyBird, setOnlyEarlyBird] = React.useState<boolean>(false);
  const [viewMode, setViewMode] = React.useState<"table" | "cards">("table");
  const [selectedEventForDrawer, setSelectedEventForDrawer] =
    React.useState<CatalogEventItemOut | null>(null);
  const [copiedEventId, setCopiedEventId] = React.useState<number | null>(null);

  const catalogTargetEventId = useManagerStore((s) => s.catalogTargetEventId);
  const setCatalogTargetEventId = useManagerStore((s) => s.setCatalogTargetEventId);

  const events = data?.events || [];

  const handleCopyLocation = (e: React.MouseEvent, ev: CatalogEventItemOut) => {
    e.stopPropagation();
    const fullText = ev.is_online
      ? "Онлайн"
      : `${ev.city || ""}${ev.venue ? `, ${ev.venue}` : ""}`.trim();
    if (!fullText) return;
    navigator.clipboard.writeText(fullText).catch(() => {});
    setCopiedEventId(ev.event_id);
    toast.success(`Адрес скопирован: ${fullText}`);
    setTimeout(() => {
      setCopiedEventId((prev) => (prev === ev.event_id ? null : prev));
    }, 2000);
  };

  // Автоматическое открытие шторки площадки при переходе из дедлайнов Early Bird
  React.useEffect(() => {
    if (!catalogTargetEventId || events.length === 0) return;
    const target = events.find((e) => e.event_id === catalogTargetEventId);
    if (target) {
      if (selectedFormat !== "all" && target.event_format !== selectedFormat) {
        setSelectedFormat("all");
      }
      if (searchQuery.trim().length > 0) {
        setSearchQuery("");
      }
      setSelectedEventForDrawer(target);
      toast.info(`Условия площадки: «${target.canonical_title}»`);
    }
    setCatalogTargetEventId(null);
  }, [catalogTargetEventId, events, selectedFormat, searchQuery, setCatalogTargetEventId]);

  const cityOptions = React.useMemo(() => {
    const counts = new Map<string, number>();
    let onlineCount = 0;
    for (const ev of events) {
      if (ev.is_online) onlineCount++;
      if (ev.city) {
        counts.set(ev.city, (counts.get(ev.city) || 0) + 1);
      }
    }
    const list: MultiSelectOption[] = [
      { value: "online", label: "Онлайн", count: onlineCount },
      ...Array.from(counts.entries())
        .map(([city, count]) => ({ value: city, label: city, count }))
        .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label)),
    ];
    return list;
  }, [events]);

  const themeMultiOptions = React.useMemo(() => {
    const map = new Map<string, number>();
    for (const ev of events) {
      for (const t of ev.themes) {
        map.set(t, (map.get(t) || 0) + 1);
      }
    }
    return Array.from(map.entries())
      .map(([name, count]) => ({ value: name, label: name, count }))
      .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
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

  const filteredEvents = React.useMemo(() => {
    const list = events.filter((ev) => {
      if (selectedFormat !== "all" && ev.event_format !== selectedFormat) {
        return false;
      }
      if (selectedCities.length > 0) {
        const matchesCity = selectedCities.some((c) => {
          if (c === "online") return ev.is_online;
          return ev.city === c;
        });
        if (!matchesCity) return false;
      }
      if (selectedThemes.length > 0) {
        const matchesTheme = selectedThemes.some((t) => ev.themes.includes(t));
        if (!matchesTheme) return false;
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

    return list.sort((a, b) => {
      if (sortBy === "date_asc") {
        return a.start_date.localeCompare(b.start_date);
      }
      if (sortBy === "date_desc") {
        return b.start_date.localeCompare(a.start_date);
      }
      if (sortBy === "price_asc") {
        const pA = getEventMinPrice(a) ?? Infinity;
        const pB = getEventMinPrice(b) ?? Infinity;
        return pA - pB;
      }
      if (sortBy === "price_desc") {
        const pA = getEventMinPrice(a) ?? -1;
        const pB = getEventMinPrice(b) ?? -1;
        return pB - pA;
      }
      if (sortBy === "savings_desc") {
        const sA = getEventMaxSavings(a).savings;
        const sB = getEventMaxSavings(b).savings;
        return sB - sA;
      }
      return 0;
    });
  }, [events, selectedFormat, selectedCities, selectedThemes, onlyEarlyBird, searchQuery, sortBy]);

  const hasActiveFilters =
    searchQuery.trim().length > 0 ||
    selectedFormat !== "all" ||
    selectedCities.length > 0 ||
    selectedThemes.length > 0 ||
    onlyEarlyBird;

  const handleResetFilters = () => {
    setSearchQuery("");
    setSelectedFormat("all");
    setSelectedCities([]);
    setSelectedThemes([]);
    setSortBy("date_asc");
    setOnlyEarlyBird(false);
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

        {/* Интерактивная строка фильтрации: Формат, Локация, Тематика, Сортировка, Early Bird и Вид */}
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
                buttonClassName="h-7 min-w-[120px] text-xs"
              />
            </div>

            {/* Выдвижная панель выбора локации */}
            <div className="flex items-center gap-1.5">
              <span className="font-serif italic text-[11px] text-[#8E95A0]">
                Локация:
              </span>
              <SearchableMultiSelectPopover
                label="Локация"
                placeholder="Поиск города..."
                options={cityOptions}
                selectedValues={selectedCities}
                onChange={setSelectedCities}
                allSelectedLabel={`Все (${events.length})`}
                popoverWidthClass="w-72"
              />
            </div>

            {/* Выдвижная панель выбора тематики */}
            <div className="flex items-center gap-1.5">
              <span className="font-serif italic text-[11px] text-[#8E95A0]">
                Тема:
              </span>
              <SearchableMultiSelectPopover
                label="Тематика"
                placeholder="Поиск темы (BIM, КРТ...)"
                options={themeMultiOptions}
                selectedValues={selectedThemes}
                onChange={setSelectedThemes}
                allSelectedLabel={`Все (${events.length})`}
                popoverWidthClass="w-80"
              />
            </div>

            {/* Меню многофакторной сортировки */}
            <div className="flex items-center gap-1.5">
              <span className="font-serif italic text-[11px] text-[#8E95A0] inline-flex items-center gap-1">
                <ArrowUpDown className="h-3 w-3 text-inherit opacity-75" />
                <span>Сортировка:</span>
              </span>
              <CustomSelect
                value={sortBy}
                onChange={(val) => setSortBy(String(val))}
                options={SORT_OPTIONS}
                buttonClassName="h-7 min-w-[155px] text-xs"
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
                <span className="ml-0.5 rounded bg-[#E5C378]/20 px-1 py-0.5 text-[10px] text-[#E5C378]">
                  {metrics.earlyBird}
                </span>
              )}
            </button>

            {/* Быстрый сброс фильтров */}
            {hasActiveFilters && (
              <button
                type="button"
                onClick={handleResetFilters}
                className="inline-flex items-center gap-1 rounded-[4px] px-2 py-1 text-xs font-serif italic text-[#8E95A0] hover:text-[#EF4444] transition-colors"
                title="Сбросить все фильтры"
              >
                <RotateCcw className="h-3 w-3" />
                <span>Сбросить фильтры</span>
              </button>
            )}
          </div>

          {/* Правая часть: счетчик и переключатель вида */}
          <div className="flex items-center gap-3">
            <span className="text-[11px] text-[#8E95A0] font-serif italic hidden sm:inline">
              Показано: <strong className="text-white font-sans font-semibold not-italic tabular-nums">{filteredEvents.length}</strong> из {events.length}
            </span>

            {/* Плавный переключатель вида Реестр / Карточки */}
            <div className="inline-flex items-center rounded-[8px] border border-[#232931] bg-[#12161A] p-1 gap-0.5 shadow-inner">
              {(
                [
                  { id: "table", label: "Реестр", icon: LayoutList, title: "Режим реестра (таблица)" },
                  { id: "cards", label: "Карточки", icon: LayoutGrid, title: "Режим визиток (карточки)" },
                ] as const
              ).map((mode) => {
                const Icon = mode.icon;
                const isActive = viewMode === mode.id;
                return (
                  <button
                    key={mode.id}
                    type="button"
                    onClick={() => setViewMode(mode.id)}
                    title={mode.title}
                    className={cn(
                      "relative inline-flex items-center gap-1.5 rounded-[6px] px-2.5 py-1 text-xs font-medium select-none cursor-pointer transition-colors duration-200 outline-none",
                      isActive ? "text-white" : "text-[#8E95A0] hover:text-white"
                    )}
                  >
                    {isActive && (
                      <motion.span
                        layoutId="catalogViewModePill"
                        transition={{
                          type: "spring",
                          stiffness: 380,
                          damping: 32,
                        }}
                        className="absolute inset-0 rounded-[6px] bg-[#1A2128] shadow-sm"
                      >
                        <span className="absolute bottom-0 left-1.5 right-1.5 h-[2px] rounded-full bg-gradient-to-r from-[#D4AF37] via-[#E5C378] to-[#D4AF37]" />
                      </motion.span>
                    )}
                    <Icon
                      className={cn(
                        "relative z-10 h-3.5 w-3.5 shrink-0 transition-colors duration-200",
                        isActive ? "text-[#E5C378]" : "text-[#8E95A0]"
                      )}
                      strokeWidth={1.75}
                    />
                    <span className="relative z-10 hidden md:inline">
                      {mode.label}
                    </span>
                  </button>
                );
              })}
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
          <p className="mx-auto mt-1.5 max-w-md text-xs leading-relaxed text-[#8E95A0]">
            Попробуйте смягчить критерии поиска (сбросить тему, формат или отключить фильтр Early Bird)
          </p>
          <Button
            type="button"
            variant="monolith"
            size="sm"
            onClick={handleResetFilters}
            className="mt-4 cursor-pointer"
          >
            <RotateCcw className="h-3.5 w-3.5 text-[#E5C378] monolith-icon" strokeWidth={1.75} />
            <span>Сбросить все фильтры</span>
          </Button>
        </div>
      ) : (
        <AnimatePresence mode="wait" initial={false}>
          {viewMode === "table" ? (
            /* ========================================================================= */
            /* РЕЖИМ 1: РЕЕСТР (ТАБЛИЦА) — Высокая плотность, до 15 событий на экран    */
            /* ========================================================================= */
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
                    {filteredEvents.map((ev) => {
                      const cal = formatCalendarBadge(ev.start_date, ev.end_date);
                      const formatLabel = FORMAT_LABELS[ev.event_format] || ev.event_format;
                      const locationLabel = ev.is_online ? "Онлайн" : ev.city || "Россия";
                      const minPrice = getEventMinPrice(ev);
                      const { savings, deadline } = getEventMaxSavings(ev);
                      const isSelected = selectedEventForDrawer?.event_id === ev.event_id;

                      return (
                        <tr
                          key={ev.event_id}
                          onClick={() => setSelectedEventForDrawer(ev)}
                          className={cn(
                            "group cursor-pointer transition-colors duration-150 active:scale-[0.998]",
                            isSelected
                              ? "bg-[#221A0E] text-[#E5C378]"
                              : "hover:bg-[#1A2128]"
                          )}
                        >
                          {/* 1. Дата события (Сроки) — единый стиль и единая высота */}
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

                      {/* 2. Название и тематика с полным тултипом */}
                      <td className="py-3 px-3 align-middle">
                        <div className="min-w-0 max-w-lg">
                          <span
                            title={ev.canonical_title}
                            className="font-serif text-[13px] font-semibold text-white group-hover:text-[#E5C378] transition-colors leading-snug line-clamp-1 cursor-pointer"
                          >
                            {ev.canonical_title}
                          </span>
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

                      {/* 3. Формат и город: кликабельный адрес с копированием в буфер */}
                      <td className="py-3 px-3 align-middle whitespace-nowrap">
                        <div className="flex items-center gap-1.5 text-xs text-[#D1D5DB]">
                          <button
                            type="button"
                            onClick={(e) => handleCopyLocation(e, ev)}
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
            </motion.div>
          ) : (
            /* ========================================================================= */
            /* РЕЖИМ 2: КАРТОЧКИ (ОБЛЕГЧЕННЫЕ) — Без простыней из тарифов, высота ~140px */
            /* ========================================================================= */
            <motion.div
              key="catalog-cards"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15, ease: "easeOut" }}
              className="grid grid-cols-1 gap-3.5 lg:grid-cols-2"
            >
              {filteredEvents.map((ev) => {
                const cal = formatCalendarBadge(ev.start_date, ev.end_date);
                const formatLabel = FORMAT_LABELS[ev.event_format] || ev.event_format;
                const locationLabel = ev.is_online ? "Онлайн" : ev.city || "Россия";
                const minPrice = getEventMinPrice(ev);
                const { savings } = getEventMaxSavings(ev);
                const isSelected = selectedEventForDrawer?.event_id === ev.event_id;

                return (
                  <div
                    key={ev.event_id}
                    onClick={() => setSelectedEventForDrawer(ev)}
                    className={cn(
                      "group flex flex-col justify-between rounded-[10px] border p-4 shadow-sm transition-colors duration-150 active:scale-[0.995] cursor-pointer",
                      isSelected
                        ? "border-[#E5C378] bg-[#1E190E] shadow-[0_0_12px_rgba(229,195,120,0.18)]"
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
                        <button
                          type="button"
                          onClick={(e) => handleCopyLocation(e, ev)}
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
                              onClick={(e) => handleCopyLocation(e, ev)}
                              title={`Клик — скопировать адрес площадки: ${ev.city || ""}, ${ev.venue}`}
                              className="inline-flex items-center gap-1 rounded-[4px] border border-transparent px-1 py-0.5 hover:border-[#7C5A20]/60 hover:bg-[#1E2530] hover:text-[#E5C378] transition-all cursor-pointer text-[#D1D5DB] leading-tight truncate max-w-[220px]"
                            >
                              <Building className="h-3 w-3 shrink-0 opacity-70" strokeWidth={1.5} />
                              <span className="truncate">{ev.venue}</span>
                            </button>
                          </>
                        )}
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
                    </div>
                  </div>

                  {/* Тематические теги */}
                  {ev.themes.length > 0 && (
                    <div className="mt-2.5 flex flex-wrap gap-1">
                      {ev.themes.slice(0, 4).map((t) => (
                        <span
                          key={t}
                          title={t}
                          className="rounded-[3px] border border-[#262D35] bg-[#12161A] px-1.5 py-0.5 text-[10px] font-serif italic text-[#8E95A0] hover:text-[#E5C378] transition-colors"
                        >
                          {t}
                        </span>
                      ))}
                      {ev.themes.length > 4 && (
                        <span
                          title={ev.themes.slice(4).join(", ")}
                          className="rounded-[3px] border border-[#262D35] bg-[#12161A] px-1.5 py-0.5 text-[10px] font-serif italic text-[#E5C378]/80 cursor-help"
                        >
                          +{ev.themes.length - 4}
                        </span>
                      )}
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
            </motion.div>
          )}
        </AnimatePresence>
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
