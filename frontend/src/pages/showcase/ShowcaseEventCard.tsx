import * as React from "react";
import {
  MapPin,
  Globe,
  Building,
  ThumbsUp,
  RefreshCcw,
  MessageSquareText,
  ArrowUpRight,
  Check,
  Sparkles,
  Send,
} from "lucide-react";
import type { ShowcaseEventItemOut } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  AGENCY_SERVICES_STAGE_09,
  FORMAT_SHORT_LABELS,
  REPLACEMENT_QUICK_REASONS,
  ROLE_LABELS,
  formatCalendarBadge,
  formatDateShort,
  formatRub,
} from "@/lib/formatters";
import { getEventCoverVisual } from "@/lib/eventCovers";
import { cn } from "@/lib/utils";

interface ShowcaseEventCardProps {
  item: ShowcaseEventItemOut;
  selectedAgencyServices: string[];
  onToggleAgencyService: (serviceTag: string) => void;
  onReact: (reaction: "interested" | "rejected", comment?: string) => void;
  isReacting: boolean;
  onOpenRegulationDrawer: (initialQuestion?: string) => void;
  quickChips: string[];
}

export function ShowcaseEventCard({
  item,
  selectedAgencyServices,
  onToggleAgencyService,
  onReact,
  isReacting,
  onOpenRegulationDrawer,
  quickChips,
}: ShowcaseEventCardProps) {
  const [activeExpandPanel, setActiveExpandPanel] = React.useState<
    "none" | "accompaniment" | "replace"
  >("none");
  const [replaceComment, setReplaceComment] = React.useState(
    item.client_reaction === "rejected" && item.client_comment
      ? item.client_comment
      : ""
  );
  const [imageError, setImageError] = React.useState(false);

  const cal = formatCalendarBadge(item.start_date, item.end_date);
  const cover = getEventCoverVisual(item.event_id, item.event_format);
  const formatText =
    FORMAT_SHORT_LABELS[item.event_format] || "Профильное мероприятие";
  const roleText = ROLE_LABELS[item.participation_role] || "Участие делегатом";
  const locationText = item.is_online ? "Онлайн-формат" : item.city || "Россия";

  const isInterested = item.client_reaction === "interested";
  const isRejected = item.client_reaction === "rejected";

  const handleApproveClick = () => {
    const comment =
      selectedAgencyServices.length > 0
        ? `Сопровождение агентства (Этап 09): ${selectedAgencyServices.join(", ")}`
        : undefined;
    onReact("interested", comment);
    setActiveExpandPanel("accompaniment");
  };

  const handleSendAccompanimentUpdate = () => {
    const comment =
      selectedAgencyServices.length > 0
        ? `Сопровождение агентства (Этап 09): ${selectedAgencyServices.join(", ")}`
        : "Подтверждено участие по базовому тарифу";
    onReact("interested", comment);
    setActiveExpandPanel("none");
  };

  const handleSubmitReplacement = (reasonText?: string) => {
    const finalComment = (reasonText ?? replaceComment).trim();
    onReact("rejected", finalComment || "Запрошена замена площадки");
    setActiveExpandPanel("none");
  };

  return (
    <article
      className={cn(
        "flex h-full flex-col justify-between overflow-hidden rounded-card border bg-surface transition-all duration-200",
        isInterested
          ? "border-sage ring-1 ring-sage/25 shadow-elevated"
          : isRejected
            ? "border-terracotta-border bg-surface/90 opacity-90 shadow-card"
            : "border-border shadow-card hover:border-border-strong hover:shadow-elevated"
      )}
    >
      <div>
        {/* 1. Атмосферная архитектурно-деловая обложка (в стиле Фото 8 + календарный лист Фото 5) */}
        <div
          className="relative h-44 w-full overflow-hidden"
          style={{ background: cover.fallbackGradient }}
        >
          {!imageError && (
            <img
              src={cover.imageUrl}
              alt={item.canonical_title}
              onError={() => setImageError(true)}
              className="h-full w-full object-cover opacity-85 transition-transform duration-500 hover:scale-[1.02]"
            />
          )}
          <div className="absolute inset-0 bg-gradient-to-t from-ink/80 via-ink/25 to-transparent" />

          {/* Календарный лист даты слева вверху */}
          <div className="absolute left-3.5 top-3.5 flex items-center gap-2">
            <div className="flex flex-col items-center justify-center rounded-control bg-surface/95 px-2.5 py-1.5 text-ink shadow-sm backdrop-blur-sm tabular-nums">
              <span className="text-xs font-bold leading-none">
                {cal.dayText}
              </span>
              <span className="mt-0.5 text-[10px] font-semibold uppercase tracking-wider text-pine">
                {cal.monthText}
              </span>
            </div>

            <span className="rounded-badge bg-ink/65 px-2 py-1 text-[11px] font-medium text-white backdrop-blur-sm">
              {cal.durationText}
            </span>
          </div>

          {/* Локация и статус решения справа вверху */}
          <div className="absolute right-3.5 top-3.5 flex flex-col items-end gap-1.5">
            <span className="inline-flex items-center gap-1 rounded-badge bg-surface/95 px-2.5 py-1 text-xs font-medium text-ink shadow-sm backdrop-blur-sm">
              {item.is_online ? (
                <Globe className="h-3 w-3 text-sage" strokeWidth={1.75} />
              ) : (
                <MapPin className="h-3 w-3 text-pine" strokeWidth={1.75} />
              )}
              {locationText}
            </span>

            {isInterested && (
              <span className="inline-flex items-center gap-1 rounded-badge bg-sage px-2.5 py-0.5 text-[11px] font-semibold text-white shadow-sm">
                <Check className="h-3 w-3" strokeWidth={2.25} />В плане участия
              </span>
            )}
            {isRejected && (
              <span className="inline-flex items-center gap-1 rounded-badge bg-terracotta px-2.5 py-0.5 text-[11px] font-semibold text-white shadow-sm">
                Запрошена замена
              </span>
            )}
          </div>

          {/* Нижняя подпись на обложке: метка «Рекомендовано» + формат */}
          <div className="absolute bottom-3 left-3.5 right-3.5 flex items-center justify-between gap-2">
            <span className="rounded-badge bg-sage-tint/95 px-2 py-0.5 text-[11px] font-semibold text-pine">
              Рекомендовано
            </span>
            <span className="truncate text-[11px] font-medium text-white/90">
              {formatText}
            </span>
          </div>
        </div>

        {/* 2. Основной контент карточки */}
        <div className="p-4 sm:p-5">
          {/* Заголовок и площадка */}
          <h3 className="text-base font-bold leading-snug text-ink">
            {item.canonical_title}
          </h3>

          <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs text-ink-muted">
            {item.venue && (
              <span className="inline-flex items-center gap-1">
                <Building className="h-3.5 w-3.5 shrink-0" strokeWidth={1.5} />
                {item.venue}
              </span>
            )}
            {item.themes.length > 0 && (
              <>
                {item.venue && <span>·</span>}
                <span>{item.themes.slice(0, 3).join(" · ")}</span>
              </>
            )}
          </div>

          {/* Аргументы выбора площадки и целевая аудитория (Слайд 04) */}
          <div className="mt-3.5 rounded-control border-l-2 border-pine bg-canvas/75 p-3">
            <span className="block text-[10px] font-semibold uppercase tracking-wider text-pine">
              Аргументы выбора и целевая аудитория
            </span>
            <p className="mt-1 text-xs leading-relaxed text-ink-secondary">
              {item.ai_rationale}
            </p>
          </div>

          {/* Стоимость, роль участия и выгода Early Bird (в стиле Фото 8) */}
          <div className="mt-4 flex items-end justify-between border-t border-border/80 pt-3.5 tabular-nums">
            <div>
              <span className="block text-xs font-semibold text-pine">
                {roleText}
              </span>
              <span className="text-[11px] text-ink-muted">
                Тариф: {item.tariff_name}
              </span>
            </div>

            <div className="text-right">
              <div className="flex items-baseline justify-end gap-1.5">
                {item.savings > 0 && item.base_price && (
                  <span className="text-xs text-ink-faint line-through">
                    {formatRub(item.base_price)}
                  </span>
                )}
                <span className="text-lg font-bold text-ink">
                  {formatRub(item.actual_price)}
                </span>
              </div>

              {item.savings > 0 ? (
                <span className="inline-block rounded bg-sage-tint px-1.5 py-0.5 text-[11px] font-semibold text-sage border border-sage-border">
                  Выгода {formatRub(item.savings)}
                  {item.early_bird_deadline
                    ? ` до ${formatDateShort(item.early_bird_deadline).slice(0, 5)}`
                    : ""}
                </span>
              ) : (
                <span className="text-[11px] text-ink-muted">
                  Фиксированный взнос
                </span>
              )}
            </div>
          </div>

          {/* 3. Заметный блок проверки по регламенту (Изолированный RAG + быстрые чипсы) */}
          <div className="mt-3.5 rounded-control border border-border bg-canvas/55 p-2.5">
            <div className="flex items-center justify-between gap-2">
              <button
                type="button"
                onClick={() => onOpenRegulationDrawer()}
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-pine hover:underline"
              >
                <MessageSquareText className="h-3.5 w-3.5" strokeWidth={1.75} />
                <span>Условия тарифа и вопросы по регламенту</span>
              </button>
              <button
                type="button"
                onClick={() => onOpenRegulationDrawer()}
                className="inline-flex items-center gap-0.5 text-[11px] font-medium text-ink-secondary hover:text-pine"
              >
                <span>Подробнее</span>
                <ArrowUpRight className="h-3 w-3" strokeWidth={1.75} />
              </button>
            </div>

            {/* 2 быстрые кнопки-вопроса прямо на карточке */}
            <div className="mt-2 flex flex-wrap gap-1.5">
              {quickChips.slice(0, 2).map((chip) => (
                <button
                  key={chip}
                  type="button"
                  onClick={() => onOpenRegulationDrawer(chip)}
                  className="rounded-badge border border-border bg-surface px-2 py-1 text-[11px] text-ink-secondary transition-colors hover:border-pine hover:text-pine"
                >
                  {chip} →
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* 4. Нижняя панель решения клиента + Раскрываемые блоки Этапа 09 и Замены */}
      <div className="border-t border-border bg-canvas/40 p-4 pt-3.5">
        <div className="grid grid-cols-2 gap-2.5">
          <Button
            type="button"
            variant={isInterested ? "sage" : "primary"}
            size="md"
            disabled={isReacting}
            onClick={handleApproveClick}
            className="w-full"
          >
            <ThumbsUp className="h-3.5 w-3.5" strokeWidth={1.75} />
            <span>{isInterested ? "Включено в план" : "Интересно"}</span>
          </Button>

          <Button
            type="button"
            variant={isRejected ? "terracottaTint" : "outline"}
            size="md"
            disabled={isReacting}
            onClick={() =>
              setActiveExpandPanel((prev) =>
                prev === "replace" ? "none" : "replace"
              )
            }
            className="w-full"
          >
            <RefreshCcw className="h-3.5 w-3.5" strokeWidth={1.75} />
            <span>{isRejected ? "Замена запрошена" : "Заменить"}</span>
          </Button>
        </div>

        {/* Опция быстрого открытия панели сопровождения агентства (Шаг 09) */}
        {activeExpandPanel === "none" && (
          <div className="mt-2 flex items-center justify-between text-[11px]">
            <button
              type="button"
              onClick={() => setActiveExpandPanel("accompaniment")}
              className="inline-flex items-center gap-1 font-medium text-ink-secondary hover:text-pine"
            >
              <Sparkles className="h-3 w-3 text-sage" strokeWidth={1.75} />
              <span>
                {selectedAgencyServices.length > 0
                  ? `Выбрана подготовка агентства (${selectedAgencyServices.length})`
                  : "Выбрать подготовку спикера / встреч (Этап 09)"}
              </span>
            </button>

            {item.client_comment && (
              <Badge variant="surface" className="max-w-[160px] truncate">
                {item.client_comment}
              </Badge>
            )}
          </div>
        )}

        {/* Раскрываемая панель А: Выбор услуг сопровождения агентства (Шаг 09 схемы «ПУТЬ КЛИЕНТА») */}
        {activeExpandPanel === "accompaniment" && (
          <div className="mt-3 rounded-control border border-sage-border bg-surface p-3 shadow-sm">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-sage">
                Этап 09 · Подготовка под задачи компании
              </span>
              <button
                type="button"
                onClick={() => setActiveExpandPanel("none")}
                className="text-[11px] text-ink-muted hover:text-ink"
              >
                Свернуть
              </button>
            </div>
            <p className="mt-0.5 text-[11px] text-ink-muted">
              Отметьте задачи, которые возьмет на себя команда агентства:
            </p>

            <div className="mt-2 space-y-1.5">
              {AGENCY_SERVICES_STAGE_09.map((srv) => {
                const checked = selectedAgencyServices.includes(srv.shortTag);
                return (
                  <label
                    key={srv.id}
                    className={cn(
                      "flex cursor-pointer items-start gap-2 rounded-badge border p-2 text-xs transition-colors",
                      checked
                        ? "border-sage bg-sage-tint/50 text-ink"
                        : "border-border bg-canvas/50 text-ink-secondary hover:bg-canvas"
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => onToggleAgencyService(srv.shortTag)}
                      className="mt-0.5 h-3.5 w-3.5 rounded accent-pine"
                    />
                    <div className="min-w-0 flex-1">
                      <span className="block font-semibold text-ink">
                        {srv.title}
                      </span>
                      <span className="block text-[11px] text-ink-muted leading-snug">
                        {srv.subtitle}
                      </span>
                    </div>
                  </label>
                );
              })}
            </div>

            <Button
              type="button"
              variant="sage"
              size="sm"
              onClick={handleSendAccompanimentUpdate}
              className="mt-2.5 w-full"
            >
              <Send className="h-3.5 w-3.5" strokeWidth={1.75} />
              <span>Сохранить и передать менеджеру</span>
            </Button>
          </div>
        )}

        {/* Раскрываемая панель Б: Быстрые причины замены в 1 касание со смартфона (Шаг 07 «Правки») */}
        {activeExpandPanel === "replace" && (
          <div className="mt-3 rounded-control border border-terracotta-border bg-surface p-3 shadow-sm">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-terracotta">
                Корректировка плана (Правки)
              </span>
              <button
                type="button"
                onClick={() => setActiveExpandPanel("none")}
                className="text-[11px] text-ink-muted hover:text-ink"
              >
                Отмена
              </button>
            </div>
            <p className="mt-0.5 text-[11px] text-ink-muted">
              Выберите причину в 1 касание или напишите комментарий для подбора замены:
            </p>

            <div className="mt-2 flex flex-wrap gap-1.5">
              {REPLACEMENT_QUICK_REASONS.map((reason) => (
                <button
                  key={reason}
                  type="button"
                  onClick={() => {
                    setReplaceComment(reason);
                    handleSubmitReplacement(reason);
                  }}
                  className="rounded-badge border border-border bg-canvas px-2 py-1 text-[11px] font-medium text-ink-secondary transition-colors hover:border-terracotta hover:bg-terracotta-tint hover:text-terracotta"
                >
                  {reason}
                </button>
              ))}
            </div>

            <div className="mt-2 flex gap-1.5">
              <input
                type="text"
                value={replaceComment}
                onChange={(e) => setReplaceComment(e.target.value)}
                placeholder="Свой комментарий (например, другие даты)..."
                className="h-8 flex-1 rounded-control border border-border bg-canvas px-2.5 text-xs text-ink placeholder:text-ink-faint focus:border-terracotta focus:bg-surface focus:outline-none"
              />
              <Button
                type="button"
                variant="terracotta"
                size="sm"
                onClick={() => handleSubmitReplacement()}
              >
                Отправить
              </Button>
            </div>
          </div>
        )}
      </div>
    </article>
  );
}

