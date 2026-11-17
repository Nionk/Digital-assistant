import * as React from "react";
import {
  Send,
  Loader2,
  HelpCircle,
  Check,
  ChevronRight,
  UserCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  GoldShimmerBar,
  RotatingStatusText,
} from "@/components/ui/ai-shimmer-bar";
import type { MergedConversationResult } from "./mergeConversation";

interface ChatMessageThreadProps {
  activeEventTitle: string;
  faqQuickChips: string[];
  mergedConversation: MergedConversationResult;
  cleanManagerName: string;
  isAsking: boolean;
  onAskQuestion: (questionText: string) => void;
  onEscalateQuestion?: (exchangeId: string, questionText: string) => void;
}

/** Лента вопросов к ИИ-консультанту по регламенту, быстрые чипсы и ответы куратора. */
export function ChatMessageThread({
  activeEventTitle,
  faqQuickChips,
  mergedConversation,
  cleanManagerName,
  isAsking,
  onAskQuestion,
  onEscalateQuestion,
}: ChatMessageThreadProps) {
  const feedEndRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    feedEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [mergedConversation.items.length, isAsking]);

  return (
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
              Выберите вопрос выше или напишите свой в поле внизу. Мы приведем
              точную информацию из условий{" "}
              <strong className="font-medium text-[#D1D5DB]">
                «{activeEventTitle}»
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
                        <Badge variant="ebEmerald" asSlanted={false} className="text-[11px]">
                          Ответ куратора
                        </Badge>
                      )}
                      {ex.createdAtLabel && (
                        <span className="text-[11px] text-[#8E95A0] tabular-nums">
                          {ex.createdAtLabel}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Состояние загрузки */}
                  {ex.isLoading && (
                    <div className="space-y-2 rounded-[8px] border border-[#262D35] bg-[#0E1116] px-3 py-2.5">
                      <RotatingStatusText
                        active={true}
                        steps={[
                          "Изучаем официальный регламент мероприятия...",
                          "Проверяем тарифы, сроки и условия участия...",
                          "Формируем точный ответ по документации...",
                        ]}
                        intervalMs={2200}
                      />
                      <GoldShimmerBar active={true} size="thin" tone="gold" />
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
                              <span className="text-[11px] text-[#A7F3D0]/85 tabular-nums">
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
                              onEscalateQuestion(ex.exchangeId, ex.questionText)
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
                            ). Ответ появится здесь, как только куратор уточнит
                            детали.
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
                    <span className="text-[11px] text-[#A7F3D0]/85 tabular-nums">
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
  );
}
