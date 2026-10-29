import * as React from "react";
import {
  Layers,
  Database,
  Clock,
  ChevronDown,
} from "lucide-react";
import type { BurningDeadlineOut } from "@/api/types";
import { useManagerStore, type ManagerWorkspaceMode } from "@/store/useManagerStore";
import { formatDateShort, formatRub, getDaysUntil } from "@/lib/formatters";
import { ProducerProfileModal } from "@/components/ui/producer-profile-modal";
import logoImage from "@/assets/images/logo.png";
import fireImage from "@/assets/images/fire.png";
import { cn } from "@/lib/utils";

interface ManagerHeaderProps {
  workspaceMode: ManagerWorkspaceMode;
  onModeChange: (mode: ManagerWorkspaceMode) => void;
  isSidebarCollapsed?: boolean;
  onToggleSidebar?: () => void;
  burningDeadlines: BurningDeadlineOut[];
  eventsCount?: number;
}

export function ManagerHeader({
  workspaceMode,
  onModeChange,
  burningDeadlines,
  eventsCount = 15,
}: ManagerHeaderProps) {
  const [isDeadlinesOpen, setIsDeadlinesOpen] = React.useState(false);
  const [flashTab, setFlashTab] = React.useState<ManagerWorkspaceMode | null>(null);
  const dropdownRef = React.useRef<HTMLDivElement>(null);

  const currentProducer = useManagerStore((s) => s.currentProducer);
  const isProducerModalOpen = useManagerStore((s) => s.isProducerModalOpen);
  const setProducerModalOpen = useManagerStore((s) => s.setProducerModalOpen);

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

  const handleSelectMode = (mode: ManagerWorkspaceMode) => {
    setFlashTab(mode);
    onModeChange(mode);
    setTimeout(() => {
      setFlashTab(null);
    }, 200);
  };

  return (
    <header className="sticky top-0 z-30 flex h-[67px] shrink-0 items-center justify-between border-b border-[#1A2026] bg-[#0E1215] px-4 sm:px-6 shadow-sm relative">
      {/* Тонкая неоново-голубая линия в цвет куба логотипа, отделяющая хедер от основного блока */}
      <div className="pointer-events-none absolute bottom-0 left-0 right-0 h-[1px] bg-gradient-to-r from-[#1E3A8A]/30 via-[#38BDF8]/80 to-[#1E3A8A]/30 shadow-[0_1px_6px_rgba(56,189,248,0.35)]" />

      {/* 1. Левая часть: ТОЛЬКО logo.png, клик ведет на подбор клиентам */}
      <div className="flex items-center">
        <button
          type="button"
          onClick={() => handleSelectMode("matching")}
          className="flex items-center transition-opacity hover:opacity-90 focus:outline-none"
          title="СКАРТ.AI — Подбор клиентам"
        >
          <img
            src={logoImage}
            alt="СКАРТ.AI"
            className="h-8 sm:h-[34px] w-auto object-contain shrink-0"
          />
        </button>
      </div>

      {/* 2. Центральная часть: Селекторы с переливом в золотой цвет, миганием и подчеркиванием */}
      <nav className="flex items-center rounded-[8px] border border-[#232931] bg-[#12161A]/90 p-1 gap-1 shadow-inner">
        {/* Вкладка: Подбор клиентам */}
        <button
          type="button"
          onClick={() => handleSelectMode("matching")}
          className={cn(
            "group relative flex items-center gap-2 rounded-[6px] px-3.5 py-1.5 text-xs font-medium transition-all duration-200 select-none cursor-pointer overflow-hidden",
            workspaceMode === "matching"
              ? "bg-[#1A2128] text-white"
              : "bg-transparent text-[#8E95A0]",
            // Золотой перелив при наведении (текст и иконка становятся черными)
            "hover:bg-gradient-to-r hover:from-[#D4AF37] hover:via-[#E5C378] hover:to-[#D4AF37] hover:text-[#0E1215] hover:font-semibold hover:shadow-[0_0_12px_rgba(229,195,120,0.35)]",
            // Эффект вспышки при клике
            flashTab === "matching" && "scale-[0.98] brightness-150 ring-1 ring-[#E5C378]"
          )}
        >
          <Layers className="h-3.5 w-3.5 text-inherit transition-colors shrink-0" strokeWidth={1.75} />
          <span>Подбор клиентам</span>

          {/* Золотая светящаяся линия подчеркивания в активном состоянии */}
          {workspaceMode === "matching" && (
            <span className="absolute bottom-0 left-2 right-2 h-[2px] rounded-full bg-gradient-to-r from-transparent via-[#E5C378] to-transparent shadow-[0_0_8px_rgba(229,195,120,0.7)]" />
          )}
        </button>

        {/* Вкладка: База площадок */}
        <button
          type="button"
          onClick={() => handleSelectMode("catalog")}
          className={cn(
            "group relative flex items-center gap-2 rounded-[6px] px-3.5 py-1.5 text-xs font-medium transition-all duration-200 select-none cursor-pointer overflow-hidden",
            workspaceMode === "catalog"
              ? "bg-[#1A2128] text-white"
              : "bg-transparent text-[#8E95A0]",
            // Золотой перелив при наведении
            "hover:bg-gradient-to-r hover:from-[#D4AF37] hover:via-[#E5C378] hover:to-[#D4AF37] hover:text-[#0E1215] hover:font-semibold hover:shadow-[0_0_12px_rgba(229,195,120,0.35)]",
            // Эффект вспышки при клике
            flashTab === "catalog" && "scale-[0.98] brightness-150 ring-1 ring-[#E5C378]"
          )}
        >
          <Database className="h-3.5 w-3.5 text-inherit transition-colors shrink-0" strokeWidth={1.75} />
          <span>База площадок</span>
          <span
            className={cn(
              "rounded bg-[#1A252A] px-1.5 py-0.2 text-[10px] font-semibold text-[#529E85] tabular-nums transition-colors",
              "group-hover:bg-[#0E1215]/20 group-hover:text-[#0E1215]"
            )}
          >
            {eventsCount}
          </span>

          {/* Золотая светящаяся линия подчеркивания в активном состоянии */}
          {workspaceMode === "catalog" && (
            <span className="absolute bottom-0 left-2 right-2 h-[2px] rounded-full bg-gradient-to-r from-transparent via-[#E5C378] to-transparent shadow-[0_0_8px_rgba(229,195,120,0.7)]" />
          )}
        </button>
      </nav>

      {/* 3. Правая часть: Дедлайны (fire.png + золотая цифра) + Разделитель + Профиль */}
      <div className="flex items-center gap-2 sm:gap-2.5">
        {/* Кнопка дедлайнов Early Bird */}
        <div className="relative" ref={dropdownRef}>
          <button
            type="button"
            onClick={() => setIsDeadlinesOpen((prev) => !prev)}
            className="inline-flex items-center gap-2 rounded-[8px] border border-[#262D35] bg-[#11161B] px-3 py-1.5 text-xs font-medium text-[#D1D5DB] transition-all hover:border-[#3E4957] hover:bg-[#161C22] tabular-nums shadow-sm"
          >
            <img
              src={fireImage}
              alt="Огонь"
              className="h-4 w-auto object-contain shrink-0"
            />
            <span className="hidden sm:inline">Дедлайны Early Bird:</span>
            <span className="sm:hidden">Дедлайны:</span>
            <span className="font-bold text-[#E5C378]">
              {burningDeadlines.length}
            </span>
            <ChevronDown className="h-3.5 w-3.5 text-[#7E8794]" strokeWidth={1.75} />
          </button>

          {/* Выпадающий список дедлайнов точно по макету (media_1793287754782_2088a7c6.jpg) */}
          {isDeadlinesOpen && (
            <div className="absolute right-0 mt-2 w-[340px] sm:w-[440px] rounded-[12px] border border-[#262B33] bg-[#0E1116] p-4 sm:p-5 shadow-2xl shadow-black/80 z-50 text-white select-none">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="text-[11px] font-semibold uppercase tracking-wider text-[#8E95A0]">
                    Контроль условий Early Bird
                  </h3>
                  <p className="mt-1 text-xs text-[#727985]">
                    Ближайшие даты истечения льготных тарифов организаторов
                  </p>
                </div>
                <span className="shrink-0 rounded-[4px] border border-[#7C4A19] bg-[#22160C]/90 px-2.5 py-1 text-[11px] font-bold text-[#E59837] tracking-wider tabular-nums">
                  [ {burningDeadlines.length} АКТИВНЫХ ]
                </span>
              </div>

              <div className="border-b border-[#21262F] my-3.5" />

              {burningDeadlines.length === 0 ? (
                <p className="py-4 text-center text-xs text-[#8E95A0]">
                  Нет горящих дедлайнов на ближайшие дни
                </p>
              ) : (
                <div className="max-h-[380px] space-y-2.5 overflow-y-auto pr-1 scrollbar-thin">
                  {burningDeadlines.map((item) => {
                    const daysLeft = getDaysUntil(item.early_bird_deadline);

                    return (
                      <div
                        key={item.event_id}
                        className="rounded-[8px] border border-[#262C35] bg-[#1A1E24] p-3 transition-colors hover:border-[#38414F] hover:bg-[#1E232B]"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <p className="text-[13px] font-medium leading-snug text-white">
                            {item.event_title}
                          </p>
                          <span className="shrink-0 rounded-[4px] border border-[#1E5241] bg-[#0E241E]/90 px-2 py-0.5 text-[11px] font-medium text-[#34D399] tabular-nums">
                            выгода {formatRub(item.potential_savings)}
                          </span>
                        </div>
                        <div className="mt-2.5 flex items-center justify-between text-xs text-[#8E95A0] tabular-nums">
                          <span className="inline-flex items-center gap-1.5">
                            <Clock className="h-3.5 w-3.5 text-[#8E95A0]" strokeWidth={1.5} />
                            Дедлайн: {formatDateShort(item.early_bird_deadline)}
                          </span>
                          <span>
                            Осталось дн.: {daysLeft ?? "—"}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Тонкий вертикальный разделитель */}
        <div className="h-6 w-[1px] bg-[#2A313C] mx-0.5 sm:mx-1" />

        {/* Профиль продюсера точь-в-точь по макету */}
        <button
          type="button"
          onClick={() => setProducerModalOpen(true)}
          className="group flex items-center gap-2.5 rounded-[8px] p-1 transition-opacity hover:opacity-90 focus:outline-none"
          title="Сменить куратора или открыть терминал продюсера"
        >
          <div className="flex h-7 w-7 items-center justify-center rounded-[6px] border border-[#2D3540] bg-[#161B21] text-[11px] font-bold text-white tabular-nums shadow-sm">
            {currentProducer.avatarText}
          </div>
          <div className="hidden sm:block text-left">
            <span className="block text-xs font-semibold leading-tight text-white group-hover:text-[#E5C378] transition-colors">
              {currentProducer.name}
            </span>
            <span className="block text-[9px] font-bold uppercase tracking-wider text-[#7E8794] leading-tight">
              {currentProducer.role}
            </span>
          </div>
        </button>
      </div>

      {/* Модальное окно терминала продюсера */}
      <ProducerProfileModal
        isOpen={isProducerModalOpen}
        onClose={() => setProducerModalOpen(false)}
      />
    </header>
  );
}

