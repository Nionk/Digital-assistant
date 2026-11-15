import * as React from "react";
import {
  ChevronDown,
  ChevronUp,
  RotateCcw,
  ArrowRight,
  FileText,
  X,
  Loader2,
  AlertTriangle,
} from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { toast } from "sonner";
import { useManagerEventsCatalog } from "@/api/queries";
import type {
  ClientQueryExtracted,
  EventFormat,
  ParticipationRole,
  ProfileSource,
} from "@/api/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { CustomSelect } from "@/components/ui/custom-select";
import {
  SearchableMultiSelectPopover,
  type MultiSelectOption,
} from "@/components/ui/searchable-multi-select-popover";
import {
  FORMAT_LABELS,
  ROLE_BADGE_LABELS,
  formatNumberCompact,
} from "@/lib/formatters";
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
    category: "Девелопмент",
    focus: "КРТ · Спикер",
    budget: "400 000 ₽",
    text: "Установочная встреча с ГК Пионер. Продукт: жилые кварталы и проекты КРТ. Ищут на осень–зиму в Москве или Санкт-Петербурге 3 профильных мероприятия (форумы и камерные круглые столы) по КРТ, урбанистике и девелопменту. Минимум на одной площадке хотят выступить спикером в целевой сессии для укрепления экспертной позиции, на остальных — деловые знакомства с застройщиками и ведомствами. Общий бюджет на взносы организаторов — до 400 000 руб.",
  },
  {
    category: "Архитектура",
    focus: "Урбанистика · Конкурсы",
    budget: "300 000 ₽",
    text: "Созвонились с архитектурным бюро. Интересуют 3 площадки в Москве, СПб или онлайн по темам: архитектура, градостроительство, BIM-проектирование и профессиональные конкурсы. Важен выход на главных архитекторов и директоров по продукту девелоперских компаний. Минимум 1 экспертное выступление спикером. Бюджет до 300 000 руб.",
  },
  {
    category: "Производство",
    focus: "Стенд · Встречи",
    budget: "650 000 ₽",
    text: "Производитель фасадных и инженерных систем. Задача: выход на застройщиков жилья, подрядчиков и проектные институты в Москве и регионах. Рассматривают 3 мероприятия: крупный строительный форум (возможен партнёрский пакет со стендом и деловой игрой) + закрытые деловые завтраки руководителей. Общий ориентир бюджета — 650 000 руб.",
  },
];

const ALL_ROLES: ParticipationRole[] = ["delegate", "speaker", "sponsor"];

const ALL_EVENT_FORMATS: EventFormat[] = [
  "forum",
  "conference",
  "roundtable",
  "business_breakfast",
  "session",
];

const FORMAT_SELECT_OPTIONS: MultiSelectOption[] = ALL_EVENT_FORMATS.map(
  (fmt) => ({
    value: fmt,
    label: FORMAT_LABELS[fmt] || fmt,
  })
);

const PROFILE_SOURCE_LABELS: Record<
  ProfileSource,
  { label: string; variant: "ebGold" | "ebBlue" | "ebTeal" }
> = {
  llm: { label: "Профиль: ИИ-разбор", variant: "ebGold" },
  heuristic: { label: "Профиль: автоанализ", variant: "ebBlue" },
  manual: { label: "Профиль: ручная правка", variant: "ebTeal" },
};

