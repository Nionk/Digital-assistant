import * as React from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  MapPin,
  Globe,
  Building,
  RefreshCcw,
  MessageSquareText,
  ChevronRight,
  ChevronDown,
  Plus,
  Check,
  Sparkles,
  Copy,
} from "lucide-react";
import type { ShowcaseEventItemOut } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  formatReactionComment,
  parseClientComment,
} from "@/lib/accompaniment";
import { copyTextToClipboard } from "@/lib/clipboard";
import {
  FORMAT_SHORT_LABELS,
  ROLE_BADGE_LABELS,
  formatCalendarBadge,
  formatDateShort,
  formatRub,
} from "@/lib/formatters";
import { getEventCoverVisual } from "@/lib/eventCovers";
import { cn } from "@/lib/utils";
import { CardAccompanimentPanel } from "./card/CardAccompanimentPanel";
import {
  CardReplacementPanel,
  mergeReplaceQuickReason,
} from "./card/CardReplacementPanel";

interface ShowcaseEventCardProps {
  item: ShowcaseEventItemOut;
  selectedAgencyServices: string[] | undefined;
  onToggleAgencyService: (serviceTag: string) => void;
  onReact: (reaction: "interested" | "rejected", comment?: string) => void;
  isReacting: boolean;
  onOpenRegulationDrawer: (initialQuestion?: string) => void;
}

