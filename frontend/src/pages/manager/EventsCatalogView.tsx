import * as React from "react";
import { AnimatePresence } from "framer-motion";
import { Compass, RotateCcw } from "lucide-react";
import { useManagerEventsCatalog } from "@/api/queries";
import type {
  CatalogEventItemOut,
  CatalogEventsFilterParams,
} from "@/api/types";
import { useManagerStore } from "@/store/useManagerStore";
import { Button } from "@/components/ui/button";
import { EventDetailsDrawer } from "./EventDetailsDrawer";
import { EventImportModal } from "./EventImportModal";
import { ScraperRunModal } from "./ScraperRunModal";
import { copyTextToClipboard } from "@/lib/clipboard";
import {
  buildCityMultiOptions,
  buildThemeMultiOptions,
  filterAndSortCatalogEvents,
} from "./catalog/catalogUtils";
import { CatalogHeaderAndFilters } from "./catalog/CatalogHeaderAndFilters";
import { CatalogTable } from "./catalog/CatalogTable";
import { CatalogCardsGrid } from "./catalog/CatalogCardsGrid";

/**
 * База площадок (реестр отраслевых мероприятий) в кабинете менеджера.
 * Организована по принципу Progressive Disclosure:
 * 1. Легковесный, неутомительный реестр (таблица / карточки) для быстрого сканирования.
 * 2. Выпадающие фильтры по формату, локации, тематике и сортировке.
 * 3. Детальная боковая шторка по клику на событие для углубленного изучения тарифов.
 */
