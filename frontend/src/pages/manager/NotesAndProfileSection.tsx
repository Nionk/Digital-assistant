import * as React from "react";
import {
  ChevronDown,
  ChevronUp,
  RotateCcw,
  ArrowRight,
  FileText,
  Plus,
  X,
  Loader2,
} from "lucide-react";
import type {
  ClientQueryExtracted,
  ParticipationRole,
} from "@/api/types";
import { Button } from "@/components/ui/button";
import { ROLE_BADGE_LABELS, formatNumberCompact } from "@/lib/formatters";
import { cn } from "@/lib/utils";

interface NotesAndProfileSectionProps {
  notes: string;
  onNotesChange: (val: string) => void;
  isCollapsed: boolean;
  onToggleCollapsed: (collapsed: boolean) => void;
  isMatching: boolean;
  hasMatchResult: boolean;
  editableProfile: ClientQueryExtracted | undefined;
  onUpdateProfile: (
    updater: (prev: ClientQueryExtracted) => ClientQueryExtracted
  ) => void;
  onRunInitialMatch: () => void;
  onRematchWithOverride: () => void;
}

const DEMO_NOTE_PRESETS = [
  {
    label: "Девелопер (КРТ + Спикер · 400 тыс.)",
    text: "Установочная встреча с ГК Пионер. Продукт: жилые кварталы и проекты КРТ. Ищут на осень–зиму в Москве или Санкт-Петербурге 3 профильных мероприятия (форумы и камерные круглые столы) по КРТ, урбанистике и девелопменту. Минимум на одной площадке хотят выступить спикером в целевой сессии для укрепления экспертной позиции, на остальных — деловые знакомства с застройщиками и ведомствами. Общий бюджет на взносы организаторов — до 400 000 руб.",
  },
  {
    label: "Архитектурное бюро (Урбанистика + Конкурсы · 300 тыс.)",
    text: "Созвонились с архитектурным бюро. Интересуют 3 площадки в Москве, СПб или онлайн по темам: архитектура, градостроительство, BIM-проектирование и профессиональные конкурсы. Важен выход на главных архитекторов и директоров по продукту девелоперских компаний. Минимум 1 экспертное выступление спикером. Бюджет до 300 000 руб.",
  },
  {
    label: "Производитель стройматериалов (Стенд + Встречи · 650 тыс.)",
    text: "Производитель фасадных и инженерных систем. Задача: выход на застройщиков жилья, подрядчиков и проектные институты в Москве и регионах. Рассматривают 3 мероприятия: крупный строительный форум (возможен партнёрский пакет со стендом и деловой игрой) + закрытые деловые завтраки руководителей. Общий ориентир бюджета — 650 000 руб.",
  },
];

const QUICK_CITIES = ["Москва", "Санкт-Петербург", "Екатеринбург", "Казань", "Сочи"];
const ALL_ROLES: ParticipationRole[] = ["delegate", "speaker", "sponsor"];

