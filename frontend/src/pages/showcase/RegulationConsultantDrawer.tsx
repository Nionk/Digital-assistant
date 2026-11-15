import * as React from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Send,
  MapPin,
  Calendar,
  Loader2,
  HelpCircle,
  ChevronDown,
  Check,
  ChevronRight,
  Plus,
  MessageSquareText,
  FileText,
  UserCheck,
  AlertCircle,
} from "lucide-react";
import type {
  ShowcaseChatMessageOut,
  ShowcaseEventItemOut,
} from "@/api/types";
import type { RegulationChatExchange } from "@/store/useShowcaseStore";
import { SlideOverDrawer } from "@/components/ui/slide-over-drawer";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  FORMAT_LABELS,
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

interface ManagerReplyEntry {
  id: number;
  text: string;
  createdAtLabel: string;
}

interface MergedConversationItem {
  key: string;
  exchangeId: string;
  questionText: string;
  createdAtLabel: string;
  answerText: string | null;
  sourceQuote: string | null;
  isAnswerFound: boolean;
  needsManagerAttention: boolean;
  managerReplies: ManagerReplyEntry[];
  isLoading: boolean;
  error: string | null;
  isEscalating: boolean;
  isEscalated: boolean;
}

function formatChatTime(raw: string | null | undefined): string {
  if (!raw) return "";
  if (/^\d{2}:\d{2}$/.test(raw.trim())) return raw.trim();
  const normalized =
    raw.includes(" ") && !raw.includes("T") ? raw.replace(" ", "T") : raw;
  const parsed = new Date(normalized);
  if (Number.isNaN(parsed.getTime())) return raw;
  return parsed.toLocaleTimeString("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function buildMergedConversation(
  serverMessages: ShowcaseChatMessageOut[],
  localExchanges: RegulationChatExchange[],
  escalatingExchangeId: string | null,
  escalatedServerIds: Record<string, boolean>
): {
  items: MergedConversationItem[];
  orphanManagerReplies: ManagerReplyEntry[];
} {
  interface ServerTurn {
    clientMsgId: number;
    questionText: string;
    createdAtLabel: string;
    needsManagerAttention: boolean;
    aiAnswerText: string | null;
    managerReplies: ManagerReplyEntry[];
  }

  const serverTurns: ServerTurn[] = [];
  const orphanManagerReplies: ManagerReplyEntry[] = [];

  for (const msg of serverMessages) {
    if (msg.sender_role === "client") {
      serverTurns.push({
        clientMsgId: msg.id,
        questionText: msg.message_text,
        createdAtLabel: formatChatTime(msg.created_at),
        needsManagerAttention: Boolean(msg.needs_manager_attention),
        aiAnswerText: null,
        managerReplies: [],
      });
    } else if (msg.sender_role === "ai_assistant") {
      for (let i = serverTurns.length - 1; i >= 0; i--) {
        if (serverTurns[i].aiAnswerText === null) {
          serverTurns[i].aiAnswerText = msg.message_text;
          break;
        }
      }
    } else if (msg.sender_role === "manager") {
      const replyEntry: ManagerReplyEntry = {
        id: msg.id,
        text: msg.message_text,
        createdAtLabel: formatChatTime(msg.created_at),
      };
      if (serverTurns.length === 0) {
        orphanManagerReplies.push(replyEntry);
      } else {
        let targetIdx = -1;
        for (let i = serverTurns.length - 1; i >= 0; i--) {
          if (
            serverTurns[i].managerReplies.length === 0 &&
            (serverTurns[i].aiAnswerText === null ||
              serverTurns[i].needsManagerAttention)
          ) {
            targetIdx = i;
            break;
          }
        }
        if (targetIdx === -1) {
          for (let i = serverTurns.length - 1; i >= 0; i--) {
            if (serverTurns[i].managerReplies.length === 0) {
              targetIdx = i;
              break;
            }
          }
        }
        if (targetIdx === -1) targetIdx = serverTurns.length - 1;
        serverTurns[targetIdx].managerReplies.push(replyEntry);
      }
    }
  }

  const usedLocalIndices = new Set<number>();
  const items: MergedConversationItem[] = [];

  for (const turn of serverTurns) {
    const normServerQ = turn.questionText.trim().toLowerCase();
    let matchedLocal: RegulationChatExchange | undefined;
    for (let i = 0; i < localExchanges.length; i++) {
      if (usedLocalIndices.has(i)) continue;
      const cand = localExchanges[i];
      if (!cand.error && cand.questionText.trim().toLowerCase() === normServerQ) {
        usedLocalIndices.add(i);
        matchedLocal = cand;
        break;
      }
    }

    const hasManagerReply = turn.managerReplies.length > 0;
    const exchangeId = matchedLocal?.id ?? `server-${turn.clientMsgId}`;
    const answerText = matchedLocal?.response?.answer_text ?? turn.aiAnswerText;
    const sourceQuote = matchedLocal?.response?.source_quote ?? null;
    const isAnswerFound = hasManagerReply
      ? true
      : matchedLocal?.response
        ? matchedLocal.response.is_answer_found
        : !turn.needsManagerAttention && Boolean(turn.aiAnswerText);

    const isEscalated = hasManagerReply
      ? false
      : Boolean(
          matchedLocal?.isEscalated ||
            matchedLocal?.response?.escalated_to_telegram ||
            escalatedServerIds[exchangeId] ||
            (turn.needsManagerAttention && turn.aiAnswerText === null)
        );

    items.push({
      key: `srv-${turn.clientMsgId}`,
      exchangeId,
      questionText: turn.questionText,
      createdAtLabel: matchedLocal?.createdAt || turn.createdAtLabel,
      answerText,
      sourceQuote,
      isAnswerFound,
      needsManagerAttention: !hasManagerReply && turn.needsManagerAttention,
      managerReplies: turn.managerReplies,
      isLoading: Boolean(matchedLocal?.isLoading),
      error: matchedLocal?.error ?? null,
      isEscalating:
        Boolean(matchedLocal?.isEscalating) ||
        escalatingExchangeId === exchangeId,
      isEscalated,
    });
  }

  for (let i = 0; i < localExchanges.length; i++) {
    if (usedLocalIndices.has(i)) continue;
    const ex = localExchanges[i];
    items.push({
      key: `loc-${ex.id}`,
      exchangeId: ex.id,
      questionText: ex.questionText,
      createdAtLabel: ex.createdAt,
      answerText: ex.response?.answer_text ?? null,
      sourceQuote: ex.response?.source_quote ?? null,
      isAnswerFound: ex.response ? ex.response.is_answer_found : false,
      needsManagerAttention: false,
      managerReplies: [],
      isLoading: ex.isLoading,
      error: ex.error,
      isEscalating: ex.isEscalating || escalatingExchangeId === ex.id,
      isEscalated: Boolean(ex.isEscalated),
    });
  }

  return { items, orphanManagerReplies };
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
  const [isEventSelectorOpen, setIsEventSelectorOpen] = React.useState(false);
  const [activeTab, setActiveTab] = React.useState<"regulation" | "benefits">(
    initialTab
  );
  const selectorRef = React.useRef<HTMLDivElement>(null);
  const feedEndRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (isOpen) {
      setActiveTab(initialTab);
    }
  }, [isOpen, initialTab, activeEvent?.event_id]);

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

  React.useEffect(() => {
    if (activeTab !== "regulation") return;
    feedEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [mergedConversation.items.length, isAsking, activeTab]);

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
              Выберите актуальное мероприятие из списка ниже или закройте панель.
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
        activeTab === "regulation" ? (
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
                      <span className="relative z-10 rounded bg-[#12161A]/80 px-1.5 py-0.5 text-[10px] font-semibold text-[#E5C378] tabular-nums">
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
                      <Badge variant="ebEmerald" className="text-[10px]">
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
            <div className="space-y-4">
              <div className="rounded-[12px] border border-[#262D35] bg-[#12161A] p-4 space-y-3">
                <div className="flex items-center justify-between gap-2 border-b border-[#21262F] pb-2.5">
                  <span className="font-serif italic text-xs font-semibold text-[#E5C378]">
                    Программа и фокус площадки
                  </span>
                  <Badge variant="darkSubtle" className="text-[10px]">
                    {FORMAT_LABELS[activeEvent.event_format] ||
                      activeEvent.event_format}
                  </Badge>
                </div>

                <p className="text-xs leading-relaxed text-[#E5E7EB]">
                  {activeEvent.summary}
                </p>

                {activeEvent.themes.length > 0 && (
                  <div className="pt-1">
                    <span className="block text-[11px] font-medium text-[#8E95A0] mb-1.5">
                      Ключевые тематические треки:
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      {activeEvent.themes.map((theme) => (
                        <span
                          key={theme}
                          className="rounded-[4px] border border-[#262D35] bg-[#161B22] px-2 py-0.5 text-[11px] font-serif italic text-[#D1D5DB]"
                        >
                          {theme}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {activeEvent.included_benefits && (
                <div className="rounded-[12px] border border-[#262D35] bg-[#12161A] p-4">
                  <span className="block font-serif italic text-xs font-semibold text-[#E5C378]">
                    Что входит в пакет «{activeEvent.tariff_name}»
                  </span>
                  <p className="mt-2 whitespace-pre-line text-xs leading-relaxed text-[#D1D5DB]">
                    {activeEvent.included_benefits}
                  </p>
                </div>
              )}

              {activeEvent.ai_rationale && (
                <div className="rounded-[12px] border border-[#262D35] border-l-2 border-l-[#E5C378] bg-[#12161A] p-4">
                  <span className="block font-serif italic text-xs font-semibold text-[#E5C378]">
                    Почему мероприятие включено в подборку
                  </span>
                  <p className="mt-1.5 text-xs leading-relaxed text-[#D1D5DB]">
                    {activeEvent.ai_rationale}
                  </p>
                </div>
              )}

              <Button
                type="button"
                variant="outline"
                size="md"
                onClick={() => setActiveTab("regulation")}
                className="w-full border-[#7C5A20]/50 bg-[#12161A] text-xs font-semibold text-[#E5C378] hover:border-[#E5C378] hover:bg-[#1A2128] hover:text-white cursor-pointer"
              >
                <MessageSquareText className="h-3.5 w-3.5" strokeWidth={1.75} />
                <span>Задать вопрос консультанту по регламенту</span>
              </Button>
            </div>
          ) : (
            <>
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

              <section className="space-y-3 pt-1">
                {mergedConversation.items.length === 0 &&
                mergedConversation.orphanManagerReplies.length === 0 ? (
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
                  <>
                    {mergedConversation.items.map((ex) => {
                      const hasManagerReply = ex.managerReplies.length > 0;
                      const showEscalateButton =
                        !ex.isLoading &&
                        !ex.error &&
                        !hasManagerReply &&
                        !ex.isEscalated &&
                        (!ex.isAnswerFound || ex.needsManagerAttention) &&
                        Boolean(onEscalateQuestion);

                      return (
                        <div
                          key={ex.key}
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
                            <div className="flex items-center gap-1.5 shrink-0">
                              {hasManagerReply && (
                                <Badge
                                  variant="ebEmerald"
                                  className="text-[9px]"
                                >
                                  Ответ куратора
                                </Badge>
                              )}
                              {ex.createdAtLabel && (
                                <span className="text-[10px] text-[#727985] tabular-nums">
                                  {ex.createdAtLabel}
                                </span>
                              )}
                            </div>
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

                          {/* Ответ ИИ и прикрепленные ответы куратора */}
                          {!ex.isLoading && (
                            <div className="space-y-3">
                              {ex.answerText && (
                                <p className="text-xs leading-relaxed text-[#E5E7EB]">
                                  {ex.answerText}
                                </p>
                              )}

                              {/* Выдержка из регламента (хранится в локальном persist) */}
                              {ex.sourceQuote && (
                                <div className="rounded-[8px] border border-[#262D35] border-l-2 border-l-[#E5C378] bg-[#161B22] p-3">
                                  <span className="block font-serif italic text-[11px] font-semibold text-[#E5C378]">
                                    Выдержка из документации организатора:
                                  </span>
                                  <blockquote className="mt-1 text-xs italic leading-relaxed text-[#D1D5DB]">
                                    «{ex.sourceQuote}»
                                  </blockquote>
                                </div>
                              )}

                              {/* Прямой ответ персонального менеджера из кабинета */}
                              {ex.managerReplies.map((reply) => (
                                <div
                                  key={reply.id}
                                  className="rounded-[10px] border border-[#1E5241] bg-[#0E241E] p-3.5 space-y-1.5"
                                >
                                  <div className="flex items-center justify-between gap-2 text-[11px]">
                                    <span className="inline-flex items-center gap-1.5 font-semibold text-[#34D399]">
                                      <UserCheck
                                        className="h-3.5 w-3.5 shrink-0"
                                        strokeWidth={2}
                                      />
                                      <span>Куратор: {cleanManagerName}</span>
                                    </span>
                                    {reply.createdAtLabel && (
                                      <span className="text-[10px] text-[#A7F3D0]/80 tabular-nums">
                                        {reply.createdAtLabel}
                                      </span>
                                    )}
                                  </div>
                                  <p className="whitespace-pre-line text-xs leading-relaxed text-white">
                                    {reply.text}
                                  </p>
                                </div>
                              ))}

                              {/* Предложение эскалации куратору (если еще не закрыто ответом менеджера) */}
                              {showEscalateButton && onEscalateQuestion && (
                                <div className="rounded-[10px] border border-[#7C5A20]/40 bg-[#161B22] p-3.5 space-y-2.5 transition-colors">
                                  <div className="flex items-start gap-2.5">
                                    <HelpCircle
                                      className="h-4 w-4 shrink-0 text-[#E5C378] mt-0.5"
                                      strokeWidth={1.75}
                                    />
                                    <p className="text-xs text-[#D1D5DB] leading-relaxed">
                                      Хотите, чтобы ваш куратор{" "}
                                      <strong className="font-semibold text-white">
                                        {cleanManagerName}
                                      </strong>{" "}
                                      официально уточнила этот вопрос у оргкомитета?
                                    </p>
                                  </div>
                                  <Button
                                    type="button"
                                    variant="monolith"
                                    size="sm"
                                    disabled={ex.isEscalating}
                                    onClick={() =>
                                      onEscalateQuestion(
                                        ex.exchangeId,
                                        ex.questionText
                                      )
                                    }
                                    className="w-full text-xs font-semibold cursor-pointer"
                                  >
                                    {ex.isEscalating ? (
                                      <Loader2 className="h-3.5 w-3.5 animate-spin text-[#E5C378]" />
                                    ) : (
                                      <Send
                                        className="h-3.5 w-3.5 text-[#E5C378] monolith-icon"
                                        strokeWidth={2}
                                      />
                                    )}
                                    <span>Передать вопрос куратору</span>
                                  </Button>
                                </div>
                              )}

                              {/* Подтверждение эскалации до ответа менеджера */}
                              {!hasManagerReply && ex.isEscalated && (
                                <div className="flex items-start gap-2.5 rounded-[10px] border border-[#1E5241] bg-[#0E241E] p-3 text-xs text-[#34D399] leading-relaxed">
                                  <Check
                                    className="h-4 w-4 shrink-0 mt-0.5 text-[#34D399]"
                                    strokeWidth={2.5}
                                  />
                                  <span>
                                    Вопрос передан куратору (
                                    <strong className="font-semibold text-white">
                                      {cleanManagerName}
                                    </strong>
                                    ). Ответ появится здесь, как только куратор уточнит детали.
                                  </span>
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}

                    {mergedConversation.orphanManagerReplies.map((reply) => (
                      <div
                        key={`orphan-${reply.id}`}
                        className="rounded-[12px] border border-[#1E5241] bg-[#0E241E] p-4 space-y-1.5 shadow-sm"
                      >
                        <div className="flex items-center justify-between gap-2 text-[11px]">
                          <span className="inline-flex items-center gap-1.5 font-semibold text-[#34D399]">
                            <UserCheck
                              className="h-3.5 w-3.5 shrink-0"
                              strokeWidth={2}
                            />
                            <span>Комментарий куратора ({cleanManagerName})</span>
                          </span>
                          {reply.createdAtLabel && (
                            <span className="text-[10px] text-[#A7F3D0]/80 tabular-nums">
                              {reply.createdAtLabel}
                            </span>
                          )}
                        </div>
                        <p className="whitespace-pre-line text-xs leading-relaxed text-white">
                          {reply.text}
                        </p>
                      </div>
                    ))}
                  </>
                )}
                <div ref={feedEndRef} />
              </section>
            </>
          )}
        </motion.div>
      </AnimatePresence>
    </SlideOverDrawer>
  );
}
