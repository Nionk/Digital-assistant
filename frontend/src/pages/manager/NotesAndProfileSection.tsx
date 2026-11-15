import * as React from "react";
import {
  ChevronDown,
  ChevronUp,
  ArrowRight,
  FileText,
  Loader2,
} from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import type { ClientQueryExtracted } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ExtractedProfilePanel } from "./notes/ExtractedProfilePanel";

interface NotesAndProfileSectionProps {
  notes: string;
  onNotesChange: (val: string) => void;
  isCollapsed: boolean;
  onToggleCollapsed: (collapsed: boolean) => void;
  isMatching: boolean;
  hasMatchResult: boolean;
  editableProfile: ClientQueryExtracted | undefined;
  onUpdateProfile: (
    updater: (prev: ClientQueryExtracted) => ClientQueryExtracted
  ) => void;
  onRunInitialMatch: () => void;
  onRematchWithOverride: () => void;
}

const DEMO_NOTE_PRESETS = [
  {
    category: "Девелопмент",
    focus: "КРТ · Спикер",
    budget: "400 000 ₽",
    text: "Установочная встреча с ГК Пионер. Продукт: жилые кварталы и проекты КРТ. Ищут на осень–зиму в Москве или Санкт-Петербурге 3 профильных мероприятия (форумы и камерные круглые столы) по КРТ, урбанистике и девелопменту. Минимум на одной площадке хотят выступить спикером в целевой сессии для укрепления экспертной позиции, на остальных — деловые знакомства с застройщиками и ведомствами. Общий бюджет на взносы организаторов — до 400 000 руб.",
  },
  {
    category: "Архитектура",
    focus: "Урбанистика · Конкурсы",
    budget: "300 000 ₽",
    text: "Созвонились с архитектурным бюро. Интересуют 3 площадки в Москве, СПб или онлайн по темам: архитектура, градостроительство, BIM-проектирование и профессиональные конкурсы. Важен выход на главных архитекторов и директоров по продукту девелоперских компаний. Минимум 1 экспертное выступление спикером. Бюджет до 300 000 руб.",
  },
  {
    category: "Производство",
    focus: "Стенд · Встречи",
    budget: "650 000 ₽",
    text: "Производитель фасадных и инженерных систем. Задача: выход на застройщиков жилья, подрядчиков и проектные институты в Москве и регионах. Рассматривают 3 мероприятия: крупный строительный форум (возможен партнёрский пакет со стендом и деловой игрой) + закрытые деловые завтраки руководителей. Общий ориентир бюджета — 650 000 руб.",
  },
];

const MATCHING_STATUS_STEPS = [
  "Анализ заметки и извлечение параметров...",
  "Семантический и FTS-поиск по каталогу площадок...",
  "Комбинаторная оптимизация пакетов без пересечения дат...",
  "Подготовка коммерческого письма и расчёт Early Bird...",
] as const;

