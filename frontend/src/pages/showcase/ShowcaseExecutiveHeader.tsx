import {
  UserCheck,
  ShieldCheck,
  CalendarCheck,
  FileSearch,
  Sparkles,
} from "lucide-react";
import type { ShowcaseViewOut } from "@/api/types";
import { Button } from "@/components/ui/button";
import { formatDateShort, formatRub } from "@/lib/formatters";

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
    <header className="border-b border-border bg-surface">
      {/* Верхняя навигационная полоса */}
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 border-b border-border/70 px-4 py-3 sm:px-6">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-badge bg-pine text-xs font-bold tracking-wider text-white">
            СК
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold tracking-tight text-ink">
                СКАРТ
              </span>
              <span className="hidden rounded-badge bg-canvas border border-border px-2 py-0.5 text-[11px] font-medium text-ink-secondary sm:inline-block">
                Отраслевые мероприятия с пользой для бизнеса
              </span>
            </div>
            <p className="text-[11px] text-ink-muted">
              Подбор площадок и сопровождение участия для строительной отрасли
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          <div className="hidden md:flex items-center gap-2 rounded-control border border-border bg-canvas px-3 py-1.5 text-xs">
            <UserCheck className="h-3.5 w-3.5 text-pine" strokeWidth={1.75} />
            <span className="text-ink-muted">Персональный менеджер:</span>
            <strong className="font-semibold text-ink">
              {showcase.manager_full_name}
            </strong>
          </div>

          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onOpenConsultant}
          >
            <FileSearch className="h-3.5 w-3.5 text-pine" strokeWidth={1.75} />
            <span>Проверить регламенты</span>
          </Button>
        </div>
      </div>

      {/* Основной двухколоночный блок «Исполнительное досье» (Executive Briefing) */}
      <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:py-8">
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12 items-stretch">
          {/* Левая колонка (7 из 12): Обращение к клиенту и письмо менеджера */}
          <div className="flex flex-col justify-between rounded-card border border-border bg-canvas/55 p-5 sm:p-6 lg:col-span-7">
            <div>
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className="inline-flex items-center gap-1 rounded-[4px] bg-[#161B22] text-[#D1D5DB] px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider border border-[#2B3545]">
                  ПЕРСОНАЛЬНАЯ СЕЛЕКЦИЯ
                </span>
                <span className="inline-flex items-center gap-1.5 rounded-[4px] bg-[#0B2528] text-[#2DD4BF] px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider border border-[#165057]">
                  <CalendarCheck className="h-3 w-3 text-[#2DD4BF]" strokeWidth={2} />
                  КАЛЕНДАРЬ БЕЗ НАКЛАДОК
                </span>
              </div>

              <h1 className="mt-3.5 font-serif text-2xl font-bold tracking-tight text-ink sm:text-3xl leading-tight">
                План участия в профильных мероприятиях для {showcase.company_name}
              </h1>

              {/* Текст сопроводительного письма от менеджера */}
              <div className="mt-4 rounded-control border-l-2 border-pine bg-surface p-4 shadow-card">
                <p className="whitespace-pre-line text-sm leading-relaxed text-ink-secondary">
                  {showcase.pitch_text}
                </p>
              </div>
            </div>

            {/* Нижняя строка прогресса согласования (Шаг 07) */}
            <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-border/80 pt-3.5 text-xs">
              <div className="flex items-center gap-2 text-ink-muted">
                <ShieldCheck className="h-4 w-4 text-sage" strokeWidth={1.75} />
                <span>
                  Отметьте подходящие площадки ниже или укажите пожелания для корректировки
                </span>
              </div>

              <div className="flex items-center gap-2 tabular-nums">
                <span className="rounded-badge bg-novel-sand text-[#282112] px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider border border-novel-sandBorder">
                  В ПЛАНЕ: {approvedCount} ИЗ {showcase.total_events_count}
                </span>
                {rejectedCount > 0 && (
                  <span className="rounded-badge bg-novel-wine text-white px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider border border-[#7A2430]">
                    НА ЗАМЕНУ: {rejectedCount}
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Правая колонка (5 из 12): Контрастная темно-хвойная финансовая сводка пакета */}
          <div className="flex flex-col justify-between rounded-card bg-pine p-5 text-white shadow-elevated sm:p-6 lg:col-span-5">
            <div>
              <div className="flex items-center justify-between border-b border-white/15 pb-3">
                <span className="text-[10px] font-bold uppercase tracking-widest text-white/80">
                  Сводный бюджет участия
                </span>
                <span className="rounded-tag bg-white/20 text-white px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider tabular-nums">
                  {showcase.total_events_count} {showcase.total_events_count === 1 ? "мероприятие" : "мероприятия"} в пакете
                </span>
              </div>

              <div className="mt-4">
                <div className="flex items-baseline justify-between text-xs text-white/75">
                  <span>Организационные взносы площадок:</span>
                  {showcase.total_savings > 0 && totalBasePrice > showcase.total_actual_price && (
                    <span className="text-white/50 line-through tabular-nums">
                      {formatRub(totalBasePrice)}
                    </span>
                  )}
                </div>

                <div className="mt-1 flex items-baseline gap-3 tabular-nums">
                  <span className="text-3xl font-bold tracking-tight text-white">
                    {formatRub(showcase.total_actual_price)}
                  </span>
                  <span className="text-xs text-white/70">с НДС</span>
                </div>
              </div>

              {/* Блок выгоды Early Bird и партнёрских условий */}
              {showcase.total_savings > 0 && (
                <div className="mt-4 rounded-control border border-white/20 bg-white/10 p-3.5">
                  <div className="flex items-center justify-between gap-2 tabular-nums">
                    <span className="text-xs font-medium text-white/90">
                      Ваша выгода по спецтарифам:
                    </span>
                    <span className="rounded-tag bg-novel-gold text-[#1F1808] px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider">
                      −{formatRub(showcase.total_savings)}
                    </span>
                  </div>
                  {showcase.min_early_bird_deadline && (
                    <p className="mt-1.5 text-xs text-white/80 tabular-nums">
                      Льготные условия действительны при согласовании до{" "}
                      <strong className="text-white underline decoration-white/40 underline-offset-2">
                        {formatDateShort(showcase.min_early_bird_deadline)}
                      </strong>
                    </p>
                  )}
                </div>
              )}
            </div>

            {/* Разделение внешних взносов и сопровождения агентства (Слайд 10) */}
            <div className="mt-5 border-t border-white/15 pt-3.5">
              <div className="flex items-start gap-2">
                <Sparkles className="h-4 w-4 shrink-0 text-sage-border mt-0.5" strokeWidth={1.75} />
                <p className="text-xs leading-relaxed text-white/80">
                  Внешние взносы организаторов фиксируются отдельно. На каждой карточке вы можете отметить необходимое{" "}
                  <strong className="text-white">
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

