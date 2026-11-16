import { motion } from "framer-motion";
import {
  Search,
  Sparkles,
  CalendarCheck,
  X,
  RotateCcw,
  LayoutList,
  LayoutGrid,
  ArrowUpDown,
  Upload,
  Radar,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { CustomSelect } from "@/components/ui/custom-select";
import { DateInput } from "@/components/ui/date-input";
import {
  SearchableMultiSelectPopover,
  type MultiSelectOption,
} from "@/components/ui/searchable-multi-select-popover";
import { cn } from "@/lib/utils";
import {
  FORMAT_OPTIONS,
  ROLE_FILTER_OPTIONS,
  DATA_STATUS_OPTIONS,
  SORT_OPTIONS,
} from "./catalogUtils";

interface CatalogHeaderAndFiltersProps {
  totalCount: number;
  filteredCount: number;
  earlyBirdCount: number;
  upcomingCount: number;
  hiddenPastCount: number;
  roleCounts: Record<string, number>;
  searchQuery: string;
  onSearchQueryChange: (value: string) => void;
  selectedFormat: string;
  onFormatChange: (value: string) => void;
  selectedRole: string;
  onRoleChange: (value: string) => void;
  cityOptions: MultiSelectOption[];
  selectedCities: string[];
  onCitiesChange: (values: string[]) => void;
  themeMultiOptions: MultiSelectOption[];
  selectedThemes: string[];
  onThemesChange: (values: string[]) => void;
  selectedDataStatus: string;
  onDataStatusChange: (value: string) => void;
  dateFrom: string;
  onDateFromChange: (value: string) => void;
  dateTo: string;
  onDateToChange: (value: string) => void;
  isDateRangeInvalid: boolean;
  sortBy: string;
  onSortByChange: (value: string) => void;
  onlyEarlyBird: boolean;
  onToggleEarlyBird: () => void;
  onlyUpcoming: boolean;
  onToggleUpcoming: () => void;
  hasActiveFilters: boolean;
  onResetFilters: () => void;
  viewMode: "table" | "cards";
  onViewModeChange: (mode: "table" | "cards") => void;
  onOpenImportModal: () => void;
  onOpenScraperModal: () => void;
}

export function CatalogHeaderAndFilters({
  totalCount,
  filteredCount,
  earlyBirdCount,
  upcomingCount,
  hiddenPastCount,
  roleCounts,
  searchQuery,
  onSearchQueryChange,
  selectedFormat,
  onFormatChange,
  selectedRole,
  onRoleChange,
  cityOptions,
  selectedCities,
  onCitiesChange,
  themeMultiOptions,
  selectedThemes,
  onThemesChange,
  selectedDataStatus,
  onDataStatusChange,
  dateFrom,
  onDateFromChange,
  dateTo,
  onDateToChange,
  isDateRangeInvalid,
  sortBy,
  onSortByChange,
  onlyEarlyBird,
  onToggleEarlyBird,
  onlyUpcoming,
  onToggleUpcoming,
  hasActiveFilters,
  onResetFilters,
  viewMode,
  onViewModeChange,
  onOpenImportModal,
  onOpenScraperModal,
}: CatalogHeaderAndFiltersProps) {
  const roleSelectOptions = ROLE_FILTER_OPTIONS.map((opt) => ({
    ...opt,
    subLabel:
      opt.value === "all"
        ? String(totalCount)
        : String(roleCounts[opt.value] ?? 0),
  }));
  return (
    <div className="rounded-[12px] border border-[#262D35] bg-[#161B22] p-3.5 sm:p-4 shadow-sm space-y-3">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <div className="flex flex-wrap items-baseline gap-2.5">
            <h1 className="font-serif italic text-base sm:text-lg font-semibold tracking-tight text-[#E5C378]">
              Отслеживаемый реестр отраслевых площадок
            </h1>
            <span className="rounded-[4px] border border-[#7C5A20]/50 bg-[#161B21] px-2 py-0.5 text-[11px] font-medium text-[#E5C378] tabular-nums select-none">
              {totalCount} в базе
            </span>
          </div>
          <p className="mt-0.5 font-serif italic text-xs leading-relaxed text-[#8E95A0]">
            Каталог конференций, форумов и круглых столов с актуальными тарифами организаторов и скидками Early Bird
          </p>
        </div>

        {/* Правая зона: поиск + действия импорта и парсера */}
        <div className="flex flex-wrap items-center gap-2 lg:justify-end">
          <div className="relative w-full sm:w-64">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[#8E95A0]"
              strokeWidth={1.75}
            />
            <input
              id="catalog-search"
              name="catalog_search"
              type="text"
              value={searchQuery}
              onChange={(e) => onSearchQueryChange(e.target.value)}
              placeholder="Поиск по названию, КРТ, BIM..."
              aria-label="Поиск мероприятий по названию или теме"
              className="h-8 w-full rounded-[6px] border border-[#262D35] bg-[#12161A] pl-8 pr-7 text-xs text-white placeholder:text-[#8E95A0] [color-scheme:dark] outline-none focus:outline-none focus:border-[#E5C378] focus:shadow-[0_0_0_1px_rgba(229,195,120,0.25)] transition-colors duration-150"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => onSearchQueryChange("")}
                aria-label="Очистить поиск"
                className="absolute right-2 top-1/2 -translate-y-1/2 text-[#8E95A0] hover:text-[#E5C378] transition-colors"
                title="Очистить поиск"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>

          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onOpenImportModal}
            className="h-8 cursor-pointer border-[#7C5A20]/60 bg-[#12161A] text-xs text-[#E5C378] hover:border-[#E5C378] hover:bg-[#1E2530] hover:text-[#E5C378]"
          >
            <Upload className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} />
            <span>Импорт PDF / Ссылки</span>
          </Button>

          <Button
            type="button"
            variant="monolith"
            size="sm"
            onClick={onOpenScraperModal}
            className="h-8 cursor-pointer text-xs"
          >
            <Radar className="h-3.5 w-3.5 text-[#E5C378] monolith-icon shrink-0" strokeWidth={1.75} />
            <span>Запустить парсер</span>
          </Button>
        </div>
      </div>

      {/* Интерактивная строка фильтрации: Формат, Локация, Тематика, Статус, Период, Сортировка, Early Bird и Вид */}
      <div className="flex flex-wrap items-center justify-between gap-2.5 border-t border-[#21262F] pt-2.5 text-xs">
        <div className="flex flex-wrap items-center gap-2">
          {/* Селектор формата */}
          <div className="flex items-center gap-1.5">
            <span className="font-serif italic text-[11px] text-[#8E95A0]">
              Формат:
            </span>
            <CustomSelect
              value={selectedFormat}
              onChange={(val) => onFormatChange(String(val))}
              options={FORMAT_OPTIONS}
              buttonClassName="h-7 min-w-[120px] text-xs"
            />
          </div>

          {/* Селектор роли участия */}
          <div className="flex items-center gap-1.5">
            <span className="font-serif italic text-[11px] text-[#8E95A0]">
              Роль:
            </span>
            <CustomSelect
              value={selectedRole}
              onChange={(val) => onRoleChange(String(val))}
              options={roleSelectOptions}
              buttonClassName="h-7 min-w-[116px] text-xs"
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
              onChange={onCitiesChange}
              allSelectedLabel={`Все (${totalCount})`}
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
              onChange={onThemesChange}
              allSelectedLabel={`Все (${totalCount})`}
              popoverWidthClass="w-80"
            />
          </div>

          {/* Селектор статуса данных (серверная фильтрация) */}
          <div className="flex items-center gap-1.5">
            <span className="font-serif italic text-[11px] text-[#8E95A0]">
              Статус:
            </span>
            <CustomSelect
              value={selectedDataStatus}
              onChange={(val) => onDataStatusChange(String(val))}
              options={DATA_STATUS_OPTIONS}
              buttonClassName="h-7 min-w-[138px] text-xs"
            />
          </div>

          {/* Фильтр периода дат проведения (серверная фильтрация) */}
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-serif italic text-[11px] text-[#8E95A0]">
              Период:
            </span>
            <DateInput
              id="catalog-date-from"
              name="catalog_date_from"
              value={dateFrom}
              onChange={onDateFromChange}
              ariaLabel="Дата проведения с"
              ariaInvalid={isDateRangeInvalid}
              inputClassName="h-7 w-[124px] text-xs"
            />
            <span className="text-[11px] text-[#8E95A0]">—</span>
            <DateInput
              id="catalog-date-to"
              name="catalog_date_to"
              value={dateTo}
              onChange={onDateToChange}
              ariaLabel="Дата проведения по"
              ariaInvalid={isDateRangeInvalid}
              inputClassName="h-7 w-[124px] text-xs"
            />
            {isDateRangeInvalid && (
              <span className="text-[11px] text-[#FCA5A5]">
                Дата «по» раньше даты «с»
              </span>
            )}
          </div>

          {/* Меню многофакторной сортировки */}
          <div className="flex items-center gap-1.5">
            <span className="font-serif italic text-[11px] text-[#8E95A0] inline-flex items-center gap-1">
              <ArrowUpDown className="h-3 w-3 text-inherit opacity-75" />
              <span>Сортировка:</span>
            </span>
            <CustomSelect
              value={sortBy}
              onChange={(val) => onSortByChange(String(val))}
              options={SORT_OPTIONS}
              buttonClassName="h-7 min-w-[155px] text-xs"
            />
          </div>

          {/* Быстрый фильтр: Только предстоящие */}
          <button
            type="button"
            onClick={onToggleUpcoming}
            aria-pressed={onlyUpcoming}
            title={
              onlyUpcoming && hiddenPastCount > 0
                ? `Скрыто прошедших: ${hiddenPastCount}. Нажмите, чтобы показать весь архив`
                : "Показать только предстоящие мероприятия"
            }
            className={cn(
              "inline-flex items-center gap-1.5 rounded-[4px] px-2.5 py-1 text-xs font-serif italic transition-all duration-150 select-none cursor-pointer outline-none",
              onlyUpcoming
                ? "border border-[#E5C378] bg-[#261E0F] text-[#E5C378] font-bold shadow-[0_0_8px_rgba(229,195,120,0.2)]"
                : "border border-[#262D35] bg-[#12161A] text-[#8E95A0] hover:border-[#38414F] hover:text-white"
            )}
          >
            <CalendarCheck className="h-3 w-3 text-inherit shrink-0" strokeWidth={1.75} />
            <span>Только предстоящие ({upcomingCount})</span>
          </button>

          {/* Быстрый фильтр: Только Early Bird */}
          <button
            type="button"
            onClick={onToggleEarlyBird}
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
              <span className="ml-0.5 rounded bg-[#E5C378]/20 px-1.5 py-0.5 text-[11px] text-[#E5C378]">
                {earlyBirdCount}
              </span>
            )}
          </button>

          {/* Быстрый сброс фильтров */}
          {hasActiveFilters && (
            <button
              type="button"
              onClick={onResetFilters}
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
            Показано:{" "}
            <strong className="text-white font-sans font-semibold not-italic tabular-nums">
              {filteredCount}
            </strong>{" "}
            из {totalCount}
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
                  onClick={() => onViewModeChange(mode.id)}
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
  );
}
