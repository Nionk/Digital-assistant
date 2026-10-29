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
import { AnimatePresence, motion } from "framer-motion";
import type {
  ClientQueryExtracted,
  ParticipationRole,
} from "@/api/types";
import { Button } from "@/components/ui/button";
import { CustomSelect } from "@/components/ui/custom-select";
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

const QUICK_CITIES = ["Москва", "Санкт-Петербург", "Екатеринбург", "Казань", "Сочи"];
const ALL_ROLES: ParticipationRole[] = ["delegate", "speaker", "sponsor"];

const LOADING_PHRASES = [
  "Подбираем предложения...",
  "Анализируем профиль клиента...",
  "Сверяем даты и проверяем календарь накладок...",
  "Рассчитываем льготные тарифы Early Bird...",
  "Еще немного, формируем варианты пакетов...",
];

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
  const [loadingPhraseIndex, setLoadingPhraseIndex] = React.useState(0);

  // Живая ротация привлекательных фраз при подборе
  React.useEffect(() => {
    if (!isMatching) {
      setLoadingPhraseIndex(0);
      return;
    }
    const interval = setInterval(() => {
      setLoadingPhraseIndex((prev) => (prev + 1) % LOADING_PHRASES.length);
    }, 1100);
    return () => clearInterval(interval);
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
    <section className="rounded-[12px] border border-[#262D35] bg-[#161B22] shadow-sm overflow-hidden">
      {/* Шапка блока Шага 01–03 */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#21262F] bg-[#12161A] px-4 py-2.5">
        <div className="flex items-baseline gap-2.5 min-w-0">
          <span className="font-serif italic font-bold text-base sm:text-lg text-[#E5C378] select-none">
            01
          </span>
          <h2 className="font-serif italic text-sm font-semibold tracking-tight text-[#E5C378] sm:text-[15px]">
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
              className="inline-flex items-center gap-1.5 rounded-[6px] border border-[#262D35] bg-[#161B21] px-2.5 py-1 text-xs font-medium text-[#D1D5DB] transition-colors hover:border-[#38414F] hover:bg-[#1E252E] hover:text-white"
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
                      className="inline-flex items-center gap-1.5 rounded-[4px] border border-[#262D35] bg-[#12161A] px-2 py-0.5 text-[11px] transition-all hover:border-[#38BDF8] hover:bg-[#161E28]"
                    >
                      <span className="rounded-[3px] bg-[#E59837] px-1.5 py-0.2 text-[9px] font-serif italic font-bold text-[#261502]">
                        {preset.category}
                      </span>
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
                placeholder="Опишите итоги разговора с клиентом: какие задачи нужно решить (выход на застройщиков, спикерство в сессии, стенд), желаемые города, период и общий лимит бюджета..."
                className="w-full rounded-[8px] border border-[#262D35] bg-[#12161A] p-3 text-sm leading-relaxed text-white placeholder:text-[#6B7280] focus:border-[#38BDF8] focus:outline-none"
              />

              <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
                <p className="text-[11px] text-[#8E95A0]">
                  Система автоматически извлечет параметры, проверит пересечения дат и рассчитает 2 пакета с учетом скидок Early Bird.
                </p>
                <Button
                  type="button"
                  variant="primary"
                  size="md"
                  disabled={isMatching || notes.trim().length < 10}
                  onClick={onRunInitialMatch}
                  className="bg-gradient-to-r from-[#D4AF37] via-[#E5C378] to-[#D4AF37] text-[#0E1215] font-semibold active:scale-[0.98] active:brightness-150 transition-all duration-100 ease-out hover:shadow-[0_0_12px_rgba(229,195,120,0.35)]"
                >
                  {isMatching ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin text-[#0E1215]" />
                      <span>Формируем подборку...</span>
                    </>
                  ) : (
                    <>
                      <span>Подобрать варианты пакетов</span>
                      <ArrowRight className="h-4 w-4 text-[#0E1215]" strokeWidth={2} />
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
          <div className="flex items-center gap-3">
            <div className="h-5 w-5 shrink-0 rounded-full border-2 border-[#262D35] border-t-[#E5C378] animate-spin" />
            <p className="font-serif italic text-xs font-medium text-[#E5C378] transition-all duration-300">
              {LOADING_PHRASES[loadingPhraseIndex]}
            </p>
          </div>
        </div>
      )}

      {/* Строгая 5-ячеечная табличная строка параметров в стиле Novel.AI */}
      {editableProfile && (
        <div className="bg-[#161B22]">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#21262F] px-4 py-2 bg-[#12161A]">
            <div className="flex items-center gap-2">
              <span className="rounded-[4px] bg-[#94A3B8] px-1.5 py-0.5 text-[9px] font-serif italic font-bold text-[#0F172A]">
                Критерии
              </span>
              <span className="text-xs font-semibold text-white">
                Параметры отбора площадок
              </span>
              <span className="hidden sm:inline text-[11px] text-[#8E95A0]">
                · Ручная калибровка параметров поиска
              </span>
            </div>
            <button
              type="button"
              disabled={isMatching}
              onClick={onRematchWithOverride}
              className="group relative inline-flex items-center gap-1.5 rounded-[6px] border border-[#262D35] bg-[#161B21] px-2.5 py-1 text-xs font-medium text-[#D1D5DB] transition-all duration-200 select-none cursor-pointer overflow-hidden shadow-sm hover:bg-gradient-to-r hover:from-[#D4AF37] hover:via-[#E5C378] hover:to-[#D4AF37] hover:text-[#0E1215] hover:font-semibold hover:shadow-[0_0_12px_rgba(229,195,120,0.35)] disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <RotateCcw className="h-3 w-3 text-inherit transition-transform shrink-0" strokeWidth={2} />
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
                  min={0}
                  value={Math.round(editableProfile.total_budget_max)}
                  onChange={(e) => {
                    const val = Math.max(0, Number(e.target.value) || 0);
                    onUpdateProfile((prev) => ({ ...prev, total_budget_max: val }));
                  }}
                  className="h-7 w-full rounded-[4px] border border-[#262D35] bg-[#12161A] pl-2 pr-7 text-xs font-semibold text-white tabular-nums focus:border-[#38BDF8] focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                />
                <div className="absolute right-1 flex flex-col">
                  <button
                    type="button"
                    onClick={() =>
                      onUpdateProfile((p) => ({
                        ...p,
                        total_budget_max: p.total_budget_max + 50000,
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
                        total_budget_max: Math.max(0, p.total_budget_max - 50000),
                      }))
                    }
                    className="h-3 w-4 flex items-center justify-center text-[#8E95A0] hover:text-[#E5C378] transition-colors"
                    title="Уменьшить на 50 000 ₽"
                  >
                    <ChevronDown className="h-2.5 w-2.5" />
                  </button>
                </div>
              </div>
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
            <div className="p-3 bg-[#161B22]">
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
                    className="h-3 w-3 rounded accent-[#38BDF8]"
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
                        "rounded-[4px] border px-1.5 py-0.5 text-[11px] transition-colors",
                        active
                          ? "border-[#38BDF8] bg-[#121E2C] text-[#60A5FA] font-medium"
                          : "border-[#262D35] bg-[#12161A] text-[#8E95A0] hover:bg-[#1A2128] hover:text-white"
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
                      className="inline-flex items-center gap-1 rounded-[4px] border border-[#38BDF8] bg-[#121E2C] px-1.5 py-0.5 text-[11px] font-medium text-[#60A5FA]"
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
                  className="h-6 w-full rounded-[4px] border border-[#262D35] bg-[#12161A] px-1.5 text-[11px] text-white placeholder:text-[#6B7280] focus:border-[#38BDF8] focus:outline-none"
                />
              </form>
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
                    className="h-6 rounded-[4px] border border-[#262D35] bg-[#12161A] px-1.5 text-[11px] text-white tabular-nums focus:border-[#38BDF8] focus:outline-none"
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
                    className="h-6 rounded-[4px] border border-[#262D35] bg-[#12161A] px-1.5 text-[11px] text-white tabular-nums focus:border-[#38BDF8] focus:outline-none"
                  />
                </div>
              </div>
            </div>

            {/* Ячейка 4: Роли участия и спикерство */}
            <div className="p-3 bg-[#161B22]">
              <span className="block font-serif italic uppercase text-[10px] font-semibold tracking-wider text-[#8E95A0]">
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
                        "rounded-[4px] border px-1.5 py-0.5 text-[11px] transition-colors",
                        active
                          ? "border-[#E5C378] bg-[#261E0F] text-[#E5C378] font-medium"
                          : "border-[#262D35] bg-[#12161A] text-[#8E95A0] hover:bg-[#1A2128] hover:text-white"
                      )}
                    >
                      {ROLE_BADGE_LABELS[role]}
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

            {/* Ячейка 5: Отраслевые темы и ЦА */}
            <div className="p-3 bg-[#161B22]">
              <span className="block font-serif italic uppercase text-[10px] font-semibold tracking-wider text-[#8E95A0]">
                5. Темы, продукт и ЦА
              </span>
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
                      className="text-[#8E95A0] hover:text-[#EF4444]"
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
                  className="h-6 flex-1 rounded-[4px] border border-[#262D35] bg-[#12161A] px-1.5 text-[11px] text-white placeholder:text-[#6B7280] focus:border-[#38BDF8] focus:outline-none"
                />
                <button
                  type="submit"
                  className="flex h-6 w-6 shrink-0 items-center justify-center rounded-[4px] border border-[#262D35] bg-[#12161A] text-[#8E95A0] hover:border-[#38BDF8] hover:text-white"
                >
                  <Plus className="h-3 w-3" />
                </button>
              </form>
            </div>
          </div>

          <div className="border-t border-[#21262F] bg-[#12161A] px-4 py-2 flex items-center justify-end text-[11px] text-[#8E95A0]">
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

