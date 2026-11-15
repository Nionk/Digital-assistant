import * as React from "react";
import { toast } from "sonner";
import { Building2, UserCheck, Compass, PanelLeftOpen, Search } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { useShallow } from "zustand/react/shallow";
import {
  useManagerDashboard,
  useManagerEventsCatalog,
  useMatchClientMutation,
  usePublicShowcase,
  usePublishSelectionMutation,
} from "@/api/queries";
import {
  computeClientFinancialSummary,
  useManagerStore,
} from "@/store/useManagerStore";
import { copyTextToClipboard } from "@/lib/clipboard";
import { pluralizeRu } from "@/lib/formatters";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { ManagerHeader } from "./ManagerHeader";
import { NotesAndProfileSection } from "./NotesAndProfileSection";
import { BundleConstructorSection } from "./BundleConstructorSection";
import { FinancialAndPitchPanel } from "./FinancialAndPitchPanel";
import { PublishedShowcaseMonitor } from "./PublishedShowcaseMonitor";
import { EventsCatalogView } from "./EventsCatalogView";
import { EventDetailsDrawer } from "./EventDetailsDrawer";

export function ManagerWorkspacePage() {
  const { data: dashboard, isLoading: isDashboardLoading } =
    useManagerDashboard();

  const workspaceMode = useManagerStore((s) => s.workspaceMode);
  const selectedClientId = useManagerStore((s) => s.selectedClientId);
  const clientSearchQuery = useManagerStore((s) => s.clientSearchQuery);
  const isNotesCollapsed = useManagerStore((s) => s.isNotesCollapsed);
  const activeNotesOverride = useManagerStore((s) =>
    s.selectedClientId !== null ? s.notesByClient[s.selectedClientId] : undefined
  );
  const activeMatchResult = useManagerStore((s) =>
    s.selectedClientId !== null
      ? s.matchResultByClient[s.selectedClientId]
      : undefined
  );
  const activeEditableProfile = useManagerStore((s) =>
    s.selectedClientId !== null
      ? s.editableProfileByClient[s.selectedClientId]
      : undefined
  );
  const activeVariantGroup = useManagerStore((s) =>
    s.selectedClientId !== null
      ? (s.selectedVariantGroupByClient[s.selectedClientId] ?? 1)
      : 1
  );
  const activeIncludedEvents = useManagerStore((s) =>
    s.selectedClientId !== null
      ? s.includedEventsByClient[s.selectedClientId]
      : undefined
  );
  const activeSelectedTariffs = useManagerStore((s) =>
    s.selectedClientId !== null
      ? s.selectedTariffByClient[s.selectedClientId]
      : undefined
  );
  const activeCustomRationales = useManagerStore((s) =>
    s.selectedClientId !== null
      ? s.customRationaleByClient[s.selectedClientId]
      : undefined
  );
  const activePitchTextOverride = useManagerStore((s) =>
    s.selectedClientId !== null
      ? s.pitchTextByClient[s.selectedClientId]
      : undefined
  );
  const activePublishedInfo = useManagerStore((s) =>
    s.selectedClientId !== null
      ? s.publishedInfoByClient[s.selectedClientId]
      : undefined
  );
  const draftClientIds = useManagerStore(
    useShallow((s) => Object.keys(s.matchResultByClient).map(Number))
  );
  const publishedClientIds = useManagerStore(
    useShallow((s) => Object.keys(s.publishedInfoByClient).map(Number))
  );

  const setWorkspaceMode = useManagerStore((s) => s.setWorkspaceMode);
  const selectClient = useManagerStore((s) => s.selectClient);
  const setClientSearchQuery = useManagerStore((s) => s.setClientSearchQuery);
  const setClientNotes = useManagerStore((s) => s.setClientNotes);
  const setNotesCollapsed = useManagerStore((s) => s.setNotesCollapsed);
  const hydrateMatchResponse = useManagerStore((s) => s.hydrateMatchResponse);
  const updateEditableProfile = useManagerStore((s) => s.updateEditableProfile);
  const selectVariantGroup = useManagerStore((s) => s.selectVariantGroup);
  const toggleEventIncluded = useManagerStore((s) => s.toggleEventIncluded);
  const changeEventTariff = useManagerStore((s) => s.changeEventTariff);
  const updateEventRationale = useManagerStore((s) => s.updateEventRationale);
  const setPitchText = useManagerStore((s) => s.setPitchText);
  const syncPitchNumbersWithPackage = useManagerStore(
    (s) => s.syncPitchNumbersWithPackage
  );
  const setPublishedInfo = useManagerStore((s) => s.setPublishedInfo);
  const hydratePublishedShowcase = useManagerStore(
    (s) => s.hydratePublishedShowcase
  );

  const [isClientsDropdownOpen, setIsClientsDropdownOpen] = React.useState(false);
  const [selectedEventIdForDrawer, setSelectedEventIdForDrawer] =
    React.useState<number | null>(null);
  const clientDropdownRef = React.useRef<HTMLDivElement>(null);

  const { data: catalogData } = useManagerEventsCatalog(
    Boolean(activeMatchResult) || selectedEventIdForDrawer !== null
  );

  const matchMutation = useMatchClientMutation();
  const publishMutation = usePublishSelectionMutation();

  const clients = dashboard?.clients || [];
  const burningDeadlines = dashboard?.burning_deadlines || [];

  const selectedCatalogEventForDrawer = React.useMemo(() => {
    if (selectedEventIdForDrawer === null || !catalogData?.events) return null;
    return (
      catalogData.events.find(
        (ev) => ev.event_id === selectedEventIdForDrawer
      ) || null
    );
  }, [selectedEventIdForDrawer, catalogData?.events]);

  const handleToggleClientsDropdown = () => {
    setIsClientsDropdownOpen((prev) => !prev);
  };

  React.useEffect(() => {
    if (!isClientsDropdownOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (clientDropdownRef.current && !clientDropdownRef.current.contains(e.target as Node)) {
        setIsClientsDropdownOpen(false);
      }
    };
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIsClientsDropdownOpen(false);
    };
    document.addEventListener("mousedown", handleClickOutside);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isClientsDropdownOpen]);

  const filteredClients = React.useMemo(() => {
    const q = clientSearchQuery.trim().toLowerCase();
    if (!q) return clients;
    return clients.filter(
      (c) =>
        c.company_name.toLowerCase().includes(q) ||
        (c.contact_person || "").toLowerCase().includes(q)
    );
  }, [clients, clientSearchQuery]);

  // Автовыбор первого клиента при загрузке дашборда
  React.useEffect(() => {
    if (selectedClientId === null && clients.length > 0) {
      const first = clients[0];
      selectClient(first.id, first.raw_manager_notes);
    }
  }, [clients, selectedClientId, selectClient]);

  const activeClient =
    clients.find((c) => c.id === selectedClientId) || null;
  const activeClientId = activeClient?.id ?? null;

  const currentNotes = activeClient
    ? (activeNotesOverride ?? activeClient.raw_manager_notes)
    : "";

  const activePitchText = activeClient
    ? (activePitchTextOverride ??
      activeMatchResult?.generated_pitch_text ??
      "")
    : "";

  const computedSummary = React.useMemo(
    () =>
      activeClientId !== null
        ? computeClientFinancialSummary(useManagerStore.getState(), activeClientId)
        : null,
    [
      activeClientId,
      activeMatchResult,
      activeVariantGroup,
      activeIncludedEvents,
      activeSelectedTariffs,
      activeCustomRationales,
      activeEditableProfile,
    ]
  );

  // Токен опубликованной витрины (из текущей сессии или из БД)
  const activeMagicToken = activeClient
    ? activePublishedInfo?.magicToken || activeClient.magic_token
    : null;

  const activePublishedUrl = activeMagicToken
    ? `/s/${activeMagicToken}`
    : null;

  // Однократная гидратация selectionId, сумм и позиций для опубликованной витрины (переживает F5 без лишнего поллинга /public/s)
  const { data: hydratedShowcase } = usePublicShowcase(activeMagicToken, 0);

  React.useEffect(() => {
    if (!activeClient || !activeMagicToken || !hydratedShowcase) return;
    if (
      activePublishedInfo?.magicToken === activeMagicToken &&
      activePublishedInfo.selectionId === hydratedShowcase.selection_id &&
      activePublishedInfo.totalPrice === hydratedShowcase.total_actual_price &&
      activePublishedInfo.totalSavings === hydratedShowcase.total_savings
    ) {
      return;
    }
    hydratePublishedShowcase(activeClient.id, activeMagicToken, hydratedShowcase);
  }, [
    activeClient,
    activeMagicToken,
    hydratedShowcase,
    activePublishedInfo,
    hydratePublishedShowcase,
  ]);

  const activeSelectionId = React.useMemo(() => {
    if (!activeClient || !activeMagicToken) return null;
    if (
      activePublishedInfo?.magicToken === activeMagicToken &&
      activePublishedInfo.selectionId != null
    ) {
      return activePublishedInfo.selectionId;
    }
    if (hydratedShowcase?.selection_id != null) {
      return hydratedShowcase.selection_id;
    }
    if (activeClient.magic_token === activeMagicToken) {
      return activeClient.latest_selection_id ?? null;
    }
    return null;
  }, [activeClient, activeMagicToken, activePublishedInfo, hydratedShowcase]);

  const activePublishedSummary = React.useMemo(() => {
    if (!activeMagicToken) return null;
    if (activePublishedInfo?.magicToken === activeMagicToken) {
      return {
        totalPrice:
          hydratedShowcase?.total_actual_price ?? activePublishedInfo.totalPrice,
        totalSavings:
          hydratedShowcase?.total_savings ?? activePublishedInfo.totalSavings,
        totalEventsCount: hydratedShowcase?.items.length,
      };
    }
    if (hydratedShowcase) {
      return {
        totalPrice: hydratedShowcase.total_actual_price,
        totalSavings: hydratedShowcase.total_savings,
        totalEventsCount: hydratedShowcase.items.length,
      };
    }
    return null;
  }, [activeMagicToken, activePublishedInfo, hydratedShowcase]);

  const draftClientIdSet = React.useMemo(
    () => new Set(draftClientIds),
    [draftClientIds]
  );
  const publishedClientIdSet = React.useMemo(
    () => new Set(publishedClientIds),
    [publishedClientIds]
  );

  const handleRunInitialMatch = async () => {
    if (!activeClient) return;
    if (currentNotes.trim().length < 10) {
      toast.error("Введите более подробный конспект встречи (минимум 10 символов)");
      return;
    }
    try {
      const res = await matchMutation.mutateAsync({
        clientId: activeClient.id,
        payload: {
          raw_manager_notes: currentNotes,
          override_profile: null,
        },
      });
      hydrateMatchResponse(activeClient.id, res);
      if (res.bundle_variants.length === 0 && res.bonus_on_request_items.length === 0) {
        toast.warning(
          "По заданным критериям не найдено подходящих мероприятий в базе знаний агентства."
        );
      } else {
        toast.success(
          `Сформировано вариантов: ${res.bundle_variants.length}. Календарь сверен без пересечений.`
        );
      }
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Не удалось выполнить подбор мероприятий"
      );
    }
  };

  const handleRematchWithOverride = async () => {
    if (!activeClient || !activeEditableProfile) return;
    if (
      activeEditableProfile.total_budget_max !== null &&
      activeEditableProfile.total_budget_max <= 0
    ) {
      toast.error("Максимальный бюджет должен быть больше нуля");
      return;
    }
    if (
      activeEditableProfile.date_from &&
      activeEditableProfile.date_to &&
      activeEditableProfile.date_to < activeEditableProfile.date_from
    ) {
      toast.error("Дата окончания периода не может быть раньше даты начала");
      return;
    }
    try {
      const res = await matchMutation.mutateAsync({
        clientId: activeClient.id,
        payload: {
          raw_manager_notes:
            currentNotes.trim().length >= 10
              ? currentNotes
              : activeClient.raw_manager_notes,
          override_profile: activeEditableProfile,
        },
      });
      hydrateMatchResponse(activeClient.id, res);
      toast.success("Пакеты пересобраны по обновленным параметрам");
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Ошибка при пересборке пакетов"
      );
    }
  };

  const handleSelectVariantGroup = (group: number) => {
    if (!activeClient) return;
    selectVariantGroup(activeClient.id, group);
    // Сразу синхронизируем цифры в письме при переключении вкладки Варианта 1 / Варианта 2
    syncPitchNumbersWithPackage(activeClient.id, activeClient.company_name);
  };

  const handleSyncPitch = () => {
    if (!activeClient) return;
    syncPitchNumbersWithPackage(activeClient.id, activeClient.company_name);
    toast.success("Цифры бюджета, выгоды и список площадок в письме обновлены");
  };

  const handleCopyShowcaseLink = async (relativeUrl: string): Promise<boolean> => {
    const fullUrl = `${window.location.origin}${relativeUrl}`;
    return copyTextToClipboard(fullUrl, {
      successMessage: "Персональная ссылка скопирована в буфер обмена",
    });
  };

  const handlePublishSelection = async () => {
    if (!activeClient || !activeMatchResult || !computedSummary) return;
    if (computedSummary.finalItemsPayload.length === 0) {
      toast.error("Выберите хотя бы одно мероприятие для публикации витрины");
      return;
    }

    try {
      const res = await publishMutation.mutateAsync({
        selectionId: activeMatchResult.selection_id,
        payload: {
          selected_bundle_group: activeVariantGroup,
          final_items: computedSummary.finalItemsPayload,
          final_pitch_text: activePitchText,
        },
      });

      setPublishedInfo(activeClient.id, {
        selectionId: activeMatchResult.selection_id,
        magicToken: res.magic_token,
        publicUrl: res.public_showcase_url,
        totalPrice: res.total_package_price,
        totalSavings: res.total_package_savings,
      });

      const fullUrl = `${window.location.origin}${res.public_showcase_url}`;
      const copied = await copyTextToClipboard(fullUrl, {
        successMessage:
          "Персональная витрина клиента опубликована! Ссылка скопирована в буфер обмена.",
        errorMessage:
          "Витрина опубликована, но скопировать ссылку автоматически не удалось.",
      });
      if (!copied) {
        toast.success("Персональная витрина клиента опубликована!");
      }
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Ошибка при публикации витрины"
      );
    }
  };

  return (
    <div className="flex min-h-screen flex-col bg-[#0B0E12] text-[#F3F4F6]">
      {/* Верхняя панель (67px) */}
      <ManagerHeader
        workspaceMode={workspaceMode}
        onModeChange={setWorkspaceMode}
        burningDeadlines={burningDeadlines}
      />

      {workspaceMode === "catalog" ? (
        <main className="flex-1 overflow-y-auto scrollbar-thin">
          <EventsCatalogView />
        </main>
      ) : (
        <div className="relative flex flex-1 overflow-hidden">
          {/* Основная рабочая область менеджера на всю ширину */}
          <main className="flex-1 overflow-y-auto p-4 lg:p-5 scrollbar-thin">
            <div className="mx-auto max-w-[1440px] space-y-4">
              {/* Верхняя строка под хедером: кнопка «Список клиентов» строго под логотипом */}
              <div className="flex items-center justify-between gap-3">
                <div className="relative inline-block" ref={clientDropdownRef}>
                  <button
                    type="button"
                    onClick={handleToggleClientsDropdown}
                    className={cn(
                      "group relative flex items-center gap-2 rounded-[8px] border bg-[#12161A] px-3.5 py-1.5 text-xs font-medium select-none cursor-pointer shadow-sm transition-colors duration-150 outline-none",
                      isClientsDropdownOpen
                        ? "border-[#E5C378] bg-[#1A2128] text-white shadow-[0_0_10px_rgba(229,195,120,0.25)]"
                        : "border-[#262D35] text-[#D1D5DB] hover:border-[#E5C378] hover:bg-[#1A2128] hover:text-white"
                    )}
                    title="Выбрать компанию клиента"
                  >
                    <PanelLeftOpen className="h-4 w-4 shrink-0 transition-colors duration-150 text-inherit group-hover:text-[#E5C378]" strokeWidth={1.75} />
                    <span className="transition-colors duration-150">Список клиентов</span>
                    <span
                      className={cn(
                        "rounded bg-[#1A252A] px-1.5 py-0.5 text-[10px] font-semibold text-[#529E85] tabular-nums transition-colors duration-150",
                        "group-hover:bg-[#1E252E] group-hover:text-[#34D399]"
                      )}
                    >
                      {clients.length}
                    </span>

                    {/* Золотая светящаяся линия подчеркивания в открытом/активном состоянии */}
                    {isClientsDropdownOpen && (
                      <span className="absolute bottom-0 left-0 right-0 h-[2.5px] rounded-b-[8px] bg-gradient-to-r from-[#D4AF37] via-[#E5C378] to-[#D4AF37] shadow-[0_0_10px_rgba(229,195,120,0.75)]" />
                    )}
                  </button>

                  {/* Выпадающее меню в стиле Early Bird Popover с плавной анимацией */}
                  <AnimatePresence>
                    {isClientsDropdownOpen && (
                      <motion.div
                        initial={{ opacity: 0, y: -6, scale: 0.98 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        exit={{ opacity: 0, y: -4, scale: 0.98 }}
                        transition={{ duration: 0.18, ease: "easeOut" }}
                        className="absolute left-0 mt-2 w-[340px] sm:w-[440px] rounded-[12px] border border-[#262B33] bg-[#0E1116] p-4 sm:p-5 shadow-2xl shadow-black/80 z-50 text-white select-none"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <h3 className="text-[11px] font-serif italic font-semibold text-[#8E95A0]">
                              Выбор клиента
                            </h3>
                            <p className="mt-1 text-xs text-[#727985]">
                              Активные компании и согласование пакетов
                            </p>
                          </div>
                          <Badge variant="ebAmber" className="text-[11px]">
                            {clients.length}{" "}
                            {pluralizeRu(clients.length, [
                              "компания",
                              "компании",
                              "компаний",
                            ])}
                          </Badge>
                        </div>

                        <div className="border-b border-[#21262F] my-3.5" />

                        {/* Выразительный поиск компании с увеличенной высотой */}
                        <div className="relative mb-3.5">
                          <Search
                            className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-[#E5C378]"
                            strokeWidth={2}
                          />
                          <input
                            type="text"
                            value={clientSearchQuery}
                            onChange={(e) => setClientSearchQuery(e.target.value)}
                            placeholder="Поиск компании или контакта..."
                            className="h-10 w-full rounded-[8px] border border-[#38414F] bg-[#161B21] pl-10 pr-3.5 text-sm text-white placeholder:text-[#8E95A0] shadow-inner transition-colors duration-150 ease-out hover:border-[#4B5565] [color-scheme:dark] outline-none focus:outline-none focus-visible:outline-none active:outline-none focus:border-[#E5C378] focus:bg-[#1A2027] focus:shadow-[0_0_0_1px_rgba(229,195,120,0.25)]"
                          />
                        </div>

                        {/* Список карточек клиентов в ячейках #1A1E24 */}
                        {filteredClients.length === 0 ? (
                          <p className="py-6 text-center text-xs text-[#8E95A0]">
                            Компании не найдены
                          </p>
                        ) : (
                          <div className="max-h-[360px] space-y-2.5 overflow-y-auto pr-1 scrollbar-thin">
                            {filteredClients.map((client) => {
                              const isSelected = client.id === selectedClientId;
                              const isPublished =
                                publishedClientIdSet.has(client.id) ||
                                client.latest_selection_status === "published";
                              const isDraft =
                                !isPublished &&
                                (draftClientIdSet.has(client.id) ||
                                  client.latest_selection_status === "draft");

                              return (
                                <div
                                  key={client.id}
                                  onClick={() => {
                                    selectClient(client.id, client.raw_manager_notes);
                                    setIsClientsDropdownOpen(false);
                                  }}
                                  className={cn(
                                    "rounded-[8px] border p-3 transition-colors cursor-pointer select-none",
                                    isSelected
                                      ? "border-[#E5C378] bg-[#1E252E] shadow-sm"
                                      : "border-[#262C35] bg-[#1A1E24] hover:border-[#38414F] hover:bg-[#1E232B]"
                                  )}
                                >
                                  <div className="flex items-start justify-between gap-3">
                                    <div className="min-w-0 flex items-center gap-2">
                                      <Building2
                                        className={cn(
                                          "h-4 w-4 shrink-0",
                                          isSelected ? "text-[#E5C378]" : "text-[#8E95A0]"
                                        )}
                                        strokeWidth={1.75}
                                      />
                                      <p
                                        className={cn(
                                          "truncate text-[13px] font-medium leading-snug",
                                          isSelected ? "text-white font-semibold" : "text-[#F3F4F6]"
                                        )}
                                      >
                                        {client.company_name}
                                      </p>
                                    </div>

                                    {/* Авторские скошенные ячейки-ленты статусов клиента */}
                                    {isPublished ? (
                                      <Badge variant="ebEmerald" className="text-[10px]">
                                        КП активно
                                      </Badge>
                                    ) : isDraft ? (
                                      <Badge variant="ebAmber" className="text-[10px]">
                                        Черновик
                                      </Badge>
                                    ) : (
                                      <Badge variant="ebBlue" className="text-[10px]">
                                        Новый
                                      </Badge>
                                    )}
                                  </div>

                                  <div className="mt-2.5 flex items-center justify-between text-xs text-[#8E95A0] tabular-nums">
                                    <span className="inline-flex items-center gap-1.5 truncate">
                                      {client.contact_person ? (
                                        <>
                                          <UserCheck className="h-3.5 w-3.5 text-[#8E95A0] shrink-0" strokeWidth={1.5} />
                                          <span className="truncate">{client.contact_person}</span>
                                        </>
                                      ) : (
                                        <span className="text-[#636B78]">Контакт не указан</span>
                                      )}
                                    </span>
                                    {isSelected && (
                                      <Badge variant="ebGold" className="text-[9px]">
                                        Выбран
                                      </Badge>
                                    )}
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              </div>

              {isDashboardLoading ? (
                <div className="flex h-64 items-center justify-center rounded-[12px] border border-[#262D35] bg-[#161B22] text-sm text-[#8E95A0]">
                  Загрузка рабочего пространства менеджера...
                </div>
              ) : !activeClient ? (
                <div className="flex h-64 flex-col items-center justify-center gap-3 rounded-[12px] border border-[#262D35] bg-[#161B22] p-6 text-center shadow-card">
                  <p className="text-sm font-medium text-white">
                    Клиент не выбран
                  </p>
                  <button
                    type="button"
                    onClick={handleToggleClientsDropdown}
                    className="inline-flex items-center gap-2 rounded-[8px] border border-[#262D35] bg-[#12161A] px-4 py-2 text-xs font-semibold text-white transition-all duration-150 hover:border-[#E5C378] hover:bg-[#1A2128] hover:text-[#E5C378] hover:shadow-[0_0_10px_rgba(229,195,120,0.2)]"
                  >
                    <PanelLeftOpen className="h-4 w-4" />
                    <span>Выбрать компанию из списка</span>
                  </button>
                </div>
              ) : (
                <AnimatePresence mode="wait">
                  <motion.div
                    key={activeClient.id}
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -6 }}
                    transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
                    className="space-y-4"
                  >
                    {/* Компактная шапка активного клиента (без иконки здания, разделение названия и контакта) */}
                    <div className="flex flex-wrap items-center justify-between gap-3 rounded-[12px] border border-[#262D35] bg-[#161B22] px-5 py-3.5 shadow-sm">
                      <div className="flex flex-wrap items-center gap-3">
                        <h1 className="text-base sm:text-lg font-semibold tracking-tight text-white">
                          {activeClient.company_name}
                        </h1>
                        {activeClient.contact_person && (
                          <>
                            <div className="hidden h-4 w-[1px] bg-[#2D3540] sm:block" />
                            <span className="text-xs font-normal text-[#8E95A0]">
                              {activeClient.contact_person}
                            </span>
                          </>
                        )}
                      </div>
                    </div>

                    {/* Живой мониторинг опубликованной витрины (если у клиента уже выпущена ссылка) */}
                    {activeMagicToken && (
                      <PublishedShowcaseMonitor
                        selectionId={activeSelectionId}
                        magicToken={activeMagicToken}
                        publishedSummary={activePublishedSummary}
                        showcaseItems={hydratedShowcase?.items}
                        onCopyLink={handleCopyShowcaseLink}
                      />
                    )}

                    {/* Асимметричная двухколоночная сетка без вертикальной простыни */}
                    <div className="grid grid-cols-1 gap-4 xl:grid-cols-12 items-start">
                      {/* Левая/Центральная колонка конструктора (7 из 12 = ~58-60%) */}
                      <div className="space-y-4 xl:col-span-8">
                        <NotesAndProfileSection
                          notes={currentNotes}
                          onNotesChange={(val) =>
                            setClientNotes(activeClient.id, val)
                          }
                          isCollapsed={isNotesCollapsed}
                          onToggleCollapsed={setNotesCollapsed}
                          isMatching={matchMutation.isPending}
                          hasMatchResult={Boolean(activeMatchResult)}
                          editableProfile={activeEditableProfile}
                          onUpdateProfile={(updater) =>
                            updateEditableProfile(activeClient.id, updater)
                          }
                          onRunInitialMatch={handleRunInitialMatch}
                          onRematchWithOverride={handleRematchWithOverride}
                        />

                        <AnimatePresence mode="wait">
                          {activeMatchResult && computedSummary ? (
                            <motion.div
                              key={`bundle-section-${activeMatchResult.selection_id}`}
                              initial={{ opacity: 0, y: 8 }}
                              animate={{ opacity: 1, y: 0 }}
                              exit={{ opacity: 0, y: -8 }}
                              transition={{ duration: 0.24, ease: "easeOut" }}
                            >
                              <BundleConstructorSection
                                variants={activeMatchResult.bundle_variants}
                                selectedVariantGroup={activeVariantGroup}
                                onSelectVariantGroup={handleSelectVariantGroup}
                                summary={computedSummary}
                                onToggleEventIncluded={(evId) =>
                                  toggleEventIncluded(activeClient.id, evId)
                                }
                                onChangeEventTariff={(evId, tarId) =>
                                  changeEventTariff(activeClient.id, evId, tarId)
                                }
                                onUpdateEventRationale={(evId, text) =>
                                  updateEventRationale(activeClient.id, evId, text)
                                }
                                onOpenEventDetails={(evId) =>
                                  setSelectedEventIdForDrawer(evId)
                                }
                              />
                            </motion.div>
                          ) : (
                            !matchMutation.isPending && (
                              <motion.div
                                key="bundle-empty"
                                initial={{ opacity: 0 }}
                                animate={{ opacity: 1 }}
                                exit={{ opacity: 0 }}
                                transition={{ duration: 0.2 }}
                                className="rounded-[12px] border border-[#21262F] bg-[#0E1116] p-8 text-center shadow-sm"
                              >
                                <Compass
                                  className="mx-auto h-9 w-9 text-[#E5C378]"
                                  strokeWidth={1.5}
                                />
                                <h3 className="mt-3 font-serif italic text-sm font-semibold text-[#E5C378]">
                                  Готово к формированию пакетов участия
                                </h3>
                                <p className="mx-auto mt-1.5 max-w-lg text-xs leading-relaxed text-[#8E95A0]">
                                  Проверьте конспект установочной встречи выше и нажмите{" "}
                                  <strong className="font-semibold text-white">
                                    «Подобрать варианты пакетов»
                                  </strong>
                                  . Система извлечет критерии отбора, сверит календарь без накладок и сформирует 2 пакета с расчетом выгоды Early Bird.
                                </p>
                              </motion.div>
                            )
                          )}
                        </AnimatePresence>
                      </div>

                      {/* Правая закрепленная колонка итога и публикации (4 из 12 = ~33-38%, sticky) */}
                      <div className="xl:col-span-4">
                        <AnimatePresence mode="wait">
                          {activeMatchResult && computedSummary ? (
                            <motion.div
                              key={`pitch-panel-${activeMatchResult.selection_id}`}
                              initial={{ opacity: 0, y: 8 }}
                              animate={{ opacity: 1, y: 0 }}
                              exit={{ opacity: 0, y: -8 }}
                              transition={{ duration: 0.24, ease: "easeOut" }}
                            >
                              <FinancialAndPitchPanel
                                companyName={activeClient.company_name}
                                summary={computedSummary}
                                pitchText={activePitchText}
                                onPitchChange={(text) =>
                                  setPitchText(activeClient.id, text)
                                }
                                onSyncPitchNumbers={handleSyncPitch}
                                onPublish={handlePublishSelection}
                                isPublishing={publishMutation.isPending}
                                publishedUrl={activePublishedUrl}
                                onCopyLink={handleCopyShowcaseLink}
                              />
                            </motion.div>
                          ) : (
                            <motion.div
                              key="pitch-empty"
                              initial={{ opacity: 0 }}
                              animate={{ opacity: 1 }}
                              exit={{ opacity: 0 }}
                              transition={{ duration: 0.2 }}
                              className="rounded-[12px] border border-[#21262F] bg-[#0E1116] p-5 shadow-sm"
                            >
                              <span className="font-serif italic font-semibold text-xs tracking-wide text-[#E5C378]">
                                Сводка и публикация КП
                              </span>
                              <h3 className="mt-1 font-serif italic text-sm font-semibold text-white">
                                Ожидание расчёта подборки
                              </h3>
                              <p className="mt-1.5 font-serif italic text-xs leading-relaxed text-white/90">
                                После запуска подбора здесь появится финансовая сводка пакета (внешние взносы организаторов и выгода Early Bird), редактор персонального письма и выпуск ссылки на витрину клиента.
                              </p>
                            </motion.div>
                          )}
                        </AnimatePresence>
                      </div>
                    </div>
                  </motion.div>
                </AnimatePresence>
              )}
            </div>
          </main>

          {/* Выдвижная шторка детального просмотра площадки прямо из конструктора пакета */}
          <EventDetailsDrawer
            event={selectedCatalogEventForDrawer}
            isOpen={Boolean(selectedCatalogEventForDrawer)}
            onClose={() => setSelectedEventIdForDrawer(null)}
          />
        </div>
      )}
    </div>
  );
}
