import {
  UserCheck,
  ShieldCheck,
  CalendarCheck,
  FileSearch,
  Sparkles,
} from "lucide-react";
import type { ShowcaseViewOut } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { formatDateShort, formatRub } from "@/lib/formatters";
import logoImage from "@/assets/images/logo.png";

interface ShowcaseExecutiveHeaderProps {
  showcase: ShowcaseViewOut;
  onOpenConsultant: () => void;
}

export function ShowcaseExecutiveHeader({
  showcase,
  onOpenConsultant,
}: ShowcaseExecutiveHeaderProps) {
  const approvedCount = showcase.items.filter(
    (i) => i.client_reaction === "interested"
  ).length;
  const rejectedCount = showcase.items.filter(
    (i) => i.client_reaction === "rejected"
  ).length;

  const totalBasePrice = showcase.items.reduce(
    (acc, item) => acc + (item.base_price ?? item.actual_price ?? 0),
    0
  );

  return (
    <header className="border-b border-[#1A2026] bg-[#0E1215] relative text-white">
      {/* Деликатная бронзово-золотая нить переплёта внизу хедера */}
      <div className="pointer-events-none absolute bottom-0 left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-[#7C5A20]/35 to-transparent" />

      {/* Верхняя навигационная полоса */}
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 border-b border-[#1F2630] px-4 py-3 sm:px-6">
        <div className="flex items-center gap-3">
          <img
            src={logoImage}
            alt="СКАРТ.AI"
            className="h-7 sm:h-8 w-auto object-contain shrink-0"
          />
          <div className="hidden h-4 w-[1px] bg-[#2D3540] sm:block" />
          <span className="hidden font-serif italic text-xs text-[#E5C378] sm:inline">
            Персональная витрина участия в деловых событиях
          </span>
        </div>

        <div className="flex items-center gap-2.5">
          <div className="hidden md:flex items-center gap-2 rounded-[8px] border border-[#262D35] bg-[#12161A] px-3 py-1.5 text-xs text-[#8E95A0]">
            <UserCheck className="h-3.5 w-3.5 text-[#E5C378]" strokeWidth={1.75} />
            <span>Продюсер проекта:</span>
            <strong className="font-semibold text-white font-serif italic">
              {showcase.manager_full_name}
            </strong>
          </div>

          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onOpenConsultant}
            className="border-[#7C5A20]/50 bg-[#161B21] text-xs text-[#E5C378] hover:border-[#E5C378] hover:bg-[#261E0F] hover:text-white transition-all shadow-sm"
          >
            <FileSearch className="h-3.5 w-3.5 text-inherit" strokeWidth={1.75} />
            <span>Проверить регламенты</span>
          </Button>
        </div>
      </div>

      {/* Основной двухколоночный блок «Исполнительное досье» (Executive Briefing) */}
      <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:py-8">
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12 items-stretch">
          {/* Левая колонка (7 из 12): Обращение к клиенту и письмо менеджера */}
          <div className="flex flex-col justify-between rounded-[12px] border border-[#262D35] bg-[#161B22] p-5 sm:p-6 lg:col-span-7 shadow-sm">
            <div>
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <Badge variant="ebGold" className="text-[10px]">
                  ПЕРСОНАЛЬНАЯ СЕЛЕКЦИЯ
                </Badge>
                <Badge variant="ebEmerald" className="text-[10px]">
                  <CalendarCheck className="h-3 w-3 mr-1 text-[#34D399]" strokeWidth={2} />
                  КАЛЕНДАРЬ БЕЗ НАКЛАДОК
                </Badge>
              </div>

              <h1 className="mt-3.5 font-serif text-2xl font-bold tracking-tight text-white sm:text-3xl leading-tight">
                План участия в профильных мероприятиях для {showcase.company_name}
              </h1>

              {/* Текст сопроводительного письма от менеджера с золотой нитью */}
              <div className="mt-4 rounded-[8px] border-l-2 border-[#E5C378] bg-[#12161A] p-4 shadow-inner">
                <p className="whitespace-pre-line text-xs sm:text-[13px] leading-relaxed text-[#D1D5DB] font-sans">
                  {showcase.pitch_text}
                </p>
              </div>
            </div>

            {/* Нижняя строка прогресса согласования (Шаг 07) */}
            <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-[#21262F] pt-3.5 text-xs">
              <div className="flex items-center gap-2 text-[#8E95A0]">
                <ShieldCheck className="h-4 w-4 text-[#34D399]" strokeWidth={1.75} />
                <span>
                  Отметьте подходящие площадки ниже или укажите пожелания для корректировки
                </span>
              </div>

              <div className="flex items-center gap-2 tabular-nums">
                <Badge variant="ebGold" className="text-[10px]">
                  В ПЛАНЕ: {approvedCount} ИЗ {showcase.total_events_count}
                </Badge>
                {rejectedCount > 0 && (
                  <Badge variant="ebRose" className="text-[10px]">
                    НА ЗАМЕНУ: {rejectedCount}
                  </Badge>
                )}
              </div>
            </div>
          </div>

          {/* Правая колонка (5 из 12): Благородная графитово-золотая финансовая сводка пакета */}
          <div className="flex flex-col justify-between rounded-[12px] border border-[#7C5A20]/60 bg-[#161B22] p-5 text-white shadow-xl sm:p-6 lg:col-span-5 relative overflow-hidden">
            <div>
              <div className="flex items-center justify-between border-b border-[#21262F] pb-3">
                <span className="font-serif italic text-xs font-semibold uppercase tracking-wider text-[#E5C378]">
                  Сводный бюджет участия
                </span>
                <span className="rounded-[4px] border border-[#7C5A20]/40 bg-[#12161A] px-2 py-0.5 text-[10px] font-bold text-[#E5C378] uppercase tracking-wider tabular-nums">
                  {showcase.total_events_count} {showcase.total_events_count === 1 ? "мероприятие" : "мероприятия"} в пакете
                </span>
              </div>

              <div className="mt-4">
                <div className="flex items-baseline justify-between text-xs text-[#8E95A0]">
                  <span>Организационные взносы площадок:</span>
                  {showcase.total_savings > 0 && totalBasePrice > showcase.total_actual_price && (
                    <span className="text-[#6B7280] line-through tabular-nums">
                      {formatRub(totalBasePrice)}
                    </span>
                  )}
                </div>

                <div className="mt-1 flex items-baseline gap-3 tabular-nums">
                  <span className="text-3xl sm:text-4xl font-sans font-bold tracking-tight text-white">
                    {formatRub(showcase.total_actual_price)}
                  </span>
                  <span className="text-xs text-[#8E95A0]">с НДС</span>
                </div>
              </div>

              {/* Блок выгоды Early Bird и партнёрских условий */}
              {showcase.total_savings > 0 && (
                <div className="mt-4 rounded-[8px] border border-[#1E5241] bg-[#0E241E]/90 p-3.5">
                  <div className="flex items-center justify-between gap-2 tabular-nums">
                    <span className="text-xs font-medium text-white/90">
                      Ваша выгода по спецтарифам:
                    </span>
                    <Badge variant="ebEmerald" className="text-[10px]">
                      −{formatRub(showcase.total_savings)}
                    </Badge>
                  </div>
                  {showcase.min_early_bird_deadline && (
                    <p className="mt-1.5 text-xs text-[#34D399] tabular-nums">
                      Льготные условия действительны при согласовании до{" "}
                      <strong className="text-white underline decoration-[#34D399]/40 underline-offset-2">
                        {formatDateShort(showcase.min_early_bird_deadline)}
                      </strong>
                    </p>
                  )}
                </div>
              )}
            </div>

            {/* Разделение внешних взносов и сопровождения агентства (Слайд 10) */}
            <div className="mt-5 border-t border-[#21262F] pt-3.5">
              <div className="flex items-start gap-2">
                <Sparkles className="h-4 w-4 shrink-0 text-[#E5C378] mt-0.5" strokeWidth={1.75} />
                <p className="text-xs leading-relaxed text-[#8E95A0]">
                  Внешние взносы организаторов фиксируются отдельно. На каждой карточке вы можете отметить необходимое{" "}
                  <strong className="text-white font-medium">
                    сопровождение агентства
                  </strong>{" "}
                  (подготовка спикера и презентации, организация целевых знакомств, интерактив на стенде).
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}
