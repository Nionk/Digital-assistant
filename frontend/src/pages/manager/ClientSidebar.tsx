import { Search, Building2, UserCheck } from "lucide-react";
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
}

export function ClientSidebar({
  clients,
  selectedClientId,
  searchQuery,
  onSearchChange,
  onSelectClient,
  publishedByClientMap,
  hasDraftInSessionMap,
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
    <aside className="flex w-[260px] shrink-0 flex-col border-r border-border bg-surface/80">
      {/* Поиск по клиентам */}
      <div className="border-b border-border p-3">
        <div className="relative">
          <Search
            className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-faint"
            strokeWidth={1.5}
          />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Поиск компании..."
            className="h-8 w-full rounded-control border border-border bg-canvas pl-8 pr-2.5 text-xs text-ink placeholder:text-ink-faint focus:border-pine focus:bg-surface focus:outline-none"
          />
        </div>
      </div>

      {/* Заголовок списка */}
      <div className="flex items-center justify-between px-3.5 py-2 text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
        <span>Клиенты в работе</span>
        <span className="tabular-nums">{filtered.length}</span>
      </div>

      {/* Список карточек клиентов */}
      <div className="flex-1 space-y-1 overflow-y-auto px-2 pb-4 scrollbar-thin">
        {filtered.length === 0 ? (
          <p className="px-2 py-6 text-center text-xs text-ink-muted">
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
                  "group flex w-full flex-col gap-1 rounded-control border px-3 py-2.5 text-left transition-all",
                  isSelected
                    ? "border-pine bg-pine/5 shadow-sm"
                    : "border-transparent bg-transparent hover:border-border hover:bg-canvas/80"
                )}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <Building2
                      className={cn(
                        "h-3.5 w-3.5 shrink-0",
                        isSelected ? "text-pine" : "text-ink-muted"
                      )}
                      strokeWidth={1.5}
                    />
                    <span
                      className={cn(
                        "truncate text-xs font-semibold",
                        isSelected ? "text-pine" : "text-ink"
                      )}
                    >
                      {client.company_name}
                    </span>
                  </div>

                  {/* Индикатор статуса подборки */}
                  {isPublished ? (
                    <Badge variant="novelSand" className="text-[9px]">
                      КП АКТИВНО
                    </Badge>
                  ) : isDraft ? (
                    <Badge variant="novelGold" className="text-[9px]">
                      ЧЕРНОВИК
                    </Badge>
                  ) : (
                    <Badge variant="darkSubtle" className="text-[9px]">
                      НОВЫЙ
                    </Badge>
                  )}
                </div>

                {client.contact_person && (
                  <div className="flex items-center gap-1 text-[11px] text-ink-muted">
                    <UserCheck className="h-3 w-3 shrink-0 opacity-75" strokeWidth={1.5} />
                    <span className="truncate">{client.contact_person}</span>
                  </div>
                )}
              </button>
            );
          })
        )}
      </div>
    </aside>
  );
}

