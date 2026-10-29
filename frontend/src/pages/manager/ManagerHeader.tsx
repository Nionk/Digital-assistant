import * as React from "react";
import {
  Flame,
  PanelLeftClose,
  PanelLeftOpen,
  Layers,
  Database,
  Clock,
  ChevronDown,
} from "lucide-react";
import type { BurningDeadlineOut } from "@/api/types";
import type { ManagerWorkspaceMode } from "@/store/useManagerStore";
import { formatDateShort, formatRub, getDaysUntil } from "@/lib/formatters";
import { cn } from "@/lib/utils";

interface ManagerHeaderProps {
  workspaceMode: ManagerWorkspaceMode;
  onModeChange: (mode: ManagerWorkspaceMode) => void;
  isSidebarCollapsed: boolean;
  onToggleSidebar: () => void;
  burningDeadlines: BurningDeadlineOut[];
  eventsCount?: number;
}

export function ManagerHeader({
  workspaceMode,
  onModeChange,
  isSidebarCollapsed,
  onToggleSidebar,
  burningDeadlines,
  eventsCount,
}: ManagerHeaderProps) {
  const [isDeadlinesOpen, setIsDeadlinesOpen] = React.useState(false);
  const dropdownRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!isDeadlinesOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsDeadlinesOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isDeadlinesOpen]);

  return (
    <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center justify-between border-b border-border bg-surface px-4">
      {/* Левая группа: сворачивание колонки клиентов + логотип */}
      <div className="flex items-center gap-3">
        {workspaceMode === "matching" && (
          <button
            type="button"
            onClick={onToggleSidebar}
            title={
              isSidebarCollapsed
                ? "Развернуть список клиентов"
                : "Свернуть список клиентов"
            }
            className="flex h-8 w-8 items-center justify-center rounded-control border border-border bg-canvas/70 text-ink-secondary transition-colors hover:bg-surface-muted hover:text-ink"
          >
            {isSidebarCollapsed ? (
              <PanelLeftOpen className="h-4 w-4" strokeWidth={1.5} />
            ) : (
              <PanelLeftClose className="h-4 w-4" strokeWidth={1.5} />
            )}
          </button>
        )}

        <div className="flex items-center gap-2.5">
          <div className="flex h-7 w-7 items-center justify-center rounded-badge bg-pine text-xs font-bold tracking-wider text-white">
            СК
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-sm font-semibold tracking-tight text-ink">
              СКАРТ
            </span>
            <span className="hidden text-xs text-ink-muted sm:inline">
              · Сопровождение отраслевых мероприятий
            </span>
          </div>
        </div>
      </div>

      {/* Центральный переключатель режима */}
      <div className="flex items-center rounded-control border border-border bg-canvas p-0.5">
        <button
          type="button"
          onClick={() => onModeChange("matching")}
          className={cn(
            "inline-flex items-center gap-1.5 rounded-[6px] px-3 py-1 text-xs font-medium transition-all",
            workspaceMode === "matching"
              ? "bg-surface text-ink shadow-sm"
              : "text-ink-muted hover:text-ink"
          )}
        >
          <Layers className="h-3.5 w-3.5" strokeWidth={1.5} />
          <span>Подбор клиентам</span>
        </button>

        <button
          type="button"
          onClick={() => onModeChange("catalog")}
          className={cn(
            "inline-flex items-center gap-1.5 rounded-[6px] px-3 py-1 text-xs font-medium transition-all",
            workspaceMode === "catalog"
              ? "bg-surface text-ink shadow-sm"
              : "text-ink-muted hover:text-ink"
          )}
        >
          <Database className="h-3.5 w-3.5" strokeWidth={1.5} />
          <span>База площадок</span>
          {typeof eventsCount === "number" && eventsCount > 0 && (
            <span className="rounded bg-surface-muted px-1.5 py-0.2 text-[10px] font-semibold text-ink-secondary tabular-nums">
              {eventsCount}
            </span>
          )}
        </button>
      </div>

      {/* Правая группа: Поповер горящих дедлайнов Early Bird */}
      <div className="relative" ref={dropdownRef}>
        <button
          type="button"
          onClick={() => setIsDeadlinesOpen((prev) => !prev)}
          className={cn(
            "inline-flex items-center gap-2 rounded-control border px-3 py-1.5 text-xs font-medium transition-colors tabular-nums",
            burningDeadlines.length > 0
              ? "border-terracotta-border bg-terracotta-tint text-terracotta hover:bg-terracotta/15"
              : "border-border bg-canvas text-ink-secondary hover:bg-surface-muted"
          )}
        >
          <Flame className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} />
          <span className="hidden md:inline">Дедлайны Early Bird:</span>
          <span className="font-semibold">{burningDeadlines.length}</span>
          <ChevronDown className="h-3.5 w-3.5 opacity-70" strokeWidth={1.5} />
        </button>

        {isDeadlinesOpen && (
          <div className="absolute right-0 mt-2 w-80 sm:w-96 rounded-card border border-border bg-surface p-4 shadow-elevated z-50">
            <div className="flex items-center justify-between border-b border-border pb-2.5">
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wider text-ink">
                  Контроль условий Early Bird
                </h3>
                <p className="mt-0.5 text-[11px] text-ink-muted">
                  Ближайшие даты истечения льготных тарифов организаторов
                </p>
              </div>
              <span className="rounded-badge bg-terracotta-tint px-2 py-0.5 text-[11px] font-semibold text-terracotta border border-terracotta-border tabular-nums">
                {burningDeadlines.length} активных
              </span>
            </div>

            {burningDeadlines.length === 0 ? (
              <p className="py-4 text-center text-xs text-ink-muted">
                Нет горящих дедлайнов на ближайшие дни
              </p>
            ) : (
              <div className="mt-2.5 max-h-72 space-y-2 overflow-y-auto pr-1 scrollbar-thin">
                {burningDeadlines.map((item) => {
                  const daysLeft = getDaysUntil(item.early_bird_deadline);
                  const isUrgent = daysLeft !== null && daysLeft <= 3;

                  return (
                    <div
                      key={item.event_id}
                      className="rounded-control border border-border/80 bg-canvas/60 p-2.5 transition-colors hover:border-border-strong"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-xs font-medium leading-snug text-ink">
                          {item.event_title}
                        </p>
                        <span className="shrink-0 rounded-badge bg-sage-tint px-1.5 py-0.5 text-[11px] font-semibold text-sage border border-sage-border tabular-nums">
                          выгода {formatRub(item.potential_savings)}
                        </span>
                      </div>
                      <div className="mt-1.5 flex items-center justify-between text-[11px] text-ink-muted tabular-nums">
                        <span className="inline-flex items-center gap-1">
                          <Clock className="h-3 w-3" strokeWidth={1.5} />
                          Дедлайн: {formatDateShort(item.early_bird_deadline)}
                        </span>
                        {daysLeft !== null && (
                          <span
                            className={cn(
                              "font-medium",
                              isUrgent ? "text-terracotta" : "text-ink-secondary"
                            )}
                          >
                            {daysLeft === 0
                              ? "Истекает сегодня"
                              : daysLeft === 1
                                ? "Остался 1 день"
                                : `Осталось дн.: ${daysLeft}`}
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
    </header>
  );
}