export function ShowcaseEventCard({
  item,
  selectedAgencyServices,
  onToggleAgencyService,
  onReact,
  isReacting,
  onOpenRegulationDrawer,
}: ShowcaseEventCardProps) {
  const parsedComment = React.useMemo(
    () => parseClientComment(item.client_comment),
    [item.client_comment]
  );

  const [activeExpandPanel, setActiveExpandPanel] = React.useState<
    "none" | "accompaniment" | "replace"
  >("none");
  const [replaceComment, setReplaceComment] = React.useState(
    item.client_reaction === "rejected" ? parsedComment.freeNote : ""
  );
  const [interestedNote, setInterestedNote] = React.useState(
    item.client_reaction === "interested" ? parsedComment.freeNote : ""
  );
  const [hasClearedInitialServices, setHasClearedInitialServices] =
    React.useState(false);
  const [imageError, setImageError] = React.useState(false);
  const [copiedAddress, setCopiedAddress] = React.useState(false);

  const copyTimerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const prevRejectedNoteRef = React.useRef(
    item.client_reaction === "rejected" ? parsedComment.freeNote : ""
  );
  const prevInterestedNoteRef = React.useRef(
    item.client_reaction === "interested" ? parsedComment.freeNote : ""
  );

  React.useEffect(() => {
    return () => {
      if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
    };
  }, []);

  React.useEffect(() => {
    const nextRejectedNote =
      item.client_reaction === "rejected" ? parsedComment.freeNote : "";
    if (nextRejectedNote !== prevRejectedNoteRef.current) {
      prevRejectedNoteRef.current = nextRejectedNote;
      if (activeExpandPanel !== "replace") {
        setReplaceComment(nextRejectedNote);
      }
    }

    const nextInterestedNote =
      item.client_reaction === "interested" ? parsedComment.freeNote : "";
    if (nextInterestedNote !== prevInterestedNoteRef.current) {
      prevInterestedNoteRef.current = nextInterestedNote;
      if (activeExpandPanel !== "accompaniment") {
        setInterestedNote(nextInterestedNote);
      }
    }
  }, [item.client_reaction, parsedComment.freeNote, activeExpandPanel]);

  React.useEffect(() => {
    if (selectedAgencyServices !== undefined) {
      setHasClearedInitialServices(false);
    }
  }, [selectedAgencyServices]);

  const effectiveAgencyServices = React.useMemo(() => {
    if (selectedAgencyServices !== undefined) return selectedAgencyServices;
    if (hasClearedInitialServices) return [];
    return parsedComment.parsedServices;
  }, [
    selectedAgencyServices,
    hasClearedInitialServices,
    parsedComment.parsedServices,
  ]);

  const handleToggleService = (serviceTag: string) => {
    if (selectedAgencyServices !== undefined) {
      onToggleAgencyService(serviceTag);
      return;
    }
    const next = effectiveAgencyServices.includes(serviceTag)
      ? effectiveAgencyServices.filter((t) => t !== serviceTag)
      : [...effectiveAgencyServices, serviceTag];
    if (next.length === 0) {
      setHasClearedInitialServices(true);
      return;
    }
    setHasClearedInitialServices(false);
    for (const tag of next) {
      onToggleAgencyService(tag);
    }
  };

  const cal = formatCalendarBadge(item.start_date, item.end_date);
  const cover = getEventCoverVisual(item.event_id, item.event_format);
  const formatText =
    FORMAT_SHORT_LABELS[item.event_format] || "Профильное мероприятие";
  const locationText = item.is_online ? "Онлайн-формат" : item.city || "Россия";

  const isInterested = item.client_reaction === "interested";
  const isRejected = item.client_reaction === "rejected";

  const cleanClientComment = React.useMemo(() => {
    if (parsedComment.freeNote) return parsedComment.freeNote;
    if (!isInterested && parsedComment.parsedServices.length > 0) {
      return parsedComment.parsedServices.join(", ");
    }
    return null;
  }, [parsedComment, isInterested]);

  const handleCopyAddress = async (e: React.MouseEvent) => {
    e.stopPropagation();
    const addressToCopy = item.venue
      ? `${item.venue}${item.city ? `, ${item.city}` : ""}`
      : item.city || (item.is_online ? "Онлайн-мероприятие" : "Россия");

    const ok = await copyTextToClipboard(addressToCopy, {
      successMessage: `Адрес скопирован: ${addressToCopy}`,
    });
    if (!ok) return;
    if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
    setCopiedAddress(true);
    copyTimerRef.current = setTimeout(() => {
      setCopiedAddress(false);
    }, 2200);
  };

  const handleApproveClick = () => {
    if (isInterested) {
      setActiveExpandPanel((prev) =>
        prev === "accompaniment" ? "none" : "accompaniment"
      );
      return;
    }
    const comment = formatReactionComment(
      effectiveAgencyServices,
      interestedNote
    );
    onReact("interested", comment);
    setActiveExpandPanel("accompaniment");
  };

  const handleSendAccompanimentUpdate = () => {
    const comment =
      formatReactionComment(effectiveAgencyServices, interestedNote) ?? "";
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
        "group flex h-full w-full flex-col justify-between overflow-hidden rounded-[12px] border transition-colors duration-200",
        isInterested
          ? "border-[#1E5241] bg-[#161B22] shadow-[0_4px_24px_rgba(16,185,129,0.12)]"
          : isRejected
            ? "border-[#5E2242]/80 bg-[#161B22]/90 opacity-90"
            : "border-[#262D35] bg-[#161B22] shadow-sm hover:border-[#7C5A20]/50"
      )}
    >
      {/* Верхняя и средняя часть карточки (растягивается через flex-1 для идеального выравнивания низа) */}
      <div className="flex flex-1 flex-col">
        <div
          className="relative h-44 w-full shrink-0 overflow-hidden"
          style={{ background: cover.fallbackGradient }}
        >
          {!imageError && (
            <img
              src={cover.imageUrl}
              alt={item.canonical_title}
              onError={() => setImageError(true)}
              className="h-full w-full object-cover opacity-80 transition-transform duration-500 group-hover:scale-[1.02]"
            />
          )}
          <div className="absolute inset-0 bg-gradient-to-t from-[#161B22] via-[#161B22]/35 to-transparent" />

          {/* Календарный лист даты слева вверху */}
          <div className="absolute left-3.5 top-3.5 flex items-center gap-2">
            <div className="flex flex-col items-center justify-center rounded-[6px] border border-[#7C5A20]/50 bg-[#12161A]/95 px-2.5 py-1.5 text-white shadow-md backdrop-blur-md tabular-nums">
              <span className="text-xs font-bold leading-none">
                {cal.dayText}
              </span>
              <span className="mt-0.5 text-[11px] font-semibold uppercase tracking-wider text-[#E5C378]">
                {cal.monthText}
              </span>
            </div>

            <span className="rounded-[6px] border border-white/10 bg-[#12161A]/85 px-2 py-1 text-[11px] font-medium text-[#D1D5DB] backdrop-blur-md">
              {cal.durationText}
            </span>
          </div>

          {/* Локация (с копированием в 1 клик) и статус справа вверху */}
          <div className="absolute right-3.5 top-3.5 flex flex-col items-end gap-1.5">
            <button
              type="button"
              onClick={handleCopyAddress}
              title="Нажмите, чтобы скопировать адрес площадки"
              className="group/loc inline-flex items-center gap-1.5 rounded-[6px] border border-[#7C5A20]/50 bg-[#12161A]/95 px-2.5 py-1 text-[11px] font-medium text-[#E5E7EB] shadow-md backdrop-blur-md transition-colors hover:border-[#E5C378] hover:text-[#E5C378] cursor-pointer"
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
              <span className="inline-flex items-center gap-1.5 rounded-[6px] border border-[#1E5241] bg-[#0E241E]/95 px-2.5 py-1 text-[11px] font-bold uppercase tracking-wider text-[#34D399] shadow-md backdrop-blur-md">
                <Check className="h-3 w-3" strokeWidth={2.5} />В ПЛАНЕ УЧАСТИЯ
              </span>
            )}
            {isRejected && (
              <span className="inline-flex items-center gap-1.5 rounded-[6px] border border-[#5E2242] bg-[#28131E]/95 px-2.5 py-1 text-[11px] font-bold uppercase tracking-wider text-[#F472B6] shadow-md backdrop-blur-md">
                ЗАПРОШЕНА ЗАМЕНА
              </span>
            )}
          </div>

          {/* Формат мероприятия внизу обложки */}
          <div className="absolute bottom-2.5 left-3.5 right-3.5 flex items-center justify-between gap-2">
            <span className="inline-flex items-center rounded-[4px] border border-[#262D35] bg-[#12161A]/90 px-2 py-0.5 text-[11px] font-medium text-[#D1D5DB] backdrop-blur-sm">
              {formatText}
            </span>
          </div>
        </div>

        <div className="flex flex-1 flex-col p-4 sm:p-5">
          {/* Заголовок и площадка */}
          <h3 className="font-serif text-lg font-bold leading-snug text-white transition-colors group-hover:text-[#E5C378] sm:text-[19px]">
            {item.canonical_title}
          </h3>

          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-[#8E95A0]">
            {item.venue && (
              <button
                type="button"
                onClick={handleCopyAddress}
                title="Скопировать местоположение"
                className="group/ven inline-flex items-center gap-1 text-[#D1D5DB] hover:text-[#E5C378] transition-colors cursor-pointer"
              >
                <Building
                  className="h-3.5 w-3.5 shrink-0 text-[#E5C378]/80"
                  strokeWidth={1.5}
                />
                <span className="truncate max-w-[230px]">{item.venue}</span>
                <Copy className="h-2.5 w-2.5 opacity-40 group-hover/ven:opacity-100 transition-opacity" />
              </button>
            )}
            {item.themes.length > 0 && (
              <>
                {item.venue && <span className="text-[#4B5563]">·</span>}
                <span className="text-[#8E95A0]">
                  {item.themes.slice(0, 3).join(" · ")}
                </span>
              </>
            )}
          </div>

          {/* Почему мы рекомендуем это событие (клиентоориентированная подача) */}
          <div className="mt-3.5 rounded-[8px] border border-[#262D35] border-l-2 border-l-[#E5C378] bg-[#12161A] p-3">
            <span className="block font-serif italic text-xs font-semibold text-[#E5C378]">
              Почему мы рекомендуем это событие
            </span>
            <p className="mt-1 text-xs leading-relaxed text-[#D1D5DB]">
              {item.ai_rationale}
            </p>
          </div>

          {/* Нижний блок внутри контента (прижат к низу через mt-auto для ровной линии в ряду карточек) */}
          <div className="mt-auto pt-4">
            {/* Стоимость, роль участия и выгода Early Bird */}
            <div className="flex items-end justify-between border-t border-[#21262F] pt-3.5 tabular-nums">
              <div className="min-w-0 pr-2">
                <div className="flex items-center gap-1.5">
                  <Badge
                    variant={
                      item.participation_role === "speaker"
                        ? "ebGold"
                        : item.participation_role === "sponsor"
                          ? "ebRose"
                          : "ebBlue"
                    }
                  >
                    {ROLE_BADGE_LABELS[item.participation_role]}
                  </Badge>
                </div>
                <span
                  className="mt-1.5 block truncate text-[11px] text-[#8E95A0]"
                  title={item.tariff_name}
                >
                  Тариф: {item.tariff_name}
                </span>
              </div>

              <div className="shrink-0 text-right">
                <div className="flex items-baseline justify-end gap-1.5">
                  {item.savings > 0 && item.base_price && (
                    <span className="text-xs text-[#8E95A0] line-through">
                      {formatRub(item.base_price)}
                    </span>
                  )}
                  <span className="text-lg font-bold text-white">
                    {formatRub(item.actual_price)}
                  </span>
                </div>

                {item.savings > 0 ? (
                  <span className="mt-0.5 inline-block shrink-0 rounded-[4px] border border-[#1E5241] bg-[#0E241E] px-2 py-0.5 text-[11px] font-bold text-[#34D399] tabular-nums">
                    ВЫГОДА {formatRub(item.savings)}
                    {item.early_bird_deadline
                      ? ` до ${formatDateShort(item.early_bird_deadline).slice(0, 5)}`
                      : ""}
                  </span>
                ) : (
                  <span className="text-[11px] text-[#8E95A0]">
                    Фиксированный взнос
                  </span>
                )}
              </div>
            </div>

            <button
              type="button"
              onClick={() => onOpenRegulationDrawer()}
              className="group/chat mt-3.5 flex w-full items-center justify-between gap-3 rounded-[8px] border border-[#262D35] bg-[#12161A] px-3.5 py-2.5 text-left transition-all duration-150 hover:border-[#7C5A20] hover:bg-[#181E25] cursor-pointer"
            >
              <div className="flex min-w-0 items-center gap-2.5">
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[6px] border border-[#7C5A20]/40 bg-[#161B22] text-[#E5C378] transition-colors group-hover/chat:border-[#E5C378]">
                  <MessageSquareText className="h-3.5 w-3.5" strokeWidth={1.75} />
                </div>
                <div className="min-w-0">
                  <span className="block truncate text-xs font-semibold text-[#F4EFE6] transition-colors group-hover/chat:text-white">
                    Условия тарифа и вопросы
                  </span>
                  <span className="mt-0.5 block truncate text-[11px] text-[#8E95A0]">
                    {item.included_benefits
                      ? item.included_benefits
                      : "Состав пакета, регламент и ответы консультанта"}
                  </span>
                </div>
              </div>

              <span className="inline-flex shrink-0 items-center gap-1 rounded-[5px] border border-[#7C5A20]/40 bg-[#161B22] px-2.5 py-1 text-[11px] font-medium text-[#E5C378] transition-all group-hover/chat:border-[#E5C378] group-hover/chat:bg-[#261E0F] group-hover/chat:text-white">
                <span>Чат</span>
                <ChevronRight className="h-3 w-3" strokeWidth={2} />
              </span>
            </button>
          </div>
        </div>
      </div>

      <div
        className={cn(
          "border-t p-4 pt-3.5 transition-colors duration-200",
          isInterested
            ? "border-[#1E5241]/70 bg-[#0B1C16]/85"
            : "border-[#21262F] bg-[#12161A]/85"
        )}
      >
        <div className="grid grid-cols-2 gap-2.5">
          {/* Кнопка Добавить в план: Золотой плюс -> Изумрудная галочка */}
          <Button
            type="button"
            variant={isInterested ? "outline" : "monolith"}
            size="md"
            disabled={isReacting}
            onClick={handleApproveClick}
            className={cn(
              "w-full text-xs font-semibold tracking-wide transition-all duration-200 cursor-pointer",
              isInterested
                ? "border-[#1E5241] bg-[#0E241E] text-[#34D399] hover:bg-[#14332A] hover:border-[#2B6E58] shadow-[0_0_12px_rgba(16,185,129,0.15)]"
                : ""
            )}
          >
            <AnimatePresence mode="wait" initial={false}>
              {isInterested ? (
                <motion.span
                  key="icon-check"
                  initial={{ scale: 0.4, rotate: -45, opacity: 0 }}
                  animate={{ scale: 1, rotate: 0, opacity: 1 }}
                  exit={{ scale: 0.4, opacity: 0 }}
                  transition={{ duration: 0.18, ease: "easeOut" }}
                  className="inline-flex items-center justify-center"
                >
                  <Check className="h-4 w-4 text-[#34D399]" strokeWidth={2.5} />
                </motion.span>
              ) : (
                <motion.span
                  key="icon-plus"
                  initial={{ scale: 0.4, rotate: 45, opacity: 0 }}
                  animate={{ scale: 1, rotate: 0, opacity: 1 }}
                  exit={{ scale: 0.4, opacity: 0 }}
                  transition={{ duration: 0.18, ease: "easeOut" }}
                  className="inline-flex items-center justify-center"
                >
                  <Plus
                    className="h-4 w-4 text-[#E5C378] monolith-icon"
                    strokeWidth={2.25}
                  />
                </motion.span>
              )}
            </AnimatePresence>
            <span>{isInterested ? "В плане участия" : "Добавить в план"}</span>
          </Button>

          {/* Кнопка Запросить замену */}
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
              "w-full text-xs font-semibold tracking-wide transition-all duration-200 cursor-pointer",
              isRejected
                ? "border-[#5E2242] bg-[#28131E] text-[#F472B6] hover:bg-[#381a2b]"
                : "border-[#262D35] bg-[#161B22] text-[#D1D5DB] hover:border-[#5E2242] hover:text-[#F472B6]"
            )}
          >
            <RefreshCcw className="h-3.5 w-3.5" strokeWidth={1.75} />
            <span>{isRejected ? "Замена запрошена" : "Запросить замену"}</span>
          </Button>
        </div>

        {/* Строка открытия деталей помощи агентства (понятным для клиента языком) */}
        {activeExpandPanel === "none" && (
          <div className="mt-2.5 flex items-center justify-between gap-2 text-[11px]">
            <button
              type="button"
              onClick={() => setActiveExpandPanel("accompaniment")}
              className={cn(
                "inline-flex items-center gap-1.5 font-medium transition-colors cursor-pointer",
                isInterested
                  ? "text-[#A7F3D0] hover:text-white"
                  : "text-[#8E95A0] hover:text-[#E5C378]"
              )}
            >
              <Sparkles
                className={cn(
                  "h-3.5 w-3.5 shrink-0",
                  isInterested ? "text-[#34D399]" : "text-[#E5C378]"
                )}
                strokeWidth={1.75}
              />
              <span>
                {effectiveAgencyServices.length > 0
                  ? `Выбрана помощь агентства (${effectiveAgencyServices.length})`
                  : "Помощь агентства на мероприятии"}
              </span>
              <ChevronDown className="h-3 w-3 opacity-70" strokeWidth={1.75} />
            </button>

            {cleanClientComment && (
              <span
                className={cn(
                  "max-w-[155px] truncate rounded-[4px] border px-2 py-0.5 text-[11px]",
                  isInterested
                    ? "border-[#1E5241] bg-[#0E241E] text-[#A7F3D0]"
                    : "border-[#262D35] bg-[#161B22] text-[#8E95A0]"
                )}
                title={cleanClientComment}
              >
                {cleanClientComment}
              </span>
            )}
          </div>
        )}

        {/* Раскрываемое изумрудное окно: Подготовка и сопровождение от агентства */}
        <AnimatePresence>
          {activeExpandPanel === "accompaniment" && (
            <CardAccompanimentPanel
              key="accompaniment"
              effectiveAgencyServices={effectiveAgencyServices}
              interestedNote={interestedNote}
              isReacting={isReacting}
              onToggleService={handleToggleService}
              onChangeInterestedNote={setInterestedNote}
              onClose={() => setActiveExpandPanel("none")}
              onSubmit={handleSendAccompanimentUpdate}
            />
          )}

          {/* Раскрываемое окно: Пожелания для подбора замены */}
          {activeExpandPanel === "replace" && (
            <CardReplacementPanel
              key="replace"
              replaceComment={replaceComment}
              isReacting={isReacting}
              onChangeReplaceComment={setReplaceComment}
              onSelectQuickReason={(reason) => {
                setReplaceComment((prev) =>
                  mergeReplaceQuickReason(prev, reason)
                );
              }}
              onSubmit={() => handleSubmitReplacement()}
              onClose={() => setActiveExpandPanel("none")}
            />
          )}
        </AnimatePresence>
      </div>
    </article>
  );
}
