import { Search, Building2, UserCheck, PanelLeftClose, Users } from "lucide-react";
import type { ClientSummaryOut } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface ClientSidebarProps {
  clients: ClientSummaryOut[];
  selectedClientId: number | null;
  searchQuery: string;
  onSearchChange: (q: string) => void;
  onSelectClient: (client: ClientSummaryOut) => void;
  publishedByClientMap: Record<number, { magicToken: string }>;
  hasDraftInSessionMap: Record<number, boolean>;
  onToggleSidebar?: () => void;
}

export function ClientSidebar({
  clients,
  selectedClientId,
  searchQuery,
  onSearchChange,
  onSelectClient,
  publishedByClientMap,
  hasDraftInSessionMap,
  onToggleSidebar,
}: ClientSidebarProps) {
  const filtered = clients.filter((c) => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return true;
    return (
      c.company_name.toLowerCase().includes(q) ||
      (c.contact_person || "").toLowerCase().includes(q)
    );
  });

  return (
    <div className="flex h-full w-full flex-col bg-[#0E1116] text-white">
      {/* Шапка колонки клиентов с кнопкой сворачивания */}
      <div className="flex items-center justify-between border-b border-[#21262F] px-3.5 py-2.5 bg-[#0E1116]">
        <div className="flex items-center gap-1.5">
          <Users className="h-3.5 w-3.5 text-[#E5C378]" strokeWidth={1.75} />
          <span className="text-xs font-bold uppercase tracking-wider text-[#8E95A0]">
            Клиенты
          </span>
          <span className="rounded-[4px] border border-[#7C4A19] bg-[#22160C]/90 px-1.5 py-0.2 text-[10px] font-bold text-[#E59837] tabular-nums">
            {filtered.length}
          </span>
        </div>
        {onToggleSidebar && (
          <button
            type="button"
            onClick={onToggleSidebar}
            title="Свернуть список клиентов"
            className="flex h-7 w-7 items-center justify-center rounded-[6px] border border-[#262D35] bg-[#161B21] text-[#8E95A0] transition-colors hover:border-[#38414F] hover:bg-[#1E232B] hover:text-white"
          >
            <PanelLeftClose className="h-3.5 w-3.5" strokeWidth={1.75} />
          </button>
        )}
      </div>

      {/* Поиск по клиентам */}
      <div className="border-b border-[#21262F] p-3">
        <div className="relative">
          <Search
            className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[#727985]"
            strokeWidth={1.5}
          />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Поиск компании..."
            className="h-8 w-full rounded-[6px] border border-[#262C35] bg-[#161B21] pl-8 pr-2.5 text-xs text-white placeholder:text-[#6B7280] [color-scheme:dark] outline-none focus:outline-none focus:border-[#E5C378] focus:bg-[#181E25] focus:shadow-[0_0_0_1px_rgba(229,195,120,0.25)] transition-colors duration-150"
          />
        </div>
      </div>

      {/* Список карточек клиентов */}
      <div className="flex-1 space-y-1.5 overflow-y-auto px-2 pb-4 scrollbar-thin">
        {filtered.length === 0 ? (
          <p className="px-2 py-6 text-center text-xs text-[#8E95A0]">
            Компании не найдены
          </p>
        ) : (
          filtered.map((client) => {
            const isSelected = client.id === selectedClientId;
            const isPublished =
              Boolean(publishedByClientMap[client.id]) ||
              client.latest_selection_status === "published";
            const isDraft =
              !isPublished &&
              (Boolean(hasDraftInSessionMap[client.id]) ||
                client.latest_selection_status === "draft");

            return (
              <button
                key={client.id}
                type="button"
                onClick={() => onSelectClient(client)}
                className={cn(
                  "group flex w-full flex-col gap-1 rounded-[8px] border px-3 py-2.5 text-left transition-all",
                  isSelected
                    ? "border-[#E5C378] bg-[#1E252E] shadow-sm"
                    : "border-[#262C35] bg-[#1A1E24] hover:border-[#38414F] hover:bg-[#1E232B]"
                )}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <Building2
                      className={cn(
                        "h-3.5 w-3.5 shrink-0",
                        isSelected ? "text-[#E5C378]" : "text-[#8E95A0]"
                      )}
                      strokeWidth={1.5}
                    />
                    <span
                      className={cn(
                        "truncate text-xs font-semibold",
                        isSelected ? "text-white" : "text-[#D1D5DB]"
                      )}
                    >
                      {client.company_name}
                    </span>
                  </div>

                  {/* Индикатор статуса подборки в виде авторской скошенной ячейки */}
                  {isPublished ? (
                    <Badge variant="ebEmerald" className="text-[9px]">
                      КП активно
                    </Badge>
                  ) : isDraft ? (
                    <Badge variant="ebAmber" className="text-[9px]">
                      Черновик
                    </Badge>
                  ) : (
                    <Badge variant="ebSlate" className="text-[9px]">
                      Новый
                    </Badge>
                  )}
                </div>

                {client.contact_person && (
                  <div className="flex items-center gap-1 text-[11px] text-[#8E95A0]">
                    <UserCheck className="h-3 w-3 shrink-0 opacity-75" strokeWidth={1.5} />
                    <span className="truncate">{client.contact_person}</span>
                  </div>
                )}
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}

