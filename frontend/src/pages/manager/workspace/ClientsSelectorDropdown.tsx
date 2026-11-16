import * as React from "react";
import {
  Building2,
  UserCheck,
  PanelLeftOpen,
  Search,
  Plus,
  Pencil,
  X,
} from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import type { ClientSummaryOut } from "@/api/types";
import type { ClientStatusFilter } from "@/store/useManagerStore";
import { Badge } from "@/components/ui/badge";
import { pluralizeRu } from "@/lib/formatters";
import { cn } from "@/lib/utils";

type ClientStatus = Exclude<ClientStatusFilter, "all">;

const PAGE_SIZE = 50;

const STATUS_PRIORITY: Record<ClientStatus, number> = {
  published: 0,
  draft: 1,
  new: 2,
};

const STATUS_BADGE_META: Record<
  ClientStatus,
  { label: string; variant: "ebEmerald" | "ebAmber" | "ebBlue" }
> = {
  published: { label: "КП активно", variant: "ebEmerald" },
  draft: { label: "Черновик", variant: "ebAmber" },
  new: { label: "Новый", variant: "ebBlue" },
};

const STATUS_FILTER_OPTIONS: Array<{ id: ClientStatusFilter; label: string }> = [
  { id: "all", label: "Все" },
  { id: "published", label: "КП активно" },
  { id: "draft", label: "Черновик" },
  { id: "new", label: "Новый" },
];

export function getClientStatus(
  client: ClientSummaryOut,
  publishedClientIdSet: Set<number>,
  draftClientIdSet: Set<number>
): ClientStatus {
  if (
    publishedClientIdSet.has(client.id) ||
    client.latest_selection_status === "published"
  ) {
    return "published";
  }
  if (
    draftClientIdSet.has(client.id) ||
    client.latest_selection_status === "draft"
  ) {
    return "draft";
  }
  return "new";
}

interface ClientsSelectorDropdownProps {
  clients: ClientSummaryOut[];
  selectedClientId: number | null;
  clientSearchQuery: string;
  clientStatusFilter: ClientStatusFilter;
  isOpen: boolean;
  draftClientIdSet: Set<number>;
  publishedClientIdSet: Set<number>;
  onToggleOpen: () => void;
  onClose: () => void;
  onSearchQueryChange: (query: string) => void;
  onStatusFilterChange: (filter: ClientStatusFilter) => void;
  onSelectClient: (client: ClientSummaryOut) => void;
  onCreateClient: () => void;
  onEditClient: (client: ClientSummaryOut) => void;
}

