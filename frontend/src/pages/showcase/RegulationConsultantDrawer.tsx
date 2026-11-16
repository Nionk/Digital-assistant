import * as React from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Send,
  MapPin,
  Calendar,
  Loader2,
  Check,
  ChevronRight,
  Plus,
  MessageSquareText,
  FileText,
  AlertCircle,
} from "lucide-react";
import type { ShowcaseEventItemOut } from "@/api/types";
import type { RegulationChatExchange } from "@/store/useShowcaseStore";
import { SlideOverDrawer } from "@/components/ui/slide-over-drawer";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  ROLE_BADGE_LABELS,
  formatDateRange,
  formatDateShort,
  formatRub,
} from "@/lib/formatters";
import { cn } from "@/lib/utils";
import { buildMergedConversation } from "./drawer/mergeConversation";
import { EventSelectorDropdown } from "./drawer/EventSelectorDropdown";
import { ChatMessageThread } from "./drawer/ChatMessageThread";
import { EventBenefitsTab } from "./drawer/EventBenefitsTab";

interface RegulationConsultantDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  events: ShowcaseEventItemOut[];
  activeEvent: ShowcaseEventItemOut | null;
  onSelectEvent: (eventId: number) => void;
  initialTab?: "regulation" | "benefits";
  faqQuickChips: string[];
  exchanges: RegulationChatExchange[];
  onAskQuestion: (questionText: string) => void;
  isAsking: boolean;
  managerFullName: string;
  onApproveEvent?: (event: ShowcaseEventItemOut) => void;
  isReacting?: boolean;
  onEscalateQuestion?: (exchangeId: string, questionText: string) => void;
  escalatingExchangeId?: string | null;
  escalatedServerIds?: Record<string, boolean>;
}

