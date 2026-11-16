import * as React from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import { History, Play, Radar, Settings2, X } from "lucide-react";
import {
  useLatestScraperRun,
  useScraperRuns,
  useScraperSources,
} from "@/api/queries";
import type { ScraperSourceKey } from "@/api/types";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { ScraperHistoryTab } from "./scraper/ScraperHistoryTab";
import { ScraperRunTab } from "./scraper/ScraperRunTab";
import { ScraperSourcesTab } from "./scraper/ScraperSourcesTab";

interface ScraperRunModalProps {
  isOpen: boolean;
  onClose: () => void;
  onOpenEventDetails?: (eventId: number) => void;
}

type ModalTab = "run" | "sources" | "history";

export function ScraperRunModal({
  isOpen,
  onClose,
  onOpenEventDetails,
}: ScraperRunModalProps) {
  const [mounted, setMounted] = React.useState(false);
  const [activeTab, setActiveTab] = React.useState<ModalTab>("run");
  const [selectedSource, setSelectedSource] =
    React.useState<ScraperSourceKey>("all");

  const sourcesQuery = useScraperSources(isOpen);
  const latestRunQuery = useLatestScraperRun(isOpen);
  const runsHistoryQuery = useScraperRuns(15, isOpen);

  const sources = React.useMemo(
    () => sourcesQuery.data ?? [],
    [sourcesQuery.data]
  );

  React.useEffect(() => {
    setMounted(true);
  }, []);

  React.useEffect(() => {
    if (
      selectedSource !== "all" &&
      sources.length > 0 &&
      !sources.some((src) => src.source_key === selectedSource)
    ) {
      setSelectedSource("all");
    }
  }, [sources, selectedSource]);

  React.useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !event.defaultPrevented) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!mounted || typeof document === "undefined") return null;

  const isLatestActive =
    latestRunQuery.data?.status === "queued" ||
    latestRunQuery.data?.status === "running";

  const handleQuickRunSource = (sourceKey: string) => {
    setSelectedSource(sourceKey);
    setActiveTab("run");
  };

  const tabs: {
    id: ModalTab;
    label: string;
    icon: React.ReactNode;
    badge?: string | number;
    pulse?: boolean;
  }[] = [
    {
      id: "run",
      label: "Запуск и прогресс",
      icon: <Play className="h-3.5 w-3.5" />,
      pulse: isLatestActive,
    },
    {
      id: "sources",
      label: "Площадки и настройки",
      icon: <Settings2 className="h-3.5 w-3.5" />,
      badge: sources.length > 0 ? sources.length : undefined,
    },
    {
      id: "history",
      label: "История прогонов",
      icon: <History className="h-3.5 w-3.5" />,
      badge:
        runsHistoryQuery.data?.items && runsHistoryQuery.data.items.length > 0
          ? runsHistoryQuery.data.items.length
          : undefined,
    },
  ];

  return createPortal(
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4">
          <motion.div
            key="scraper-modal-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18, ease: "easeOut" }}
            className="fixed inset-0 bg-black/75 backdrop-blur-md"
            onClick={onClose}
          />

          <motion.div
            key="scraper-modal-content"
            initial={{ opacity: 0, scale: 0.96, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 8 }}
            transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
            className="relative z-10 w-full max-w-3xl max-h-[85vh] overflow-y-auto scrollbar-thin rounded-[10px] border border-[#7C5A20] bg-[#161B22] text-white shadow-[0_25px_60px_-15px_rgba(0,0,0,0.9),0_0_20px_rgba(229,195,120,0.1)]"
          >
            <div className="p-4 sm:p-5 space-y-4">
              {/* Заголовок */}
              <div className="flex items-center justify-between border-b border-[#21262F] pb-3">
                <div className="flex items-center gap-2.5">
                  <Radar
                    className="h-4 w-4 text-[#E5C378]"
                    strokeWidth={1.75}
                  />
                  <div>
                    <h2 className="font-serif italic text-base font-semibold tracking-tight text-[#E5C378]">
                      Центр управления парсером площадок
                    </h2>
                    <p className="text-[11px] text-[#8E95A0]">
                      Запуск обхода, настройка источников и история сборов
                    </p>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={onClose}
                  aria-label="Закрыть окно"
                  className="rounded-[6px] border border-[#7C5A20]/40 bg-[#12161A] p-1.5 text-[#E5C378] transition-all duration-150 hover:border-[#E5C378] hover:bg-[#261E0F] hover:text-white outline-none cursor-pointer"
                >
                  <X className="h-4 w-4 stroke-[2]" />
                </button>
              </div>

              {/* 3 вкладки */}
              <div
                role="tablist"
                aria-label="Разделы центра управления парсером"
                className="flex flex-wrap gap-1.5 rounded-[8px] border border-[#21262F] bg-[#12161A] p-1"
              >
                {tabs.map((tab) => {
                  const isActive = activeTab === tab.id;
                  return (
                    <button
                      key={tab.id}
                      type="button"
                      role="tab"
                      aria-selected={isActive}
                      onClick={() => setActiveTab(tab.id)}
                      className={cn(
                        "flex-1 min-w-[140px] inline-flex items-center justify-center gap-1.5 rounded-[6px] px-3 py-1.5 text-xs font-medium transition-all cursor-pointer",
                        isActive
                          ? "border border-[#7C5A20] bg-[#1E190E] text-[#E5C378] shadow-xs"
                          : "border border-transparent text-[#8E95A0] hover:bg-[#161B22] hover:text-white"
                      )}
                    >
                      {tab.icon}
                      <span>{tab.label}</span>
                      {tab.pulse && (
                        <span className="h-2 w-2 rounded-full bg-[#34D399] animate-pulse" />
                      )}
                      {tab.badge !== undefined && (
                        <span
                          className={cn(
                            "rounded-full px-1.5 py-0.5 text-[10px] leading-none tabular-nums",
                            isActive
                              ? "bg-[#7C5A20]/40 text-[#E5C378]"
                              : "bg-[#21262F] text-[#8E95A0]"
                          )}
                        >
                          {tab.badge}
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>

              {/* Контент вкладок (сохраняем состояние при переключении пока модалка открыта) */}
              <div
                role="tabpanel"
                hidden={activeTab !== "run"}
                className={activeTab !== "run" ? "hidden" : undefined}
              >
                <ScraperRunTab
                  sources={sources}
                  isLoadingSources={sourcesQuery.isLoading}
                  selectedSource={selectedSource}
                  onSelectSource={setSelectedSource}
                  latestRun={latestRunQuery.data}
                  isLoadingLatestRun={latestRunQuery.isLoading}
                  onSwitchToSourcesTab={() => setActiveTab("sources")}
                  onOpenEventDetails={onOpenEventDetails}
                />
              </div>

              <div
                role="tabpanel"
                hidden={activeTab !== "sources"}
                className={activeTab !== "sources" ? "hidden" : undefined}
              >
                <ScraperSourcesTab
                  sources={sources}
                  isLoading={sourcesQuery.isLoading}
                  onQuickRunSource={handleQuickRunSource}
                />
              </div>

              <div
                role="tabpanel"
                hidden={activeTab !== "history"}
                className={activeTab !== "history" ? "hidden" : undefined}
              >
                <ScraperHistoryTab
                  runs={runsHistoryQuery.data?.items ?? []}
                  isLoading={runsHistoryQuery.isLoading}
                  sources={sources}
                  onOpenEventDetails={onOpenEventDetails}
                />
              </div>

              <div className="flex items-center justify-end border-t border-[#21262F] pt-3">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={onClose}
                  className="border-[#262D35] bg-[#12161A] text-xs text-[#D1D5DB] hover:border-[#E5C378] hover:text-white cursor-pointer"
                >
                  Закрыть
                </Button>
              </div>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>,
    document.body
  );
}
