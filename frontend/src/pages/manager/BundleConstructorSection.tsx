import * as React from "react";
import {
  MapPin,
  Globe,
  Plus,
  Compass,
  Edit3,
  Building,
  Sparkles,
} from "lucide-react";
import type { BundleVariantOut } from "@/api/types";
import type {
  ComputedBundleItem,
  ComputedFinancialSummary,
} from "@/store/useManagerStore";
import { CalendarTimeline } from "@/components/ui/calendar-timeline";
import { Badge } from "@/components/ui/badge";
import {
  FORMAT_LABELS,
  ROLE_BADGE_LABELS,
  formatCalendarBadge,
  formatDateShort,
  formatRub,
} from "@/lib/formatters";
import { cn } from "@/lib/utils";

interface BundleConstructorSectionProps {
  variants: BundleVariantOut[];
  selectedVariantGroup: number;
  onSelectVariantGroup: (group: number) => void;
  summary: ComputedFinancialSummary;
  onToggleEventIncluded: (eventId: number) => void;
  onChangeEventTariff: (eventId: number, tariffId: number) => void;
  onUpdateEventRationale: (eventId: number, rationale: string) => void;
}

export function BundleConstructorSection({
  variants,
  selectedVariantGroup,
  onSelectVariantGroup,
  summary,
  onToggleEventIncluded,
  onChangeEventTariff,
  onUpdateEventRationale,
}: BundleConstructorSectionProps) {
  const mainRows = summary.rows.filter((r) => !r.isBonusSlot);
  const bonusRows = summary.rows.filter((r) => r.isBonusSlot);

  const timelineItems = summary.includedRows.map((r) => ({
    event_id: r.item.event_id,
    canonical_title: r.item.canonical_title,
    start_date: r.item.start_date,
    end_date: r.item.end_date,
    is_online: r.item.is_online,
    city: r.item.city,
  }));

  if (variants.length === 0 && bonusRows.length === 0) {
    return (
      <section className="rounded-[12px] border border-[#21262F] bg-[#0E1116] p-8 text-center shadow-sm">
        <Compass className="mx-auto h-9 w-9 text-[#E5C378]" strokeWidth={1.5} />
        <h3 className="mt-3 font-serif italic text-sm font-semibold text-[#E5C378]">
          Подходящих мероприятий не найдено
        </h3>
        <p className="mx-auto mt-1.5 max-w-md font-serif italic text-xs leading-relaxed text-[#D4AF37]/90">
          По заданным критериям (город, период дат, формат) в базе знаний агентства нет активных площадок.
          Скорректируйте географию или параметры отбора в блоке выше, либо добавьте новые мероприятия во вкладке «База мероприятий».
        </p>
      </section>
    );
  }

  return (
    <section className="space-y-3">
      {/* Переключатель вариантов пакета (Шаг 05 «Сравнение вариантов») */}
      <div className="rounded-[12px] border border-[#262D35] bg-[#161B22] p-3.5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2 pb-2.5 border-b border-[#21262F]">
          <div className="flex items-baseline gap-2.5">
            <span className="font-serif italic font-bold text-base sm:text-lg text-[#E5C378] select-none">
              02
            </span>
            <h2 className="font-serif italic text-sm sm:text-[15px] font-semibold tracking-tight text-[#E5C378]">
              Сравнение вариантов и выбор тарифов
            </h2>
          </div>
          <span className="text-[11px] text-[#8E95A0]">
            Выбор тарифа синхронно пересчитывает общую смету
          </span>
        </div>

        {/* Сегментированные вкладки Вариант №1 / Вариант №2 */}
        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
          {variants.map((v) => {
            const isActive = v.bundle_group === selectedVariantGroup;
            return (
              <button
                key={v.bundle_group}
                type="button"
                onClick={() => onSelectVariantGroup(v.bundle_group)}
                className={cn(
                  "flex flex-col justify-between rounded-[8px] border p-3.5 text-left transition-all",
                  isActive
                    ? "border-[#E5C378] bg-[#1E252E] shadow-sm"
                    : "border-[#262D35] bg-[#1A1E24] hover:border-[#38414F] hover:bg-[#1E232B]"
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <span
                    className={cn(
                      "text-xs font-semibold",
                      isActive ? "text-[#E5C378]" : "text-white"
                    )}
                  >
                    {v.bundle_group === 1
                      ? "Вариант 1 · Приоритетное попадание в ЦА"
                      : "Вариант 2 · Оптимизация бюджета и скидок"}
                  </span>
                  <span
                    className={cn(
                      "flex h-4 w-4 items-center justify-center rounded-[3px] border text-[10px]",
                      isActive
                        ? "border-[#E5C378] bg-[#E5C378] text-[#1A1405]"
                        : "border-[#262D35] bg-[#12161A]"
                    )}
                  >
                    {isActive && <Plus className="h-3 w-3 stroke-[3]" />}
                  </span>
                </div>

                <div className="mt-2.5 flex flex-wrap items-baseline justify-between gap-2 text-xs tabular-nums">
                  <span className="font-serif italic text-[11px] text-[#8E95A0]">
                    Площадок: <strong className="font-sans not-italic font-bold text-white">{v.items.length}</strong>
                  </span>
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-white">
                      {formatRub(v.total_actual_price)}
                    </span>
                    {v.total_savings > 0 && (
                      <Badge variant="ebEmerald" className="text-[9px]">
                        Выгода {formatRub(v.total_savings)}
                      </Badge>
                    )}
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Визуальная шкала «Календарь без пересечений по срокам» */}
      <CalendarTimeline items={timelineItems} />

      {/* Горизонтальные строки мероприятий выбранного варианта */}
      <div className="space-y-2.5">
        {mainRows.map((row) => (
          <EventBuilderRow
            key={row.item.event_id}
            row={row}
            onToggleIncluded={() => onToggleEventIncluded(row.item.event_id)}
            onChangeTariff={(tariffId) =>
              onChangeEventTariff(row.item.event_id, tariffId)
            }
            onUpdateRationale={(text) =>
              onUpdateEventRationale(row.item.event_id, text)
            }
          />
        ))}
      </div>

      {/* Бонусный слот: Спецпроекты и партнёрские пакеты «По запросу» */}
      {bonusRows.length > 0 && (
        <div className="rounded-[12px] border border-[#262D35] bg-[#161B22] p-3.5 shadow-sm">
          <div className="mb-2.5 flex items-center justify-between gap-2 border-b border-[#21262F] pb-2">
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-[#E5C378]" strokeWidth={1.5} />
              <span className="font-serif italic text-xs font-semibold tracking-wide text-[#E5C378]">
                Дополнительные возможности: спецпроекты и стенды «По запросу»
              </span>
            </div>
            <span className="text-[11px] text-[#8E95A0]">
              Отметьте плюсиком, чтобы включить в персональную витрину клиента
            </span>
          </div>

          <div className="space-y-2">
            {bonusRows.map((row) => (
              <EventBuilderRow
                key={row.item.event_id}
                row={row}
                onToggleIncluded={() => onToggleEventIncluded(row.item.event_id)}
                onChangeTariff={(tariffId) =>
                  onChangeEventTariff(row.item.event_id, tariffId)
                }
                onUpdateRationale={(text) =>
                  onUpdateEventRationale(row.item.event_id, text)
                }
              />
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

interface EventBuilderRowProps {
  row: ComputedBundleItem;
  onToggleIncluded: () => void;
  onChangeTariff: (tariffId: number) => void;
  onUpdateRationale: (rationale: string) => void;
}

function EventBuilderRow({
  row,
  onToggleIncluded,
  onChangeTariff,
  onUpdateRationale,
}: EventBuilderRowProps) {
  const [isEditingRationale, setIsEditingRationale] = React.useState(false);
  const { item, isIncluded, selectedTariff, rationale, isBonusSlot } = row;
  const cal = formatCalendarBadge(item.start_date, item.end_date);
  const formatName = FORMAT_LABELS[item.event_format] || item.event_format;
  const locationLabel = item.is_online ? "Онлайн" : item.city || "Россия";

  return (
    <div
      className={cn(
        "rounded-[8px] border p-3.5 transition-all duration-300 ease-in-out",
        isBonusSlot
          ? isIncluded
            ? "border-[#262C35] bg-[#1A1E24] shadow-sm text-white opacity-100"
            : "border-[#1D232A] bg-[#101317] text-[#9CA3AF] opacity-80 hover:opacity-100 hover:border-[#2D3540]"
          : isIncluded
            ? "border-[#262C35] bg-[#1A1E24] shadow-sm text-white"
            : "border-[#21262F] bg-[#14181D]/60 opacity-60 text-[#8E95A0]"
      )}
    >
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        {/* Левая колонка: Чекбокс-плюсик + Календарный лист + Название и Аргументы выбора */}
        <div className="flex items-start gap-3 min-w-0 flex-1">
          <button
            type="button"
            onClick={onToggleIncluded}
            title={
              isIncluded
                ? "Включено в подборку клиента"
                : "Включить мероприятие в подборку"
            }
            className={cn(
              "flex h-4 w-4 shrink-0 self-center items-center justify-center rounded-[3px] border transition-colors cursor-pointer",
              isIncluded
                ? "border-[#E5C378] bg-[#E5C378] text-[#1A1405]"
                : "border-[#262D35] bg-[#12161A] hover:border-[#E5C378]"
            )}
          >
            {isIncluded && <Plus className="h-3 w-3 stroke-[3]" />}
          </button>

          {/* Календарный лист даты с золотой рамкой, увеличенной высотой и вертикальным центрированием */}
          <div
            className={cn(
              "flex min-h-[64px] min-w-[62px] shrink-0 self-center flex-col items-center justify-center rounded-[6px] border border-[#7C5A20]/50 bg-[#161B21] px-2 py-2 tabular-nums shadow-inner transition-colors",
              isIncluded ? "text-white" : "text-[#8E95A0]"
            )}
          >
            <span className="text-sm font-bold leading-none">{cal.dayText}</span>
            <span className="mt-1 text-[10px] font-semibold uppercase tracking-wider opacity-85 leading-none">
              {cal.monthText}
            </span>
            <span className="mt-1 text-[9px] opacity-70 leading-none">{cal.durationText}</span>
          </div>

          {/* Основная информация о площадке */}
          <div className="min-w-0 flex-1">
            {/* Мета-строка через точку */}
            <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-[#8E95A0]">
              <span className="font-semibold text-[#D1D5DB]">{formatName}</span>
              <span>·</span>
              <span className="inline-flex items-center gap-1 font-medium text-[#D1D5DB]">
                {item.is_online ? (
                  <Globe className="h-3 w-3 text-[#38BDF8]" strokeWidth={1.5} />
                ) : (
                  <MapPin className="h-3 w-3 text-[#8E95A0]" strokeWidth={1.5} />
                )}
                {locationLabel}
              </span>
              {item.venue && (
                <>
                  <span>·</span>
                  <span className="inline-flex items-center gap-1 truncate max-w-[240px]">
                    <Building className="h-3 w-3 shrink-0 opacity-70" strokeWidth={1.5} />
                    {item.venue}
                  </span>
                </>
              )}
              {isBonusSlot && (
                <Badge variant="ebGold" className="ml-1 text-[9px]">
                  Спецпроект
                </Badge>
              )}
            </div>

            <h3 className="mt-1 font-serif text-[15px] font-semibold leading-snug text-white">
              {item.canonical_title}
            </h3>

            {/* Темы строкой */}
            {item.themes.length > 0 && (
              <p className="mt-0.5 text-[11px] text-[#8E95A0]">
                Темы: {item.themes.join(" · ")}
              </p>
            )}

            {/* Блок «Аргументы выбора и целевая аудитория» (Слайд 04) с редактированием по клику */}
            <div className="mt-2 rounded-[6px] border-l-2 border-[#E5C378] bg-[#161B21] pl-2.5 pr-2 py-1.5">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-[#8E95A0]">
                  Аргументы выбора площадки и ЦА
                </span>
                <button
                  type="button"
                  onClick={() => setIsEditingRationale((p) => !p)}
                  className="inline-flex items-center gap-1 text-[11px] text-[#8E95A0] hover:text-[#E5C378]"
                >
                  <Edit3 className="h-3 w-3" strokeWidth={1.5} />
                  <span>{isEditingRationale ? "Готово" : "Изменить"}</span>
                </button>
              </div>

              {isEditingRationale ? (
                <textarea
                  rows={2}
                  value={rationale}
                  onChange={(e) => onUpdateRationale(e.target.value)}
                  className="mt-1 w-full rounded border border-[#262D35] bg-[#12161A] p-1.5 text-xs text-white focus:border-[#38BDF8] focus:outline-none"
                />
              ) : (
                <p
                  onClick={() => setIsEditingRationale(true)}
                  className="mt-0.5 cursor-pointer text-xs leading-relaxed text-[#D1D5DB] hover:text-white"
                  title="Нажмите, чтобы отредактировать аргументацию для клиента"
                >
                  {rationale}
                </p>
              )}
            </div>
          </div>
        </div>

        {/* Правая колонка: Выбор тарифа и расчёт выгоды Early Bird */}
        <div className="flex shrink-0 flex-col justify-between gap-1.5 border-t border-[#262D35] pt-2.5 lg:w-[255px] lg:border-l lg:border-t-0 lg:pl-3.5 lg:pt-0">
          <div>
            <div className="flex items-center justify-between text-[11px]">
              <span className="font-medium text-[#8E95A0]">Тариф участия:</span>
              <Badge
                variant={
                  selectedTariff.participation_role === "speaker"
                    ? "ebGold"
                    : selectedTariff.participation_role === "sponsor"
                      ? "ebRose"
                      : "ebBlue"
                }
              >
                {ROLE_BADGE_LABELS[selectedTariff.participation_role]}
              </Badge>
            </div>

            <select
              value={selectedTariff.tariff_id}
              onChange={(e) => onChangeTariff(Number(e.target.value))}
              className="mt-1.5 h-8 w-full rounded-[6px] border border-[#262D35] bg-[#12161A] px-2 text-xs font-medium text-white tabular-nums transition-all duration-150 ease-out hover:border-[#E5C378] focus:border-[#E5C378] focus:ring-1 focus:ring-[#E5C378]/30 focus:outline-none cursor-pointer"
            >
              {item.available_tariffs.map((t) => (
                <option key={t.tariff_id} value={t.tariff_id} className="bg-[#161B21] text-white">
                  {t.tariff_name} — {formatRub(t.actual_price)}
                </option>
              ))}
            </select>
          </div>

          <div className="mt-1.5 flex flex-col gap-1 tabular-nums">
            <div className="flex items-baseline gap-2">
              <span className="text-sm font-bold text-white">
                {formatRub(selectedTariff.actual_price)}
              </span>
              {selectedTariff.savings > 0 && selectedTariff.base_price && (
                <span className="text-xs text-[#727985] line-through">
                  {formatRub(selectedTariff.base_price)}
                </span>
              )}
            </div>

            {selectedTariff.savings > 0 ? (
              <div className="flex items-center">
                <span className="rounded-[4px] bg-[#34D399] px-2 py-0.5 font-serif italic text-[10px] font-bold text-[#02291D] tabular-nums">
                  Выгода {formatRub(selectedTariff.savings)}
                  {selectedTariff.early_bird_deadline
                    ? ` до ${formatDateShort(selectedTariff.early_bird_deadline).slice(0, 5)}`
                    : ""}
                </span>
              </div>
            ) : (
              <span className="text-[11px] text-[#727985]">Базовый тариф</span>
            )}
          </div>

          {selectedTariff.included_benefits && (
            <p
              className="truncate text-[11px] text-[#8E95A0]"
              title={selectedTariff.included_benefits}
            >
              {selectedTariff.included_benefits}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

