import * as React from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  X,
  Radar,
  Play,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  AlertCircle,
} from "lucide-react";
import { toast } from "sonner";
import { ApiError } from "@/api/client";
import { useRunScraperMutation } from "@/api/queries";
import type { ScraperRunOut, ScraperSourceKey } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CustomSelect, type CustomSelectOption } from "@/components/ui/custom-select";

interface ScraperRunModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const SCRAPER_SOURCE_META: Record<
  ScraperSourceKey,
  { label: string; subLabel: string }
> = {
  all: {
    label: "Все отраслевые площадки",
    subLabel: "Полный обход",
  },
  expomap_construction: {
    label: "Expomap — Строительство",
    subLabel: "expomap.ru",
  },
  expomap_design: {
    label: "Expomap — Дизайн",
    subLabel: "expomap.ru",
  },
  architime: {
    label: "ARCHITIME",
    subLabel: "architime.ru",
  },
  archi_ru: {
    label: "Архи.ру",
    subLabel: "archi.ru",
  },
  helpinver: {
    label: "Хелпинвер",
    subLabel: "helpinver.com",
  },
  archdialog: {
    label: "АрхДиалог (Timepad)",
    subLabel: "timepad.ru",
  },
  design_mate: {
    label: "Design Mate",
    subLabel: "design-mate.ru",
  },
  votkuda: {
    label: "ВотКуда",
    subLabel: "votkuda.ru",
  },
  archdaily: {
    label: "ArchDaily",
    subLabel: "archdaily.com",
  },
};

const SCRAPER_SOURCE_OPTIONS: CustomSelectOption<ScraperSourceKey>[] = (
  Object.keys(SCRAPER_SOURCE_META) as ScraperSourceKey[]
).map((key) => ({
  value: key,
  label: SCRAPER_SOURCE_META[key].label,
  subLabel: SCRAPER_SOURCE_META[key].subLabel,
}));

interface ScraperFeedbackState {
  tone: "success" | "warning" | "error";
  title: string;
  message: string;
  statusBadge?: string;
}

function isAlreadyRunningResponse(res: ScraperRunOut): boolean {
  const lower = res.message.toLowerCase();
  return (
    lower.includes("уже выполняется") ||
    lower.includes("повторный запуск отклонен")
  );
}