export function RegulationConsultantDrawer({
  isOpen,
  onClose,
  events,
  activeEvent,
  onSelectEvent,
  initialTab = "regulation",
  faqQuickChips,
  exchanges,
  onAskQuestion,
  isAsking,
  managerFullName,
  onApproveEvent,
  isReacting,
  onEscalateQuestion,
  escalatingExchangeId = null,
  escalatedServerIds = {},
}: RegulationConsultantDrawerProps) {
  const [inputQuestion, setInputQuestion] = React.useState("");
  const [activeTab, setActiveTab] = React.useState<"regulation" | "benefits">(
    initialTab
  );

  React.useEffect(() => {
    if (isOpen) {
      setActiveTab(initialTab);
    }
  }, [isOpen, initialTab, activeEvent?.event_id]);

  const mergedConversation = React.useMemo(
    () =>
      buildMergedConversation(
        activeEvent?.chat_messages || [],
        exchanges,
        escalatingExchangeId,
        escalatedServerIds
      ),
    [
      activeEvent?.chat_messages,
      exchanges,
      escalatingExchangeId,
      escalatedServerIds,
    ]
  );

  if (!activeEvent) {
    return (
      <SlideOverDrawer
        isOpen={isOpen}
        onClose={onClose}
        subtitle="Состав подборки обновлён"
        title="Мероприятие больше не в пакете"
      >
        <div className="space-y-4">
          <div className="rounded-[12px] border border-[#7C5A20]/50 bg-[#12161A] p-5 text-center shadow-sm">
            <AlertCircle
              className="mx-auto h-8 w-8 text-[#E5C378]"
              strokeWidth={1.5}
            />
            <h3 className="mt-3 font-serif text-sm font-semibold text-white">
              Выбранное мероприятие было обновлено или удалено куратором
            </h3>
            <p className="mt-1.5 text-xs leading-relaxed text-[#8E95A0]">
              Выберите актуальное мероприятие из списка ниже или закройте
              панель.
            </p>
          </div>

          {events.length > 0 && (
            <div className="space-y-2">
              <span className="block font-serif italic text-xs font-semibold text-[#E5C378]">
                Мероприятия в актуальной подборке:
              </span>
              {events.map((ev) => (
                <button
                  key={ev.event_id}
                  type="button"
                  onClick={() => onSelectEvent(ev.event_id)}
                  className="flex w-full items-center justify-between gap-3 rounded-[8px] border border-[#262D35] bg-[#12161A] px-3.5 py-2.5 text-left text-xs text-[#E5E7EB] transition-colors hover:border-[#7C5A20] hover:bg-[#181E25] hover:text-white cursor-pointer"
                >
                  <div className="min-w-0 flex-1">
                    <span className="block truncate font-semibold text-white">
                      {ev.canonical_title}
                    </span>
                    <span className="mt-0.5 block text-[11px] text-[#8E95A0]">
                      {ev.is_online ? "Онлайн" : ev.city} ·{" "}
                      {formatDateRange(ev.start_date, ev.end_date)}
                    </span>
                  </div>
                  <ChevronRight className="h-3.5 w-3.5 shrink-0 text-[#E5C378]" />
                </button>
              ))}
            </div>
          )}

          <Button
            type="button"
            variant="outline"
            size="md"
            onClick={onClose}
            className="w-full text-xs cursor-pointer"
          >
            Закрыть панель
          </Button>
        </div>
      </SlideOverDrawer>
    );
  }

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
          <EventSelectorDropdown
            isDrawerOpen={isOpen}
            events={events}
            activeEvent={activeEvent}
            onSelectEvent={onSelectEvent}
          />
        ) : undefined
      }
      footer={
        activeTab === "regulation" ? (
          <form onSubmit={handleFormSubmit} className="space-y-2">
            <label
              htmlFor="regulation-question-input"
              className="block text-[11px] font-medium text-[#8E95A0]"
            >
              Задайте вопрос по условиям участия, программе или логистике:
            </label>
            <div className="flex gap-2">
              <input
                id="regulation-question-input"
                name="question_text"
                type="text"
                value={inputQuestion}
                onChange={(e) => setInputQuestion(e.target.value)}
                placeholder="Например: какие требования к презентации спикера?"
                className="h-9 flex-1 rounded-[8px] border border-[#262D35] bg-[#161B22] px-3 text-xs text-white placeholder:text-[#8E95A0] focus:border-[#E5C378] focus:outline-none transition-colors"
              />
              <Button
                type="submit"
                variant="monolith"
                size="md"
                disabled={isAsking || inputQuestion.trim().length < 3}
                aria-label="Отправить вопрос"
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
        ) : undefined
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
          className="space-y-4"
        >
          {/* Переключатель вкладок в стиле витрины */}
          <div className="grid grid-cols-2 rounded-[8px] border border-[#232931] bg-[#12161A] p-1 gap-1 shadow-inner">
            {(
              [
                {
                  id: "regulation",
                  label: "ИИ-консультант",
                  icon: MessageSquareText,
                },
                {
                  id: "benefits",
                  label: "Условия и программа",
                  icon: FileText,
                },
              ] as const
            ).map((tab) => {
              const Icon = tab.icon;
              const isSelected = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setActiveTab(tab.id)}
                  className={cn(
                    "relative flex items-center justify-center gap-1.5 rounded-[6px] px-3 py-1.5 text-xs font-medium select-none cursor-pointer transition-colors duration-200 outline-none",
                    isSelected ? "text-white" : "text-[#8E95A0] hover:text-white"
                  )}
                >
                  {isSelected && (
                    <motion.span
                      layoutId="showcaseDrawerTabPill"
                      transition={{
                        type: "spring",
                        stiffness: 380,
                        damping: 32,
                      }}
                      className="absolute inset-0 rounded-[6px] bg-[#1A2128] shadow-sm"
                    >
                      <span className="absolute bottom-0 left-2 right-2 h-[2px] rounded-full bg-gradient-to-r from-[#D4AF37] via-[#E5C378] to-[#D4AF37]" />
                    </motion.span>
                  )}
                  <Icon
                    className={cn(
                      "relative z-10 h-3.5 w-3.5 shrink-0 transition-colors",
                      isSelected ? "text-[#E5C378]" : "text-[#8E95A0]"
                    )}
                    strokeWidth={1.75}
                  />
                  <span className="relative z-10 truncate">{tab.label}</span>
                  {tab.id === "regulation" &&
                    mergedConversation.items.length > 0 && (
                      <span className="relative z-10 rounded bg-[#12161A]/80 px-1.5 py-0.5 text-[11px] font-semibold text-[#E5C378] tabular-nums">
                        {mergedConversation.items.length}
                      </span>
                    )}
                </button>
              );
            })}
          </div>

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

              <Badge
                variant={
                  activeEvent.participation_role === "speaker"
                    ? "ebGold"
                    : activeEvent.participation_role === "sponsor"
                      ? "ebRose"
                      : "ebBlue"
                }
                className="text-[11px] shrink-0"
              >
                {ROLE_BADGE_LABELS[activeEvent.participation_role]}
              </Badge>
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
                    <div className="mt-1">
                      <Badge variant="ebEmerald" asSlanted={false} className="text-[11px]">
                        Выгода {formatRub(activeEvent.savings)}
                        {activeEvent.early_bird_deadline
                          ? ` до ${formatDateShort(activeEvent.early_bird_deadline)}`
                          : ""}
                      </Badge>
                    </div>
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

          {activeTab === "benefits" ? (
            <EventBenefitsTab
              activeEvent={activeEvent}
              onSwitchToRegulationTab={() => setActiveTab("regulation")}
            />
          ) : (
            <ChatMessageThread
              activeEventTitle={activeEvent.canonical_title}
              faqQuickChips={faqQuickChips}
              mergedConversation={mergedConversation}
              cleanManagerName={cleanManagerName}
              isAsking={isAsking}
              onAskQuestion={onAskQuestion}
              onEscalateQuestion={onEscalateQuestion}
            />
          )}
        </motion.div>
      </AnimatePresence>
    </SlideOverDrawer>
  );
}
