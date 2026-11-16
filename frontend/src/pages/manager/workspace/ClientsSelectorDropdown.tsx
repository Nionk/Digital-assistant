import * as React from "react";
import {
  Building2,
  UserCheck,
  PanelLeftOpen,
  Search,
  Plus,
  Pencil,
} from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import type { ClientSummaryOut } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { pluralizeRu } from "@/lib/formatters";
import { cn } from "@/lib/utils";

interface ClientsSelectorDropdownProps {
  clients: ClientSummaryOut[];
  selectedClientId: number | null;
  clientSearchQuery: string;
  isOpen: boolean;
  draftClientIdSet: Set<number>;
  publishedClientIdSet: Set<number>;
  onToggleOpen: () => void;
  onClose: () => void;
  onSearchQueryChange: (query: string) => void;
  onSelectClient: (client: ClientSummaryOut) => void;
  onCreateClient: () => void;
  onEditClient: (client: ClientSummaryOut) => void;
}

export function ClientsSelectorDropdown({
  clients,
  selectedClientId,
  clientSearchQuery,
  isOpen,
  draftClientIdSet,
  publishedClientIdSet,
  onToggleOpen,
  onClose,
  onSearchQueryChange,
  onSelectClient,
  onCreateClient,
  onEditClient,
}: ClientsSelectorDropdownProps) {
  const clientDropdownRef = React.useRef<HTMLDivElement>(null);

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
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", handleClickOutside);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, onClose]);

  const filteredClients = React.useMemo(() => {
    const q = clientSearchQuery.trim().toLowerCase();
    if (!q) return clients;
    return clients.filter(
      (c) =>
        c.company_name.toLowerCase().includes(q) ||
        (c.contact_person || "").toLowerCase().includes(q)
    );
  }, [clients, clientSearchQuery]);

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
              "rounded bg-[#1A252A] px-1.5 py-0.5 text-[10px] font-semibold text-[#529E85] tabular-nums transition-colors duration-150",
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

        {/* Выпадающее меню в стиле Early Bird Popover с плавной анимацией */}
        <AnimatePresence>
          {isOpen && (
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
                  onChange={(e) => onSearchQueryChange(e.target.value)}
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
                          onSelectClient(client);
                          onClose();
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
                                <UserCheck
                                  className="h-3.5 w-3.5 text-[#8E95A0] shrink-0"
                                  strokeWidth={1.5}
                                />
                                <span className="truncate">{client.contact_person}</span>
                              </>
                            ) : (
                              <span className="text-[#636B78]">Контакт не указан</span>
                            )}
                          </span>
                          <div className="flex items-center gap-1.5">
                            {isSelected && (
                              <Badge variant="ebGold" className="text-[9px]">
                                Выбран
                              </Badge>
                            )}
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                onClose();
                                onEditClient(client);
                              }}
                              aria-label={`Редактировать клиента ${client.company_name}`}
                              title="Редактировать или архивировать клиента"
                              className="inline-flex h-6 w-6 items-center justify-center rounded-[5px] border border-[#262D35] bg-[#12161A] text-[#8E95A0] transition-colors hover:border-[#E5C378] hover:text-[#E5C378]"
                            >
                              <Pencil className="h-3 w-3" strokeWidth={1.75} />
                            </button>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              <div className="mt-3 border-t border-[#21262F] pt-3">
                <button
                  type="button"
                  onClick={() => {
                    onClose();
                    onCreateClient();
                  }}
                  className="flex w-full items-center justify-center gap-1.5 rounded-[7px] border border-[#7C5A20]/70 bg-[#1E190E] px-3 py-2 text-xs font-semibold text-[#E5C378] transition-colors hover:border-[#E5C378] hover:bg-[#261E0F] hover:text-white cursor-pointer"
                >
                  <Plus className="h-3.5 w-3.5" strokeWidth={2.25} />
                  <span>Новый клиент</span>
                </button>
              </div>
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
