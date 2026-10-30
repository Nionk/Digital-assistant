import * as React from "react";
import { useParams } from "react-router-dom";
import useEmblaCarousel from "embla-carousel-react";
import { toast } from "sonner";
import { motion, AnimatePresence } from "framer-motion";
import {
  ChevronLeft,
  ChevronRight,
  LayoutGrid,
  GalleryHorizontalEnd,
  MessageSquareText,
  AlertCircle,
  Sparkles,
} from "lucide-react";
import {
  useAskRegulationMutation,
  useClientReactionMutation,
  usePublicShowcase,
} from "@/api/queries";
import {
  useShowcaseStore,
  type ShowcaseRoleFilter,
} from "@/store/useShowcaseStore";
import { CalendarTimeline } from "@/components/ui/calendar-timeline";
import { ShowcaseExecutiveHeader } from "./ShowcaseExecutiveHeader";
import { ShowcaseEventCard } from "./ShowcaseEventCard";
import { RegulationConsultantDrawer } from "./RegulationConsultantDrawer";
import { AgencyWorkflowStepsSection } from "./AgencyWorkflowStepsSection";
import { cn } from "@/lib/utils";

export function ClientShowcasePage() {
  const { magicToken } = useParams<{ magicToken: string }>();
  const {
    data: showcase,
    isLoading,
    isError,
  } = usePublicShowcase(magicToken, 10000);

  const reactionMutation = useClientReactionMutation(magicToken || "");
  const askMutation = useAskRegulationMutation(magicToken || "");

  const {
    layoutMode,
    roleFilter,
    activeDrawerEventId,
    chatByEventId,
    selectedAgencyServicesByItem,
    setLayoutMode,
    setRoleFilter,
    openEventDrawer,
    closeEventDrawer,
    startQuestionExchange,
    completeQuestionExchange,
    failQuestionExchange,
    toggleAgencyServiceForItem,
  } = useShowcaseStore();

  // Инициализация Embla Carousel с поддержкой свайпа
  const [emblaRef, emblaApi] = useEmblaCarousel({
    align: "start",
    containScroll: "trimSnaps",
    dragFree: false,
  });

  const [canScrollPrev, setCanScrollPrev] = React.useState(false);
  const [canScrollNext, setCanScrollNext] = React.useState(false);

  const updateScrollButtons = React.useCallback(() => {
    if (!emblaApi) return;
    setCanScrollPrev(emblaApi.canScrollPrev());
    setCanScrollNext(emblaApi.canScrollNext());
  }, [emblaApi]);

  React.useEffect(() => {
    if (!emblaApi) return;
    updateScrollButtons();
    emblaApi.on("select", updateScrollButtons);
    emblaApi.on("reInit", updateScrollButtons);
  }, [emblaApi, updateScrollButtons, roleFilter]);

  const items = showcase?.items || [];

  const filteredItems = items.filter((item) => {
    if (roleFilter === "all") return true;
    return item.participation_role === roleFilter;
  });

  const timelineItems = items.map((item) => ({
    event_id: item.event_id,
    canonical_title: item.canonical_title,
    start_date: item.start_date,
    end_date: item.end_date,
    is_online: item.is_online,
    city: item.city,
  }));

  const activeDrawerEvent = React.useMemo(() => {
    if (!activeDrawerEventId) return null;
    return (
      items.find((i) => i.event_id === activeDrawerEventId) || items[0] || null
    );
  }, [activeDrawerEventId, items]);

  const handleReactToItem = async (
    selectionItemId: number,
    reaction: "interested" | "rejected",
    comment?: string
  ) => {
    try {
      await reactionMutation.mutateAsync({
        selectionItemId,
        payload: {
          reaction,
          comment: comment || null,
        },
      });
      if (reaction === "interested") {
        toast.success(
          comment
            ? "Мероприятие и выбранные опции подготовки сохранены"
            : "Мероприятие добавлено в ваш план участия"
        );
      } else {
        toast.success("Пожелание по замене передано вашему куратору");
      }
    } catch (err) {
      toast.error(
        err instanceof Error
          ? err.message
          : "Не удалось сохранить выбор. Повторите попытку."
      );
    }
  };

  const handleAskQuestion = async (eventId: number, questionText: string) => {
    const exchangeId = `${eventId}-${Date.now()}`;
    startQuestionExchange(eventId, exchangeId, questionText);

    try {
      const res = await askMutation.mutateAsync({
        eventId,
        payload: { question_text: questionText },
      });
      completeQuestionExchange(eventId, exchangeId, res);
    } catch (err) {
      failQuestionExchange(
        eventId,
        exchangeId,
        err instanceof Error
          ? err.message
          : "Не удалось получить ответ. Попробуйте еще раз."
      );
    }
  };

  const handleOpenRegulationDrawerForCard = (
    eventId: number,
    initialQuestion?: string
  ) => {
    openEventDrawer(eventId, "regulation");
    if (initialQuestion) {
      const existing = chatByEventId[eventId] || [];
      const alreadyAsked = existing.some(
        (ex) => ex.questionText.toLowerCase() === initialQuestion.toLowerCase()
      );
      if (!alreadyAsked) {
        handleAskQuestion(eventId, initialQuestion);
      }
    }
  };

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#0B0E12] bg-[radial-gradient(ellipse_80%_35%_at_50%_0%,rgba(124,90,32,0.06),transparent_70%)] p-6 text-white">
        <div className="rounded-[12px] border border-[#262D35] bg-[#161B22] p-8 text-center shadow-sm max-w-md w-full">
          <div className="mx-auto h-8 w-8 rounded-full border-2 border-[#262D35] border-t-[#E5C378] animate-spin" />
          <h2 className="mt-4 font-serif text-base font-semibold text-white">
            Загрузка персонального предложения...
          </h2>
          <p className="mt-1 font-serif italic text-xs text-[#E5C378]">
            Подготавливаем календарь мероприятий и условия участия
          </p>
        </div>
      </div>
    );
  }

  if (isError || !showcase) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#0B0E12] bg-[radial-gradient(ellipse_80%_35%_at_50%_0%,rgba(124,90,32,0.06),transparent_70%)] p-6 text-white">
        <div className="rounded-[12px] border border-[#262D35] bg-[#161B22] p-8 text-center shadow-sm max-w-md w-full">
          <AlertCircle
            className="mx-auto h-10 w-10 text-[#E5C378]"
            strokeWidth={1.5}
          />
          <h2 className="mt-3 font-serif text-base font-semibold text-white">
            Страница не найдена
          </h2>
          <p className="mt-1.5 font-serif italic text-xs leading-relaxed text-[#8E95A0]">
            Проверьте корректность ссылки или свяжитесь с вашим персональным куратором.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0B0E12] bg-[radial-gradient(ellipse_80%_35%_at_50%_0%,rgba(124,90,32,0.06),transparent_70%)] text-[#F3F4F6] pb-20">
      {/* 1. Шапка витрины и сводный бюджет */}
      <ShowcaseExecutiveHeader showcase={showcase} />

      {/* 2. График участия по датам */}
      <div className="mx-auto max-w-7xl px-4 pt-6 sm:px-6">
        <CalendarTimeline items={timelineItems} />
      </div>

      {/* 3. Секция рекомендованных мероприятий */}
      <section className="mx-auto max-w-7xl px-4 pt-6 sm:px-6">
        <div className="rounded-[12px] border border-[#262D35] bg-[#161B22] p-5 sm:p-6 shadow-sm">
          {/* Верхняя панель: Заголовок + Плавные селекторы без вспышек */}
          <div className="flex flex-col justify-between gap-4 border-b border-[#21262F] pb-4 lg:flex-row lg:items-center">
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-[#E5C378]" strokeWidth={1.5} />
              <h2 className="font-serif text-lg font-bold tracking-tight text-white sm:text-xl">
                Рекомендовано для вас
              </h2>
            </div>

            <div className="flex flex-wrap items-center gap-2.5">
              {/* Плавный селектор ролей без скачков рамки */}
              <div className="flex items-center rounded-[8px] border border-[#232931] bg-[#12161A] p-1 gap-0.5 shadow-inner">
                {(
                  [
                    { id: "all", label: "Все" },
                    { id: "speaker", label: "Спикер" },
                    { id: "delegate", label: "Делегат" },
                    { id: "sponsor", label: "Стенд / Партнёр" },
                  ] as { id: ShowcaseRoleFilter; label: string }[]
                ).map((tab) => {
                  const isActive = roleFilter === tab.id;
                  return (
                    <button
                      key={tab.id}
                      type="button"
                      onClick={() => setRoleFilter(tab.id)}
                      className={cn(
                        "relative rounded-[6px] px-3 py-1.5 text-xs font-medium select-none cursor-pointer transition-colors duration-200 outline-none",
                        isActive
                          ? "text-white"
                          : "text-[#8E95A0] hover:text-white"
                      )}
                    >
                      {isActive && (
                        <motion.span
                          layoutId="showcaseRoleSelectorPill"
                          transition={{
                            type: "spring",
                            stiffness: 380,
                            damping: 32,
                          }}
                          className="absolute inset-0 rounded-[6px] bg-[#1A2128] shadow-sm"
                        >
                          <span className="absolute bottom-0 left-1.5 right-1.5 h-[2px] rounded-full bg-gradient-to-r from-[#D4AF37] via-[#E5C378] to-[#D4AF37]" />
                        </motion.span>
                      )}
                      <span className="relative z-10">{tab.label}</span>
                    </button>
                  );
                })}
              </div>

              {/* Плавный переключатель Карусель / Сетка */}
              <div className="flex items-center rounded-[8px] border border-[#232931] bg-[#12161A] p-1 gap-0.5 shadow-inner">
                {(
                  [
                    {
                      id: "carousel",
                      label: "Карусель",
                      icon: GalleryHorizontalEnd,
                    },
                    {
                      id: "grid",
                      label: "Сетка",
                      icon: LayoutGrid,
                    },
                  ] as const
                ).map((mode) => {
                  const Icon = mode.icon;
                  const isActive = layoutMode === mode.id;
                  return (
                    <button
                      key={mode.id}
                      type="button"
                      onClick={() => setLayoutMode(mode.id)}
                      title={mode.label}
                      className={cn(
                        "relative inline-flex items-center gap-1.5 rounded-[6px] px-3 py-1.5 text-xs font-medium select-none cursor-pointer transition-colors duration-200 outline-none",
                        isActive
                          ? "text-white"
                          : "text-[#8E95A0] hover:text-white"
                      )}
                    >
                      {isActive && (
                        <motion.span
                          layoutId="showcaseLayoutSelectorPill"
                          transition={{
                            type: "spring",
                            stiffness: 380,
                            damping: 32,
                          }}
                          className="absolute inset-0 rounded-[6px] bg-[#1A2128] shadow-sm"
                        >
                          <span className="absolute bottom-0 left-1.5 right-1.5 h-[2px] rounded-full bg-gradient-to-r from-[#D4AF37] via-[#E5C378] to-[#D4AF37]" />
                        </motion.span>
                      )}
                      <Icon
                        className={cn(
                          "relative z-10 h-3.5 w-3.5 transition-colors duration-200",
                          isActive ? "text-[#E5C378]" : "text-[#8E95A0]"
                        )}
                        strokeWidth={1.75}
                      />
                      <span className="relative z-10 hidden sm:inline">
                        {mode.label}
                      </span>
                    </button>
                  );
                })}
              </div>

              {/* Стрелки прокрутки карусели < > */}
              {layoutMode === "carousel" && (
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => emblaApi?.scrollPrev()}
                    disabled={!canScrollPrev}
                    aria-label="Предыдущая карточка"
                    className="flex h-8 w-8 items-center justify-center rounded-[6px] border border-[#262D35] bg-[#12161A] text-white transition-colors duration-150 hover:border-[#E5C378] hover:text-[#E5C378] disabled:opacity-30 cursor-pointer"
                  >
                    <ChevronLeft className="h-4 w-4" strokeWidth={1.75} />
                  </button>
                  <button
                    type="button"
                    onClick={() => emblaApi?.scrollNext()}
                    disabled={!canScrollNext}
                    aria-label="Следующая карточка"
                    className="flex h-8 w-8 items-center justify-center rounded-[6px] border border-[#262D35] bg-[#12161A] text-white transition-colors duration-150 hover:border-[#E5C378] hover:text-[#E5C378] disabled:opacity-30 cursor-pointer"
                  >
                    <ChevronRight className="h-4 w-4" strokeWidth={1.75} />
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Отображение карточек с плавным переходом: Карусель или Сетка */}
          <div className="mt-5">
            {filteredItems.length === 0 ? (
              <div className="py-10 text-center font-serif italic text-xs text-[#8E95A0]">
                В подборке нет мероприятий с выбранным форматом участия
              </div>
            ) : (
              <AnimatePresence mode="wait">
                {layoutMode === "carousel" ? (
                  <motion.div
                    key={`showcase-carousel-${roleFilter}`}
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -4 }}
                    transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
                    className="overflow-hidden"
                    ref={emblaRef}
                  >
                    <div className="-ml-4 flex items-stretch">
                      {filteredItems.map((item) => (
                        <div
                          key={item.selection_item_id}
                          className="min-w-0 shrink-0 grow-0 basis-[88%] pl-4 sm:basis-[56%] lg:basis-1/3 flex"
                        >
                          <ShowcaseEventCard
                            item={item}
                            selectedAgencyServices={
                              selectedAgencyServicesByItem[
                                item.selection_item_id
                              ] || []
                            }
                            onToggleAgencyService={(tag) =>
                              toggleAgencyServiceForItem(
                                item.selection_item_id,
                                tag
                              )
                            }
                            onReact={(reaction, comment) =>
                              handleReactToItem(
                                item.selection_item_id,
                                reaction,
                                comment
                              )
                            }
                            isReacting={reactionMutation.isPending}
                            onOpenRegulationDrawer={(initialQuestion) =>
                              handleOpenRegulationDrawerForCard(
                                item.event_id,
                                initialQuestion
                              )
                            }
                          />
                        </div>
                      ))}
                    </div>
                  </motion.div>
                ) : (
                  <motion.div
                    key={`showcase-grid-${roleFilter}`}
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -4 }}
                    transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
                    className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3 items-stretch"
                  >
                    {filteredItems.map((item) => (
                      <ShowcaseEventCard
                        key={item.selection_item_id}
                        item={item}
                        selectedAgencyServices={
                          selectedAgencyServicesByItem[item.selection_item_id] ||
                          []
                        }
                        onToggleAgencyService={(tag) =>
                          toggleAgencyServiceForItem(
                            item.selection_item_id,
                            tag
                          )
                        }
                        onReact={(reaction, comment) =>
                          handleReactToItem(
                            item.selection_item_id,
                            reaction,
                            comment
                          )
                        }
                        isReacting={reactionMutation.isPending}
                        onOpenRegulationDrawer={(initialQuestion) =>
                          handleOpenRegulationDrawerForCard(
                            item.event_id,
                            initialQuestion
                          )
                        }
                      />
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            )}
          </div>
        </div>
      </section>

      {/* 4. Блок сопровождения агентства */}
      <AgencyWorkflowStepsSection />

      {/* 5. Стильная боковая закладка справа для открытия вопросов по условиям */}
      <AnimatePresence>
        {!activeDrawerEventId && items.length > 0 && (
          <motion.button
            initial={{ x: 40, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 40, opacity: 0 }}
            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
            type="button"
            onClick={() => openEventDrawer(items[0].event_id, "regulation")}
            className="group fixed bottom-8 right-0 z-30 flex items-center gap-2.5 rounded-l-[10px] border border-r-0 border-[#7C5A20]/60 bg-[#12161A]/95 py-2.5 pl-3 pr-4 text-left shadow-[-6px_6px_24px_rgba(0,0,0,0.65)] backdrop-blur-md transition-all duration-200 hover:border-[#E5C378] hover:bg-[#181E25] hover:pr-5 active:scale-[0.99] cursor-pointer"
          >
            {/* Золотой корешок закладки */}
            <span className="h-6 w-[3px] shrink-0 rounded-full bg-gradient-to-b from-[#E5C378] to-[#8C6A28]" />
            <MessageSquareText
              className="h-4 w-4 shrink-0 text-[#E5C378] transition-transform duration-200 group-hover:scale-105"
              strokeWidth={1.75}
            />
            <div className="leading-tight">
              <span className="block text-xs font-semibold text-[#F4EFE6] transition-colors group-hover:text-white">
                Вопросы по условиям
              </span>
              <span className="mt-0.5 block font-serif italic text-[10px] text-[#8E95A0]">
                Тарифы и документация
              </span>
            </div>
          </motion.button>
        )}
      </AnimatePresence>

      {/* 6. Выдвижная панель деталей тарифа и консультанта */}
      <RegulationConsultantDrawer
        isOpen={Boolean(activeDrawerEventId)}
        onClose={closeEventDrawer}
        events={items}
        activeEvent={activeDrawerEvent}
        onSelectEvent={(evId) => openEventDrawer(evId, "regulation")}
        faqQuickChips={showcase.faq_quick_chips}
        exchanges={
          activeDrawerEvent
            ? chatByEventId[activeDrawerEvent.event_id] || []
            : []
        }
        onAskQuestion={(q) => {
          if (activeDrawerEvent) {
            handleAskQuestion(activeDrawerEvent.event_id, q);
          }
        }}
        isAsking={askMutation.isPending}
        managerFullName={showcase.manager_full_name}
      />
    </div>
  );
}
