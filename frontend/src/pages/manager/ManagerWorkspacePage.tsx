import * as React from "react";
import { toast } from "sonner";
import { Building2, UserCheck, Compass, PanelLeftOpen, Search } from "lucide-react";
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
import { cn } from "@/lib/utils";
import { ManagerHeader } from "./ManagerHeader";
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

  // Состояние выпадающего меню списка клиентов (стиль Early Bird Popover)
  const [isClientsDropdownOpen, setIsClientsDropdownOpen] = React.useState(false);
  const [flashClientsBtn, setFlashClientsBtn] = React.useState(false);
  const clientDropdownRef = React.useRef<HTMLDivElement>(null);

  const handleToggleClientsDropdown = () => {
    setFlashClientsBtn(true);
    setIsClientsDropdownOpen((prev) => !prev);
    setTimeout(() => setFlashClientsBtn(false), 200);
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
        burningDeadlines={burningDeadlines}
        eventsCount={catalogData?.total_count}
      />

      {workspaceMode === "catalog" ? (
        <main className="flex-1">
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
                      "group relative flex items-center gap-2 rounded-[8px] border border-[#262D35] bg-[#12161A] px-3.5 py-1.5 text-xs font-medium transition-all duration-200 select-none cursor-pointer overflow-hidden shadow-sm",
                      isClientsDropdownOpen
                        ? "bg-[#1A2128] text-white border-[#38414F]"
                        : "text-[#D1D5DB]",
                      // Золотой перелив при наведении (текст и иконка становятся черными)
                      "hover:bg-gradient-to-r hover:from-[#D4AF37] hover:via-[#E5C378] hover:to-[#D4AF37] hover:text-[#0E1215] hover:font-semibold hover:shadow-[0_0_12px_rgba(229,195,120,0.35)]",
                      // Эффект вспышки при клике
                      flashClientsBtn && "scale-[0.98] brightness-150 ring-1 ring-[#E5C378]"
                    )}
                    title="Выбрать компанию клиента"
                  >
                    <PanelLeftOpen className="h-4 w-4 text-inherit transition-transform shrink-0" strokeWidth={1.75} />
                    <span>Список клиентов</span>
                    <span
                      className={cn(
                        "rounded bg-[#1A252A] px-1.5 py-0.2 text-[10px] font-semibold text-[#529E85] tabular-nums transition-colors",
                        "group-hover:bg-[#0E1215]/20 group-hover:text-[#0E1215]"
                      )}
                    >
                      {clients.length}
                    </span>

                    {/* Золотая светящаяся линия подчеркивания в открытом/активном состоянии */}
                    {isClientsDropdownOpen && (
                      <span className="absolute bottom-0 left-2 right-2 h-[2px] rounded-full bg-gradient-to-r from-transparent via-[#E5C378] to-transparent shadow-[0_0_8px_rgba(229,195,120,0.7)]" />
                    )}
                  </button>

                  {/* Выпадающее меню в стиле Early Bird Popover (media_1793287754782_2088a7c6.jpg) */}
                  {isClientsDropdownOpen && (
                    <div className="absolute left-0 mt-2 w-[340px] sm:w-[440px] rounded-[12px] border border-[#262B33] bg-[#0E1116] p-4 sm:p-5 shadow-2xl shadow-black/80 z-50 text-white select-none">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <h3 className="text-[11px] font-semibold uppercase tracking-wider text-[#8E95A0]">
                            ВЫБОР КЛИЕНТА
                          </h3>
                          <p className="mt-1 text-xs text-[#727985]">
                            Активные компании и согласование пакетов
                          </p>
                        </div>
                        <span className="shrink-0 rounded-[4px] border border-[#7C4A19] bg-[#22160C]/90 px-2.5 py-1 text-[11px] font-bold text-[#E59837] tracking-wider tabular-nums">
                          [ {clients.length} КОМПАНИИ ]
                        </span>
                      </div>

                      <div className="border-b border-[#21262F] my-3.5" />

                      {/* Поиск компании */}
                      <div className="relative mb-3">
                        <Search
                          className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[#727985]"
                          strokeWidth={1.75}
                        />
                        <input
                          type="text"
                          value={clientSearchQuery}
                          onChange={(e) => setClientSearchQuery(e.target.value)}
                          placeholder="Поиск компании или контакта..."
                          className="h-8.5 w-full rounded-[8px] border border-[#262C35] bg-[#161B21] pl-9 pr-3 text-xs text-white placeholder:text-[#6B7280] focus:border-[#38BDF8] focus:bg-[#1A2027] focus:outline-none transition-colors"
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
                              Boolean(publishedInfoByClient[client.id]) ||
                              client.latest_selection_status === "published";
                            const isDraft =
                              !isPublished &&
                              (Boolean(hasDraftInSessionMap[client.id]) ||
                                client.latest_selection_status === "draft");

                            return (
                              <div
                                key={client.id}
                                onClick={() => {
                                  selectClient(
                                    client.id,
                                    notesByClient[client.id] ?? client.raw_manager_notes
                                  );
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

                                  {/* Строгие статусные ячейки Novel.AI */}
                                  {isPublished ? (
                                    <span className="shrink-0 rounded-[4px] border border-[#1E5241] bg-[#0E241E]/90 px-2 py-0.5 text-[10px] font-bold text-[#34D399] tracking-wider tabular-nums">
                                      [ КП АКТИВНО ]
                                    </span>
                                  ) : isDraft ? (
                                    <span className="shrink-0 rounded-[4px] border border-[#7C4A19] bg-[#22160C]/90 px-2 py-0.5 text-[10px] font-bold text-[#E59837] tracking-wider tabular-nums">
                                      [ ЧЕРНОВИК ]
                                    </span>
                                  ) : (
                                    <span className="shrink-0 rounded-[4px] border border-[#2B3545] bg-[#161B22]/90 px-2 py-0.5 text-[10px] font-bold text-[#8E95A0] tracking-wider tabular-nums">
                                      [ НОВЫЙ ]
                                    </span>
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
                                    <span className="text-[10px] font-bold uppercase tracking-wider text-[#E5C378]">
                                      ВЫБРАН
                                    </span>
                                  )}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  )}
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
                    className="inline-flex items-center gap-2 rounded-[8px] border border-[#262D35] bg-[#12161A] px-4 py-2 text-xs font-semibold text-white transition-all hover:bg-gradient-to-r hover:from-[#D4AF37] hover:via-[#E5C378] hover:to-[#D4AF37] hover:text-[#0E1215]"
                  >
                    <PanelLeftOpen className="h-4 w-4" />
                    <span>Выбрать компанию из списка</span>
                  </button>
                </div>
              ) : (
                <>
                  {/* Компактная шапка активного клиента */}
                  <div className="flex flex-wrap items-center justify-between gap-3 rounded-[12px] border border-[#262D35] bg-[#161B22] px-4 py-3 shadow-md">
                    <div className="flex items-center gap-3">
                      <div className="flex h-9 w-9 items-center justify-center rounded-[6px] border border-[#2D3540] bg-[#12161A] text-[#38BDF8]">
                        <Building2 className="h-4 w-4" strokeWidth={1.75} />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <h1 className="text-base font-semibold text-white">
                            {activeClient.company_name}
                          </h1>
                          {activeClient.contact_person && (
                            <span className="inline-flex items-center gap-1 text-xs text-[#8E95A0]">
                              · <UserCheck className="h-3.5 w-3.5" strokeWidth={1.5} />
                              {activeClient.contact_person}
                            </span>
                          )}
                        </div>
                        <p className="text-[11px] text-[#8E95A0]">
                          Формирование календаря отраслевых мероприятий, расчет взносов и подготовка спикеров
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 text-xs text-[#8E95A0]">
                      <span className="text-[11px] font-semibold uppercase tracking-wider text-[#8E95A0]">Путь клиента:</span>
                      <span className="rounded-[4px] border border-[#262D35] bg-[#1A1E24] px-2.5 py-0.5 text-xs font-medium text-[#D1D5DB] tabular-nums">
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
              </>
            )}
          </div>
        </main>
        </div>
      )}
    </div>
  );
}
