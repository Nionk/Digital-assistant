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
import { Badge } from "@/components/ui/badge";
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

  // Инициализация Embla Carousel с поддержкой свайпа и частичным показом следующей карточки на мобильном
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
  }, [emblaApi, updateScrollButtons]);

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
            ? "Площадка и запрошенная подготовка сохранены. Менеджер уведомлен в Telegram."
            : "Площадка отмечена как интересная. Менеджер получил уведомление."
        );
      } else {
        toast.success(
          "Пожелание по замене передано вашему менеджеру в Telegram."
        );
      }
    } catch (err) {
      toast.error(
        err instanceof Error
          ? err.message
          : "Не удалось сохранить отклик. Повторите попытку."
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
          : "Ошибка при обращении к консультанту по регламенту"
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
      <div className="flex min-h-screen items-center justify-center bg-[#0B0E12] p-6 text-white">
        <div className="rounded-[12px] border border-[#262D35] bg-[#161B22] p-8 text-center shadow-sm max-w-md w-full">
          <div className="mx-auto h-8 w-8 rounded-full border-2 border-[#262D35] border-t-[#E5C378] animate-spin" />
          <h2 className="mt-4 font-serif text-base font-semibold text-white">
            Загрузка персонального предложения...
          </h2>
          <p className="mt-1 font-serif italic text-xs text-[#E5C378]">
            Формируем рекомендованный календарь мероприятий и условия участия
          </p>
        </div>
      </div>
    );
  }

  if (isError || !showcase) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#0B0E12] p-6 text-white">
        <div className="rounded-[12px] border border-[#262D35] bg-[#161B22] p-8 text-center shadow-sm max-w-md w-full">
          <AlertCircle
            className="mx-auto h-10 w-10 text-[#E5C378]"
            strokeWidth={1.5}
          />
          <h2 className="mt-3 font-serif text-base font-semibold text-white">
            Персональная витрина не найдена
          </h2>
          <p className="mt-1.5 font-serif italic text-xs leading-relaxed text-[#8E95A0]">
            Проверьте корректность ссылки или обратитесь к вашему персональному продюсеру сопровождения ГК «СКАРТ».
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0B0E12] text-[#F3F4F6] pb-16">
      {/* 1. Шапка «Исполнительное досье» (Executive Briefing) */}
      <ShowcaseExecutiveHeader
        showcase={showcase}
        onOpenConsultant={() => {
          if (items[0]) openEventDrawer(items[0].event_id);
        }}
      />

      {/* 2. Визуальная шкала календаря без пересечений по датам */}
      <div className="mx-auto max-w-7xl px-4 pt-6 sm:px-6">
        <CalendarTimeline items={timelineItems} />
      </div>

      {/* 3. Секция «Рекомендовано для вас» (Карусель / Сетка в стиле Фото 8) */}
      <section className="mx-auto max-w-7xl px-4 pt-7 sm:px-6">
        <div className="rounded-[12px] border border-[#262D35] bg-[#161B22] p-5 sm:p-6 shadow-sm">
          {/* Верхняя панель секции карточек: Заголовок + Фильтры ролей + Переключатель вида + Стрелки < > */}
          <div className="flex flex-col justify-between gap-4 border-b border-[#21262F] pb-4 lg:flex-row lg:items-center">
            <div>
              <div className="flex items-center gap-2">
                <Badge variant="ebGold" className="text-[10px]">
                  ВЫБОР АГЕНТСТВА
                </Badge>
                <h2 className="font-serif text-xl font-bold tracking-tight text-white sm:text-2xl">
                  Рекомендовано для вас
                </h2>
              </div>
              <p className="mt-1 text-xs text-[#8E95A0] font-serif italic">
                Площадки отобраны с учетом ваших целевых ориентиров, аудитории и лимита бюджета
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2.5">
              {/* Быстрый фильтр по ролям */}
              <div className="flex items-center rounded-[8px] border border-[#262D35] bg-[#12161A] p-0.5">
                {(
                  [
                    { id: "all", label: "Все" },
                    { id: "speaker", label: "Спикер" },
                    { id: "delegate", label: "Делегат" },
                    { id: "sponsor", label: "Стенд / Партнёр" },
                  ] as { id: ShowcaseRoleFilter; label: string }[]
                ).map((tab) => (
                  <button
                    key={tab.id}
                    type="button"
                    onClick={() => setRoleFilter(tab.id)}
                    className={cn(
                      "rounded-[6px] px-2.5 py-1 text-xs font-serif italic transition-all select-none cursor-pointer",
                      roleFilter === tab.id
                        ? "bg-[#261E0F] text-[#E5C378] border border-[#7C5A20]/60 font-semibold shadow-xs"
                        : "text-[#8E95A0] hover:text-white"
                    )}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>

              {/* Переключатель Карусель / Сетка */}
              <div className="flex items-center rounded-[8px] border border-[#262D35] bg-[#12161A] p-0.5">
                <button
                  type="button"
                  onClick={() => setLayoutMode("carousel")}
                  title="Горизонтальная карусель"
                  className={cn(
                    "inline-flex items-center gap-1 rounded-[6px] px-2.5 py-1 text-xs font-serif italic transition-all select-none cursor-pointer",
                    layoutMode === "carousel"
                      ? "bg-[#261E0F] text-[#E5C378] border border-[#7C5A20]/60 font-semibold shadow-xs"
                      : "text-[#8E95A0] hover:text-white"
                  )}
                >
                  <GalleryHorizontalEnd
                    className="h-3.5 w-3.5"
                    strokeWidth={1.5}
                  />
                  <span className="hidden sm:inline">Карусель</span>
                </button>
                <button
                  type="button"
                  onClick={() => setLayoutMode("grid")}
                  title="Сетка карточек"
                  className={cn(
                    "inline-flex items-center gap-1 rounded-[6px] px-2.5 py-1 text-xs font-serif italic transition-all select-none cursor-pointer",
                    layoutMode === "grid"
                      ? "bg-[#261E0F] text-[#E5C378] border border-[#7C5A20]/60 font-semibold shadow-xs"
                      : "text-[#8E95A0] hover:text-white"
                  )}
                >
                  <LayoutGrid className="h-3.5 w-3.5" strokeWidth={1.5} />
                  <span className="hidden sm:inline">Сетка</span>
                </button>
              </div>

              {/* Стрелки прокрутки карусели < > (как на Фото 8) */}
              {layoutMode === "carousel" && (
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => emblaApi?.scrollPrev()}
                    disabled={!canScrollPrev}
                    aria-label="Предыдущая карточка"
                    className="flex h-8 w-8 items-center justify-center rounded-[6px] border border-[#262D35] bg-[#12161A] text-white transition-colors hover:border-[#E5C378] hover:text-[#E5C378] disabled:opacity-30 cursor-pointer"
                  >
                    <ChevronLeft className="h-4 w-4" strokeWidth={1.75} />
                  </button>
                  <button
                    type="button"
                    onClick={() => emblaApi?.scrollNext()}
                    disabled={!canScrollNext}
                    aria-label="Следующая карточка"
                    className="flex h-8 w-8 items-center justify-center rounded-[6px] border border-[#262D35] bg-[#12161A] text-white transition-colors hover:border-[#E5C378] hover:text-[#E5C378] disabled:opacity-30 cursor-pointer"
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
                В пакете нет площадок с выбранным фильтром роли
              </div>
            ) : (
              <AnimatePresence mode="wait">
                {layoutMode === "carousel" ? (
                  <motion.div
                    key="showcase-carousel"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.18 }}
                    className="overflow-hidden"
                    ref={emblaRef}
                  >
                    <div className="-ml-4 flex">
                      {filteredItems.map((item) => (
                        <div
                          key={item.selection_item_id}
                          className="min-w-0 shrink-0 grow-0 basis-[88%] pl-4 sm:basis-[56%] lg:basis-1/3"
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
                            quickChips={showcase.faq_quick_chips}
                          />
                        </div>
                      ))}
                    </div>
                  </motion.div>
                ) : (
                  <motion.div
                    key="showcase-grid"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.18 }}
                    className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3"
                  >
                    {filteredItems.map((item) => (
                      <ShowcaseEventCard
                        key={item.selection_item_id}
                        item={item}
                        selectedAgencyServices={
                          selectedAgencyServicesByItem[item.selection_item_id] || []
                        }
                        onToggleAgencyService={(tag) =>
                          toggleAgencyServiceForItem(item.selection_item_id, tag)
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
                        quickChips={showcase.faq_quick_chips}
                      />
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            )}
          </div>
        </div>
      </section>

      {/* 4. Блок «Этапы совместной работы и подготовка под задачи бизнеса» */}
      <AgencyWorkflowStepsSection />

      {/* 5. Плавающая кнопка запуска ИИ-консультанта по регламентам в стиле золотого слитка */}
      {!activeDrawerEventId && items.length > 0 && (
        <button
          type="button"
          onClick={() => openEventDrawer(items[0].event_id, "regulation")}
          className="fixed bottom-5 right-5 z-30 inline-flex items-center gap-2 rounded-[8px] btn-gold-ingot px-4 py-3 text-xs font-semibold shadow-2xl active:scale-[0.98] transition-transform"
        >
          <MessageSquareText className="h-4 w-4 text-[#0E1215]" strokeWidth={2} />
          <span>Вопросы по регламенту и тарифам</span>
        </button>
      )}

      {/* 6. Выдвижная панель «Паспорт участия и ИИ-консультант по регламенту» */}
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
