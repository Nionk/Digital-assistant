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
            <label className="block text-[10px] font-semibold uppercase tracking-wider text-ink-muted">
              Переключить проверяемую площадку пакета:
            </label>
            <select
              value={activeEvent.event_id}
              onChange={(e) => onSelectEvent(Number(e.target.value))}
              className="mt-1 h-8 w-full rounded-control border border-border bg-surface px-2.5 text-xs font-medium text-ink focus:border-pine focus:outline-none"
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
          <label className="block text-[11px] font-medium text-ink-secondary">
            Свободный вопрос по программе, требованиям к спикеру, застройке или логистике:
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              value={inputQuestion}
              onChange={(e) => setInputQuestion(e.target.value)}
              placeholder="Например: какие требования к презентации спикера?"
              className="h-9 flex-1 rounded-control border border-border bg-canvas px-3 text-xs text-ink placeholder:text-ink-faint focus:border-pine focus:bg-surface focus:outline-none"
            />
            <Button
              type="submit"
              variant="primary"
              size="md"
              disabled={isAsking || inputQuestion.trim().length < 3}
            >
              {isAsking ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" strokeWidth={1.75} />
              )}
            </Button>
          </div>
        </form>
      }
    >
      <div className="space-y-5">
        {/* 1. Паспорт рекомендованного тарифа и площадки */}
        <section className="rounded-card border border-border bg-canvas/60 p-4">
          <div className="flex items-center justify-between gap-2 border-b border-border/80 pb-2.5">
            <div>
              <span className="text-[10px] font-semibold uppercase tracking-wider text-pine">
                Паспорт участия в пакете
              </span>
              <h3 className="text-sm font-semibold text-ink">
                {activeEvent.tariff_name}
              </h3>
            </div>
            <Badge variant="pine">
              {ROLE_LABELS[activeEvent.participation_role]}
            </Badge>
          </div>

          <div className="mt-3 grid grid-cols-2 gap-2.5 text-xs tabular-nums">
            <div className="rounded-control border border-border/80 bg-surface p-2.5">
              <span className="block text-[10px] text-ink-muted">
                Взнос организатора:
              </span>
              <span className="mt-0.5 block text-sm font-bold text-ink">
                {formatRub(activeEvent.actual_price)}
              </span>
              {activeEvent.savings > 0 && (
                <span className="text-[11px] font-medium text-sage">
                  Выгода {formatRub(activeEvent.savings)}
                  {activeEvent.early_bird_deadline
                    ? ` до ${formatDateShort(activeEvent.early_bird_deadline)}`
                    : ""}
                </span>
              )}
            </div>

            <div className="rounded-control border border-border/80 bg-surface p-2.5">
              <span className="block text-[10px] text-ink-muted">
                Даты и место:
              </span>
              <span className="mt-0.5 flex items-center gap-1 font-medium text-ink">
                <Calendar className="h-3 w-3 shrink-0 text-pine" strokeWidth={1.5} />
                {formatDateRange(activeEvent.start_date, activeEvent.end_date)}
              </span>
              <span className="mt-0.5 flex items-center gap-1 truncate text-[11px] text-ink-muted">
                <MapPin className="h-3 w-3 shrink-0" strokeWidth={1.5} />
                {activeEvent.is_online
                  ? "Онлайн"
                  : activeEvent.venue || activeEvent.city}
              </span>
            </div>
          </div>

          {activeEvent.included_benefits && (
            <div className="mt-3 rounded-control border border-border/80 bg-surface p-3">
              <span className="flex items-center gap-1.5 text-[11px] font-semibold text-ink">
                <CheckCircle2 className="h-3.5 w-3.5 text-sage" strokeWidth={1.75} />
                Что входит в рекомендованный тариф:
              </span>
              <p className="mt-1 text-xs leading-relaxed text-ink-secondary">
                {activeEvent.included_benefits}
              </p>
            </div>
          )}
        </section>

        {/* 2. Три быстрые кнопки FAQ (мгновенный ответ из llm_cache < 50 мс) */}
        <section>
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-semibold text-ink">
              Быстрая проверка ключевых условий регламента:
            </span>
            <span className="text-[10px] text-ink-muted">В 1 клик</span>
          </div>

          <div className="space-y-1.5">
            {faqQuickChips.map((chip) => (
              <button
                key={chip}
                type="button"
                disabled={isAsking}
                onClick={() => onAskQuestion(chip)}
                className="flex w-full items-center justify-between rounded-control border border-border bg-surface px-3 py-2 text-left text-xs font-medium text-ink transition-colors hover:border-pine hover:bg-canvas disabled:opacity-50"
              >
                <span>{chip}</span>
                <span className="text-pine">→</span>
              </button>
            ))}
          </div>
        </section>

        {/* 3. Лента ответов по регламенту с дословными цитатами и защитой от галлюцинаций */}
        <section className="space-y-3 pt-1">
          {exchanges.length === 0 ? (
            <div className="rounded-card border border-dashed border-border-strong bg-canvas/40 p-5 text-center">
              <HelpCircle
                className="mx-auto h-6 w-6 text-ink-faint"
                strokeWidth={1.5}
              />
              <p className="mt-2 text-xs leading-relaxed text-ink-muted">
                Выберите любой вопрос выше или введите свой. Консультант проверяет строго официальный регламент площадки{" "}
                <strong className="text-ink-secondary">
                  «{activeEvent.canonical_title}»
                </strong>{" "}
                и приводит точную выдержку из документа.
              </p>
            </div>
          ) : (
            exchanges.map((ex) => (
              <div
                key={ex.id}
                className="rounded-card border border-border bg-surface p-3.5 shadow-card space-y-2.5"
              >
                {/* Вопрос клиента */}
                <div className="flex items-start justify-between gap-2 border-b border-border/70 pb-2">
                  <p className="text-xs font-semibold text-ink">
                    {ex.questionText}
                  </p>
                  <span className="shrink-0 text-[10px] text-ink-faint tabular-nums">
                    {ex.createdAt}
                  </span>
                </div>

                {/* Состояние загрузки */}
                {ex.isLoading && (
                  <div className="flex items-center gap-2 py-2 text-xs text-ink-muted">
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-pine" />
                    <span>Сверяем с регламентом организатора...</span>
                  </div>
                )}

                {/* Ошибка сети */}
                {ex.error && (
                  <p className="text-xs text-terracotta">{ex.error}</p>
                )}

                {/* Ответ ИИ по регламенту */}
                {ex.response && (
                  <div className="space-y-2.5">
                    <div className="flex flex-wrap items-center gap-1.5">
                      {ex.response.from_cache && (
                        <span className="inline-flex items-center gap-1 rounded-badge bg-sage-tint px-2 py-0.5 text-[10px] font-semibold text-sage border border-sage-border">
                          <Zap className="h-3 w-3" strokeWidth={1.75} />
                          Мгновенный ответ по базе регламента
                        </span>
                      )}
                      {ex.response.is_answer_found ? (
                        <span className="inline-flex items-center gap-1 rounded-badge bg-canvas px-2 py-0.5 text-[10px] font-medium text-ink-secondary border border-border">
                          Подтверждено регламентом
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 rounded-badge bg-terracotta-tint px-2 py-0.5 text-[10px] font-semibold text-terracotta border border-terracotta-border">
                          Вне документа · Передано менеджеру
                        </span>
                      )}
                    </div>

                    <p className="text-xs leading-relaxed text-ink">
                      {ex.response.answer_text}
                    </p>

                    {/* Дословная цитата из регламента (защита от галлюцинаций) */}
                    {ex.response.source_quote && (
                      <div className="rounded-control border-l-2 border-sage bg-canvas p-2.5">
                        <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-sage">
                          <FileCheck2 className="h-3.5 w-3.5" strokeWidth={1.75} />
                          <span>Цитата из официального регламента</span>
                        </div>
                        <blockquote className="mt-1 text-xs italic leading-relaxed text-ink-secondary">
                          «{ex.response.source_quote}»
                        </blockquote>
                      </div>
                    )}

                    {/* Плашка эскалации вопроса менеджеру в Telegram */}
                    {ex.response.escalated_to_telegram && (
                      <div className="flex items-start gap-2 rounded-control border border-terracotta-border bg-terracotta-tint/70 p-2.5 text-[11px] text-terracotta">
                        <BellRing
                          className="h-4 w-4 shrink-0 mt-0.5"
                          strokeWidth={1.75}
                        />
                        <span>
                          В тексте регламента нет этих деталей. Ваш вопрос уже автоматически передан персональному менеджеру (
                          <strong>{managerFullName}</strong>) в Telegram для уточнения у организаторов.
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