export function NotesAndProfileSection({
  notes,
  onNotesChange,
  isCollapsed,
  onToggleCollapsed,
  isMatching,
  hasMatchResult,
  editableProfile,
  onUpdateProfile,
  onRunInitialMatch,
  onRematchWithOverride,
}: NotesAndProfileSectionProps) {
  const [newTagText, setNewTagText] = React.useState("");
  const [newCityText, setNewCityText] = React.useState("");
  const [loadingStep, setLoadingStep] = React.useState(0);

  // Анимация шагов во время работы ИИ-пайплайна (3–5 секунд)
  React.useEffect(() => {
    if (!isMatching) {
      setLoadingStep(0);
      return;
    }
    const t1 = setTimeout(() => setLoadingStep(1), 1100);
    const t2 = setTimeout(() => setLoadingStep(2), 2400);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
    };
  }, [isMatching]);

  const handleAddTheme = (e: React.FormEvent) => {
    e.preventDefault();
    const cleaned = newTagText.trim();
    if (!cleaned || !editableProfile) return;
    if (!editableProfile.themes_keywords.includes(cleaned)) {
      onUpdateProfile((prev) => ({
        ...prev,
        themes_keywords: [...prev.themes_keywords, cleaned],
        semantic_search_query: `${prev.semantic_search_query} ${cleaned}`.trim(),
      }));
    }
    setNewTagText("");
  };

  const handleRemoveTheme = (tag: string) => {
    onUpdateProfile((prev) => ({
      ...prev,
      themes_keywords: prev.themes_keywords.filter((t) => t !== tag),
    }));
  };

  const handleToggleCity = (city: string) => {
    if (!editableProfile) return;
    const exists = editableProfile.cities.includes(city);
    onUpdateProfile((prev) => ({
      ...prev,
      cities: exists
        ? prev.cities.filter((c) => c !== city)
        : [...prev.cities, city],
    }));
  };

  const handleAddCustomCity = (e: React.FormEvent) => {
    e.preventDefault();
    const cleaned = newCityText.trim();
    if (!cleaned || !editableProfile) return;
    if (!editableProfile.cities.includes(cleaned)) {
      onUpdateProfile((prev) => ({
        ...prev,
        cities: [...prev.cities, cleaned],
      }));
    }
    setNewCityText("");
  };

  const handleToggleRole = (role: ParticipationRole) => {
    if (!editableProfile) return;
    const exists = editableProfile.required_roles.includes(role);
    const nextRoles = exists
      ? editableProfile.required_roles.filter((r) => r !== role)
      : [...editableProfile.required_roles, role];

    onUpdateProfile((prev) => ({
      ...prev,
      required_roles: nextRoles.length > 0 ? nextRoles : ["delegate"],
      min_speaker_events:
        role === "speaker" && !exists && prev.min_speaker_events === 0
          ? 1
          : role === "speaker" && exists
            ? 0
            : prev.min_speaker_events,
    }));
  };

  return (
    <section className="rounded-card border border-border bg-surface shadow-card overflow-hidden">
      {/* Шапка блока Шага 01–03 */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border bg-canvas/50 px-4 py-2.5">
        <div className="flex items-center gap-2 min-w-0">
          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-pine text-[10px] font-bold text-white tabular-nums">
            01
          </span>
          <span className="text-xs font-semibold uppercase tracking-wider text-ink">
            Запрос клиента и аналитика задач
          </span>
          {hasMatchResult && isCollapsed && (
            <span className="hidden truncate text-xs text-ink-muted md:inline max-w-[380px]">
              · «{notes.slice(0, 68)}...»
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {hasMatchResult && (
            <button
              type="button"
              onClick={() => onToggleCollapsed(!isCollapsed)}
              className="inline-flex items-center gap-1 rounded-control border border-border bg-surface px-2.5 py-1 text-xs font-medium text-ink-secondary transition-colors hover:bg-surface-muted hover:text-ink"
            >
              <FileText className="h-3.5 w-3.5" strokeWidth={1.5} />
              <span>{isCollapsed ? "Развернуть конспект" : "Свернуть конспект"}</span>
              {isCollapsed ? (
                <ChevronDown className="h-3.5 w-3.5" strokeWidth={1.5} />
              ) : (
                <ChevronUp className="h-3.5 w-3.5" strokeWidth={1.5} />
              )}
            </button>
          )}
        </div>
      </div>

      {/* Раскрываемая область ввода конспекта установочной встречи */}
      {(!isCollapsed || !hasMatchResult) && (
        <div className="p-4 border-b border-border/80 bg-surface">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <label className="text-xs font-medium text-ink-secondary">
              Конспект установочной встречи (цели, продукт, целевая аудитория, бюджет и роли):
            </label>
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-[11px] text-ink-faint">Шаблоны:</span>
              {DEMO_NOTE_PRESETS.map((preset) => (
                <button
                  key={preset.label}
                  type="button"
                  onClick={() => onNotesChange(preset.text)}
                  className="rounded-badge border border-border bg-canvas px-2 py-0.5 text-[11px] text-ink-secondary transition-colors hover:border-border-strong hover:bg-surface-muted hover:text-ink"
                >
                  {preset.label}
                </button>
              ))}
            </div>
          </div>

          <textarea
            rows={3}
            value={notes}
            onChange={(e) => onNotesChange(e.target.value)}
            placeholder="Опишите итоги разговора с клиентом: какие задачи нужно решить (выход на застройщиков, спикерство в сессии, стенд), желаемые города, период и общий лимит бюджета..."
            className="w-full rounded-control border border-border bg-canvas/40 p-3 text-sm leading-relaxed text-ink placeholder:text-ink-faint focus:border-pine focus:bg-surface focus:outline-none"
          />

          <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
            <p className="text-[11px] text-ink-muted">
              Система автоматически извлечет параметры, проверит пересечения дат и рассчитает 2 пакета с учетом скидок Early Bird.
            </p>
            <Button
              type="button"
              variant="primary"
              size="md"
              disabled={isMatching || notes.trim().length < 10}
              onClick={onRunInitialMatch}
            >
              {isMatching ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span>Формируем подборку...</span>
                </>
              ) : (
                <>
                  <span>Подобрать варианты пакетов</span>
                  <ArrowRight className="h-4 w-4" strokeWidth={1.75} />
                </>
              )}
            </Button>
          </div>
        </div>
      )}

      {/* Индикатор прогресса во время работы ИИ */}
      {isMatching && (
        <div className="border-b border-border bg-sage-tint/40 px-4 py-3">
          <div className="flex items-center gap-3">
            <Loader2 className="h-4 w-4 shrink-0 animate-spin text-pine" />
            <div className="flex-1">
              <div className="flex items-center justify-between text-xs font-medium text-pine">
                <span>
                  {loadingStep === 0 &&
                    "Шаг 1/3: Извлечение целевой аудитории, ролей, географии и бюджета..."}
                  {loadingStep === 1 &&
                    "Шаг 2/3: Гибридный поиск (pgvector + FTS RRF) и сверка календаря без накладок..."}
                  {loadingStep === 2 &&
                    "Шаг 3/3: Расчет выгоды Early Bird и подготовка аргументов выбора площадок..."}
                </span>
                <span className="tabular-nums">{(loadingStep + 1) * 33}%</span>
              </div>
              <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-border">
                <div
                  className="h-full bg-pine transition-all duration-500"
                  style={{ width: `${(loadingStep + 1) * 33.3}%` }}
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Строгая 5-ячеечная табличная строка параметров (без нейросетевого конфетти) */}
      {editableProfile && (
        <div className="bg-surface">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/70 px-4 py-2 bg-surface-muted/40">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-secondary">
              Параметры отбора площадок (можно скорректировать вручную без анкетирования клиента)
            </span>
            <Button
              type="button"
              variant="outline"
              size="xs"
              disabled={isMatching}
              onClick={onRematchWithOverride}
            >
              <RotateCcw className="h-3 w-3" strokeWidth={1.75} />
              <span>Пересобрать пакеты по параметрам</span>
            </Button>
          </div>

          <div className="grid grid-cols-1 divide-y divide-border md:grid-cols-5 md:divide-x md:divide-y-0">
            {/* Ячейка 1: Бюджет и кол-во событий */}
            <div className="p-3">
              <span className="block text-[10px] font-semibold uppercase tracking-wider text-ink-muted">
                1. Лимит бюджета (₽)
              </span>
              <div className="mt-1.5 flex items-center gap-1.5">
                <input
                  type="number"
                  step={10000}
                  min={0}
                  value={Math.round(editableProfile.total_budget_max)}
                  onChange={(e) => {
                    const val = Math.max(0, Number(e.target.value) || 0);
                    onUpdateProfile((prev) => ({ ...prev, total_budget_max: val }));
                  }}
                  className="h-7 w-full rounded-badge border border-border bg-canvas px-2 text-xs font-semibold text-ink tabular-nums focus:border-pine focus:bg-surface focus:outline-none"
                />
              </div>
              <div className="mt-2 flex items-center justify-between text-[11px] text-ink-muted">
                <span>Площадок в пакете:</span>
                <select
                  value={editableProfile.target_events_count}
                  onChange={(e) =>
                    onUpdateProfile((prev) => ({
                      ...prev,
                      target_events_count: Number(e.target.value) || 3,
                    }))
                  }
                  className="rounded border border-border bg-canvas px-1.5 py-0.5 text-xs font-semibold text-ink tabular-nums focus:border-pine focus:outline-none"
                >
                  {[1, 2, 3, 4, 5].map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Ячейка 2: География и Онлайн */}
            <div className="p-3">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted">
                  2. География
                </span>
                <label className="inline-flex cursor-pointer items-center gap-1 text-[11px] font-medium text-ink-secondary">
                  <input
                    type="checkbox"
                    checked={editableProfile.include_online}
                    onChange={(e) =>
                      onUpdateProfile((prev) => ({
                        ...prev,
                        include_online: e.target.checked,
                      }))
                    }
                    className="h-3 w-3 rounded accent-pine"
                  />
                  <span>+ Онлайн</span>
                </label>
              </div>

              <div className="mt-1.5 flex flex-wrap gap-1">
                {QUICK_CITIES.map((city) => {
                  const active = editableProfile.cities.includes(city);
                  return (
                    <button
                      key={city}
                      type="button"
                      onClick={() => handleToggleCity(city)}
                      className={cn(
                        "rounded-badge border px-1.5 py-0.5 text-[11px] transition-colors",
                        active
                          ? "border-pine bg-pine text-white font-medium"
                          : "border-border bg-canvas text-ink-secondary hover:bg-surface-muted"
                      )}
                    >
                      {city === "Санкт-Петербург" ? "СПб" : city}
                    </button>
                  );
                })}
                {editableProfile.cities
                  .filter((c) => !QUICK_CITIES.includes(c))
                  .map((customCity) => (
                    <span
                      key={customCity}
                      className="inline-flex items-center gap-1 rounded-badge border border-pine bg-pine px-1.5 py-0.5 text-[11px] font-medium text-white"
                    >
                      {customCity}
                      <button
                        type="button"
                        onClick={() => handleToggleCity(customCity)}
                        className="opacity-80 hover:opacity-100"
                      >
                        <X className="h-2.5 w-2.5" />
                      </button>
                    </span>
                  ))}
              </div>

              <form onSubmit={handleAddCustomCity} className="mt-1.5 flex gap-1">
                <input
                  type="text"
                  value={newCityText}
                  onChange={(e) => setNewCityText(e.target.value)}
                  placeholder="+ Город..."
                  className="h-6 w-full rounded border border-border bg-canvas px-1.5 text-[11px] text-ink placeholder:text-ink-faint focus:border-pine focus:outline-none"
                />
              </form>
            </div>

            {/* Ячейка 3: Период планирования */}
            <div className="p-3">
              <span className="block text-[10px] font-semibold uppercase tracking-wider text-ink-muted">
                3. Период календаря
              </span>
              <div className="mt-1.5 space-y-1.5">
                <div className="flex items-center justify-between gap-1 text-[11px]">
                  <span className="text-ink-muted">С:</span>
                  <input
                    type="date"
                    value={editableProfile.date_from || ""}
                    onChange={(e) =>
                      onUpdateProfile((prev) => ({
                        ...prev,
                        date_from: e.target.value || null,
                      }))
                    }
                    className="h-6 rounded border border-border bg-canvas px-1.5 text-[11px] text-ink tabular-nums focus:border-pine focus:outline-none"
                  />
                </div>
                <div className="flex items-center justify-between gap-1 text-[11px]">
                  <span className="text-ink-muted">По:</span>
                  <input
                    type="date"
                    value={editableProfile.date_to || ""}
                    onChange={(e) =>
                      onUpdateProfile((prev) => ({
                        ...prev,
                        date_to: e.target.value || null,
                      }))
                    }
                    className="h-6 rounded border border-border bg-canvas px-1.5 text-[11px] text-ink tabular-nums focus:border-pine focus:outline-none"
                  />
                </div>
              </div>
            </div>

            {/* Ячейка 4: Роли участия и спикерство */}
            <div className="p-3">
              <span className="block text-[10px] font-semibold uppercase tracking-wider text-ink-muted">
                4. Форматы участия
              </span>
              <div className="mt-1.5 flex flex-wrap gap-1">
                {ALL_ROLES.map((role) => {
                  const active = editableProfile.required_roles.includes(role);
                  return (
                    <button
                      key={role}
                      type="button"
                      onClick={() => handleToggleRole(role)}
                      className={cn(
                        "rounded-badge border px-1.5 py-0.5 text-[11px] transition-colors",
                        active
                          ? "border-pine bg-pine text-white font-medium"
                          : "border-border bg-canvas text-ink-secondary hover:bg-surface-muted"
                      )}
                    >
                      {ROLE_BADGE_LABELS[role]}
                    </button>
                  );
                })}
              </div>

              <div className="mt-2 flex items-center justify-between text-[11px] text-ink-muted">
                <span>Мин. докладов спикером:</span>
                <select
                  value={editableProfile.min_speaker_events}
                  onChange={(e) => {
                    const count = Number(e.target.value) || 0;
                    onUpdateProfile((prev) => ({
                      ...prev,
                      min_speaker_events: count,
                      required_roles:
                        count > 0 && !prev.required_roles.includes("speaker")
                          ? [...prev.required_roles, "speaker"]
                          : prev.required_roles,
                    }));
                  }}
                  className="rounded border border-border bg-canvas px-1.5 py-0.5 text-xs font-semibold text-ink tabular-nums focus:border-pine focus:outline-none"
                >
                  {[0, 1, 2, 3].map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Ячейка 5: Отраслевые темы и ЦА */}
            <div className="p-3">
              <span className="block text-[10px] font-semibold uppercase tracking-wider text-ink-muted">
                5. Темы, продукт и ЦА
              </span>
              <div className="mt-1.5 flex flex-wrap gap-1 max-h-16 overflow-y-auto scrollbar-thin">
                {editableProfile.themes_keywords.map((tag) => (
                  <span
                    key={tag}
                    className="inline-flex items-center gap-1 rounded-badge border border-border bg-canvas px-1.5 py-0.5 text-[11px] font-medium text-ink"
                  >
                    <span>{tag}</span>
                    <button
                      type="button"
                      onClick={() => handleRemoveTheme(tag)}
                      className="text-ink-muted hover:text-terracotta"
                    >
                      <X className="h-2.5 w-2.5" />
                    </button>
                  </span>
                ))}
              </div>
              <form onSubmit={handleAddTheme} className="mt-1.5 flex gap-1">
                <input
                  type="text"
                  value={newTagText}
                  onChange={(e) => setNewTagText(e.target.value)}
                  placeholder="+ Добавить тему (КРТ, BIM...)"
                  className="h-6 flex-1 rounded border border-border bg-canvas px-1.5 text-[11px] text-ink placeholder:text-ink-faint focus:border-pine focus:outline-none"
                />
                <button
                  type="submit"
                  className="flex h-6 w-6 shrink-0 items-center justify-center rounded border border-border bg-canvas text-ink-secondary hover:bg-surface-muted"
                >
                  <Plus className="h-3 w-3" />
                </button>
              </form>
            </div>
          </div>

          <div className="border-t border-border/60 bg-canvas/40 px-4 py-1.5 flex items-center justify-between text-[11px] text-ink-muted">
            <span className="truncate">
              Поисковый вектор (RRF):{" "}
              <strong className="font-medium text-ink-secondary">
                {editableProfile.semantic_search_query}
              </strong>
            </span>
            <span className="shrink-0 tabular-nums">
              Ориентир: {formatNumberCompact(editableProfile.total_budget_max)} ₽
            </span>
          </div>
        </div>
      )}
    </section>
  );
}