export function EventsCatalogView() {
  const [searchQuery, setSearchQuery] = React.useState("");
  const [selectedFormat, setSelectedFormat] = React.useState<string>("all");
  const [selectedCities, setSelectedCities] = React.useState<string[]>([]);
  const [selectedThemes, setSelectedThemes] = React.useState<string[]>([]);
  const [selectedDataStatus, setSelectedDataStatus] = React.useState<string>("all");
  const [dateFrom, setDateFrom] = React.useState<string>("");
  const [dateTo, setDateTo] = React.useState<string>("");
  const [sortBy, setSortBy] = React.useState<string>("date_asc");
  const [onlyEarlyBird, setOnlyEarlyBird] = React.useState<boolean>(false);
  const [viewMode, setViewMode] = React.useState<"table" | "cards">("table");
  const [selectedEventIdForDrawer, setSelectedEventIdForDrawer] =
    React.useState<number | null>(null);
  const [isImportModalOpen, setIsImportModalOpen] = React.useState(false);
  const [isScraperModalOpen, setIsScraperModalOpen] = React.useState(false);
  const [copiedEventId, setCopiedEventId] = React.useState<number | null>(null);
  const copyTimerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  const isDateRangeInvalid = Boolean(dateFrom && dateTo && dateTo < dateFrom);

  const catalogFilters = React.useMemo<CatalogEventsFilterParams | undefined>(() => {
    const status =
      selectedDataStatus === "ready" || selectedDataStatus === "needs_enrichment"
        ? selectedDataStatus
        : null;
    const validDateFrom = !isDateRangeInvalid && dateFrom ? dateFrom : null;
    const validDateTo = !isDateRangeInvalid && dateTo ? dateTo : null;
    if (!status && !validDateFrom && !validDateTo) return undefined;
    return {
      data_status: status,
      date_from: validDateFrom,
      date_to: validDateTo,
    };
  }, [selectedDataStatus, dateFrom, dateTo, isDateRangeInvalid]);

  const { data, isLoading } = useManagerEventsCatalog(true, catalogFilters);

  const catalogTargetEventId = useManagerStore((s) => s.catalogTargetEventId);
  const setCatalogTargetEventId = useManagerStore((s) => s.setCatalogTargetEventId);

  const events = React.useMemo(() => data?.events || [], [data?.events]);

  const selectedEventForDrawer = React.useMemo(() => {
    if (selectedEventIdForDrawer === null) return null;
    return events.find((e) => e.event_id === selectedEventIdForDrawer) ?? null;
  }, [events, selectedEventIdForDrawer]);

  React.useEffect(() => {
    return () => {
      if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
    };
  }, []);

  const handleCopyLocation = async (
    e: React.MouseEvent,
    ev: CatalogEventItemOut
  ) => {
    e.stopPropagation();
    const fullText = ev.is_online
      ? "Онлайн"
      : `${ev.city || ""}${ev.venue ? `, ${ev.venue}` : ""}`.trim();
    if (!fullText) return;
    const ok = await copyTextToClipboard(fullText, {
      successMessage: `Адрес скопирован: ${fullText}`,
    });
    if (!ok) return;
    if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
    setCopiedEventId(ev.event_id);
    copyTimerRef.current = setTimeout(() => {
      setCopiedEventId((prev) => (prev === ev.event_id ? null : prev));
    }, 2000);
  };

  // Автоматическое открытие шторки площадки при переходе из дедлайнов Early Bird
  React.useEffect(() => {
    if (!catalogTargetEventId || isLoading) return;
    const target = events.find((e) => e.event_id === catalogTargetEventId);
    if (target) {
      if (selectedFormat !== "all" && target.event_format !== selectedFormat) {
        setSelectedFormat("all");
      }
      if (searchQuery.trim().length > 0) {
        setSearchQuery("");
      }
      setSelectedEventIdForDrawer(target.event_id);
      setCatalogTargetEventId(null);
      return;
    }
    // Если событие отфильтровано серверными фильтрами каталога, сбрасываем их перед открытием
    if (selectedDataStatus !== "all" || dateFrom || dateTo) {
      setSelectedDataStatus("all");
      setDateFrom("");
      setDateTo("");
      return;
    }
    setCatalogTargetEventId(null);
  }, [
    catalogTargetEventId,
    events,
    isLoading,
    selectedFormat,
    searchQuery,
    selectedDataStatus,
    dateFrom,
    dateTo,
    setCatalogTargetEventId,
  ]);

  const cityOptions = React.useMemo(
    () => buildCityMultiOptions(events),
    [events]
  );

  const themeMultiOptions = React.useMemo(
    () => buildThemeMultiOptions(events),
    [events]
  );

  const earlyBirdCount = React.useMemo(
    () => events.filter((e) => e.tariffs.some((t) => t.savings > 0)).length,
    [events]
  );

  const filteredEvents = React.useMemo(
    () =>
      filterAndSortCatalogEvents(events, {
        selectedFormat,
        selectedCities,
        selectedThemes,
        onlyEarlyBird,
        searchQuery,
        sortBy,
      }),
    [
      events,
      selectedFormat,
      selectedCities,
      selectedThemes,
      onlyEarlyBird,
      searchQuery,
      sortBy,
    ]
  );

  const hasActiveFilters =
    searchQuery.trim().length > 0 ||
    selectedFormat !== "all" ||
    selectedCities.length > 0 ||
    selectedThemes.length > 0 ||
    selectedDataStatus !== "all" ||
    Boolean(dateFrom) ||
    Boolean(dateTo) ||
    onlyEarlyBird;

  const handleResetFilters = () => {
    setSearchQuery("");
    setSelectedFormat("all");
    setSelectedCities([]);
    setSelectedThemes([]);
    setSelectedDataStatus("all");
    setDateFrom("");
    setDateTo("");
    setSortBy("date_asc");
    setOnlyEarlyBird(false);
  };

  return (
    <div className="mx-auto max-w-[1440px] p-4 lg:p-5 space-y-3.5">
      <CatalogHeaderAndFilters
        totalCount={events.length}
        filteredCount={filteredEvents.length}
        earlyBirdCount={earlyBirdCount}
        searchQuery={searchQuery}
        onSearchQueryChange={setSearchQuery}
        selectedFormat={selectedFormat}
        onFormatChange={setSelectedFormat}
        cityOptions={cityOptions}
        selectedCities={selectedCities}
        onCitiesChange={setSelectedCities}
        themeMultiOptions={themeMultiOptions}
        selectedThemes={selectedThemes}
        onThemesChange={setSelectedThemes}
        selectedDataStatus={selectedDataStatus}
        onDataStatusChange={setSelectedDataStatus}
        dateFrom={dateFrom}
        onDateFromChange={setDateFrom}
        dateTo={dateTo}
        onDateToChange={setDateTo}
        isDateRangeInvalid={isDateRangeInvalid}
        sortBy={sortBy}
        onSortByChange={setSortBy}
        onlyEarlyBird={onlyEarlyBird}
        onToggleEarlyBird={() => setOnlyEarlyBird((prev) => !prev)}
        hasActiveFilters={hasActiveFilters}
        onResetFilters={handleResetFilters}
        viewMode={viewMode}
        onViewModeChange={setViewMode}
        onOpenImportModal={() => setIsImportModalOpen(true)}
        onOpenScraperModal={() => setIsScraperModalOpen(true)}
      />

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
            <CatalogTable
              key="catalog-table"
              events={filteredEvents}
              selectedEventId={selectedEventForDrawer?.event_id ?? null}
              copiedEventId={copiedEventId}
              onSelectEvent={setSelectedEventIdForDrawer}
              onCopyLocation={handleCopyLocation}
            />
          ) : (
            <CatalogCardsGrid
              key="catalog-cards"
              events={filteredEvents}
              selectedEventId={selectedEventForDrawer?.event_id ?? null}
              copiedEventId={copiedEventId}
              onSelectEvent={setSelectedEventIdForDrawer}
              onCopyLocation={handleCopyLocation}
            />
          )}
        </AnimatePresence>
      )}

      <EventDetailsDrawer
        event={selectedEventForDrawer}
        isOpen={Boolean(selectedEventForDrawer)}
        onClose={() => setSelectedEventIdForDrawer(null)}
      />

      <EventImportModal
        isOpen={isImportModalOpen}
        onClose={() => setIsImportModalOpen(false)}
      />

      <ScraperRunModal
        isOpen={isScraperModalOpen}
        onClose={() => setIsScraperModalOpen(false)}
      />
    </div>
  );
}
