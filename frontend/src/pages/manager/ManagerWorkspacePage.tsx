import * as React from "react";
import { toast } from "sonner";
import { Building2, UserCheck, Compass } from "lucide-react";
import {
  useManagerDashboard,
  useManagerEventsCatalog,
  useMatchClientMutation,
  usePublishSelectionMutation,
} from "@/api/queries";
import {
  computeClientFinancialSummary,
  useManagerStore,
} from "@/store/useManagerStore";
import { ManagerHeader } from "./ManagerHeader";
import { ClientSidebar } from "./ClientSidebar";
import { NotesAndProfileSection } from "./NotesAndProfileSection";
import { BundleConstructorSection } from "./BundleConstructorSection";
import { FinancialAndPitchPanel } from "./FinancialAndPitchPanel";
import { PublishedShowcaseMonitor } from "./PublishedShowcaseMonitor";
import { EventsCatalogView } from "./EventsCatalogView";

export function ManagerWorkspacePage() {
  const { data: dashboard, isLoading: isDashboardLoading } =
    useManagerDashboard();
  const { data: catalogData } = useManagerEventsCatalog(true);

  const matchMutation = useMatchClientMutation();
  const publishMutation = usePublishSelectionMutation();

  const state = useManagerStore();
  const {
    workspaceMode,
    isSidebarCollapsed,
    selectedClientId,
    clientSearchQuery,
    notesByClient,
    isNotesCollapsed,
    matchResultByClient,
    editableProfileByClient,
    selectedVariantGroupByClient,
    pitchTextByClient,
    publishedInfoByClient,
    setWorkspaceMode,
    toggleSidebar,
    selectClient,
    setClientSearchQuery,
    setClientNotes,
    setNotesCollapsed,
    hydrateMatchResponse,
    updateEditableProfile,
    selectVariantGroup,
    toggleEventIncluded,
    changeEventTariff,
    updateEventRationale,
    setPitchText,
    syncPitchNumbersWithPackage,
    setPublishedInfo,
  } = state;

  const clients = dashboard?.clients || [];
  const burningDeadlines = dashboard?.burning_deadlines || [];

  // Автовыбор первого клиента при загрузке дашборда
  React.useEffect(() => {
    if (selectedClientId === null && clients.length > 0) {
      const first = clients[0];
      selectClient(first.id, first.raw_manager_notes);
    }
  }, [clients, selectedClientId, selectClient]);

  const activeClient =
    clients.find((c) => c.id === selectedClientId) || null;

  const currentNotes = activeClient
    ? (notesByClient[activeClient.id] ?? activeClient.raw_manager_notes)
    : "";

  const activeMatchResult = activeClient
    ? matchResultByClient[activeClient.id]
    : undefined;

  const activeEditableProfile = activeClient
    ? editableProfileByClient[activeClient.id]
    : undefined;

  const activeVariantGroup = activeClient
    ? (selectedVariantGroupByClient[activeClient.id] ?? 1)
    : 1;

  const activePitchText = activeClient
    ? (pitchTextByClient[activeClient.id] ??
      activeMatchResult?.generated_pitch_text ??
      "")
    : "";

  const computedSummary = React.useMemo(
    () =>
      activeClient
        ? computeClientFinancialSummary(state, activeClient.id)
        : null,
    [state, activeClient]
  );

  // Токен опубликованной витрины (из текущей сессии или из БД)
  const activeMagicToken = activeClient
    ? publishedInfoByClient[activeClient.id]?.magicToken ||
      activeClient.magic_token
    : null;

  const activePublishedUrl = activeMagicToken
    ? `/s/${activeMagicToken}`
    : null;

  const hasDraftInSessionMap = React.useMemo(() => {
    const map: Record<number, boolean> = {};
    for (const k of Object.keys(matchResultByClient)) {
      map[Number(k)] = true;
    }
    return map;
  }, [matchResultByClient]);

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
    setTimeout(() => {
      useManagerStore
        .getState()
        .syncPitchNumbersWithPackage(activeClient.id, activeClient.company_name);
    }, 0);
  };

  const handleSyncPitch = () => {
    if (!activeClient) return;
    syncPitchNumbersWithPackage(activeClient.id, activeClient.company_name);
    toast.success("Цифры бюджета, выгоды и список площадок в письме обновлены");
  };

  const handleCopyShowcaseLink = (relativeUrl: string) => {
    const fullUrl = `${window.location.origin}${relativeUrl}`;
    navigator.clipboard.writeText(fullUrl).catch(() => {});
    toast.success("Персональная ссылка скопирована в буфер обмена");
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
        magicToken: res.magic_token,
        publicUrl: res.public_showcase_url,
        totalPrice: res.total_package_price,
        totalSavings: res.total_package_savings,
      });

      const fullUrl = `${window.location.origin}${res.public_showcase_url}`;
      navigator.clipboard.writeText(fullUrl).catch(() => {});
      toast.success(
        "Персональная витрина клиента опубликована! Ссылка скопирована в буфер обмена."
      );
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Ошибка при публикации витрины"
      );
    }
  };

  return (
    <div className="flex min-h-screen flex-col bg-canvas text-ink">
      {/* Верхняя панель (56px) */}
      <ManagerHeader
        workspaceMode={workspaceMode}
        onModeChange={setWorkspaceMode}
        isSidebarCollapsed={isSidebarCollapsed}
        onToggleSidebar={toggleSidebar}
        burningDeadlines={burningDeadlines}
        eventsCount={catalogData?.total_count}
      />

      {workspaceMode === "catalog" ? (
        <main className="flex-1">
          <EventsCatalogView />
        </main>
      ) : (
        <div className="flex flex-1 overflow-hidden">
          {/* Левая узкая колонка клиентов (260px, сворачиваемая) */}
          {!isSidebarCollapsed && (
            <ClientSidebar
              clients={clients}
              selectedClientId={selectedClientId}
              searchQuery={clientSearchQuery}
              onSearchChange={setClientSearchQuery}
              onSelectClient={(c) => selectClient(c.id, c.raw_manager_notes)}
              publishedByClientMap={publishedInfoByClient}
              hasDraftInSessionMap={hasDraftInSessionMap}
            />
          )}

          {/* Основная рабочая область выбранного клиента */}
          <main className="flex-1 overflow-y-auto p-4 lg:p-5 scrollbar-thin">
            {isDashboardLoading ? (
              <div className="flex h-64 items-center justify-center rounded-card border border-border bg-surface text-sm text-ink-muted">
                Загрузка рабочего пространства менеджера...
              </div>
            ) : !activeClient ? (
              <div className="flex h-64 items-center justify-center rounded-card border border-border bg-surface text-sm text-ink-muted">
                Выберите компанию клиента в списке слева
              </div>
            ) : (
              <div className="mx-auto max-w-[1440px] space-y-4">
                {/* Компактная шапка активного клиента */}
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-border bg-surface px-4 py-3 shadow-card">
                  <div className="flex items-center gap-3">
                    <div className="flex h-9 w-9 items-center justify-center rounded-control bg-pine/10 text-pine">
                      <Building2 className="h-4 w-4" strokeWidth={1.75} />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h1 className="text-base font-semibold text-ink">
                          {activeClient.company_name}
                        </h1>
                        {activeClient.contact_person && (
                          <span className="inline-flex items-center gap-1 text-xs text-ink-muted">
                            · <UserCheck className="h-3.5 w-3.5" strokeWidth={1.5} />
                            {activeClient.contact_person}
                          </span>
                        )}
                      </div>
                      <p className="text-[11px] text-ink-muted">
                        Формирование календаря отраслевых мероприятий, расчет взносов и подготовка спикеров
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 text-xs text-ink-muted">
                    <span>Путь клиента:</span>
                    <span className="rounded-badge bg-canvas border border-border px-2 py-0.5 font-medium text-ink-secondary">
                      {activeMatchResult
                        ? activeMagicToken
                          ? "Этап 07 · Согласование с клиентом"
                          : "Этап 05–06 · Сравнение и рекомендация"
                        : "Этап 01–04 · Запрос и подбор возможностей"}
                    </span>
                  </div>
                </div>

                {/* Живой мониторинг опубликованной витрины (если у клиента уже выпущена ссылка) */}
                {activeMagicToken && (
                  <PublishedShowcaseMonitor
                    magicToken={activeMagicToken}
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
                      />
                    ) : (
                      !matchMutation.isPending && (
                        <div className="rounded-card border border-dashed border-border-strong bg-surface/60 p-8 text-center">
                          <Compass
                            className="mx-auto h-8 w-8 text-ink-faint"
                            strokeWidth={1.5}
                          />
                          <h3 className="mt-2.5 text-sm font-semibold text-ink">
                            Готово к формированию пакетов участия
                          </h3>
                          <p className="mx-auto mt-1 max-w-lg text-xs leading-relaxed text-ink-muted">
                            Проверьте конспект установочной встречи выше и нажмите{" "}
                            <strong className="text-ink-secondary">
                              «Подобрать варианты пакетов»
                            </strong>
                            . Система извлечет критерии отбора, сверит календарь без накладок и сформирует 2 пакета с расчетом выгоды Early Bird.
                          </p>
                        </div>
                      )
                    )}
                  </div>

                  {/* Правая закрепленная колонка итога и публикации (4 из 12 = ~33-38%, sticky) */}
                  <div className="xl:col-span-4">
                    {activeMatchResult && computedSummary ? (
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
                    ) : (
                      <div className="rounded-card border border-border bg-surface p-5 shadow-card">
                        <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted">
                          Сводка и публикация КП
                        </span>
                        <h3 className="mt-1 text-sm font-semibold text-ink">
                          Ожидание расчёта подборки
                        </h3>
                        <p className="mt-1.5 text-xs leading-relaxed text-ink-muted">
                          После запуска подбора здесь появится финансовая сводка пакета (внешние взносы организаторов и выгода Early Bird), редактор персонального письма и выпуск ссылки на витрину клиента.
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}
          </main>
        </div>
      )}
    </div>
  );
}
