import * as React from "react";
import { toast } from "sonner";
import { motion } from "framer-motion";
import { useShallow } from "zustand/react/shallow";
import {
  useClientWorkspace,
  useGenerateSelectionPitchMutation,
  useManagerDashboard,
  useManagerEventsCatalog,
  useMatchClientMutation,
  usePublicShowcase,
  usePublishSelectionMutation,
} from "@/api/queries";
import type { ClientSummaryOut } from "@/api/types";
import {
  computeClientFinancialSummary,
  useManagerStore,
} from "@/store/useManagerStore";
import { copyTextToClipboard } from "@/lib/clipboard";
import { ManagerHeader } from "./ManagerHeader";
import { NotesAndProfileSection } from "./NotesAndProfileSection";
import { BundleConstructorSection } from "./BundleConstructorSection";
import { FinancialAndPitchPanel } from "./FinancialAndPitchPanel";
import { PublishedShowcaseMonitor } from "./PublishedShowcaseMonitor";
import { EventsCatalogView } from "./EventsCatalogView";
import { EventDetailsDrawer } from "./EventDetailsDrawer";
import { ClientsSelectorDropdown } from "./workspace/ClientsSelectorDropdown";
import { ClientFormModal } from "./workspace/ClientFormModal";
import {
  ActiveClientHeader,
  BundleOnboardingEmptyState,
  PitchWaitingEmptyState,
  WorkspaceEmptyClientState,
  WorkspaceLoadingState,
} from "./workspace/WorkspaceStates";

