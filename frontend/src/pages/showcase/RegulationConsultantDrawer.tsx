import * as React from "react";
import {
  FileCheck2,
  Send,
  Zap,
  BellRing,
  MapPin,
  Calendar,
  CheckCircle2,
  Loader2,
  HelpCircle,
} from "lucide-react";
import type { ShowcaseEventItemOut } from "@/api/types";
import type { RegulationChatExchange } from "@/store/useShowcaseStore";
import { SlideOverDrawer } from "@/components/ui/slide-over-drawer";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  ROLE_LABELS,
  formatDateRange,
  formatDateShort,
  formatRub,
} from "@/lib/formatters";

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
}: RegulationConsultantDrawerProps) {
  const [inputQuestion, setInputQuestion] = React.useState("");
  const feedEndRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    feedEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [exchanges.length, isAsking]);

  if (!activeEvent) return null;

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
      subtitle="Проверка по официальному регламенту организатора"
      title={activeEvent.canonical_title}
      headerSelector={
        events.length > 1 ? (
          <div>
            <label className="block text-[10px] font-semibold uppercase tracking-wider text-neutral-400">
              Переключить проверяемую площадку пакета:
            </label>
            <select
              value={activeEvent.event_id}
              onChange={(e) => onSelectEvent(Number(e.target.value))}
              className="mt-1 h-9 w-full rounded-lg border border-[#333C48] bg-[#12161A] px-3 text-xs font-medium text-white focus:border-[#E5C378] focus:outline-none"
            >
              {events.map((ev) => (
                <option key={ev.event_id} value={ev.event_id}>
                  {ev.canonical_title} ({ev.is_online ? "Онлайн" : ev.city})
                </option>
              ))}
            </select>
          </div>
        ) : undefined
      }
      footer={
        <form onSubmit={handleFormSubmit} className="space-y-2">
          <label className="block text-[11px] font-medium text-neutral-300">
            Свободный вопрос по программе, требованиям к спикеру, застройке или логистике:
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              value={inputQuestion}
              onChange={(e) => setInputQuestion(e.target.value)}
              placeholder="Например: какие требования к презентации спикера?"
              className="h-9 flex-1 rounded-lg border border-[#333C48] bg-[#12161A] px-3 text-xs text-white placeholder:text-neutral-500 focus:border-[#E5C378] focus:bg-[#161B22] focus:outline-none"
            />
            <Button
              type="submit"
              variant="monolith"
              size="md"
              disabled={isAsking || inputQuestion.trim().length < 3}
            >
              {isAsking ? (
                <Loader2 className="h-4 w-4 animate-spin text-[#E5C378]" />
              ) : (
                <Send className="h-4 w-4 text-[#E5C378] monolith-icon" strokeWidth={2} />
              )}
            </Button>
          </div>
        </form>
      }
    >
      <div className="space-y-5">
        {/* 1. Паспорт рекомендованного тарифа и площадки */}
        <section className="rounded-2xl border border-[#262D35] bg-[#12161A] p-4.5 shadow-lg">
          <div className="flex items-center justify-between gap-2 border-b border-[#262D35] pb-3">
            <div>
              <span className="text-[10px] font-bold uppercase tracking-wider text-[#E5C378]">
                Паспорт участия в пакете
              </span>
              <h3 className="mt-0.5 text-sm font-semibold text-white">
                {activeEvent.tariff_name}
              </h3>
            </div>
            <Badge
              variant={
                activeEvent.participation_role === "speaker"
                  ? "ebGold"
                  : activeEvent.participation_role === "sponsor"
                    ? "ebRose"
                    : "ebEmerald"
              }
            >
              {ROLE_LABELS[activeEvent.participation_role]}
            </Badge>
          </div>

          <div className="mt-3.5 grid grid-cols-2 gap-2.5 text-xs tabular-nums">
            <div className="rounded-xl border border-[#262D35] bg-[#161B22] p-3">
              <span className="block text-[10px] font-medium text-neutral-400">
                Взнос организатора:
              </span>
              <span className="mt-0.5 block text-base font-bold text-white">
                {formatRub(activeEvent.actual_price)}
              </span>
              {activeEvent.savings > 0 && (
                <span className="mt-1 block text-[11px] font-bold text-[#34D399]">
                  Выгода {formatRub(activeEvent.savings)}
                  {activeEvent.early_bird_deadline
                    ? ` до ${formatDateShort(activeEvent.early_bird_deadline)}`
                    : ""}
                </span>
              )}
            </div>

            <div className="rounded-xl border border-[#262D35] bg-[#161B22] p-3">
              <span className="block text-[10px] font-medium text-neutral-400">
                Даты и место:
              </span>
              <span className="mt-0.5 flex items-center gap-1.5 font-medium text-white">
                <Calendar className="h-3.5 w-3.5 shrink-0 text-[#E5C378]" strokeWidth={1.5} />
                {formatDateRange(activeEvent.start_date, activeEvent.end_date)}
              </span>
              <span className="mt-1 flex items-center gap-1.5 truncate text-[11px] text-neutral-400">
                <MapPin className="h-3.5 w-3.5 shrink-0 text-[#E5C378]" strokeWidth={1.5} />
                {activeEvent.is_online
                  ? "Онлайн"
                  : activeEvent.venue || activeEvent.city}
              </span>
            </div>
          </div>

          {activeEvent.included_benefits && (
            <div className="mt-3.5 rounded-xl border border-[#262D35] bg-[#161B22] p-3">
              <span className="flex items-center gap-1.5 text-[11px] font-semibold text-white">
                <CheckCircle2 className="h-3.5 w-3.5 text-[#34D399]" strokeWidth={2} />
                Что входит в рекомендованный тариф:
              </span>
              <p className="mt-1.5 text-xs leading-relaxed text-neutral-300">
                {activeEvent.included_benefits}
              </p>
            </div>
          )}
        </section>

        {/* 2. Три быстрые кнопки FAQ (мгновенный ответ из llm_cache < 50 мс) */}
        <section>
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-semibold text-white">
              Быстрая проверка ключевых условий регламента:
            </span>
            <span className="text-[10px] text-neutral-400">В 1 клик</span>
          </div>

          <div className="space-y-1.5">
            {faqQuickChips.map((chip) => (
              <button
                key={chip}
                type="button"
                disabled={isAsking}
                onClick={() => onAskQuestion(chip)}
                className="group flex w-full items-center justify-between rounded-xl border border-[#262D35] bg-[#161B22] px-3.5 py-2.5 text-left text-xs font-medium text-neutral-200 transition-colors hover:border-[#7C5A20] hover:bg-[#12161A] hover:text-[#E5C378] disabled:opacity-50"
              >
                <span>{chip}</span>
                <span className="text-[#E5C378] transition-transform group-hover:translate-x-0.5">→</span>
              </button>
            ))}
          </div>
        </section>

        {/* 3. Лента ответов по регламенту с дословными цитатами и защитой от галлюцинаций */}
        <section className="space-y-3 pt-1">
          {exchanges.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-[#333C48] bg-[#12161A] p-6 text-center">
              <HelpCircle
                className="mx-auto h-7 w-7 text-[#E5C378]/60"
                strokeWidth={1.5}
              />
              <p className="mt-2 text-xs leading-relaxed text-neutral-400">
                Выберите любой вопрос выше или введите свой. Консультант проверяет строго официальный регламент площадки{" "}
                <strong className="text-neutral-200">
                  «{activeEvent.canonical_title}»
                </strong>{" "}
                и приводит точную выдержку из документа.
              </p>
            </div>
          ) : (
            exchanges.map((ex) => (
              <div
                key={ex.id}
                className="rounded-2xl border border-[#262D35] bg-[#12161A] p-4 shadow-lg space-y-3"
              >
                {/* Вопрос клиента */}
                <div className="flex items-start justify-between gap-2 border-b border-[#262D35] pb-2.5">
                  <div className="flex items-center gap-2">
                    <span className="h-2 w-2 rounded-full bg-[#E5C378]" />
                    <p className="text-xs font-semibold text-white">
                      {ex.questionText}
                    </p>
                  </div>
                  <span className="shrink-0 text-[10px] text-neutral-500 tabular-nums">
                    {ex.createdAt}
                  </span>
                </div>

                {/* Состояние загрузки */}
                {ex.isLoading && (
                  <div className="flex items-center gap-2 py-2 text-xs text-neutral-400">
                    <Loader2 className="h-4 w-4 animate-spin text-[#E5C378]" />
                    <span>Сверяем с официальным регламентом организатора...</span>
                  </div>
                )}

                {/* Ошибка сети */}
                {ex.error && (
                  <p className="text-xs text-[#F472B6]">{ex.error}</p>
                )}

                {/* Ответ ИИ по регламенту */}
                {ex.response && (
                  <div className="space-y-2.5">
                    <div className="flex flex-wrap items-center gap-1.5">
                      {ex.response.from_cache && (
                        <span className="inline-flex items-center gap-1 rounded-md bg-[#0E241E] px-2 py-0.5 text-[10px] font-semibold text-[#34D399] border border-[#1E5241]">
                          <Zap className="h-3 w-3" strokeWidth={1.75} />
                          Мгновенный ответ по базе регламента
                        </span>
                      )}
                      {ex.response.is_answer_found ? (
                        <span className="inline-flex items-center gap-1 rounded-md bg-[#161B22] px-2 py-0.5 text-[10px] font-medium text-neutral-300 border border-[#333C48]">
                          Подтверждено регламентом
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 rounded-md bg-[#28131E] px-2 py-0.5 text-[10px] font-semibold text-[#F472B6] border border-[#5E2242]">
                          Вне документа · Передано менеджеру
                        </span>
                      )}
                    </div>

                    <p className="text-xs leading-relaxed text-neutral-200">
                      {ex.response.answer_text}
                    </p>

                    {/* Дословная цитата из регламента (защита от галлюцинаций) */}
                    {ex.response.source_quote && (
                      <div className="rounded-xl border-l-2 border-[#E5C378] bg-[#161B22] p-3">
                        <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-[#E5C378]">
                          <FileCheck2 className="h-3.5 w-3.5" strokeWidth={1.75} />
                          <span>Цитата из официального регламента</span>
                        </div>
                        <blockquote className="mt-1.5 text-xs italic leading-relaxed text-neutral-300">
                          «{ex.response.source_quote}»
                        </blockquote>
                      </div>
                    )}

                    {/* Плашка эскалации вопроса менеджеру в Telegram */}
                    {ex.response.escalated_to_telegram && (
                      <div className="flex items-start gap-2.5 rounded-xl border border-[#5E2242] bg-[#28131E] p-3 text-[11px] text-[#F472B6]">
                        <BellRing
                          className="h-4 w-4 shrink-0 mt-0.5 text-[#F472B6]"
                          strokeWidth={1.75}
                        />
                        <span>
                          В тексте регламента нет этих деталей. Ваш вопрос уже автоматически передан персональному менеджеру (
                          <strong className="text-white">{managerFullName}</strong>) в Telegram для уточнения у организаторов.
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
      </div>
    </SlideOverDrawer>
  );
}