export function ClientsSelectorDropdown({
  clients,
  selectedClientId,
  clientSearchQuery,
  clientStatusFilter,
  isOpen,
  draftClientIdSet,
  publishedClientIdSet,
  onToggleOpen,
  onClose,
  onSearchQueryChange,
  onStatusFilterChange,
  onSelectClient,
  onCreateClient,
  onEditClient,
}: ClientsSelectorDropdownProps) {
  const clientDropdownRef = React.useRef<HTMLDivElement>(null);
  const searchInputRef = React.useRef<HTMLInputElement>(null);
  const rowRefs = React.useRef<Map<number, HTMLDivElement>>(new Map());
  const shouldScrollIntoViewRef = React.useRef(false);

  const [visibleCount, setVisibleCount] = React.useState(PAGE_SIZE);
  const [highlightedIndex, setHighlightedIndex] = React.useState(-1);

  const clientsWithStatus = React.useMemo(
    () =>
      clients.map((client, index) => ({
        client,
        index,
        status: getClientStatus(client, publishedClientIdSet, draftClientIdSet),
      })),
    [clients, publishedClientIdSet, draftClientIdSet]
  );

  const searchMatchedClients = React.useMemo(() => {
    const q = clientSearchQuery.trim().toLowerCase();
    if (!q) return clientsWithStatus;
    return clientsWithStatus.filter(
      ({ client }) =>
        client.company_name.toLowerCase().includes(q) ||
        (client.contact_person || "").toLowerCase().includes(q)
    );
  }, [clientsWithStatus, clientSearchQuery]);

  const statusCounts = React.useMemo(() => {
    const counts: Record<ClientStatusFilter, number> = {
      all: searchMatchedClients.length,
      published: 0,
      draft: 0,
      new: 0,
    };
    for (const item of searchMatchedClients) {
      counts[item.status] += 1;
    }
    return counts;
  }, [searchMatchedClients]);

  const filteredClients = React.useMemo(() => {
    const filtered =
      clientStatusFilter === "all"
        ? searchMatchedClients
        : searchMatchedClients.filter(
            (item) => item.status === clientStatusFilter
          );

    return [...filtered].sort((a, b) => {
      const aSelected = a.client.id === selectedClientId ? 0 : 1;
      const bSelected = b.client.id === selectedClientId ? 0 : 1;
      if (aSelected !== bSelected) return aSelected - bSelected;

      const priorityDiff =
        STATUS_PRIORITY[a.status] - STATUS_PRIORITY[b.status];
      if (priorityDiff !== 0) return priorityDiff;

      return a.index - b.index;
    });
  }, [searchMatchedClients, clientStatusFilter, selectedClientId]);

  const visibleClients = React.useMemo(
    () => filteredClients.slice(0, visibleCount),
    [filteredClients, visibleCount]
  );

  const remaining = Math.max(0, filteredClients.length - visibleClients.length);

  // Сброс порции рендера при закрытии поповера или смене критериев фильтрации
  React.useEffect(() => {
    if (!isOpen) {
      setVisibleCount(PAGE_SIZE);
      setHighlightedIndex(-1);
      return;
    }
    setVisibleCount(PAGE_SIZE);
  }, [isOpen, clientSearchQuery, clientStatusFilter]);

  // Автофокус поля поиска при открытии поповера
  React.useEffect(() => {
    if (!isOpen) return;
    const focusTimer = window.setTimeout(() => {
      searchInputRef.current?.focus();
    }, 50);
    return () => {
      window.clearTimeout(focusTimer);
    };
  }, [isOpen]);

  // Поддерживаем корректный индекс подсветки при изменении видимого списка
  React.useEffect(() => {
    if (!isOpen) return;
    if (visibleClients.length === 0) {
      setHighlightedIndex(-1);
      return;
    }
    setHighlightedIndex((prev) => {
      if (prev < 0) return 0;
      if (prev >= visibleClients.length) return visibleClients.length - 1;
      return prev;
    });
  }, [isOpen, visibleClients.length]);

  // Прокрутка подсвеченного клиента в видимую зону при навигации с клавиатуры
  React.useEffect(() => {
    if (!isOpen || !shouldScrollIntoViewRef.current) return;
    shouldScrollIntoViewRef.current = false;
    if (highlightedIndex < 0 || highlightedIndex >= visibleClients.length) {
      return;
    }
    const targetClient = visibleClients[highlightedIndex]?.client;
    if (!targetClient) return;
    rowRefs.current.get(targetClient.id)?.scrollIntoView({ block: "nearest" });
  }, [isOpen, highlightedIndex, visibleClients]);

  // Закрытие по клику снаружи и клавиатурная навигация внутри открытого поповера
  React.useEffect(() => {
    if (!isOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (
        clientDropdownRef.current &&
        !clientDropdownRef.current.contains(e.target as Node)
      ) {
        onClose();
      }
    };
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
        return;
      }

      if (visibleClients.length === 0) return;

      if (e.key === "ArrowDown") {
        e.preventDefault();
        shouldScrollIntoViewRef.current = true;
        setHighlightedIndex((prev) =>
          prev < 0 ? 0 : (prev + 1) % visibleClients.length
        );
        return;
      }

      if (e.key === "ArrowUp") {
        e.preventDefault();
        shouldScrollIntoViewRef.current = true;
        setHighlightedIndex((prev) =>
          prev <= 0 ? visibleClients.length - 1 : prev - 1
        );
        return;
      }

      if (e.key === "Enter") {
        const target = e.target as HTMLElement | null;
        if (target instanceof HTMLButtonElement) return;
        const activeEntry =
          highlightedIndex >= 0 ? visibleClients[highlightedIndex] : undefined;
        if (!activeEntry) return;
        e.preventDefault();
        onSelectClient(activeEntry.client);
        onClose();
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, visibleClients, highlightedIndex, onSelectClient, onClose]);

  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-2">
        <div className="relative inline-block" ref={clientDropdownRef}>
          <button
            type="button"
            onClick={onToggleOpen}
            className={cn(
              "group relative flex items-center gap-2 rounded-[8px] border bg-[#12161A] px-3.5 py-1.5 text-xs font-medium select-none cursor-pointer shadow-sm transition-colors duration-150 outline-none",
              isOpen
                ? "border-[#E5C378] bg-[#1A2128] text-white shadow-[0_0_10px_rgba(229,195,120,0.25)]"
                : "border-[#262D35] text-[#D1D5DB] hover:border-[#E5C378] hover:bg-[#1A2128] hover:text-white"
            )}
            title="Выбрать компанию клиента"
          >
            <PanelLeftOpen
              className="h-4 w-4 shrink-0 transition-colors duration-150 text-inherit group-hover:text-[#E5C378]"
              strokeWidth={1.75}
            />
            <span className="transition-colors duration-150">Список клиентов</span>
            <span
              className={cn(
                "rounded bg-[#1A252A] px-1.5 py-0.5 text-[11px] font-semibold text-[#529E85] tabular-nums transition-colors duration-150",
                "group-hover:bg-[#1E252E] group-hover:text-[#34D399]"
              )}
            >
              {clients.length}
            </span>

            {/* Золотая светящаяся линия подчеркивания в открытом/активном состоянии */}
            {isOpen && (
              <span className="absolute bottom-0 left-0 right-0 h-[2.5px] rounded-b-[8px] bg-gradient-to-r from-[#D4AF37] via-[#E5C378] to-[#D4AF37] shadow-[0_0_10px_rgba(229,195,120,0.75)]" />
            )}
          </button>

          {/* Выпадающее меню с viewport-aware flex-компоновкой */}
          <AnimatePresence>
            {isOpen && (
              <motion.div
                initial={{ opacity: 0, y: -6, scale: 0.98 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -4, scale: 0.98 }}
                transition={{ duration: 0.18, ease: "easeOut" }}
                className="absolute left-0 mt-2 flex flex-col w-[min(calc(100vw-2rem),440px)] max-h-[min(540px,calc(100vh-148px))] overflow-hidden rounded-[12px] border border-[#262B33] bg-[#0E1116] p-4 shadow-2xl shadow-black/80 z-50 text-white select-none"
              >
                {/* Непрокручиваемая шапка, поиск и фильтр статусов */}
                <div className="shrink-0">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h3 className="text-[11px] font-serif italic font-semibold text-[#8E95A0]">
                        Выбор клиента
                      </h3>
                      <p className="mt-0.5 text-xs text-[#8E95A0]">
                        Активные компании и согласование пакетов
                      </p>
                    </div>
                    <Badge
                      variant="ebAmber"
                      asSlanted={false}
                      className="text-[11px] shrink-0"
                    >
                      {clients.length}{" "}
                      {pluralizeRu(clients.length, [
                        "компания",
                        "компании",
                        "компаний",
                      ])}
                    </Badge>
                  </div>

                  <div className="border-b border-[#21262F] my-3" />

                  <div className="relative mb-2.5">
                    <Search
                      className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#E5C378]"
                      strokeWidth={2}
                    />
                    <input
                      ref={searchInputRef}
                      id="clients-dropdown-search"
                      name="clients_search"
                      aria-label="Поиск компании или контакта"
                      type="text"
                      value={clientSearchQuery}
                      onChange={(e) => onSearchQueryChange(e.target.value)}
                      placeholder="Поиск компании или контакта..."
                      className="h-9 w-full rounded-[8px] border border-[#38414F] bg-[#161B21] pl-9 pr-9 text-sm text-white placeholder:text-[#8E95A0] shadow-inner transition-colors duration-150 ease-out hover:border-[#4B5565] [color-scheme:dark] outline-none focus:outline-none focus-visible:outline-none active:outline-none focus:border-[#E5C378] focus:bg-[#1A2027] focus:shadow-[0_0_0_1px_rgba(229,195,120,0.25)]"
                    />
                    {clientSearchQuery.length > 0 && (
                      <button
                        type="button"
                        onClick={() => {
                          onSearchQueryChange("");
                          searchInputRef.current?.focus();
                        }}
                        aria-label="Очистить поиск"
                        title="Очистить поиск"
                        className="absolute right-2 top-1/2 -translate-y-1/2 inline-flex h-6 w-6 items-center justify-center rounded text-[#8E95A0] transition-colors hover:bg-[#262D35] hover:text-white cursor-pointer"
                      >
                        <X className="h-3.5 w-3.5" strokeWidth={2} />
                      </button>
                    )}
                  </div>

                  {/* Компактная полоса фильтров статуса */}
                  <div className="mb-3 flex flex-wrap items-center gap-1.5">
                    {STATUS_FILTER_OPTIONS.map((option) => {
                      const isActive = clientStatusFilter === option.id;
                      const count = statusCounts[option.id];
                      return (
                        <button
                          key={option.id}
                          type="button"
                          onClick={() => onStatusFilterChange(option.id)}
                          className={cn(
                            "inline-flex items-center gap-1 rounded-[6px] border px-2 py-1 text-[11px] font-medium transition-colors cursor-pointer tabular-nums",
                            isActive
                              ? "border-[#E5C378] bg-[#261E0F] text-[#E5C378]"
                              : "border-[#262D35] bg-[#12161A] text-[#8E95A0] hover:border-[#38414F] hover:text-white"
                          )}
                        >
                          <span>{option.label}</span>
                          <span
                            className={cn(
                              "rounded px-1 text-[10px] font-semibold",
                              isActive
                                ? "bg-[#E5C378]/20 text-[#E5C378]"
                                : "bg-[#1A2027] text-[#8E95A0]"
                            )}
                          >
                            {count}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Прокручивается только список клиентов */}
                {filteredClients.length === 0 ? (
                  <p className="py-6 text-center text-xs text-[#8E95A0]">
                    Компании не найдены
                  </p>
                ) : (
                  <div
                    role="listbox"
                    aria-label="Список клиентов"
                    className="flex-1 min-h-0 overflow-y-auto pr-1 scrollbar-thin space-y-1.5"
                  >
                    {visibleClients.map(({ client, status }, idx) => {
                      const isSelected = client.id === selectedClientId;
                      const isHighlighted = idx === highlightedIndex;
                      const statusMeta = STATUS_BADGE_META[status];

                      return (
                        <div
                          key={client.id}
                          ref={(el) => {
                            if (el) {
                              rowRefs.current.set(client.id, el);
                            } else {
                              rowRefs.current.delete(client.id);
                            }
                          }}
                          role="option"
                          aria-selected={isSelected}
                          onMouseEnter={() => setHighlightedIndex(idx)}
                          onClick={() => {
                            onSelectClient(client);
                            onClose();
                          }}
                          className={cn(
                            "relative rounded-[8px] border px-3 py-2 transition-colors cursor-pointer select-none",
                            isSelected
                              ? "border-[#E5C378] bg-[#1E252E] shadow-sm border-l-[3px] border-l-[#E5C378]"
                              : "border-[#262C35] bg-[#1A1E24] hover:border-[#38414F] hover:bg-[#1E232B]",
                            isHighlighted &&
                              !isSelected &&
                              "border-[#7C5A20] bg-[#1E232B] ring-1 ring-[#E5C378]/40",
                            isHighlighted &&
                              isSelected &&
                              "ring-1 ring-[#E5C378]/60"
                          )}
                        >
                          {/* Верхняя строка: иконка + название + бейдж статуса */}
                          <div className="flex items-center justify-between gap-2">
                            <div className="min-w-0 flex items-center gap-2">
                              <Building2
                                className={cn(
                                  "h-3.5 w-3.5 shrink-0",
                                  isSelected
                                    ? "text-[#E5C378]"
                                    : "text-[#8E95A0]"
                                )}
                                strokeWidth={1.75}
                              />
                              <p
                                className={cn(
                                  "truncate text-[13px] leading-snug",
                                  isSelected
                                    ? "font-semibold text-white"
                                    : "font-medium text-[#F3F4F6]"
                                )}
                              >
                                {client.company_name}
                              </p>
                            </div>

                            <Badge
                              variant={statusMeta.variant}
                              asSlanted={false}
                              className="text-[11px] shrink-0"
                            >
                              {statusMeta.label}
                            </Badge>
                          </div>

                          {/* Нижняя строка: контакт слева + редактирование справа */}
                          <div className="mt-1 flex items-center justify-between gap-2 text-[11px] text-[#8E95A0] tabular-nums">
                            <span className="inline-flex min-w-0 items-center gap-1.5 truncate">
                              {client.contact_person ? (
                                <>
                                  <UserCheck
                                    className="h-3 w-3 text-[#8E95A0] shrink-0"
                                    strokeWidth={1.5}
                                  />
                                  <span className="truncate">
                                    {client.contact_person}
                                  </span>
                                </>
                              ) : (
                                <span className="text-[#8E95A0]">
                                  Контакт не указан
                                </span>
                              )}
                            </span>

                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                onClose();
                                onEditClient(client);
                              }}
                              aria-label={`Редактировать клиента ${client.company_name}`}
                              title="Редактировать или архивировать клиента"
                              className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-[5px] border border-[#262D35] bg-[#12161A] text-[#8E95A0] transition-colors hover:border-[#E5C378] hover:text-[#E5C378] cursor-pointer"
                            >
                              <Pencil className="h-3 w-3" strokeWidth={1.75} />
                            </button>
                          </div>
                        </div>
                      );
                    })}

                    {filteredClients.length > visibleCount && (
                      <button
                        type="button"
                        onClick={() => setVisibleCount((prev) => prev + PAGE_SIZE)}
                        className="w-full rounded-[8px] border border-[#262D35] bg-[#12161A] px-3 py-2 text-center text-xs font-medium text-[#E5C378] transition-colors hover:border-[#E5C378] hover:bg-[#1E190E] hover:text-white cursor-pointer tabular-nums"
                      >
                        Показать ещё {Math.min(PAGE_SIZE, remaining)} (осталось{" "}
                        {remaining})
                      </button>
                    )}
                  </div>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <button
          type="button"
          onClick={onCreateClient}
          className="inline-flex items-center gap-1.5 rounded-[8px] border border-[#7C5A20]/70 bg-[#1A150B] px-3 py-1.5 text-xs font-medium text-[#E5C378] shadow-sm transition-colors duration-150 hover:border-[#E5C378] hover:bg-[#261E0F] hover:text-white cursor-pointer select-none"
        >
          <Plus className="h-3.5 w-3.5" strokeWidth={2.25} />
          <span>Новый клиент</span>
        </button>
      </div>
    </div>
  );
}