export function ManagerWorkspacePage() {
  const { data: dashboard, isLoading: isDashboardLoading } =
    useManagerDashboard();

  const workspaceMode = useManagerStore((s) => s.workspaceMode);
  const selectedClientId = useManagerStore((s) => s.selectedClientId);
  const clientSearchQuery = useManagerStore((s) => s.clientSearchQuery);
  const clientStatusFilter = useManagerStore((s) => s.clientStatusFilter);
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
  const clearSelectedClient = useManagerStore((s) => s.clearSelectedClient);
  const removeClientWorkspace = useManagerStore(
    (s) => s.removeClientWorkspace
  );
  const setClientSearchQuery = useManagerStore((s) => s.setClientSearchQuery);
  const setClientStatusFilter = useManagerStore((s) => s.setClientStatusFilter);
  const setClientNotes = useManagerStore((s) => s.setClientNotes);
  const syncClientNotes = useManagerStore((s) => s.syncClientNotes);
  const setNotesCollapsed = useManagerStore((s) => s.setNotesCollapsed);
  const hydrateMatchResponse = useManagerStore((s) => s.hydrateMatchResponse);
  const hydrateServerWorkspace = useManagerStore(
    (s) => s.hydrateServerWorkspace
  );
  const updateEditableProfile = useManagerStore((s) => s.updateEditableProfile);
  const selectVariantGroup = useManagerStore((s) => s.selectVariantGroup);
  const toggleEventIncluded = useManagerStore((s) => s.toggleEventIncluded);
  const changeEventTariff = useManagerStore((s) => s.changeEventTariff);
  const updateEventRationale = useManagerStore((s) => s.updateEventRationale);
  const setPitchText = useManagerStore((s) => s.setPitchText);
  const setPublishedInfo = useManagerStore((s) => s.setPublishedInfo);
  const hydratePublishedShowcase = useManagerStore(
    (s) => s.hydratePublishedShowcase
  );

  const [isClientsDropdownOpen, setIsClientsDropdownOpen] = React.useState(false);
  const [selectedEventIdForDrawer, setSelectedEventIdForDrawer] =
    React.useState<number | null>(null);
  const [clientModalState, setClientModalState] = React.useState<{
    isOpen: boolean;
    mode: "create" | "edit";
    client: ClientSummaryOut | null;
  }>({ isOpen: false, mode: "create", client: null });

  const { data: catalogData } = useManagerEventsCatalog(
    Boolean(activeMatchResult) || selectedEventIdForDrawer !== null
  );

  const matchMutation = useMatchClientMutation();
  const publishMutation = usePublishSelectionMutation();
  const generatePitchMutation = useGenerateSelectionPitchMutation();

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

  const handleCloseClientsDropdown = React.useCallback(() => {
    setIsClientsDropdownOpen(false);
  }, []);

  // Автовыбор первого клиента и безопасное переключение при архивации/отсутствии выбранного клиента
  React.useEffect(() => {
    if (isDashboardLoading) return;
    if (clients.length === 0) {
      if (selectedClientId !== null) {
        clearSelectedClient();
      }
      return;
    }
    const existsInDashboard =
      selectedClientId !== null &&
      clients.some((c) => c.id === selectedClientId);
    if (!existsInDashboard) {
      const first = clients[0];
      selectClient(first.id, first.raw_manager_notes);
    }
  }, [
    isDashboardLoading,
    clients,
    selectedClientId,
    selectClient,
    clearSelectedClient,
  ]);

  const activeClient =
    clients.find((c) => c.id === selectedClientId) || null;
  const activeClientId = activeClient?.id ?? null;

  const needsWorkspaceSync = React.useMemo(() => {
    if (!activeClient) return false;
    if (!activeMatchResult) return true;
    if (
      activeClient.latest_selection_id != null &&
      activeClient.latest_selection_id > activeMatchResult.selection_id
    ) {
      return true;
    }
    if (
      activeClient.latest_selection_status === "published" &&
      activeClient.latest_selection_id != null &&
      activeClient.latest_selection_id === activeMatchResult.selection_id &&
      activePublishedInfo?.selectionId !== activeClient.latest_selection_id
    ) {
      return true;
    }
    return false;
  }, [activeClient, activeMatchResult, activePublishedInfo]);

  const { data: serverWorkspace, isFetching: isWorkspaceFetching } =
    useClientWorkspace(activeClientId, needsWorkspaceSync);

  React.useEffect(() => {
    if (!activeClient || !serverWorkspace) return;
    if (serverWorkspace.client_id !== activeClient.id) return;
    hydrateServerWorkspace(activeClient.id, serverWorkspace);
  }, [activeClient, serverWorkspace, hydrateServerWorkspace]);

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
  };

  const handleGeneratePitch = async () => {
    if (!activeClient || !activeMatchResult || !computedSummary) return;
    if (computedSummary.finalItemsPayload.length === 0) {
      toast.error("Выберите хотя бы одно мероприятие в конструкторе");
      return;
    }

    try {
      const res = await generatePitchMutation.mutateAsync({
        selectionId: activeMatchResult.selection_id,
        payload: {
          final_items: computedSummary.finalItemsPayload,
          raw_manager_notes: currentNotes.trim() || null,
          total_budget_max:
            computedSummary.budgetMax > 0 ? computedSummary.budgetMax : null,
          include_budget_limit: !(
            activeEditableProfile?.budget_is_assumed ?? false
          ),
        },
      });
      setPitchText(activeClient.id, res.generated_pitch_text);
      if (res.used_llm) {
        toast.success("Сопроводительное письмо обновлено с помощью ИИ");
      } else {
        toast.info(
          "ИИ-шлюз временно недоступен — применён резервный шаблон с актуальными цифрами"
        );
      }
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Не удалось обновить письмо"
      );
    }
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
    <div className="flex h-screen overflow-hidden flex-col bg-[#0B0E12] text-[#F3F4F6]">
      {/* Верхняя панель (67px) */}
      <ManagerHeader
        workspaceMode={workspaceMode}
        onModeChange={setWorkspaceMode}
        burningDeadlines={burningDeadlines}
      />

      {workspaceMode === "catalog" ? (
        <main className="flex-1 min-h-0 overflow-y-auto scrollbar-thin">
          <EventsCatalogView />
        </main>
      ) : (
        <div className="relative flex flex-1 min-h-0 overflow-hidden">
          {/* Основная рабочая область менеджера на всю ширину */}
          <main className="flex-1 min-h-0 overflow-y-auto p-4 lg:p-5 scrollbar-thin">
            <div className="mx-auto max-w-[1440px] space-y-4">
              {/* Верхняя строка под хедером: кнопка «Список клиентов» строго под логотипом */}
              <ClientsSelectorDropdown
                clients={clients}
                selectedClientId={selectedClientId}
                clientSearchQuery={clientSearchQuery}
                clientStatusFilter={clientStatusFilter}
                isOpen={isClientsDropdownOpen}
                draftClientIdSet={draftClientIdSet}
                publishedClientIdSet={publishedClientIdSet}
                onToggleOpen={handleToggleClientsDropdown}
                onClose={handleCloseClientsDropdown}
                onSearchQueryChange={setClientSearchQuery}
                onStatusFilterChange={setClientStatusFilter}
                onSelectClient={(client) =>
                  selectClient(client.id, client.raw_manager_notes)
                }
                onCreateClient={() =>
                  setClientModalState({ isOpen: true, mode: "create", client: null })
                }
                onEditClient={(client) =>
                  setClientModalState({ isOpen: true, mode: "edit", client })
                }
              />

              {isDashboardLoading ? (
                <WorkspaceLoadingState />
              ) : !activeClient ? (
                <WorkspaceEmptyClientState
                  hasClients={clients.length > 0}
                  onOpenClientsDropdown={handleToggleClientsDropdown}
                  onCreateClient={() =>
                    setClientModalState({ isOpen: true, mode: "create", client: null })
                  }
                />
              ) : (
                <motion.div
                  key={activeClient.id}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
                  className="space-y-4"
                >
                    {/* Компактная шапка активного клиента (без иконки здания, разделение названия и контакта) */}
                    <ActiveClientHeader
                      companyName={activeClient.company_name}
                      contactPerson={activeClient.contact_person}
                      onEditClient={() =>
                        setClientModalState({
                          isOpen: true,
                          mode: "edit",
                          client: activeClient,
                        })
                      }
                    />

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

                        {activeMatchResult && computedSummary ? (
                          <motion.div
                            key={`bundle-section-${activeMatchResult.selection_id}`}
                            initial={{ opacity: 0, y: 6 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ duration: 0.2, ease: "easeOut" }}
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
                          !matchMutation.isPending &&
                          (needsWorkspaceSync && isWorkspaceFetching ? (
                            <div
                              key="bundle-hydrating"
                              className="flex h-40 items-center justify-center rounded-[12px] border border-[#262D35] bg-[#161B22] text-xs text-[#8E95A0]"
                            >
                              Загрузка сохранённой подборки клиента...
                            </div>
                          ) : (
                            <BundleOnboardingEmptyState key="bundle-empty" />
                          ))
                        )}
                      </div>

                      {/* Правая закрепленная колонка итога и публикации (4 из 12 = ~33-38%, sticky) */}
                      <div className="xl:col-span-4">
                        {activeMatchResult && computedSummary ? (
                          <motion.div
                            key={`pitch-panel-${activeMatchResult.selection_id}`}
                            initial={{ opacity: 0, y: 6 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ duration: 0.2, ease: "easeOut" }}
                          >
                            <FinancialAndPitchPanel
                              companyName={activeClient.company_name}
                              summary={computedSummary}
                              pitchText={activePitchText}
                              onPitchChange={(text) =>
                                setPitchText(activeClient.id, text)
                              }
                              onGeneratePitch={handleGeneratePitch}
                              isGeneratingPitch={
                                generatePitchMutation.isPending
                              }
                              onPublish={handlePublishSelection}
                              isPublishing={publishMutation.isPending}
                              publishedUrl={activePublishedUrl}
                              onCopyLink={handleCopyShowcaseLink}
                            />
                          </motion.div>
                        ) : (
                          <PitchWaitingEmptyState key="pitch-empty" />
                        )}
                      </div>
                    </div>
                  </motion.div>
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

      <ClientFormModal
        isOpen={clientModalState.isOpen}
        mode={clientModalState.mode}
        client={clientModalState.client}
        onClose={() =>
          setClientModalState((prev) => ({ ...prev, isOpen: false }))
        }
        onCreated={(created) => {
          selectClient(created.id, created.raw_manager_notes);
        }}
        onUpdated={(updated) => {
          syncClientNotes(updated.id, updated.raw_manager_notes);
        }}
        onArchived={(archived) => {
          removeClientWorkspace(archived.id);
        }}
      />
    </div>
  );
}
