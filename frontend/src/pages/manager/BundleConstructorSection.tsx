import * as React from "react";
import {
  MapPin,
  Globe,
  Check,
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
      <section className="rounded-card border border-dashed border-border bg-surface p-8 text-center shadow-card">
        <Building className="mx-auto h-9 w-9 text-ink-muted" strokeWidth={1.5} />
        <h3 className="mt-3 text-sm font-semibold text-ink">
          Подходящих мероприятий не найдено
        </h3>
        <p className="mx-auto mt-1.5 max-w-md text-xs leading-relaxed text-ink-muted">
          По заданным критериям (город, период дат, формат) в базе знаний агентства нет активных площадок.
          Скорректируйте географию или параметры отбора в блоке выше, либо добавьте новые мероприятия во вкладке «База мероприятий».
        </p>
      </section>
    );
  }

  return (
    <section className="space-y-3">
      {/* Переключатель вариантов пакета (Шаг 05 «Сравнение вариантов») */}
      <div className="rounded-card border border-border bg-surface p-3 shadow-card">
        <div className="flex flex-wrap items-center justify-between gap-2 pb-2.5 border-b border-border/80">
          <div className="flex items-center gap-2">
            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-pine text-[10px] font-bold text-white tabular-nums">
              02
            </span>
            <span className="text-xs font-semibold uppercase tracking-wider text-ink">
              Сравнение вариантов и настройка тарифов участия
            </span>
          </div>
          <span className="text-[11px] text-ink-muted">
            Переключение тарифа мгновенно пересчитывает смету справа
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
                  "flex flex-col justify-between rounded-control border p-3 text-left transition-all",
                  isActive
                    ? "border-pine bg-pine/5 shadow-sm ring-1 ring-pine/20"
                    : "border-border bg-canvas/50 hover:border-border-strong hover:bg-canvas"
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <span
                    className={cn(
                      "text-xs font-semibold",
                      isActive ? "text-pine" : "text-ink"
                    )}
                  >
                    {v.bundle_group === 1
                      ? "Вариант 1 · Приоритетное попадание в ЦА"
                      : "Вариант 2 · Оптимизация бюджета и скидок"}
                  </span>
                  <span
                    className={cn(
                      "flex h-4 w-4 items-center justify-center rounded-full border text-[10px]",
                      isActive
                        ? "border-pine bg-pine text-white"
                        : "border-border-strong bg-surface"
                    )}
                  >
                    {isActive && <Check className="h-2.5 w-2.5" strokeWidth={2.5} />}
                  </span>
                </div>

                <div className="mt-2 flex flex-wrap items-baseline justify-between gap-2 text-xs tabular-nums">
                  <span className="text-ink-muted">
                    Площадок: <strong className="text-ink">{v.items.length}</strong>
                  </span>
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-ink">
                      {formatRub(v.total_actual_price)}
                    </span>
                    {v.total_savings > 0 && (
                      <span className="rounded bg-sage-tint px-1.5 py-0.5 text-[10px] font-medium text-sage border border-sage-border">
                        выгода {formatRub(v.total_savings)}
                      </span>
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
        <div className="rounded-card border border-border bg-surface/90 p-3.5 shadow-card">
          <div className="mb-2.5 flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-sage" strokeWidth={1.5} />
              <span className="text-xs font-semibold uppercase tracking-wider text-ink-secondary">
                Дополнительные возможности: спецпроекты и стенды «По запросу»
              </span>
            </div>
            <span className="text-[11px] text-ink-muted">
              Отметьте галочкой, чтобы включить в персональную витрину клиента
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
        "rounded-card border bg-surface p-3.5 transition-all",
        isIncluded
          ? "border-border shadow-card"
          : "border-border/60 bg-canvas/40 opacity-65"
      )}
    >
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        {/* Левая колонка: Чекбокс + Календарный лист + Название и Аргументы выбора (Слайд 04) */}
        <div className="flex items-start gap-3 min-w-0 flex-1">
          <input
            type="checkbox"
            checked={isIncluded}
            onChange={onToggleIncluded}
            title={
              isIncluded
                ? "Включено в подборку клиента"
                : "Включить мероприятие в подборку"
            }
            className="mt-1.5 h-4 w-4 shrink-0 cursor-pointer rounded accent-pine"
          />

          {/* Календарный лист даты */}
          <div
            className={cn(
              "flex h-12 w-14 shrink-0 flex-col items-center justify-center rounded-control border tabular-nums",
              isIncluded
                ? "border-pine/20 bg-pine text-white"
                : "border-border bg-surface-muted text-ink-secondary"
            )}
          >
            <span className="text-xs font-bold leading-none">{cal.dayText}</span>
            <span className="mt-0.5 text-[10px] font-semibold uppercase tracking-wider opacity-85">
              {cal.monthText}
            </span>
            <span className="mt-0.5 text-[9px] opacity-70">{cal.durationText}</span>
          </div>

          {/* Основная информация о площадке */}
          <div className="min-w-0 flex-1">
            {/* Мета-строка через точку (вместо овальных таблеток) */}
            <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-ink-muted">
              <span className="font-semibold text-ink-secondary">{formatName}</span>
              <span>·</span>
              <span className="inline-flex items-center gap-1 font-medium text-ink-secondary">
                {item.is_online ? (
                  <Globe className="h-3 w-3 text-sage" strokeWidth={1.5} />
                ) : (
                  <MapPin className="h-3 w-3 text-ink-muted" strokeWidth={1.5} />
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
                <Badge variant="sage" className="ml-1">
                  Спецпроект / По запросу
                </Badge>
              )}
            </div>

            <h3 className="mt-0.5 text-sm font-semibold leading-snug text-ink">
              {item.canonical_title}
            </h3>

            {/* Темы строкой */}
            {item.themes.length > 0 && (
              <p className="mt-0.5 text-[11px] text-ink-muted">
                Темы: {item.themes.join(" · ")}
              </p>
            )}

            {/* Блок «Аргументы выбора и целевая аудитория» (Слайд 04) с редактированием по клику */}
            <div className="mt-2 rounded-control border-l-2 border-pine bg-canvas/70 pl-2.5 pr-2 py-1.5">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted">
                  Аргументы выбора площадки и ЦА
                </span>
                <button
                  type="button"
                  onClick={() => setIsEditingRationale((p) => !p)}
                  className="inline-flex items-center gap-1 text-[11px] text-ink-muted hover:text-pine"
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
                  className="mt-1 w-full rounded border border-border bg-surface p-1.5 text-xs text-ink focus:border-pine focus:outline-none"
                />
              ) : (
                <p
                  onClick={() => setIsEditingRationale(true)}
                  className="mt-0.5 cursor-pointer text-xs leading-relaxed text-ink-secondary hover:text-ink"
                  title="Нажмите, чтобы отредактировать аргументацию для клиента"
                >
                  {rationale}
                </p>
              )}
            </div>
          </div>
        </div>

        {/* Правая колонка: Выбор тарифа и расчёт выгоды Early Bird */}
        <div className="flex shrink-0 flex-col justify-between gap-1.5 border-t border-border/70 pt-2.5 lg:w-[255px] lg:border-l lg:border-t-0 lg:pl-3.5 lg:pt-0">
          <div>
            <div className="flex items-center justify-between text-[11px]">
              <span className="font-medium text-ink-muted">Тариф участия:</span>
              <Badge
                variant={
                  selectedTariff.participation_role === "speaker"
                    ? "pine"
                    : selectedTariff.participation_role === "sponsor"
                      ? "terracotta"
                      : "neutral"
                }
              >
                {ROLE_BADGE_LABELS[selectedTariff.participation_role]}
              </Badge>
            </div>

            <select
              value={selectedTariff.tariff_id}
              onChange={(e) => onChangeTariff(Number(e.target.value))}
              className="mt-1.5 h-8 w-full rounded-control border border-border bg-canvas px-2 text-xs font-medium text-ink tabular-nums focus:border-pine focus:bg-surface focus:outline-none"
            >
              {item.available_tariffs.map((t) => (
                <option key={t.tariff_id} value={t.tariff_id}>
                  {t.tariff_name} — {formatRub(t.actual_price)}
                </option>
              ))}
            </select>
          </div>

          <div className="mt-1 flex items-baseline justify-between tabular-nums">
            <div className="flex items-baseline gap-1.5">
              <span className="text-sm font-bold text-ink">
                {formatRub(selectedTariff.actual_price)}
              </span>
              {selectedTariff.savings > 0 && selectedTariff.base_price && (
                <span className="text-xs text-ink-faint line-through">
                  {formatRub(selectedTariff.base_price)}
                </span>
              )}
            </div>

            {selectedTariff.savings > 0 ? (
              <span className="text-[11px] font-semibold text-sage">
                −{formatRub(selectedTariff.savings)}
                {selectedTariff.early_bird_deadline
                  ? ` до ${formatDateShort(selectedTariff.early_bird_deadline).slice(0, 5)}`
                  : ""}
              </span>
            ) : (
              <span className="text-[11px] text-ink-faint">Базовый тариф</span>
            )}
          </div>

          {selectedTariff.included_benefits && (
            <p
              className="truncate text-[11px] text-ink-muted"
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

