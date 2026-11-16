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
  getTodayIsoDate,
  isPastEvent,
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
  const [selectedRole, setSelectedRole] = React.useState<string>("all");
  const [selectedCities, setSelectedCities] = React.useState<string[]>([]);
  const [selectedThemes, setSelectedThemes] = React.useState<string[]>([]);
  const [selectedDataStatus, setSelectedDataStatus] = React.useState<string>("all");
  const [dateFrom, setDateFrom] = React.useState<string>("");
  const [dateTo, setDateTo] = React.useState<string>("");
  const [sortBy, setSortBy] = React.useState<string>("date_asc");
  const [onlyEarlyBird, setOnlyEarlyBird] = React.useState<boolean>(false);
  const [onlyUpcoming, setOnlyUpcoming] = React.useState<boolean>(false);
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

  const todayIso = getTodayIsoDate();

  const earlyBirdCount = React.useMemo(
    () => events.filter((e) => e.tariffs.some((t) => t.savings > 0)).length,
    [events]
  );

  const upcomingCount = React.useMemo(
    () => events.filter((e) => !isPastEvent(e, todayIso)).length,
    [events, todayIso]
  );

  const roleCounts = React.useMemo(() => {
    const counts: Record<string, number> = {
      speaker: 0,
      delegate: 0,
      sponsor: 0,
    };
    for (const ev of events) {
      const roles = new Set(ev.tariffs.map((t) => t.participation_role));
      for (const r of roles) {
        counts[r] = (counts[r] ?? 0) + 1;
      }
    }
    return counts;
  }, [events]);

  const baseFilteredEvents = React.useMemo(
    () =>
      filterAndSortCatalogEvents(events, {
        selectedFormat,
        selectedRole,
        selectedCities,
        selectedThemes,
        onlyEarlyBird,
        onlyUpcoming: false,
        searchQuery,
        sortBy,
        todayIso,
      }),
    [
      events,
      selectedFormat,
      selectedRole,
      selectedCities,
      selectedThemes,
      onlyEarlyBird,
      searchQuery,
      sortBy,
      todayIso,
    ]
  );

  const hiddenPastCount = React.useMemo(
    () =>
      onlyUpcoming
        ? baseFilteredEvents.filter((e) => isPastEvent(e, todayIso)).length
        : 0,
    [baseFilteredEvents, onlyUpcoming, todayIso]
  );

  const filteredEvents = React.useMemo(
    () =>
      onlyUpcoming
        ? baseFilteredEvents.filter((e) => !isPastEvent(e, todayIso))
        : baseFilteredEvents,
    [baseFilteredEvents, onlyUpcoming, todayIso]
  );

  const hasActiveFilters =
    searchQuery.trim().length > 0 ||
    selectedFormat !== "all" ||
    selectedRole !== "all" ||
    selectedCities.length > 0 ||
    selectedThemes.length > 0 ||
    selectedDataStatus !== "all" ||
    Boolean(dateFrom) ||
    Boolean(dateTo) ||
    onlyEarlyBird ||
    onlyUpcoming;

  const handleResetFilters = () => {
    setSearchQuery("");
    setSelectedFormat("all");
    setSelectedRole("all");
    setSelectedCities([]);
    setSelectedThemes([]);
    setSelectedDataStatus("all");
    setDateFrom("");
    setDateTo("");
    setSortBy("date_asc");
    setOnlyEarlyBird(false);
    setOnlyUpcoming(false);
  };

  return (
    <div className="mx-auto max-w-[1440px] p-4 lg:p-5 space-y-3.5">
      <CatalogHeaderAndFilters
        totalCount={events.length}
        filteredCount={filteredEvents.length}
        earlyBirdCount={earlyBirdCount}
        upcomingCount={upcomingCount}
        hiddenPastCount={hiddenPastCount}
        roleCounts={roleCounts}
        searchQuery={searchQuery}
        onSearchQueryChange={setSearchQuery}
        selectedFormat={selectedFormat}
        onFormatChange={setSelectedFormat}
        selectedRole={selectedRole}
        onRoleChange={setSelectedRole}
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
        onlyUpcoming={onlyUpcoming}
        onToggleUpcoming={() => setOnlyUpcoming((prev) => !prev)}
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
            {onlyUpcoming && hiddenPastCount > 0
              ? "Предстоящих мероприятий по заданным фильтрам нет"
              : "Мероприятия по заданным фильтрам не найдены"}
          </h3>
          <p className="mx-auto mt-1.5 max-w-md text-xs leading-relaxed text-[#8E95A0]">
            {onlyUpcoming && hiddenPastCount > 0
              ? `В архиве найдено прошедших площадок: ${hiddenPastCount}. Вы можете показать их в 1 клик или сбросить все фильтры.`
              : "Попробуйте смягчить критерии поиска (сбросить тему, формат, роль или отключить фильтр Early Bird)"}
          </p>
          <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
            {onlyUpcoming && hiddenPastCount > 0 && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setOnlyUpcoming(false)}
                className="cursor-pointer border-[#7C5A20]/60 bg-[#1E190E] text-xs text-[#E5C378] hover:border-[#E5C378] hover:bg-[#261E0F] hover:text-white"
              >
                <span>Показать прошедшие ({hiddenPastCount})</span>
              </Button>
            )}
            <Button
              type="button"
              variant="monolith"
              size="sm"
              onClick={handleResetFilters}
              className="cursor-pointer"
            >
              <RotateCcw className="h-3.5 w-3.5 text-[#E5C378] monolith-icon" strokeWidth={1.75} />
              <span>Сбросить все фильтры</span>
            </Button>
          </div>
        </div>
      ) : (
        <>
          <AnimatePresence mode="wait" initial={false}>
            {viewMode === "table" ? (
              <CatalogTable
                key="catalog-table"
                events={filteredEvents}
                todayIso={todayIso}
                selectedEventId={selectedEventForDrawer?.event_id ?? null}
                copiedEventId={copiedEventId}
                onSelectEvent={setSelectedEventIdForDrawer}
                onCopyLocation={handleCopyLocation}
              />
            ) : (
              <CatalogCardsGrid
                key="catalog-cards"
                events={filteredEvents}
                todayIso={todayIso}
                selectedEventId={selectedEventForDrawer?.event_id ?? null}
                copiedEventId={copiedEventId}
                onSelectEvent={setSelectedEventIdForDrawer}
                onCopyLocation={handleCopyLocation}
              />
            )}
          </AnimatePresence>

          {onlyUpcoming && hiddenPastCount > 0 && (
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-[8px] border border-[#21262F] bg-[#12161A] px-3.5 py-2 text-xs text-[#8E95A0]">
              <span className="font-serif italic">
                Скрыто прошедших мероприятий:{" "}
                <strong className="font-sans not-italic font-semibold text-white tabular-nums">
                  {hiddenPastCount}
                </strong>
              </span>
              <button
                type="button"
                onClick={() => setOnlyUpcoming(false)}
                className="inline-flex items-center gap-1 rounded-[4px] border border-[#7C5A20]/50 bg-[#1E190E] px-2.5 py-1 text-[11px] font-medium text-[#E5C378] hover:border-[#E5C378] hover:bg-[#261E0F] hover:text-white transition-colors cursor-pointer"
              >
                Показать весь архив ({hiddenPastCount})
              </button>
            </div>
          )}
        </>
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
