import * as React from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Send,
  BellRing,
  MapPin,
  Calendar,
  Loader2,
  HelpCircle,
  ChevronDown,
  Check,
  ChevronRight,
  Plus,
} from "lucide-react";
import type { ShowcaseEventItemOut } from "@/api/types";
import type { RegulationChatExchange } from "@/store/useShowcaseStore";
import { SlideOverDrawer } from "@/components/ui/slide-over-drawer";
import { Button } from "@/components/ui/button";
import {
  ROLE_BADGE_LABELS,
  formatDateRange,
  formatDateShort,
  formatRub,
} from "@/lib/formatters";
import { cn } from "@/lib/utils";

interface RegulationConsultantDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  events: ShowcaseEventItemOut[];
  activeEvent: ShowcaseEventItemOut | null;
  onSelectEvent: (eventId: number) => void;
  faqQuickChips: string[];
  exchanges: RegulationChatExchange[];
  onAskQuestion: (questionText: string) => void;
  isAsking: boolean;
  managerFullName: string;
  onApproveEvent?: (event: ShowcaseEventItemOut) => void;
  isReacting?: boolean;
}

export function RegulationConsultantDrawer({
  isOpen,
  onClose,
  events,
  activeEvent,
  onSelectEvent,
  faqQuickChips,
  exchanges,
  onAskQuestion,
  isAsking,
  managerFullName,
  onApproveEvent,
  isReacting,
}: RegulationConsultantDrawerProps) {
  const [inputQuestion, setInputQuestion] = React.useState("");
  const [isEventSelectorOpen, setIsEventSelectorOpen] = React.useState(false);
  const selectorRef = React.useRef<HTMLDivElement>(null);
  const feedEndRef = React.useRef<HTMLDivElement>(null);

  // Закрытие кастомного выпадающего списка при клике вне
  React.useEffect(() => {
    if (!isEventSelectorOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (
        selectorRef.current &&
        !selectorRef.current.contains(e.target as Node)
      ) {
        setIsEventSelectorOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isEventSelectorOpen]);

  // Закрываем дропдаун при закрытии шторки
  React.useEffect(() => {
    if (!isOpen) setIsEventSelectorOpen(false);
  }, [isOpen]);

  React.useEffect(() => {
    feedEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [exchanges.length, isAsking]);

  if (!activeEvent) return null;

  // Очищаем имя куратора от скобок с должностью
  const parenIndex = managerFullName.indexOf("(");
  const cleanManagerName = (
    parenIndex !== -1 ? managerFullName.slice(0, parenIndex) : managerFullName
  ).trim();

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = inputQuestion.trim();
    if (trimmed.length < 3 || isAsking) return;
    onAskQuestion(trimmed);
    setInputQuestion("");
  };

  return (
    <SlideOverDrawer
      isOpen={isOpen}
      onClose={onClose}
      subtitle="Условия участия и консультант"
      title={activeEvent.canonical_title}
      headerSelector={
        events.length > 1 ? (
          <div className="relative" ref={selectorRef}>
            <button
              type="button"
              onClick={() => setIsEventSelectorOpen((prev) => !prev)}
              className={cn(
                "flex w-full items-center justify-between gap-2 rounded-[8px] border bg-[#161B22] px-3 py-2 text-left text-xs transition-colors duration-150 cursor-pointer",
                isEventSelectorOpen
                  ? "border-[#E5C378] text-white"
                  : "border-[#262D35] text-[#E5E7EB] hover:border-[#7C5A20]"
              )}
            >
              <div className="min-w-0 flex-1">
                <span className="block text-[10px] text-[#8E95A0]">
                  Мероприятие:
                </span>
                <span className="mt-0.5 block truncate font-medium text-white">
                  {activeEvent.canonical_title}{" "}
                  <span className="text-[#8E95A0]">
                    ({activeEvent.is_online ? "Онлайн" : activeEvent.city})
                  </span>
                </span>
              </div>
              <ChevronDown
                className={cn(
                  "h-4 w-4 shrink-0 text-[#E5C378] transition-transform duration-200",
                  isEventSelectorOpen && "rotate-180"
                )}
                strokeWidth={1.75}
              />
            </button>

            <AnimatePresence>
              {isEventSelectorOpen && (
                <motion.div
                  initial={{ opacity: 0, y: -4, scale: 0.99 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: -4, scale: 0.99 }}
                  transition={{ duration: 0.16, ease: "easeOut" }}
                  className="absolute left-0 right-0 z-50 mt-1.5 max-h-60 overflow-y-auto rounded-[10px] border border-[#262D35] bg-[#0E1216] p-1.5 shadow-2xl scrollbar-thin"
                >
                  {events.map((ev) => {
                    const isSelected = ev.event_id === activeEvent.event_id;
                    return (
                      <button
                        key={ev.event_id}
                        type="button"
                        onClick={() => {
                          onSelectEvent(ev.event_id);
                          setIsEventSelectorOpen(false);
                        }}
                        className={cn(
                          "flex w-full items-center justify-between gap-2 rounded-[6px] px-3 py-2 text-left text-xs transition-colors cursor-pointer",
                          isSelected
                            ? "bg-[#1A2128] text-white font-semibold"
                            : "text-[#D1D5DB] hover:bg-[#161B22] hover:text-white"
                        )}
                      >
                        <div className="min-w-0 flex-1">
                          <span className="block truncate">
                            {ev.canonical_title}
                          </span>
                          <span className="mt-0.5 block text-[10px] text-[#8E95A0]">
                            {ev.is_online ? "Онлайн" : ev.city} ·{" "}
                            {formatDateRange(ev.start_date, ev.end_date)}
                          </span>
                        </div>
                        {isSelected && (
                          <Check
                            className="h-3.5 w-3.5 shrink-0 text-[#E5C378]"
                            strokeWidth={2.25}
                          />
                        )}
                      </button>
                    );
                  })}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        ) : undefined
      }
      footer={
        <form onSubmit={handleFormSubmit} className="space-y-2">
          <label className="block text-[11px] font-medium text-[#8E95A0]">
            Задайте вопрос по условиям участия, программе или логистике:
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              value={inputQuestion}
              onChange={(e) => setInputQuestion(e.target.value)}
              placeholder="Например: какие требования к презентации спикера?"
              className="h-9 flex-1 rounded-[8px] border border-[#262D35] bg-[#161B22] px-3 text-xs text-white placeholder:text-[#727985] focus:border-[#E5C378] focus:outline-none transition-colors"
            />
            <Button
              type="submit"
              variant="monolith"
              size="md"
              disabled={isAsking || inputQuestion.trim().length < 3}
              className="shrink-0"
            >
              {isAsking ? (
                <Loader2 className="h-4 w-4 animate-spin text-[#E5C378]" />
              ) : (
                <Send
                  className="h-4 w-4 text-[#E5C378] monolith-icon"
                  strokeWidth={2}
                />
              )}
            </Button>
          </div>
        </form>
      }
    >
      {/* Плавная анимация смены контента при переключении мероприятия */}
      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={activeEvent.event_id}
          initial={{ opacity: 0, y: 5 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -5 }}
          transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
          className="space-y-5"
        >
          {/* 1. Карточка рекомендованного тарифа с выверенными отступами p-4 */}
          <section className="rounded-[12px] border border-[#262D35] bg-[#12161A] p-4 shadow-sm">
            <div className="flex items-start justify-between gap-3 border-b border-[#21262F] pb-3">
              <div className="min-w-0 flex-1">
                <span className="font-serif italic text-xs font-semibold text-[#E5C378]">
                  Рекомендованный тариф
                </span>
                <h3 className="mt-1 text-sm font-semibold leading-snug text-white">
                  {activeEvent.tariff_name}
                </h3>
              </div>

              <span
                className={cn(
                  "shrink-0 whitespace-nowrap rounded-[6px] border px-2.5 py-1 text-[11px] font-semibold",
                  activeEvent.participation_role === "speaker"
                    ? "border-[#7C5A20]/60 bg-[#261E0F] text-[#E5C378]"
                    : activeEvent.participation_role === "sponsor"
                      ? "border-[#5E2242] bg-[#28131E] text-[#F472B6]"
                      : "border-[#1E5241] bg-[#0E241E] text-[#34D399]"
                )}
              >
                {ROLE_BADGE_LABELS[activeEvent.participation_role]}
              </span>
            </div>

            <div className="mt-3.5 grid grid-cols-1 gap-3 sm:grid-cols-2 text-xs tabular-nums">
              <div className="flex flex-col justify-between rounded-[8px] border border-[#262D35] bg-[#161B22] p-3">
                <span className="block text-[11px] text-[#8E95A0]">
                  Взнос организатора:
                </span>
                <div className="mt-1">
                  <span className="block text-base font-bold text-white">
                    {formatRub(activeEvent.actual_price)}
                  </span>
                  {activeEvent.savings > 0 && (
                    <span className="mt-0.5 block text-[11px] font-semibold text-[#34D399]">
                      Выгода {formatRub(activeEvent.savings)}
                      {activeEvent.early_bird_deadline
                        ? ` до ${formatDateShort(activeEvent.early_bird_deadline)}`
                        : ""}
                    </span>
                  )}
                </div>
              </div>

              <div className="flex flex-col justify-between rounded-[8px] border border-[#262D35] bg-[#161B22] p-3 min-w-0">
                <span className="block text-[11px] text-[#8E95A0]">
                  Даты и место:
                </span>
                <div className="mt-1 space-y-1 min-w-0">
                  <span className="flex items-center gap-1.5 font-medium text-white">
                    <Calendar
                      className="h-3.5 w-3.5 shrink-0 text-[#E5C378]"
                      strokeWidth={1.5}
                    />
                    <span className="truncate">
                      {formatDateRange(
                        activeEvent.start_date,
                        activeEvent.end_date
                      )}
                    </span>
                  </span>
                  <span
                    className="flex items-center gap-1.5 text-[11px] text-[#8E95A0]"
                    title={
                      activeEvent.is_online
                        ? "Онлайн"
                        : activeEvent.venue || activeEvent.city || ""
                    }
                  >
                    <MapPin
                      className="h-3.5 w-3.5 shrink-0 text-[#E5C378]"
                      strokeWidth={1.5}
                    />
                    <span className="truncate">
                      {activeEvent.is_online
                        ? "Онлайн"
                        : activeEvent.venue || activeEvent.city}
                    </span>
                  </span>
                </div>
              </div>
            </div>

            {activeEvent.included_benefits && (
              <div className="mt-3 rounded-[8px] border border-[#262D35] bg-[#161B22] p-3.5">
                <span className="block font-serif italic text-xs font-semibold text-[#E5C378]">
                  Что входит в рекомендованный тариф:
                </span>
                <p className="mt-1.5 text-xs leading-relaxed text-[#D1D5DB]">
                  {activeEvent.included_benefits}
                </p>
              </div>
            )}

            {/* Быстрое добавление мероприятия в план участия прямо из окна консультанта */}
            {onApproveEvent && (
              <div className="mt-3.5 border-t border-[#21262F] pt-3">
                {activeEvent.client_reaction === "interested" ? (
                  <div className="flex items-center justify-center gap-2 rounded-[8px] border border-[#1E5241] bg-[#0E241E] px-3 py-2 text-xs font-semibold text-[#34D399]">
                    <Check className="h-4 w-4 shrink-0" strokeWidth={2.5} />
                    <span>Мероприятие в вашем плане участия</span>
                  </div>
                ) : (
                  <Button
                    type="button"
                    variant="monolith"
                    size="md"
                    disabled={isReacting}
                    onClick={() => onApproveEvent(activeEvent)}
                    className="w-full text-xs font-semibold cursor-pointer"
                  >
                    <Plus
                      className="h-4 w-4 text-[#E5C378] monolith-icon"
                      strokeWidth={2.25}
                    />
                    <span>Добавить мероприятие в план</span>
                  </Button>
                )}
              </div>
            )}
          </section>

          {/* 2. Быстрые вопросы по условиям участия */}
          <section>
            <div className="mb-2.5">
              <span className="block font-serif italic text-xs font-semibold text-[#E5C378]">
                Частые вопросы по мероприятию
              </span>
              <span className="mt-0.5 block text-[11px] text-[#8E95A0]">
                Ответы формируются по официальному регламенту организатора
              </span>
            </div>

            <div className="space-y-1.5">
              {faqQuickChips.map((chip) => (
                <button
                  key={chip}
                  type="button"
                  disabled={isAsking}
                  onClick={() => onAskQuestion(chip)}
                  className="group flex w-full items-center justify-between gap-3 rounded-[8px] border border-[#262D35] bg-[#12161A] px-3.5 py-2.5 text-left text-xs font-medium text-[#E5E7EB] transition-colors hover:border-[#7C5A20] hover:bg-[#181E25] hover:text-white disabled:opacity-50 cursor-pointer"
                >
                  <span className="leading-snug">{chip}</span>
                  <ChevronRight
                    className="h-3.5 w-3.5 shrink-0 text-[#E5C378] transition-transform group-hover:translate-x-0.5"
                    strokeWidth={2}
                  />
                </button>
              ))}
            </div>
          </section>

          {/* 3. Лента ответов без технических плашек */}
          <section className="space-y-3 pt-1">
            {exchanges.length === 0 ? (
              <div className="rounded-[12px] border border-dashed border-[#262D35] bg-[#12161A]/70 p-5 text-center">
                <HelpCircle
                  className="mx-auto h-6 w-6 text-[#E5C378]/60"
                  strokeWidth={1.5}
                />
                <p className="mt-2 text-xs leading-relaxed text-[#8E95A0]">
                  Выберите вопрос выше или напишите свой в поле внизу. Мы приведем точную информацию из условий{" "}
                  <strong className="font-medium text-[#D1D5DB]">
                    «{activeEvent.canonical_title}»
                  </strong>
                  .
                </p>
              </div>
            ) : (
              exchanges.map((ex) => (
                <div
                  key={ex.id}
                  className="rounded-[12px] border border-[#262D35] bg-[#12161A] p-4 shadow-sm space-y-3"
                >
                  {/* Вопрос клиента */}
                  <div className="flex items-start justify-between gap-2 border-b border-[#21262F] pb-2.5">
                    <div className="flex items-start gap-2">
                      <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[#E5C378]" />
                      <p className="text-xs font-semibold leading-snug text-white">
                        {ex.questionText}
                      </p>
                    </div>
                    <span className="shrink-0 text-[10px] text-[#727985] tabular-nums">
                      {ex.createdAt}
                    </span>
                  </div>

                  {/* Состояние загрузки */}
                  {ex.isLoading && (
                    <div className="flex items-center gap-2 py-1.5 text-xs text-[#8E95A0]">
                      <Loader2 className="h-3.5 w-3.5 animate-spin text-[#E5C378]" />
                      <span>Уточняем информацию по документации...</span>
                    </div>
                  )}

                  {/* Ошибка сети */}
                  {ex.error && (
                    <p className="text-xs text-[#F472B6]">{ex.error}</p>
                  )}

                  {/* Чистый ответ для клиента */}
                  {ex.response && (
                    <div className="space-y-3">
                      <p className="text-xs leading-relaxed text-[#E5E7EB]">
                        {ex.response.answer_text}
                      </p>

                      {/* Выдержка из регламента */}
                      {ex.response.source_quote && (
                        <div className="rounded-[8px] border border-[#262D35] border-l-2 border-l-[#E5C378] bg-[#161B22] p-3">
                          <span className="block font-serif italic text-[11px] font-semibold text-[#E5C378]">
                            Выдержка из документации организатора:
                          </span>
                          <blockquote className="mt-1 text-xs italic leading-relaxed text-[#D1D5DB]">
                            «{ex.response.source_quote}»
                          </blockquote>
                        </div>
                      )}

                      {/* Вежливое уведомление о передаче вопроса куратору */}
                      {ex.response.escalated_to_telegram && (
                        <div className="flex items-start gap-2.5 rounded-[8px] border border-[#7C5A20]/50 bg-[#1B1710] p-3 text-[11px] leading-relaxed text-[#D1D5DB]">
                          <BellRing
                            className="mt-0.5 h-4 w-4 shrink-0 text-[#E5C378]"
                            strokeWidth={1.75}
                          />
                          <span>
                            Этих деталей нет в общем документе. Мы уже передали ваш вопрос персональному куратору (
                            <strong className="font-semibold text-white">
                              {cleanManagerName}
                            </strong>
                            ) для индивидуального уточнения у организаторов.
                          </span>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))
            )}
            <div ref={feedEndRef} />
          </section>
        </motion.div>
      </AnimatePresence>
    </SlideOverDrawer>
  );
}