const MATCHING_STATUS_STEPS = [
  "Анализ заметки и извлечение параметров...",
  "Семантический и FTS-поиск по каталогу площадок...",
  "Комбинаторная оптимизация пакетов без пересечения дат...",
  "Подготовка коммерческого письма и расчёт Early Bird...",
] as const;

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
  const { data: catalogData } = useManagerEventsCatalog(Boolean(editableProfile));
  const [loadingStepIndex, setLoadingStepIndex] = React.useState(0);

  // Все уникальные города из каталога с количеством мероприятий
  const catalogCityOptions = React.useMemo<MultiSelectOption[]>(() => {
    const counts = new Map<string, number>();
    for (const ev of catalogData?.events || []) {
      if (ev.city) {
        counts.set(ev.city, (counts.get(ev.city) || 0) + 1);
      }
    }
    return Array.from(counts.entries())
      .map(([city, count]) => ({ value: city, label: city, count }))
      .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
  }, [catalogData?.events]);

  // Все уникальные темы площадок из каталога с количеством мероприятий
  const catalogThemeOptions = React.useMemo<MultiSelectOption[]>(() => {
    const counts = new Map<string, number>();
    for (const ev of catalogData?.events || []) {
      for (const t of ev.themes) {
        counts.set(t, (counts.get(t) || 0) + 1);
      }
    }
    return Array.from(counts.entries())
      .map(([theme, count]) => ({ value: theme, label: theme, count }))
      .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
  }, [catalogData?.events]);

  // Последовательная индикация реальных этапов конвейера подбора
  React.useEffect(() => {
    if (!isMatching) {
      setLoadingStepIndex(0);
      return;
    }
    setLoadingStepIndex(0);
    const interval = window.setInterval(() => {
      setLoadingStepIndex((prev) =>
        Math.min(prev + 1, MATCHING_STATUS_STEPS.length - 1)
      );
    }, 3500);
    return () => window.clearInterval(interval);
  }, [isMatching]);

  const handleUpdateCities = (newCities: string[]) => {
    if (!editableProfile) return;
    onUpdateProfile((prev) => ({
      ...prev,
      cities: newCities,
    }));
  };

  const handleCreateCustomCity = (customCity: string) => {
    const trimmed = customCity.trim();
    if (!trimmed || !editableProfile) return;
    if (!editableProfile.cities.includes(trimmed)) {
      handleUpdateCities([...editableProfile.cities, trimmed]);
    }
  };

  const handleRemoveCity = (city: string) => {
    onUpdateProfile((prev) => ({
      ...prev,
      cities: prev.cities.filter((c) => c !== city),
    }));
  };

  const handleUpdateThemes = (newThemes: string[]) => {
    if (!editableProfile) return;
    onUpdateProfile((prev) => ({
      ...prev,
      themes_keywords: newThemes,
    }));
  };

  const handleCreateCustomTheme = (customTheme: string) => {
    const trimmed = customTheme.trim();
    if (!trimmed || !editableProfile) return;
    if (!editableProfile.themes_keywords.includes(trimmed)) {
      handleUpdateThemes([...editableProfile.themes_keywords, trimmed]);
    }
  };

  const handleRemoveTheme = (tag: string) => {
    onUpdateProfile((prev) => ({
      ...prev,
      themes_keywords: prev.themes_keywords.filter((t) => t !== tag),
    }));
  };

  const handleUpdatePreferredFormats = (values: string[]) => {
    if (!editableProfile) return;
    const validFormats = values.filter((v): v is EventFormat =>
      ALL_EVENT_FORMATS.includes(v as EventFormat)
    );
    onUpdateProfile((prev) => ({
      ...prev,
      preferred_formats: validFormats,
    }));
  };

  const handleRemovePreferredFormat = (fmt: EventFormat) => {
    onUpdateProfile((prev) => ({
      ...prev,
      preferred_formats: prev.preferred_formats.filter((f) => f !== fmt),
    }));
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

  const isBudgetInvalid = Boolean(
    editableProfile &&
    (!Number.isFinite(editableProfile.total_budget_max) ||
      editableProfile.total_budget_max <= 0)
  );
  const isDateRangeInvalid = Boolean(
    editableProfile?.date_from &&
    editableProfile?.date_to &&
    editableProfile.date_to < editableProfile.date_from
  );
  const hasProfileValidationError = isBudgetInvalid || isDateRangeInvalid;

  const handleRematchClick = () => {
    if (isBudgetInvalid) {
      toast.error("Укажите лимит бюджета больше 0 ₽ перед пересборкой пакетов.");
      return;
    }
    if (isDateRangeInvalid) {
      toast.error("Дата окончания периода не может быть раньше даты начала.");
      return;
    }
    onRematchWithOverride();
  };

  return (
    <section className="rounded-[12px] border border-[#262D35] bg-[#161B22] shadow-sm relative">
      {/* Шапка блока Шага 01–03 */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#21262F] bg-[#12161A] px-4 py-2.5 rounded-t-[12px]">
        <div className="flex items-baseline gap-2.5 min-w-0">
          <span className="font-serif italic font-bold text-base sm:text-lg text-[#E5C378] select-none leading-none">
            01
          </span>
          <h2 className="font-serif italic text-sm font-semibold tracking-tight text-[#E5C378] sm:text-[15px] leading-snug">
            Запрос клиента и аналитика задач
          </h2>
          {hasMatchResult && isCollapsed && (
            <span className="hidden truncate text-xs text-[#8E95A0] md:inline max-w-[380px]">
              · «{notes.slice(0, 68)}...»
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {hasMatchResult && (
            <button
              type="button"
              onClick={() => onToggleCollapsed(!isCollapsed)}
              className="inline-flex items-center gap-1.5 rounded-[6px] border border-[#262D35] bg-[#161B21] px-2.5 py-1 text-xs font-medium text-[#D1D5DB] transition-colors hover:border-[#E5C378] hover:bg-[#1E252E] hover:text-[#E5C378]"
            >
              <FileText className="h-3.5 w-3.5" strokeWidth={1.5} />
              <span>{isCollapsed ? "Развернуть бриф" : "Свернуть бриф"}</span>
              {isCollapsed ? (
                <ChevronDown className="h-3.5 w-3.5" strokeWidth={1.5} />
              ) : (
                <ChevronUp className="h-3.5 w-3.5" strokeWidth={1.5} />
              )}
            </button>
          )}
        </div>
      </div>

      {/* Раскрываемая область ввода конспекта установочной встречи с плавной анимацией */}
      <AnimatePresence initial={false}>
        {(!isCollapsed || !hasMatchResult) && (
          <motion.div
            key="brief-content"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22, ease: "easeInOut" }}
            className="overflow-hidden"
          >
            <div className="p-4 border-b border-[#21262F] bg-[#161B22]">
              <div className="mb-2.5 flex flex-wrap items-center justify-between gap-2">
                <label className="text-xs font-semibold text-[#D1D5DB]">
                  Конспект установочной встречи с клиентом:
                </label>
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-[11px] font-medium text-[#727985]">Готовые кейсы:</span>
                  {DEMO_NOTE_PRESETS.map((preset) => (
                    <button
                      key={preset.category}
                      type="button"
                      onClick={() => onNotesChange(preset.text)}
                      className="inline-flex items-center gap-1.5 rounded-[4px] border border-[#262D35] bg-[#12161A] px-2 py-0.5 text-[11px] transition-all hover:border-[#E5C378] hover:bg-[#161E28]"
                    >
                      <Badge variant="ebAmber" className="text-[9px]">
                        {preset.category}
                      </Badge>
                      <span className="text-[#D1D5DB] font-medium">{preset.focus}</span>
                      <span className="text-[#8E95A0]">· {preset.budget}</span>
                    </button>
                  ))}
                </div>
              </div>

              <textarea
                rows={3}
                value={notes}
                onChange={(e) => onNotesChange(e.target.value)}
                placeholder="Вводные встречи: задачи участия, ключевые темы, спикерство/стенд, география и лимит бюджета..."
                className="w-full rounded-[8px] border border-[#262D35] bg-[#12161A] p-3 text-sm leading-relaxed text-white placeholder:text-[#6B7280] [color-scheme:dark] outline-none focus:outline-none focus-visible:outline-none active:outline-none focus:border-[#E5C378] focus:shadow-[0_0_0_1px_rgba(229,195,120,0.25)] transition-colors duration-150"
              />

              <div className="mt-3 flex items-center justify-end">
                <Button
                  type="button"
                  variant="monolith"
                  size="md"
                  disabled={isMatching || notes.trim().length < 10}
                  onClick={onRunInitialMatch}
                  className="font-semibold text-xs px-4"
                >
                  {isMatching ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin text-[#E5C378]" />
                      <span>Формируем подборку...</span>
                    </>
                  ) : (
                    <>
                      <span>Подобрать варианты пакетов</span>
                      <ArrowRight className="h-4 w-4 text-[#E5C378] monolith-icon" strokeWidth={2} />
                    </>
                  )}
                </Button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Круглый движущийся индикатор загрузки со сменяющимися фразами */}
      {isMatching && (
        <div className="border-b border-[#21262F] bg-[#12161A] px-4 py-3">
          <div className="flex items-center gap-3 min-h-[26px]">
            <div className="h-5 w-5 shrink-0 rounded-full border-2 border-[#262D35] border-t-[#E5C378] animate-spin" />
            <AnimatePresence mode="wait">
              <motion.p
                key={loadingStepIndex}
                initial={{ opacity: 0, y: 3 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -3 }}
                transition={{ duration: 0.28, ease: "easeInOut" }}
                className="font-serif italic text-xs font-medium text-[#E5C378]"
              >
                {MATCHING_STATUS_STEPS[loadingStepIndex]}
              </motion.p>
            </AnimatePresence>
          </div>
        </div>
      )}

      {/* Строгая 5-ячеечная табличная строка параметров в стиле Novel.AI */}
      {editableProfile && (
        <div className="bg-[#161B22] rounded-b-[12px]">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#21262F] px-4 py-2 bg-[#12161A]">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-semibold text-white">
                Параметры отбора площадок
              </span>
              <Badge
                variant={
                  PROFILE_SOURCE_LABELS[editableProfile.profile_source]?.variant ??
                  "ebGold"
                }
                asSlanted={false}
                className="text-[10px]"
              >
                {PROFILE_SOURCE_LABELS[editableProfile.profile_source]?.label ??
                  editableProfile.profile_source}
              </Badge>
              {editableProfile.budget_is_assumed && (
                <Badge
                  variant="ebAmber"
                  asSlanted={false}
                  className="text-[10px]"
                  title="В конспекте не был явно указан бюджет — применен ориентир по умолчанию"
                >
                  Ориентир бюджета подобран системой
                </Badge>
              )}
            </div>
            <button
              type="button"
              disabled={isMatching}
              onClick={handleRematchClick}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-[6px] border px-2.5 py-1 text-xs font-medium select-none cursor-pointer shadow-sm transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed outline-none",
                hasProfileValidationError
                  ? "border-[#7C4A19] bg-[#22160C] text-[#E59837] hover:border-[#EF4444]"
                  : "border-[#262D35] bg-[#161B21] text-[#D1D5DB] hover:border-[#E5C378] hover:text-[#E5C378] hover:bg-[#1E252E]"
              )}
            >
              <RotateCcw className="h-3 w-3 shrink-0 text-inherit transition-transform" strokeWidth={2} />
              <span>Пересобрать пакеты</span>
            </button>
          </div>

          <div className="grid grid-cols-1 divide-y divide-[#262D35] md:grid-cols-5 md:divide-x md:divide-y-0">
            {/* Ячейка 1: Бюджет и кол-во событий */}
            <div className="p-3 bg-[#161B22]">
              <span className="block font-serif italic uppercase text-[10px] font-semibold tracking-wider text-[#8E95A0]">
                1. Лимит бюджета (₽)
              </span>
              <div className="relative mt-1.5 flex items-center">
                <input
                  type="number"
                  step={50000}
                  min={1}
                  value={Math.round(editableProfile.total_budget_max)}
                  onChange={(e) => {
                    const parsed = Number(e.target.value);
                    const val =
                      Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
                    onUpdateProfile((prev) => ({
                      ...prev,
                      total_budget_max: val,
                      budget_is_assumed: false,
                    }));
                  }}
                  aria-invalid={isBudgetInvalid}
                  className={cn(
                    "h-7 w-full rounded-[4px] border bg-[#12161A] pl-2 pr-7 text-xs font-semibold text-white tabular-nums [color-scheme:dark] outline-none focus:outline-none focus-visible:outline-none active:outline-none transition-colors duration-150 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none",
                    isBudgetInvalid
                      ? "border-[#EF4444] focus:border-[#EF4444]"
                      : "border-[#262D35] focus:border-[#E5C378] focus:shadow-[0_0_0_1px_rgba(229,195,120,0.25)]"
                  )}
                />
                <div className="absolute right-1 flex flex-col">
                  <button
                    type="button"
                    onClick={() =>
                      onUpdateProfile((p) => ({
                        ...p,
                        total_budget_max: p.total_budget_max + 50000,
                        budget_is_assumed: false,
                      }))
                    }
                    className="h-3 w-4 flex items-center justify-center text-[#8E95A0] hover:text-[#E5C378] transition-colors"
                    title="Увеличить на 50 000 ₽"
                  >
                    <ChevronUp className="h-2.5 w-2.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      onUpdateProfile((p) => ({
                        ...p,
                        total_budget_max:
                          p.total_budget_max > 50000
                            ? p.total_budget_max - 50000
                            : Math.max(10000, p.total_budget_max),
                        budget_is_assumed: false,
                      }))
                    }
                    className="h-3 w-4 flex items-center justify-center text-[#8E95A0] hover:text-[#E5C378] transition-colors"
                    title="Уменьшить на 50 000 ₽"
                  >
                    <ChevronDown className="h-2.5 w-2.5" />
                  </button>
                </div>
              </div>
              {isBudgetInvalid && (
                <p className="mt-1 flex items-center gap-1 text-[10px] text-[#FCA5A5]">
                  <AlertTriangle className="h-3 w-3 shrink-0 text-[#F87171]" />
                  <span>Укажите сумму больше 0 ₽</span>
                </p>
              )}
              <div className="mt-2 flex items-center justify-between text-[11px] text-[#8E95A0]">
                <span>Площадок в пакете:</span>
                <CustomSelect
                  value={editableProfile.target_events_count}
                  onChange={(val) =>
                    onUpdateProfile((prev) => ({
                      ...prev,
                      target_events_count: Number(val) || 3,
                    }))
                  }
                  options={[1, 2, 3, 4, 5].map((n) => ({
                    value: n,
                    label: String(n),
                  }))}
                  buttonClassName="h-6 px-2 py-0.5"
                  menuClassName="min-w-[60px]"
                />
              </div>
            </div>

            {/* Ячейка 2: География и Онлайн */}
            <div className="p-3 bg-[#161B22] relative flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between">
                  <span className="font-serif italic uppercase text-[10px] font-semibold tracking-wider text-[#8E95A0]">
                    2. География
                  </span>
                  <label className="inline-flex cursor-pointer items-center gap-1 text-[11px] font-medium text-[#D1D5DB]">
                    <input
                      type="checkbox"
                      checked={editableProfile.include_online}
                      onChange={(e) =>
                        onUpdateProfile((prev) => ({
                          ...prev,
                          include_online: e.target.checked,
                        }))
                      }
                      className="h-3 w-3 rounded accent-[#E5C378]"
                    />
                    <span>+ Онлайн</span>
                  </label>
                </div>

                {/* Отображение выбранных городов в ячейке */}
                <div className="mt-1.5 flex flex-wrap gap-1 max-h-16 overflow-y-auto scrollbar-thin">
                  {editableProfile.cities.map((city) => (
                    <span
                      key={city}
                      className="inline-flex items-center gap-1 rounded-[4px] border border-[#262D35] bg-[#12161A] px-1.5 py-0.5 text-[11px] font-medium text-white"
                    >
                      <span>{city === "Санкт-Петербург" ? "СПб" : city}</span>
                      <button
                        type="button"
                        onClick={() => handleRemoveCity(city)}
                        className="text-[#8E95A0] hover:text-[#EF4444] transition-colors"
                        title="Удалить город"
                      >
                        <X className="h-2.5 w-2.5" />
                      </button>
                    </span>
                  ))}
                  {editableProfile.cities.length === 0 && (
                    <span className="text-[11px] font-serif italic text-[#6B7280]">
                      Все города (без ограничений)
                    </span>
                  )}
                </div>
              </div>

              {/* Выдвижная панель с живым поиском и мультивыбором городов */}
              <div className="mt-2">
                <SearchableMultiSelectPopover
                  label="Города"
                  placeholder="Поиск города по каталогу..."
                  options={catalogCityOptions}
                  selectedValues={editableProfile.cities}
                  onChange={handleUpdateCities}
                  allowCustomCreation={true}
                  onCreateCustom={handleCreateCustomCity}
                  align="left"
                  popoverWidthClass="w-80 sm:w-96"
                  triggerClassName="w-full justify-between h-6 px-2 text-[11px]"
                  allSelectedLabel="Все"
                  renderTriggerContent={({ isOpen }) => (
                    <button
                      type="button"
                      className={cn(
                        "w-full flex h-7 items-center justify-between gap-1.5 rounded-[4px] border border-[#262D35] bg-[#12161A] px-2 text-[11px] text-[#8E95A0] transition-colors hover:border-[#E5C378] hover:text-[#E5C378]",
                        isOpen && "border-[#E5C378] text-[#E5C378] bg-[#161B21]"
                      )}
                    >
                      <span className="truncate">
                        + Выбрать города ({catalogCityOptions.length})
                      </span>
                      <ChevronDown
                        className={cn(
                          "h-3 w-3 shrink-0 transition-transform duration-200",
                          isOpen && "rotate-180 text-[#E5C378]"
                        )}
                      />
                    </button>
                  )}
                />
              </div>
            </div>

            {/* Ячейка 3: Период планирования */}
            <div className="p-3 bg-[#161B22]">
              <span className="block font-serif italic uppercase text-[10px] font-semibold tracking-wider text-[#8E95A0]">
                3. Период календаря
              </span>
              <div className="mt-1.5 space-y-1.5">
                <div className="flex items-center justify-between gap-1 text-[11px]">
                  <span className="text-[#8E95A0]">С:</span>
                  <input
                    type="date"
                    value={editableProfile.date_from || ""}
                    onChange={(e) =>
                      onUpdateProfile((prev) => ({
                        ...prev,
                        date_from: e.target.value || null,
                      }))
                    }
                    aria-invalid={isDateRangeInvalid}
                    className={cn(
                      "h-6 rounded-[4px] border bg-[#12161A] px-1.5 text-[11px] text-white tabular-nums [color-scheme:dark] outline-none focus:outline-none focus-visible:outline-none active:outline-none transition-colors duration-150",
                      isDateRangeInvalid
                        ? "border-[#EF4444] focus:border-[#EF4444]"
                        : "border-[#262D35] focus:border-[#E5C378] focus:shadow-[0_0_0_1px_rgba(229,195,120,0.25)]"
                    )}
                  />
                </div>
                <div className="flex items-center justify-between gap-1 text-[11px]">
                  <span className="text-[#8E95A0]">По:</span>
                  <input
                    type="date"
                    value={editableProfile.date_to || ""}
                    onChange={(e) =>
                      onUpdateProfile((prev) => ({
                        ...prev,
                        date_to: e.target.value || null,
                      }))
                    }
                    aria-invalid={isDateRangeInvalid}
                    className={cn(
                      "h-6 rounded-[4px] border bg-[#12161A] px-1.5 text-[11px] text-white tabular-nums [color-scheme:dark] outline-none focus:outline-none focus-visible:outline-none active:outline-none transition-colors duration-150",
                      isDateRangeInvalid
                        ? "border-[#EF4444] focus:border-[#EF4444]"
                        : "border-[#262D35] focus:border-[#E5C378] focus:shadow-[0_0_0_1px_rgba(229,195,120,0.25)]"
                    )}
                  />
                </div>
                {isDateRangeInvalid && (
                  <p className="flex items-center gap-1 text-[10px] text-[#FCA5A5]">
                    <AlertTriangle className="h-3 w-3 shrink-0 text-[#F87171]" />
                    <span>Дата «По» раньше даты «С»</span>
                  </p>
                )}
              </div>
            </div>

            {/* Ячейка 4: Роли участия, спикерство и форматы событий */}
            <div className="p-3 bg-[#161B22] flex flex-col justify-between">
              <div>
                <span className="block font-serif italic uppercase text-[10px] font-semibold tracking-wider text-[#8E95A0]">
                  4. Роли и форматы
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
                          "px-2 py-0.5 text-[11px] font-serif italic transition-colors outline-none",
                          active
                            ? "-skew-x-[9deg] rounded-[2px] border border-[#E5C378] bg-[#261E0F] text-[#E5C378] font-bold shadow-xs"
                            : "rounded-[3px] border border-[#262D35] bg-[#12161A] text-[#8E95A0] hover:bg-[#1A2128] hover:text-white"
                        )}
                      >
                        <span className={active ? "inline-block skew-x-[9deg]" : ""}>
                          {ROLE_BADGE_LABELS[role]}
                        </span>
                      </button>
                    );
                  })}
                </div>

                <div className="mt-2 flex items-center justify-between text-[11px] text-[#8E95A0]">
                  <span>Мин. докладов спикером:</span>
                  <CustomSelect
                    value={editableProfile.min_speaker_events}
                    onChange={(val) => {
                      const count = Number(val) || 0;
                      onUpdateProfile((prev) => ({
                        ...prev,
                        min_speaker_events: count,
                        required_roles:
                          count > 0 && !prev.required_roles.includes("speaker")
                            ? [...prev.required_roles, "speaker"]
                            : prev.required_roles,
                      }));
                    }}
                    options={[0, 1, 2, 3].map((n) => ({
                      value: n,
                      label: String(n),
                    }))}
                    buttonClassName="h-6 px-2 py-0.5"
                    menuClassName="min-w-[60px]"
                  />
                </div>
              </div>

              <div className="mt-2 border-t border-[#21262F] pt-2">
                {editableProfile.preferred_formats.length > 0 && (
                  <div className="mb-1.5 flex flex-wrap gap-1 max-h-14 overflow-y-auto scrollbar-thin">
                    {editableProfile.preferred_formats.map((fmt) => (
                      <span
                        key={fmt}
                        className="inline-flex items-center gap-1 rounded-[4px] border border-[#262D35] bg-[#12161A] px-1.5 py-0.5 text-[10px] font-medium text-white"
                      >
                        <span>{FORMAT_LABELS[fmt] || fmt}</span>
                        <button
                          type="button"
                          onClick={() => handleRemovePreferredFormat(fmt)}
                          className="text-[#8E95A0] hover:text-[#EF4444] transition-colors"
                          title="Убрать формат"
                        >
                          <X className="h-2.5 w-2.5" />
                        </button>
                      </span>
                    ))}
                  </div>
                )}

                <SearchableMultiSelectPopover
                  label="Форматы"
                  placeholder="Фильтр форматов..."
                  options={FORMAT_SELECT_OPTIONS}
                  selectedValues={editableProfile.preferred_formats}
                  onChange={handleUpdatePreferredFormats}
                  align="left"
                  popoverWidthClass="w-64 sm:w-72"
                  allSelectedLabel="Любые"
                  renderTriggerContent={({ isOpen }) => (
                    <button
                      type="button"
                      className={cn(
                        "w-full flex h-7 items-center justify-between gap-1.5 rounded-[4px] border border-[#262D35] bg-[#12161A] px-2 text-[11px] text-[#8E95A0] transition-colors hover:border-[#E5C378] hover:text-[#E5C378]",
                        isOpen && "border-[#E5C378] text-[#E5C378] bg-[#161B21]",
                        editableProfile.preferred_formats.length > 0 &&
                        "border-[#7C5A20] text-[#E5C378]"
                      )}
                    >
                      <span className="truncate">
                        {editableProfile.preferred_formats.length > 0
                          ? `Форматы (${editableProfile.preferred_formats.length})`
                          : "Форматы: любые"}
                      </span>
                      <ChevronDown
                        className={cn(
                          "h-3 w-3 shrink-0 transition-transform duration-200",
                          isOpen && "rotate-180 text-[#E5C378]"
                        )}
                      />
                    </button>
                  )}
                />
              </div>
            </div>

            {/* Ячейка 5: Отраслевые темы и ЦА */}
            <div className="p-3 bg-[#161B22] relative flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between">
                  <span className="block font-serif italic uppercase text-[10px] font-semibold tracking-wider text-[#8E95A0]">
                    5. Темы, продукт и ЦА
                  </span>
                  {editableProfile.themes_keywords.length > 0 && (
                    <span className="font-serif italic text-[10px] text-[#E5C378]">
                      {editableProfile.themes_keywords.length} выбрано
                    </span>
                  )}
                </div>

                <div className="mt-1.5 flex flex-wrap gap-1 max-h-16 overflow-y-auto scrollbar-thin">
                  {editableProfile.themes_keywords.map((tag) => (
                    <span
                      key={tag}
                      className="inline-flex items-center gap-1 rounded-[4px] border border-[#262D35] bg-[#12161A] px-1.5 py-0.5 text-[11px] font-medium text-white"
                    >
                      <span>{tag}</span>
                      <button
                        type="button"
                        onClick={() => handleRemoveTheme(tag)}
                        className="text-[#8E95A0] hover:text-[#EF4444] transition-colors"
                        title="Удалить тему"
                      >
                        <X className="h-2.5 w-2.5" />
                      </button>
                    </span>
                  ))}
                  {editableProfile.themes_keywords.length === 0 && (
                    <span className="text-[11px] font-serif italic text-[#6B7280]">
                      Темы не выбраны
                    </span>
                  )}
                </div>
              </div>

              <div className="mt-2">
                <SearchableMultiSelectPopover
                  label="Темы"
                  placeholder="Поиск по каталогу или ввод новой..."
                  options={catalogThemeOptions}
                  selectedValues={editableProfile.themes_keywords}
                  onChange={handleUpdateThemes}
                  allowCustomCreation={true}
                  onCreateCustom={handleCreateCustomTheme}
                  align="right"
                  popoverWidthClass="w-80 sm:w-96"
                  triggerClassName="w-full justify-between h-6 px-2 text-[11px]"
                  renderTriggerContent={({ isOpen }) => (
                    <button
                      type="button"
                      className={cn(
                        "w-full flex h-7 items-center justify-between gap-1.5 rounded-[4px] border border-[#262D35] bg-[#12161A] px-2 text-[11px] text-[#8E95A0] transition-colors hover:border-[#E5C378] hover:text-[#E5C378]",
                        isOpen && "border-[#E5C378] text-[#E5C378] bg-[#161B21]"
                      )}
                    >
                      <span className="truncate">
                        + Выбрать темы ({catalogThemeOptions.length})
                      </span>
                      <ChevronDown
                        className={cn(
                          "h-3 w-3 shrink-0 transition-transform duration-200",
                          isOpen && "rotate-180 text-[#E5C378]"
                        )}
                      />
                    </button>
                  )}
                />
              </div>
            </div>
          </div>

          <div className="border-t border-[#21262F] bg-[#12161A] px-4 py-2 flex items-center justify-end text-[11px] text-[#8E95A0] rounded-b-[12px]">
            <span className="font-serif italic uppercase tracking-wider text-[10px] text-[#8E95A0] mr-2">
              Ориентир бюджета:
            </span>
            <span className="tabular-nums font-semibold text-[#E5C378]">
              {formatNumberCompact(editableProfile.total_budget_max)} ₽
            </span>
          </div>
        </div>
      )}
    </section>
  );
}