export function ScraperRunModal({ isOpen, onClose }: ScraperRunModalProps) {
  const runScraperMutation = useRunScraperMutation();

  const [mounted, setMounted] = React.useState(false);
  const [selectedSource, setSelectedSource] =
    React.useState<ScraperSourceKey>("all");
  const [feedback, setFeedback] = React.useState<ScraperFeedbackState | null>(
    null
  );

  React.useEffect(() => {
    setMounted(true);
  }, []);

  React.useEffect(() => {
    if (!isOpen) return;
    setFeedback(null);
  }, [isOpen]);

  React.useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !runScraperMutation.isPending) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose, runScraperMutation.isPending]);

  if (!mounted || typeof document === "undefined") return null;

  const handleRun = async () => {
    setFeedback(null);
    try {
      const res = await runScraperMutation.mutateAsync({
        source_key: selectedSource,
      });

      if (res.status === "failed") {
        setFeedback({
          tone: "error",
          title: "Запуск парсера завершился ошибкой",
          message: res.message,
          statusBadge: "Ошибка",
        });
        toast.error(res.message);
        return;
      }

      if (res.status === "queued" && isAlreadyRunningResponse(res)) {
        setFeedback({
          tone: "warning",
          title: "Мониторинг уже выполняется",
          message: res.message,
          statusBadge: "В работе",
        });
        toast.warning(res.message);
        return;
      }

      setFeedback({
        tone: "success",
        title:
          res.status === "completed"
            ? "Сбор данных завершен"
            : "Задача поставлена в фоновую очередь",
        message: res.message,
        statusBadge: res.status === "completed" ? "Завершено" : "В очереди",
      });
      toast.success(res.message);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        const detail =
          err.detail ||
          "Задача мониторинга уже выполняется в фоне. Дождитесь её завершения.";
        setFeedback({
          tone: "warning",
          title: "Конфликт запуска (409 Conflict)",
          message: detail,
          statusBadge: "Уже запущен",
        });
        toast.warning(detail);
        return;
      }

      const message =
        err instanceof Error
          ? err.message
          : "Не удалось поставить задачу парсинга в очередь.";
      setFeedback({
        tone: "error",
        title: "Ошибка запуска скрейпера",
        message,
      });
      toast.error(message);
    }
  };

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
            onClick={() => {
              if (!runScraperMutation.isPending) onClose();
            }}
          />

          <motion.div
            key="scraper-modal-content"
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 8 }}
            transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
            className="relative z-10 w-full max-w-md rounded-[10px] border border-[#7C5A20] bg-[#161B22] text-white shadow-[0_25px_60px_-15px_rgba(0,0,0,0.9),0_0_20px_rgba(229,195,120,0.1)]"
          >
            <div className="p-4 sm:p-5">
              <div className="flex items-center justify-between border-b border-[#21262F] pb-3">
                <div className="flex items-center gap-2">
                  <Radar className="h-4 w-4 text-[#E5C378]" strokeWidth={1.75} />
                  <h2 className="font-serif italic text-base font-semibold tracking-tight text-[#E5C378]">
                    Запуск мониторинга площадок
                  </h2>
                </div>

                <button
                  type="button"
                  disabled={runScraperMutation.isPending}
                  onClick={onClose}
                  aria-label="Закрыть окно"
                  className="rounded-[6px] border border-[#7C5A20]/40 bg-[#12161A] p-1.5 text-[#E5C378] transition-all duration-150 hover:border-[#E5C378] hover:bg-[#261E0F] hover:text-white disabled:opacity-50 outline-none"
                >
                  <X className="h-4 w-4 stroke-[2]" />
                </button>
              </div>

              <div className="mt-4 space-y-3.5">
                <div>
                  <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-[#8E95A0]">
                    Источник сбора данных
                  </span>
                  <CustomSelect<ScraperSourceKey>
                    value={selectedSource}
                    onChange={setSelectedSource}
                    options={SCRAPER_SOURCE_OPTIONS}
                    disabled={runScraperMutation.isPending}
                    className="w-full"
                    buttonClassName="w-full h-9 px-3 text-xs"
                    menuClassName="w-full"
                  />
                </div>

                {feedback && (
                  <div
                    role="status"
                    className={
                      feedback.tone === "success"
                        ? "rounded-[8px] border border-[#1E5241] bg-[#0E241E]/90 p-3 text-xs space-y-1.5"
                        : feedback.tone === "warning"
                          ? "rounded-[8px] border border-[#7C4A19] bg-[#22160C] p-3 text-xs space-y-1.5"
                          : "rounded-[8px] border border-[#EA4335]/40 bg-[#EA4335]/10 p-3 text-xs space-y-1.5"
                    }
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-1.5 font-semibold">
                        {feedback.tone === "success" ? (
                          <CheckCircle2 className="h-4 w-4 shrink-0 text-[#34D399]" />
                        ) : feedback.tone === "warning" ? (
                          <AlertTriangle className="h-4 w-4 shrink-0 text-[#E59837]" />
                        ) : (
                          <AlertCircle className="h-4 w-4 shrink-0 text-[#F87171]" />
                        )}
                        <span
                          className={
                            feedback.tone === "success"
                              ? "text-[#34D399]"
                              : feedback.tone === "warning"
                                ? "text-[#E59837]"
                                : "text-[#FCA5A5]"
                          }
                        >
                          {feedback.title}
                        </span>
                      </div>
                      {feedback.statusBadge && (
                        <Badge
                          variant={
                            feedback.tone === "success"
                              ? "ebEmerald"
                              : feedback.tone === "warning"
                                ? "ebAmber"
                                : "ebRose"
                          }
                          asSlanted={false}
                          className="text-[11px] shrink-0"
                        >
                          {feedback.statusBadge}
                        </Badge>
                      )}
                    </div>
                    <p className="text-[#D1D5DB] leading-relaxed">
                      {feedback.message}
                    </p>
                  </div>
                )}

                <div className="flex items-center justify-end gap-2 border-t border-[#21262F] pt-3">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={runScraperMutation.isPending}
                    onClick={onClose}
                    className="border-[#262D35] bg-[#12161A] text-xs text-[#D1D5DB] hover:border-[#E5C378] hover:text-white"
                  >
                    Закрыть
                  </Button>
                  <Button
                    type="button"
                    variant="monolith"
                    size="sm"
                    disabled={runScraperMutation.isPending}
                    onClick={handleRun}
                    className="text-xs font-semibold px-4"
                  >
                    {runScraperMutation.isPending ? (
                      <>
                        <Loader2 className="h-3.5 w-3.5 animate-spin text-[#E5C378]" />
                        <span>Запуск...</span>
                      </>
                    ) : (
                      <>
                        <Play className="h-3.5 w-3.5 text-[#E5C378] monolith-icon" />
                        <span>Запустить парсер</span>
                      </>
                    )}
                  </Button>
                </div>
              </div>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>,
    document.body
  );
}