export function NotesAndProfileSection({
  notes,
  onNotesChange,
  isCollapsed,
  onToggleCollapsed,
  isMatching,
  hasMatchResult,
  editableProfile,
  onUpdateProfile,
  onRunInitialMatch,
  onRematchWithOverride,
}: NotesAndProfileSectionProps) {
  const [loadingStepIndex, setLoadingStepIndex] = React.useState(0);

  // Последовательная индикация реальных этапов конвейера подбора
  React.useEffect(() => {
    if (!isMatching) {
      setLoadingStepIndex(0);
      return;
    }
    setLoadingStepIndex(0);
    const interval = window.setInterval(() => {
      setLoadingStepIndex((prev) =>
        Math.min(prev + 1, MATCHING_STATUS_STEPS.length - 1)
      );
    }, 3500);
    return () => window.clearInterval(interval);
  }, [isMatching]);

  return (
    <section className="rounded-[12px] border border-[#262D35] bg-[#161B22] shadow-sm relative">
      {/* Шапка блока Шага 01–03 */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#21262F] bg-[#12161A] px-4 py-2.5 rounded-t-[12px]">
        <div className="flex items-baseline gap-2.5 min-w-0">
          <span className="font-serif italic font-bold text-base sm:text-lg text-[#E5C378] select-none leading-none">
            01
          </span>
          <h2 className="font-serif italic text-sm font-semibold tracking-tight text-[#E5C378] sm:text-[15px] leading-snug">
            Запрос клиента и аналитика задач
          </h2>
          {hasMatchResult && isCollapsed && (
            <span className="hidden truncate text-xs text-[#8E95A0] md:inline max-w-[380px]">
              · «{notes.slice(0, 68)}...»
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {hasMatchResult && (
            <button
              type="button"
              onClick={() => onToggleCollapsed(!isCollapsed)}
              className="inline-flex items-center gap-1.5 rounded-[6px] border border-[#262D35] bg-[#161B21] px-2.5 py-1 text-xs font-medium text-[#D1D5DB] transition-colors hover:border-[#E5C378] hover:bg-[#1E252E] hover:text-[#E5C378]"
            >
              <FileText className="h-3.5 w-3.5" strokeWidth={1.5} />
              <span>{isCollapsed ? "Развернуть бриф" : "Свернуть бриф"}</span>
              {isCollapsed ? (
                <ChevronDown className="h-3.5 w-3.5" strokeWidth={1.5} />
              ) : (
                <ChevronUp className="h-3.5 w-3.5" strokeWidth={1.5} />
              )}
            </button>
          )}
        </div>
      </div>

      {/* Раскрываемая область ввода конспекта установочной встречи с плавной анимацией */}
      <AnimatePresence initial={false}>
        {(!isCollapsed || !hasMatchResult) && (
          <motion.div
            key="brief-content"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22, ease: "easeInOut" }}
            className="overflow-hidden"
          >
            <div className="p-4 border-b border-[#21262F] bg-[#161B22]">
              <div className="mb-2.5 flex flex-wrap items-center justify-between gap-2">
                <label className="text-xs font-semibold text-[#D1D5DB]">
                  Конспект установочной встречи с клиентом:
                </label>
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-[11px] font-medium text-[#727985]">Готовые кейсы:</span>
                  {DEMO_NOTE_PRESETS.map((preset) => (
                    <button
                      key={preset.category}
                      type="button"
                      onClick={() => onNotesChange(preset.text)}
                      className="inline-flex items-center gap-1.5 rounded-[4px] border border-[#262D35] bg-[#12161A] px-2 py-0.5 text-[11px] transition-all hover:border-[#E5C378] hover:bg-[#161E28]"
                    >
                      <Badge variant="ebAmber" className="text-[9px]">
                        {preset.category}
                      </Badge>
                      <span className="text-[#D1D5DB] font-medium">{preset.focus}</span>
                      <span className="text-[#8E95A0]">· {preset.budget}</span>
                    </button>
                  ))}
                </div>
              </div>

              <textarea
                rows={3}
                value={notes}
                onChange={(e) => onNotesChange(e.target.value)}
                placeholder="Вводные встречи: задачи участия, ключевые темы, спикерство/стенд, география и лимит бюджета..."
                className="w-full rounded-[8px] border border-[#262D35] bg-[#12161A] p-3 text-sm leading-relaxed text-white placeholder:text-[#6B7280] [color-scheme:dark] outline-none focus:outline-none focus-visible:outline-none active:outline-none focus:border-[#E5C378] focus:shadow-[0_0_0_1px_rgba(229,195,120,0.25)] transition-colors duration-150"
              />

              <div className="mt-3 flex items-center justify-end">
                <Button
                  type="button"
                  variant="monolith"
                  size="md"
                  disabled={isMatching || notes.trim().length < 10}
                  onClick={onRunInitialMatch}
                  className="font-semibold text-xs px-4"
                >
                  {isMatching ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin text-[#E5C378]" />
                      <span>Формируем подборку...</span>
                    </>
                  ) : (
                    <>
                      <span>Подобрать варианты пакетов</span>
                      <ArrowRight className="h-4 w-4 text-[#E5C378] monolith-icon" strokeWidth={2} />
                    </>
                  )}
                </Button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Круглый движущийся индикатор загрузки со сменяющимися фразами */}
      {isMatching && (
        <div className="border-b border-[#21262F] bg-[#12161A] px-4 py-3">
          <div className="flex items-center gap-3 min-h-[26px]">
            <div className="h-5 w-5 shrink-0 rounded-full border-2 border-[#262D35] border-t-[#E5C378] animate-spin" />
            <AnimatePresence mode="wait">
              <motion.p
                key={loadingStepIndex}
                initial={{ opacity: 0, y: 3 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -3 }}
                transition={{ duration: 0.28, ease: "easeInOut" }}
                className="font-serif italic text-xs font-medium text-[#E5C378]"
              >
                {MATCHING_STATUS_STEPS[loadingStepIndex]}
              </motion.p>
            </AnimatePresence>
          </div>
        </div>
      )}

      {/* Строгая 5-ячеечная табличная строка параметров в стиле Novel.AI */}
      {editableProfile && (
        <ExtractedProfilePanel
          editableProfile={editableProfile}
          isMatching={isMatching}
          onUpdateProfile={onUpdateProfile}
          onRematchWithOverride={onRematchWithOverride}
        />
      )}
    </section>
  );
}
