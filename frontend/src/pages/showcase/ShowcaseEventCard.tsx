import * as React from "react";
import {
  MapPin,
  Globe,
  Building,
  RefreshCcw,
  MessageSquareText,
  ArrowUpRight,
  Check,
  Sparkles,
  Send,
  Copy,
} from "lucide-react";
import { toast } from "sonner";
import type { ShowcaseEventItemOut } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  AGENCY_SERVICES_STAGE_09,
  FORMAT_SHORT_LABELS,
  REPLACEMENT_QUICK_REASONS,
  ROLE_BADGE_LABELS,
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
  const [copiedAddress, setCopiedAddress] = React.useState(false);

  const cal = formatCalendarBadge(item.start_date, item.end_date);
  const cover = getEventCoverVisual(item.event_id, item.event_format);
  const formatText =
    FORMAT_SHORT_LABELS[item.event_format] || "Профильное мероприятие";
  const locationText = item.is_online ? "Онлайн-формат" : item.city || "Россия";

  const isInterested = item.client_reaction === "interested";
  const isRejected = item.client_reaction === "rejected";

  const handleCopyAddress = (e: React.MouseEvent) => {
    e.stopPropagation();
    const addressToCopy = item.venue
      ? `${item.venue}${item.city ? `, ${item.city}` : ""}`
      : item.city || (item.is_online ? "Онлайн-мероприятие" : "Россия");
    
    if (navigator?.clipboard?.writeText) {
      navigator.clipboard.writeText(addressToCopy);
      setCopiedAddress(true);
      toast.success("Адрес скопирован в буфер", {
        description: addressToCopy,
      });
      setTimeout(() => setCopiedAddress(false), 2200);
    }
  };

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
        "group flex h-full flex-col justify-between overflow-hidden rounded-2xl border transition-all duration-200",
        isInterested
          ? "border-[#1E5241] bg-[#161B22] shadow-[0_4px_24px_rgba(30,82,65,0.25)] ring-1 ring-[#1E5241]/60"
          : isRejected
            ? "border-[#5E2242] bg-[#161B22]/90 opacity-90 shadow-lg"
            : "border-[#262D35] bg-[#161B22] shadow-xl hover:border-[#7C5A20]/60 hover:shadow-[0_8px_30px_rgba(0,0,0,0.5)]"
      )}
    >
      <div>
        {/* 1. Атмосферная архитектурно-деловая обложка с золотыми акцентами */}
        <div
          className="relative h-44 w-full overflow-hidden"
          style={{ background: cover.fallbackGradient }}
        >
          {!imageError && (
            <img
              src={cover.imageUrl}
              alt={item.canonical_title}
              onError={() => setImageError(true)}
              className="h-full w-full object-cover opacity-80 transition-transform duration-500 group-hover:scale-[1.03]"
            />
          )}
          <div className="absolute inset-0 bg-gradient-to-t from-[#161B22] via-[#161B22]/40 to-transparent" />

          {/* Календарный лист даты слева вверху */}
          <div className="absolute left-3.5 top-3.5 flex items-center gap-2">
            <div className="flex flex-col items-center justify-center rounded-lg border border-[#7C5A20]/40 bg-[#12161A]/95 px-2.5 py-1.5 text-white shadow-md backdrop-blur-md tabular-nums">
              <span className="text-xs font-bold leading-none">
                {cal.dayText}
              </span>
              <span className="mt-0.5 text-[10px] font-semibold uppercase tracking-wider text-[#E5C378]">
                {cal.monthText}
              </span>
            </div>

            <span className="rounded-md border border-white/10 bg-[#161B22]/85 px-2 py-1 text-[11px] font-medium text-neutral-200 backdrop-blur-md">
              {cal.durationText}
            </span>
          </div>

          {/* Локация (с копированием в 1 клик) и статус решения справа вверху */}
          <div className="absolute right-3.5 top-3.5 flex flex-col items-end gap-1.5">
            <button
              type="button"
              onClick={handleCopyAddress}
              title="Нажмите, чтобы скопировать адрес площадки"
              className="group/loc inline-flex items-center gap-1.5 rounded-lg border border-[#7C5A20]/50 bg-[#12161A]/95 px-2.5 py-1 text-[11px] font-medium text-neutral-200 shadow-md backdrop-blur-md transition-all hover:border-[#E5C378] hover:text-[#E5C378]"
            >
              {copiedAddress ? (
                <>
                  <Check className="h-3 w-3 text-[#34D399]" strokeWidth={2.5} />
                  <span className="text-[#34D399] font-medium">Скопировано</span>
                </>
              ) : (
                <>
                  {item.is_online ? (
                    <Globe className="h-3 w-3 text-[#34D399]" strokeWidth={1.75} />
                  ) : (
                    <MapPin className="h-3 w-3 text-[#E5C378]" strokeWidth={1.75} />
                  )}
                  <span className="max-w-[140px] truncate">{locationText}</span>
                  <Copy className="h-2.5 w-2.5 opacity-40 group-hover/loc:opacity-100 transition-opacity" />
                </>
              )}
            </button>

            {isInterested && (
              <span className="inline-flex items-center gap-1.5 rounded-md bg-[#0E241E] px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-[#34D399] border border-[#1E5241] shadow-md backdrop-blur-md">
                <Check className="h-3 w-3" strokeWidth={2.5} />В ПЛАНЕ УЧАСТИЯ
              </span>
            )}
            {isRejected && (
              <span className="inline-flex items-center gap-1.5 rounded-md bg-[#28131E] px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-[#F472B6] border border-[#5E2242] shadow-md backdrop-blur-md">
                ЗАПРОШЕНА ЗАМЕНА
              </span>
            )}
          </div>

          {/* Нижняя подпись на обложке: литературный бейдж «Рекомендовано» + формат */}
          <div className="absolute bottom-3 left-3.5 right-3.5 flex items-center justify-between gap-2">
            <Badge variant="ebGold" className="text-[10px] tracking-wider uppercase">
              РЕКОМЕНДОВАНО
            </Badge>
            <span className="truncate text-[11px] font-medium text-neutral-300">
              {formatText}
            </span>
          </div>
        </div>

        {/* 2. Основной контент карточки */}
        <div className="p-4 sm:p-5">
          {/* Заголовок и площадка */}
          <h3 className="font-serif text-lg font-bold leading-snug text-white transition-colors group-hover:text-[#E5C378] sm:text-[19px]">
            {item.canonical_title}
          </h3>

          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-neutral-400">
            {item.venue && (
              <button
                type="button"
                onClick={handleCopyAddress}
                title="Скопировать местоположение"
                className="group/ven inline-flex items-center gap-1 text-neutral-300 hover:text-[#E5C378] transition-colors"
              >
                <Building className="h-3.5 w-3.5 shrink-0 text-[#E5C378]/80" strokeWidth={1.5} />
                <span className="truncate max-w-[220px]">{item.venue}</span>
                <Copy className="h-2.5 w-2.5 opacity-40 group-hover/ven:opacity-100 transition-opacity" />
              </button>
            )}
            {item.themes.length > 0 && (
              <>
                {item.venue && <span className="text-neutral-600">·</span>}
                <span className="text-neutral-400">{item.themes.slice(0, 3).join(" · ")}</span>
              </>
            )}
          </div>

          {/* Аргументы выбора площадки и целевая аудитория */}
          <div className="mt-3.5 rounded-xl border-l-2 border-[#E5C378] bg-[#12161A] p-3 shadow-inner">
            <span className="block text-[10px] font-bold uppercase tracking-wider text-[#E5C378]">
              Аргументы выбора и целевая аудитория
            </span>
            <p className="mt-1 text-xs leading-relaxed text-neutral-300">
              {item.ai_rationale}
            </p>
          </div>

          {/* Стоимость, роль участия и выгода Early Bird */}
          <div className="mt-4 flex items-end justify-between border-t border-[#262D35] pt-3.5 tabular-nums">
            <div>
              <div className="flex items-center gap-1.5">
                <Badge
                  variant={
                    item.participation_role === "speaker"
                      ? "ebGold"
                      : item.participation_role === "sponsor"
                        ? "ebRose"
                        : "ebEmerald"
                  }
                >
                  {ROLE_BADGE_LABELS[item.participation_role]}
                </Badge>
              </div>
              <span className="mt-1 block text-[11px] text-neutral-400">
                Тариф: {item.tariff_name}
              </span>
            </div>

            <div className="text-right">
              <div className="flex items-baseline justify-end gap-1.5">
                {item.savings > 0 && item.base_price && (
                  <span className="text-xs text-neutral-500 line-through">
                    {formatRub(item.base_price)}
                  </span>
                )}
                <span className="text-lg font-bold text-white">
                  {formatRub(item.actual_price)}
                </span>
              </div>

              {item.savings > 0 ? (
                <span className="inline-block shrink-0 rounded-md border border-[#1E5241] bg-[#0E241E] px-2 py-0.5 text-[10px] font-bold text-[#34D399] tabular-nums">
                  ВЫГОДА {formatRub(item.savings)}
                  {item.early_bird_deadline
                    ? ` до ${formatDateShort(item.early_bird_deadline).slice(0, 5)}`
                    : ""}
                </span>
              ) : (
                <span className="text-[11px] text-neutral-500">
                  Фиксированный взнос
                </span>
              )}
            </div>
          </div>

          {/* 3. Блок проверки по регламенту (Изолированный RAG + быстрые чипсы) */}
          <div className="mt-3.5 rounded-xl border border-[#262D35] bg-[#12161A] p-2.5">
            <div className="flex items-center justify-between gap-2">
              <button
                type="button"
                onClick={() => onOpenRegulationDrawer()}
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#E5C378] hover:text-[#F3D796] transition-colors"
              >
                <MessageSquareText className="h-3.5 w-3.5" strokeWidth={1.75} />
                <span>Условия тарифа и вопросы по регламенту</span>
              </button>
              <button
                type="button"
                onClick={() => onOpenRegulationDrawer()}
                className="inline-flex items-center gap-0.5 text-[11px] font-medium text-neutral-400 hover:text-[#E5C378] transition-colors"
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
                  className="rounded-lg border border-[#262D35] bg-[#161B22] px-2.5 py-1 text-[11px] text-neutral-300 transition-colors hover:border-[#7C5A20] hover:text-[#E5C378]"
                >
                  {chip} →
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* 4. Нижняя панель решения клиента + Раскрываемые блоки Этапа 09 и Замены */}
      <div className="border-t border-[#262D35] bg-[#12161A]/80 p-4 pt-3.5">
        <div className="grid grid-cols-2 gap-2.5">
          <Button
            type="button"
            variant={isInterested ? "outline" : "monolith"}
            size="md"
            disabled={isReacting}
            onClick={handleApproveClick}
            className={cn(
              "w-full text-xs font-bold tracking-wider uppercase transition-all duration-200",
              isInterested
                ? "border-[#1E5241] bg-[#0E241E] text-[#34D399] hover:bg-[#153a2e] hover:border-[#2b6e58]"
                : ""
            )}
          >
            <Check className={cn("h-3.5 w-3.5", isInterested ? "text-[#34D399]" : "text-[#E5C378] monolith-icon")} strokeWidth={2.5} />
            <span>{isInterested ? "В плане участия" : "Включить в план"}</span>
          </Button>

          <Button
            type="button"
            variant="outline"
            size="md"
            disabled={isReacting}
            onClick={() =>
              setActiveExpandPanel((prev) =>
                prev === "replace" ? "none" : "replace"
              )
            }
            className={cn(
              "w-full text-xs font-bold tracking-wider uppercase transition-all duration-200",
              isRejected
                ? "border-[#5E2242] bg-[#28131E] text-[#F472B6] hover:bg-[#381a2b]"
                : "border-[#333C48] bg-[#161B22] text-neutral-300 hover:border-[#5E2242] hover:text-[#F472B6]"
            )}
          >
            <RefreshCcw className="h-3.5 w-3.5" strokeWidth={1.75} />
            <span>{isRejected ? "Замена запрошена" : "Запросить замену"}</span>
          </Button>
        </div>

        {/* Опция быстрого открытия панели сопровождения агентства (Шаг 09) */}
        {activeExpandPanel === "none" && (
          <div className="mt-2.5 flex items-center justify-between text-[11px]">
            <button
              type="button"
              onClick={() => setActiveExpandPanel("accompaniment")}
              className="inline-flex items-center gap-1.5 font-medium text-neutral-400 hover:text-[#E5C378] transition-colors"
            >
              <Sparkles className="h-3.5 w-3.5 text-[#E5C378]" strokeWidth={1.75} />
              <span>
                {selectedAgencyServices.length > 0
                  ? `Выбрана подготовка агентства (${selectedAgencyServices.length})`
                  : "Выбрать подготовку спикера / встреч (Этап 09)"}
              </span>
            </button>

            {item.client_comment && (
              <span className="max-w-[160px] truncate rounded-md border border-[#262D35] bg-[#161B22] px-2 py-0.5 text-[10px] text-neutral-400">
                {item.client_comment}
              </span>
            )}
          </div>
        )}

        {/* Раскрываемая панель А: Выбор услуг сопровождения агентства (Шаг 09 схемы «ПУТЬ КЛИЕНТА») */}
        {activeExpandPanel === "accompaniment" && (
          <div className="mt-3 rounded-xl border border-[#1E5241]/60 bg-[#12161A] p-3.5 shadow-lg">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-[#34D399]">
                Этап 09 · Подготовка под задачи компании
              </span>
              <button
                type="button"
                onClick={() => setActiveExpandPanel("none")}
                className="text-[11px] text-neutral-400 hover:text-white transition-colors"
              >
                Свернуть
              </button>
            </div>
            <p className="mt-1 text-[11px] text-neutral-400">
              Отметьте задачи, которые возьмет на себя команда агентства:
            </p>

            <div className="mt-2.5 space-y-1.5">
              {AGENCY_SERVICES_STAGE_09.map((srv) => {
                const checked = selectedAgencyServices.includes(srv.shortTag);
                return (
                  <label
                    key={srv.id}
                    className={cn(
                      "flex cursor-pointer items-start gap-2.5 rounded-lg border p-2 text-xs transition-colors",
                      checked
                        ? "border-[#1E5241] bg-[#0E241E] text-white"
                        : "border-[#262D35] bg-[#161B22] text-neutral-300 hover:border-[#333C48]"
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => onToggleAgencyService(srv.shortTag)}
                      className="mt-0.5 h-3.5 w-3.5 rounded accent-[#34D399]"
                    />
                    <div className="min-w-0 flex-1">
                      <span className="block font-semibold text-white">
                        {srv.title}
                      </span>
                      <span className="block text-[11px] text-neutral-400 leading-snug">
                        {srv.subtitle}
                      </span>
                    </div>
                  </label>
                );
              })}
            </div>

            <Button
              type="button"
              variant="monolith"
              size="sm"
              onClick={handleSendAccompanimentUpdate}
              className="mt-3 w-full"
            >
              <Send className="h-3.5 w-3.5 text-[#E5C378] monolith-icon" strokeWidth={1.75} />
              <span>Сохранить и передать менеджеру</span>
            </Button>
          </div>
        )}

        {/* Раскрываемая панель Б: Быстрые причины замены в 1 касание (Шаг 07 «Правки») */}
        {activeExpandPanel === "replace" && (
          <div className="mt-3 rounded-xl border border-[#5E2242]/60 bg-[#12161A] p-3.5 shadow-lg">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-[#F472B6]">
                Корректировка плана (Правки)
              </span>
              <button
                type="button"
                onClick={() => setActiveExpandPanel("none")}
                className="text-[11px] text-neutral-400 hover:text-white transition-colors"
              >
                Отмена
              </button>
            </div>
            <p className="mt-1 text-[11px] text-neutral-400">
              Выберите причину в 1 касание или напишите комментарий для подбора замены:
            </p>

            <div className="mt-2.5 flex flex-wrap gap-1.5">
              {REPLACEMENT_QUICK_REASONS.map((reason) => (
                <button
                  key={reason}
                  type="button"
                  onClick={() => {
                    setReplaceComment(reason);
                    handleSubmitReplacement(reason);
                  }}
                  className="rounded-lg border border-[#333C48] bg-[#161B22] px-2.5 py-1 text-[11px] font-medium text-neutral-300 transition-colors hover:border-[#5E2242] hover:bg-[#28131E] hover:text-[#F472B6]"
                >
                  {reason}
                </button>
              ))}
            </div>

            <div className="mt-2.5 flex gap-1.5">
              <input
                type="text"
                value={replaceComment}
                onChange={(e) => setReplaceComment(e.target.value)}
                placeholder="Свой комментарий (например, другие даты)..."
                className="h-8 flex-1 rounded-lg border border-[#333C48] bg-[#161B22] px-2.5 text-xs text-white placeholder:text-neutral-500 focus:border-[#F472B6] focus:outline-none"
              />
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => handleSubmitReplacement()}
                className="border-[#5E2242] bg-[#28131E] text-[#F472B6] hover:bg-[#381a2b]"
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
