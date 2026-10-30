import * as React from "react";
import {
  Layers,
  Database,
  Clock,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import type { BurningDeadlineOut } from "@/api/types";
import { useManagerStore, type ManagerWorkspaceMode } from "@/store/useManagerStore";
import { formatDateShort, formatRub, getDaysUntil } from "@/lib/formatters";
import { ProducerProfileModal } from "@/components/ui/producer-profile-modal";
import { Badge } from "@/components/ui/badge";
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
  const dropdownRef = React.useRef<HTMLDivElement>(null);

  const currentProducer = useManagerStore((s) => s.currentProducer);
  const isProducerModalOpen = useManagerStore((s) => s.isProducerModalOpen);
  const setProducerModalOpen = useManagerStore((s) => s.setProducerModalOpen);
  const navigateToCatalogEvent = useManagerStore((s) => s.navigateToCatalogEvent);

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
    <header className="sticky top-0 z-30 flex h-[67px] shrink-0 items-center justify-between border-b border-[#1A2026] bg-[#0E1215] px-4 sm:px-6 shadow-sm relative">
      {/* Деликатная бронзово-золотая нить переплёта, отделяющая хедер от контента */}
      <div className="pointer-events-none absolute bottom-0 left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-[#7C5A20]/35 to-transparent" />

      {/* 1. Левая часть: ТОЛЬКО logo.png, клик ведет на подбор клиентам */}
      <div className="flex items-center">
        <button
          type="button"
          onClick={() => onModeChange("matching")}
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
          onClick={() => onModeChange("matching")}
          className={cn(
            "group relative flex items-center gap-2 rounded-[6px] px-3.5 py-1.5 text-xs font-medium select-none cursor-pointer transition-colors duration-150 outline-none",
            workspaceMode === "matching"
              ? "bg-[#1A2128] text-white shadow-sm"
              : "bg-transparent text-[#8E95A0] hover:bg-[#1A2128]/70 hover:text-white"
          )}
        >
          <Layers
            className={cn(
              "h-3.5 w-3.5 shrink-0 transition-colors duration-150",
              workspaceMode === "matching" ? "text-[#E5C378]" : "text-[#8E95A0] group-hover:text-[#E5C378]"
            )}
            strokeWidth={1.75}
          />
          <span className="transition-colors duration-150">
            Подбор клиентам
          </span>

          {/* Золотая светящаяся линия подчеркивания: плавно расходится от центра к краям */}
          <span
            className={cn(
              "absolute bottom-0 left-0 right-0 h-[2.5px] rounded-b-[6px] bg-gradient-to-r from-[#D4AF37] via-[#E5C378] to-[#D4AF37] shadow-[0_0_10px_rgba(229,195,120,0.75)]",
              "transform origin-center transition-all duration-300 ease-out",
              workspaceMode === "matching"
                ? "scale-x-100 opacity-100"
                : "scale-x-0 opacity-0 pointer-events-none"
            )}
          />
        </button>

        {/* Вкладка: База площадок */}
        <button
          type="button"
          onClick={() => onModeChange("catalog")}
          className={cn(
            "group relative flex items-center gap-2 rounded-[6px] px-3.5 py-1.5 text-xs font-medium select-none cursor-pointer transition-colors duration-150 outline-none",
            workspaceMode === "catalog"
              ? "bg-[#1A2128] text-white shadow-sm"
              : "bg-transparent text-[#8E95A0] hover:bg-[#1A2128]/70 hover:text-white"
          )}
        >
          <Database
            className={cn(
              "h-3.5 w-3.5 shrink-0 transition-colors duration-150",
              workspaceMode === "catalog" ? "text-[#E5C378]" : "text-[#8E95A0] group-hover:text-[#E5C378]"
            )}
            strokeWidth={1.75}
          />
          <span className="transition-colors duration-150">
            База площадок
          </span>
          <span
            className={cn(
              "rounded bg-[#1A252A] px-1.5 py-0.5 text-[10px] font-semibold text-[#529E85] tabular-nums transition-colors duration-150",
              "group-hover:bg-[#1E252E] group-hover:text-[#34D399]"
            )}
          >
            {eventsCount}
          </span>

          {/* Золотая светящаяся линия подчеркивания: плавно расходится от центра к краям */}
          <span
            className={cn(
              "absolute bottom-0 left-0 right-0 h-[2.5px] rounded-b-[6px] bg-gradient-to-r from-[#D4AF37] via-[#E5C378] to-[#D4AF37] shadow-[0_0_10px_rgba(229,195,120,0.75)]",
              "transform origin-center transition-all duration-300 ease-out",
              workspaceMode === "catalog"
                ? "scale-x-100 opacity-100"
                : "scale-x-0 opacity-0 pointer-events-none"
            )}
          />
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

          {/* Выпадающий список дедлайнов с плавной анимацией */}
          <AnimatePresence>
            {isDeadlinesOpen && (
              <motion.div
                initial={{ opacity: 0, y: -6, scale: 0.98 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -4, scale: 0.98 }}
                transition={{ duration: 0.18, ease: "easeOut" }}
                className="absolute right-0 mt-2 w-[340px] sm:w-[440px] rounded-[12px] border border-[#262B33] bg-[#0E1116] p-4 sm:p-5 shadow-2xl shadow-black/80 z-50 text-white select-none"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h3 className="text-[11px] font-serif italic font-semibold text-[#8E95A0]">
                      Контроль условий Early Bird
                    </h3>
                    <p className="mt-1 text-xs text-[#727985]">
                      Ближайшие даты истечения льготных тарифов организаторов
                    </p>
                  </div>
                  <Badge variant="ebAmber" className="text-[11px]">
                    {burningDeadlines.length} активных
                  </Badge>
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
                          onClick={() => {
                            navigateToCatalogEvent(item.event_id);
                            setIsDeadlinesOpen(false);
                          }}
                          title="Нажмите, чтобы открыть подробную информацию и тарифы в Базе площадок"
                          className="group/deadline rounded-[8px] border border-[#262C35] bg-[#1A1E24] p-3 transition-colors hover:border-[#E5C378] hover:bg-[#1E252E] cursor-pointer"
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0 flex-1">
                              <p className="text-[13px] font-medium leading-snug text-white group-hover/deadline:text-[#E5C378] transition-colors">
                                {item.event_title}
                              </p>
                            </div>
                            <Badge variant="ebEmerald" className="shrink-0 py-1 px-3">
                              <span className="flex flex-col items-center leading-tight">
                                <span className="text-[9px] uppercase tracking-wider opacity-90 font-semibold">
                                  Выгода
                                </span>
                                <span className="whitespace-nowrap font-bold text-xs">
                                  {formatRub(item.potential_savings)}
                                </span>
                              </span>
                            </Badge>
                          </div>
                          <div className="mt-2.5 flex items-center justify-between text-xs text-[#8E95A0] tabular-nums">
                            <span className="inline-flex items-center gap-1.5">
                              <Clock className="h-3.5 w-3.5 text-[#8E95A0]" strokeWidth={1.5} />
                              Дедлайн: {formatDateShort(item.early_bird_deadline)}
                            </span>
                            <span className="inline-flex items-center gap-1 font-serif italic text-[11px] text-[#8E95A0] group-hover/deadline:text-[#E5C378] transition-colors">
                              <span>Осталось дн.: {daysLeft ?? "—"}</span>
                              <ChevronRight className="h-3 w-3 stroke-[2] transition-transform group-hover/deadline:translate-x-0.5" />
                            </span>
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

        {/* Тонкий вертикальный разделитель */}
        <div className="h-6 w-[1px] bg-[#2A313C] mx-0.5 sm:mx-1" />

        {/* Профиль продюсера точь-в-точь по макету */}
        <button
          type="button"
          onClick={() => setProducerModalOpen(true)}
          className="group flex items-center gap-2.5 rounded-[8px] p-1 transition-opacity hover:opacity-90 focus:outline-none"
          title="Сменить куратора или открыть терминал продюсера"
        >
          <div className="flex h-7 w-7 items-center justify-center rounded-[6px] border border-[#7C5A20]/60 bg-[#161B21] text-[11px] font-bold text-white tabular-nums shadow-sm group-hover:border-[#E5C378] group-hover:text-[#E5C378] transition-colors">
            {currentProducer.avatarText}
          </div>
          <div className="hidden sm:block text-left">
            <span className="block text-xs font-semibold leading-tight text-white group-hover:text-[#E5C378] transition-colors">
              {currentProducer.name}
            </span>
            <span className="block font-serif italic text-[11px] text-[#8E95A0] leading-tight group-hover:text-[#E5C378]/80 transition-colors">
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

