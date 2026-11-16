import {
  RefreshCcw,
  Clock,
  ExternalLink,
  Copy,
  Check,
  MessageSquare,
  Send,
  Loader2,
  HelpCircle,
  ChevronDown,
  History,
  UserCheck,
} from "lucide-react";
import * as React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  queryKeys,
  useManagerReplyMutation,
  useSelectionActivity,
} from "@/api/queries";
import type {
  SelectionActivityOut,
  SelectionItemReactionActivity,
  ShowcaseEventItemOut,
} from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { parseClientComment } from "@/lib/accompaniment";
import {
  ROLE_BADGE_LABELS,
  formatDateRange,
  formatRub,
} from "@/lib/formatters";
import { cn } from "@/lib/utils";

interface PublishedShowcaseMonitorProps {
  selectionId: number | null;
  magicToken: string;
  publishedSummary?: {
    totalPrice: number;
    totalSavings: number;
    totalEventsCount?: number;
  } | null;
  showcaseItems?: ShowcaseEventItemOut[];
  onCopyLink: (url: string) => Promise<boolean> | boolean | void;
}

function formatQuestionTime(raw: string | null | undefined): string {
  if (!raw) return "";
  const normalized = raw.includes(" ") && !raw.includes("T") ? raw.replace(" ", "T") : raw;
  const parsed = new Date(normalized);
  if (Number.isNaN(parsed.getTime())) return raw;
  return parsed.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Панель живого мониторинга опубликованной витрины клиента (TanStack Query Polling 10s через /activity).
 * Показывает реакции на мероприятия и вопросы клиентов от ИИ-консультанта с формой прямого ответа.
 */
export function PublishedShowcaseMonitor({
  selectionId,
  magicToken,
  publishedSummary,
  showcaseItems,
  onCopyLink,
}: PublishedShowcaseMonitorProps) {
  const queryClient = useQueryClient();
  const { data: activity, isLoading: isActivityLoading } = useSelectionActivity(
    selectionId,
    10_000
  );
  const replyMutation = useManagerReplyMutation(selectionId ?? 0);

  const [copied, setCopied] = React.useState(false);
  const [replyDrafts, setReplyDrafts] = React.useState<Record<number, string>>({});
  const [sendingMessageId, setSendingMessageId] = React.useState<number | null>(
    null
  );
  const [isHistoryOpen, setIsHistoryOpen] = React.useState(false);
  const copyTimerRef = React.useRef<number | null>(null);

  React.useEffect(() => {
    setCopied(false);
    setReplyDrafts({});
    setSendingMessageId(null);
    setIsHistoryOpen(false);
  }, [magicToken, selectionId]);

  React.useEffect(() => {
    return () => {
      if (copyTimerRef.current !== null) {
        window.clearTimeout(copyTimerRef.current);
      }
    };
  }, []);

  const relativeUrl = `/s/${magicToken}`;

  const handleCopy = async () => {
    const ok = await onCopyLink(relativeUrl);
    if (ok === false) return;
    setCopied(true);
    if (copyTimerRef.current !== null) {
      window.clearTimeout(copyTimerRef.current);
    }
    copyTimerRef.current = window.setTimeout(() => {
      setCopied(false);
      copyTimerRef.current = null;
    }, 2000);
  };

  const reactionByItemId = React.useMemo(() => {
    const map = new Map<number, SelectionItemReactionActivity>();
    for (const r of activity?.reactions ?? []) {
      map.set(r.item_id, r);
    }
    return map;
  }, [activity?.reactions]);

  const reactionByEventId = React.useMemo(() => {
    const map = new Map<number, SelectionItemReactionActivity>();
    for (const r of activity?.reactions ?? []) {
      map.set(r.event_id, r);
    }
    return map;
  }, [activity?.reactions]);

  const handleReplySubmit = async (
    e: React.FormEvent<HTMLFormElement>,
    messageId: number
  ) => {
    e.preventDefault();
    if (!selectionId) {
      toast.error("Идентификатор подборки ещё не загружен.");
      return;
    }
    const text = (replyDrafts[messageId] || "").trim();
    if (!text) {
      toast.error("Введите текст ответа для клиента.");
      return;
    }

    setSendingMessageId(messageId);
    try {
      const res = await replyMutation.mutateAsync({
        message_id: messageId,
        reply_text: text,
      });

      queryClient.setQueryData<SelectionActivityOut>(
        queryKeys.selectionActivity(selectionId),
        (prev) => {
          if (!prev) return prev;
          const answeredQ = prev.pending_questions.find(
            (q) => q.message_id === messageId
          );
          const nowIso = new Date().toISOString();
          const newReply = {
            reply_message_id: res.reply_message_id,
            reply_text: text,
            created_at: nowIso,
          };
          const nextResolved = answeredQ
            ? [
                {
                  message_id: answeredQ.message_id,
                  event_id: answeredQ.event_id,
                  event_title: answeredQ.event_title,
                  question_text: answeredQ.question_text,
                  question_created_at: answeredQ.created_at,
                  replies: [newReply],
                  latest_reply_text: text,
                  replied_at: nowIso,
                },
                ...prev.resolved_questions.filter(
                  (r) => r.message_id !== answeredQ.message_id
                ),
              ]
            : prev.resolved_questions;

          return {
            ...prev,
            pending_questions: prev.pending_questions.filter(
              (q) => q.message_id !== messageId
            ),
            resolved_questions: nextResolved,
          };
        }
      );
      queryClient.invalidateQueries({
        queryKey: queryKeys.selectionActivity(selectionId),
      });
      queryClient.invalidateQueries({
        queryKey: queryKeys.showcase(magicToken),
      });

      setReplyDrafts((prev) => {
        const next = { ...prev };
        delete next[messageId];
        return next;
      });
      toast.success(res.message || "Ответ отправлен в витрину клиента.");
    } catch (err) {
      toast.error(
        err instanceof Error
          ? err.message
          : "Не удалось отправить ответ клиенту."
      );
    } finally {
      setSendingMessageId((prev) => (prev === messageId ? null : prev));
    }
  };

  const hasShowcaseItems = Boolean(showcaseItems && showcaseItems.length > 0);
  const pendingQuestions = activity?.pending_questions ?? [];
  const resolvedQuestions = activity?.resolved_questions ?? [];

  if (!selectionId && !hasShowcaseItems) {
    return null;
  }
  if (isActivityLoading && !activity && !hasShowcaseItems) {
    return null;
  }

  const displayCards = hasShowcaseItems
    ? showcaseItems!.map((item) => {
      const live =
        reactionByItemId.get(item.selection_item_id) ??
        reactionByEventId.get(item.event_id);
      return {
        key: item.selection_item_id,
        title: item.canonical_title,
        role: item.participation_role,
        isOnline: item.is_online,
        city: item.city,
        startDate: item.start_date,
        endDate: item.end_date,
        actualPrice: item.actual_price,
        reaction: live ? live.reaction : item.client_reaction,
        comment: live ? live.comment : item.client_comment,
      };
    })
    : (activity?.reactions ?? []).map((r) => ({
      key: r.item_id,
      title: r.event_title,
      role: null,
      isOnline: null,
      city: null,
      startDate: null,
      endDate: null,
      actualPrice: null,
      reaction: r.reaction,
      comment: r.comment,
    }));

  const approvedCount = displayCards.filter(
    (c) => c.reaction === "interested"
  ).length;
  const rejectedCount = displayCards.filter(
    (c) => c.reaction === "rejected"
  ).length;

  const totalEventsCount = hasShowcaseItems
    ? showcaseItems!.length
    : (publishedSummary?.totalEventsCount ?? displayCards.length);
  const totalPrice = publishedSummary?.totalPrice ?? null;
  const totalSavings = publishedSummary?.totalSavings ?? 0;

  return (
    <section className="rounded-[12px] border border-[#262D35] bg-[#161B22] p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#21262F] pb-3">
        <div className="flex items-center gap-2.5">
          <span className="text-[#34D399] text-xs select-none">✦</span>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="font-serif italic text-[17px] sm:text-[18px] font-semibold tracking-tight text-[#E5C378]">
                Мониторинг согласования витрины
              </h2>
              <Badge variant="ebEmerald" asSlanted={false} className="text-[11px]">
                Опубликовано
              </Badge>
            </div>
            <p className="mt-0.5 text-xs text-[#8E95A0] tabular-nums">
              {totalEventsCount > 0 ? `Площадок в КП: ${totalEventsCount}` : "Живой статус реакций и вопросов"}
              {totalPrice !== null && (
                <>
                  {" "}
                  · Взносы:{" "}
                  <strong className="text-white">{formatRub(totalPrice)}</strong>
                </>
              )}
              {totalSavings > 0 && (
                <>
                  {" "}
                  · Выгода по спецтарифам:{" "}
                  <strong className="text-[#34D399]">
                    {formatRub(totalSavings)}
                  </strong>
                </>
              )}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="hidden sm:flex items-center gap-1.5 mr-2 text-xs tabular-nums">
            <Badge variant="ebTeal" asSlanted={false} className="text-[11px]">
              В плане: {approvedCount}
            </Badge>
            {rejectedCount > 0 && (
              <Badge variant="ebRose" asSlanted={false} className="text-[11px]">
                Запрос замены: {rejectedCount}
              </Badge>
            )}
            {pendingQuestions.length > 0 && (
              <Badge variant="ebAmber" asSlanted={false} className="text-[11px]">
                Вопросы: {pendingQuestions.length}
              </Badge>
            )}
          </div>

          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleCopy}
            className="border-[#262D35] bg-[#12161A] text-white hover:border-[#E5C378] hover:text-[#E5C378] hover:bg-[#1A2128] transition-colors"
          >
            {copied ? (
              <>
                <Check className="h-3.5 w-3.5 text-[#34D399]" />
                <span>Ссылка скопирована</span>
              </>
            ) : (
              <>
                <Copy className="h-3.5 w-3.5" strokeWidth={1.5} />
                <span>Скопировать ссылку</span>
              </>
            )}
          </Button>

          <a
            href={relativeUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex h-8 items-center gap-1.5 rounded-[6px] border border-[#7C5A20]/70 bg-[#1E190E] px-3 text-xs font-serif italic text-[#E5C378] transition-all duration-150 hover:border-[#E5C378] hover:bg-[#261E0F] hover:text-white hover:shadow-[0_0_10px_rgba(229,195,120,0.2)] select-none"
          >
            <ExternalLink className="h-3.5 w-3.5 text-[#E5C378]" strokeWidth={1.75} />
            <span>Витрина клиента</span>
          </a>
        </div>
      </div>

      {/* Статусы и комментарии клиента по каждому мероприятию опубликованного пакета */}
      {displayCards.length > 0 && (
        <div className="mt-3 grid grid-cols-1 gap-2.5 md:grid-cols-3">
          {displayCards.map((item) => {
            const isInterested = item.reaction === "interested";
            const isRejected = item.reaction === "rejected";
            const parsedComment = parseClientComment(item.comment);
            const hasCommentContent =
              Boolean(parsedComment.freeNote) ||
              parsedComment.parsedServices.length > 0;

            return (
              <div
                key={item.key}
                className="flex flex-col justify-between rounded-[8px] border border-[#262C35] bg-[#1A1E24] p-3"
              >
                <div>
                  <div className="flex items-center justify-between gap-2">
                    {item.role ? (
                      <Badge
                        variant={
                          item.role === "speaker"
                            ? "ebGold"
                            : item.role === "sponsor"
                              ? "ebRose"
                              : "ebBlue"
                        }
                      >
                        {ROLE_BADGE_LABELS[item.role]}
                      </Badge>
                    ) : (
                      <span className="text-[11px] font-serif italic text-[#8E95A0]">
                        Реакция клиента
                      </span>
                    )}

                    {isInterested ? (
                      <Badge variant="ebEmerald" asSlanted={false} className="text-[11px]">
                        <Check className="h-3 w-3 stroke-[2.5]" />
                        В плане
                      </Badge>
                    ) : isRejected ? (
                      <Badge variant="ebRose" asSlanted={false} className="text-[11px]">
                        <RefreshCcw className="h-3 w-3 stroke-[2.5]" />
                        Запрос замены
                      </Badge>
                    ) : (
                      <Badge variant="ebSlate" asSlanted={false} className="text-[11px]">
                        <Clock className="h-3 w-3" strokeWidth={2} />
                        Ожидает решения
                      </Badge>
                    )}
                  </div>

                  <h4 className="mt-2 text-xs font-semibold leading-snug text-white">
                    {item.title}
                  </h4>

                  {item.startDate && item.endDate && (
                    <p className="mt-0.5 text-[11px] text-[#8E95A0]">
                      {item.isOnline ? "Онлайн" : item.city || "Россия"} ·{" "}
                      {formatDateRange(item.startDate, item.endDate)} ·{" "}
                      <strong className="text-[#D1D5DB] tabular-nums">
                        {formatRub(item.actualPrice)}
                      </strong>
                    </p>
                  )}
                </div>

                {hasCommentContent && (
                  <div className="mt-2.5 rounded-[6px] border border-[#262C35] bg-[#12161A] p-2 text-[11px] text-[#D1D5DB] space-y-1.5">
                    {parsedComment.freeNote && (
                      <div>
                        <div className="flex items-center gap-1 font-semibold text-white">
                          <MessageSquare
                            className="h-3 w-3 text-[#E5C378]"
                            strokeWidth={1.5}
                          />
                          <span>Комментарий клиента:</span>
                        </div>
                        <p className="mt-0.5 leading-relaxed whitespace-pre-line">
                          {parsedComment.freeNote}
                        </p>
                      </div>
                    )}
                    {parsedComment.parsedServices.length > 0 && (
                      <div className="space-y-1">
                        <span className="block text-[11px] font-semibold uppercase tracking-wider text-[#34D399]">
                          Опции сопровождения:
                        </span>
                        <div className="flex flex-wrap gap-1">
                          {parsedComment.parsedServices.map((srv) => (
                            <span
                              key={srv}
                              className="inline-flex items-center rounded-[4px] border border-[#1E5241] bg-[#0E241E] px-1.5 py-0.5 text-[11px] font-medium text-[#A7F3D0]"
                            >
                              {srv}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Лента эскалированных вопросов клиентов от ИИ-консультанта и форма ответа менеджера */}
      <div className="mt-3.5 border-t border-[#21262F] pt-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <HelpCircle className="h-4 w-4 text-[#E5C378]" strokeWidth={1.75} />
            <h3 className="font-serif italic text-xs font-semibold tracking-wide text-[#E5C378]">
              Вопросы клиентов от ИИ-консультанта
            </h3>
            <Badge
              variant={pendingQuestions.length > 0 ? "ebAmber" : "darkSubtle"}
              asSlanted={false}
              className="text-[11px]"
            >
              {pendingQuestions.length > 0
                ? `Ожидают ответа: ${pendingQuestions.length}`
                : "Нет открытых вопросов"}
            </Badge>
          </div>
        </div>

        {pendingQuestions.length > 0 && (
          <div className="mt-2.5 space-y-2.5">
            {pendingQuestions.map((q) => {
              const draftValue = replyDrafts[q.message_id] ?? "";
              const isSending = sendingMessageId === q.message_id;
              const formattedTime = formatQuestionTime(q.created_at);

              return (
                <form
                  key={q.message_id}
                  onSubmit={(e) => handleReplySubmit(e, q.message_id)}
                  className="rounded-[8px] border border-[#7C5A20]/50 bg-[#12161A] p-3 space-y-2"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2 text-[11px]">
                    <span className="font-semibold text-[#E5C378]">
                      {q.event_title || "Общий вопрос по подборке"}
                    </span>
                    {formattedTime && (
                      <span className="text-[#8E95A0] tabular-nums">
                        {formattedTime}
                      </span>
                    )}
                  </div>

                  <p className="text-xs leading-relaxed text-white">
                    {q.question_text}
                  </p>

                  <div className="flex flex-col sm:flex-row items-stretch sm:items-end gap-2 pt-1">
                    <textarea
                      id={`monitor-reply-${q.message_id}`}
                      name={`reply_${q.message_id}`}
                      aria-label={`Официальный ответ клиенту по вопросу: ${q.event_title || "подборка"}`}
                      rows={2}
                      value={draftValue}
                      disabled={isSending}
                      onChange={(e) =>
                        setReplyDrafts((prev) => ({
                          ...prev,
                          [q.message_id]: e.target.value,
                        }))
                      }
                      placeholder="Напишите официальный ответ клиенту (он сразу появится в шторке витрины)..."
                      className="flex-1 rounded-[6px] border border-[#262D35] bg-[#161B22] p-2 text-xs text-white placeholder:text-[#8E95A0] [color-scheme:dark] outline-none focus:border-[#E5C378] focus:shadow-[0_0_0_1px_rgba(229,195,120,0.25)] transition-colors"
                    />
                    <Button
                      type="submit"
                      variant="monolith"
                      size="sm"
                      disabled={isSending || draftValue.trim().length === 0}
                      className="shrink-0 h-8 px-3.5 text-xs font-semibold"
                    >
                      {isSending ? (
                        <>
                          <Loader2 className="h-3.5 w-3.5 animate-spin text-[#E5C378]" />
                          <span>Отправка...</span>
                        </>
                      ) : (
                        <>
                          <Send
                            className="h-3.5 w-3.5 text-[#E5C378] monolith-icon"
                            strokeWidth={1.75}
                          />
                          <span>Отправить ответ</span>
                        </>
                      )}
                    </Button>
                  </div>
                </form>
              );
            })}
          </div>
        )}

        {resolvedQuestions.length > 0 && (
          <div className="mt-3 border-t border-[#21262F] pt-2.5">
            <button
              type="button"
              onClick={() => setIsHistoryOpen((prev) => !prev)}
              aria-expanded={isHistoryOpen}
              className="flex w-full items-center justify-between gap-2 rounded-[8px] border border-[#262D35] bg-[#12161A] px-3 py-2 text-left text-xs transition-colors hover:border-[#34D399]/50 hover:bg-[#161B21] cursor-pointer"
            >
              <span className="inline-flex items-center gap-2 font-medium text-[#D1D5DB]">
                <History className="h-3.5 w-3.5 text-[#34D399]" strokeWidth={1.75} />
                <span>История ответов куратора ({resolvedQuestions.length})</span>
              </span>
              <ChevronDown
                className={cn(
                  "h-3.5 w-3.5 text-[#8E95A0] transition-transform duration-150",
                  isHistoryOpen && "rotate-180 text-[#34D399]"
                )}
              />
            </button>

            {isHistoryOpen && (
              <div className="mt-2 space-y-2">
                {resolvedQuestions.map((resolved) => {
                  const qTime = formatQuestionTime(resolved.question_created_at);
                  return (
                    <div
                      key={resolved.message_id}
                      className="rounded-[8px] border border-[#262C35] bg-[#12161A] p-3 space-y-2"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2 text-[11px]">
                        <span className="font-semibold text-[#E5C378]">
                          {resolved.event_title || "Общий вопрос по подборке"}
                        </span>
                        {qTime && (
                          <span className="text-[#8E95A0] tabular-nums">
                            {qTime}
                          </span>
                        )}
                      </div>

                      <p className="text-xs leading-relaxed text-[#D1D5DB]">
                        {resolved.question_text}
                      </p>

                      <div className="space-y-1.5">
                        {(resolved.replies.length > 0
                          ? resolved.replies
                          : [
                              {
                                reply_message_id: resolved.message_id,
                                reply_text: resolved.latest_reply_text,
                                created_at: resolved.replied_at,
                              },
                            ]
                        ).map((reply) => {
                          const rTime = formatQuestionTime(reply.created_at);
                          return (
                            <div
                              key={reply.reply_message_id}
                              className="rounded-[6px] border border-[#1E5241] bg-[#0E241E]/75 p-2.5 space-y-1"
                            >
                              <div className="flex items-center justify-between gap-2 text-[11px]">
                                <span className="inline-flex items-center gap-1 font-semibold text-[#34D399]">
                                  <UserCheck className="h-3 w-3 shrink-0" strokeWidth={2} />
                                  <span>Ответ куратора</span>
                                </span>
                                {rTime && (
                                  <span className="text-[#A7F3D0]/80 tabular-nums">
                                    {rTime}
                                  </span>
                                )}
                              </div>
                              <p className="whitespace-pre-line text-xs leading-relaxed text-white">
                                {reply.reply_text}
                              </p>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

