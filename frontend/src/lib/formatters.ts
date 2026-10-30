import type { EventFormat, ParticipationRole } from "@/api/types";

const MONTHS_GENITIVE = [
  "января",
  "февраля",
  "марта",
  "апреля",
  "мая",
  "июня",
  "июля",
  "августа",
  "сентября",
  "октября",
  "ноября",
  "декабря",
];

const MONTHS_SHORT_UPPER = [
  "ЯНВ",
  "ФЕВ",
  "МАР",
  "АПР",
  "МАЙ",
  "ИЮН",
  "ИЮЛ",
  "АВГ",
  "СЕН",
  "ОКТ",
  "НОЯ",
  "ДЕК",
];

const MONTHS_SHORT_LOWER = [
  "янв.",
  "фев.",
  "мар.",
  "апр.",
  "мая",
  "июн.",
  "июл.",
  "авг.",
  "сент.",
  "окт.",
  "нояб.",
  "дек.",
];

export const FORMAT_LABELS: Record<string, string> = {
  roundtable: "Круглый стол",
  business_breakfast: "Деловой завтрак",
  forum: "Отраслевой форум",
  conference: "Конференция",
  session: "Профильная сессия",
};

export const FORMAT_SHORT_LABELS: Record<string, string> = {
  roundtable: "Круглый стол · Камерный формат",
  business_breakfast: "Закрытый деловой завтрак",
  forum: "Форум и выставка",
  conference: "Конференция",
  session: "Экспертная сессия",
};

export const ROLE_LABELS: Record<ParticipationRole, string> = {
  speaker: "Участие спикером",
  delegate: "Участие делегатом",
  sponsor: "Партнёр / Стенд",
};

export const ROLE_BADGE_LABELS: Record<ParticipationRole, string> = {
  speaker: "Спикер",
  delegate: "Делегат",
  sponsor: "Партнёр / Стенд",
};

/**
 * Услуги сопровождения агентства (Шаг 09 схемы «ПУТЬ КЛИЕНТА» и Слайды 05–07).
 */
export const AGENCY_SERVICES_STAGE_09 = [
  {
    id: "speaker_prep",
    title: "Подготовка спикера и презентации",
    subtitle: "Согласование целевой сессии, ключевые смыслы, структура доклада и репетиция",
    shortTag: "Подготовка спикера и презентации",
  },
  {
    id: "b2b_matchmaking",
    title: "Организация целевых знакомств и встреч",
    subtitle: "Выход на ключевых игроков отрасли и подготовка графика личных встреч",
    shortTag: "Организация целевых встреч и знакомств",
  },
  {
    id: "booth_interactive",
    title: "Интерактивная программа / деловая игра",
    subtitle: "Механика вовлечения аудитории на стенде или в деловой зоне",
    shortTag: "Интерактив / деловая игра для площадки",
  },
] as const;

/**
 * Быстрые причины для запроса замены со смартфона в 1 касание (Шаг 07 «Правки»).
 */
export const REPLACEMENT_QUICK_REASONS = [
  "Не подходят даты проведения",
  "Нужна роль спикера в деловой программе",
  "Требуется более камерный закрытый формат",
  "Скорректировать стоимость участия",
] as const;

export function formatRub(amount: number | null | undefined): string {
  if (amount === null || amount === undefined) {
    return "По запросу";
  }
  if (amount === 0) {
    return "Бесплатно";
  }
  const rounded = Math.round(amount);
  return `${rounded.toString().replace(/\B(?=(\d{3})+(?!\d))/g, "\u00A0")}\u00A0₽`;
}

export function formatNumberCompact(amount: number): string {
  const rounded = Math.round(amount);
  return rounded.toString().replace(/\B(?=(\d{3})+(?!\d))/g, "\u00A0");
}

function parseIsoDate(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, (m || 1) - 1, d || 1);
}

export function formatDateShort(iso: string | null | undefined): string {
  if (!iso) return "—";
  const parts = iso.split("-");
  if (parts.length !== 3) return iso;
  return `${parts[2]}.${parts[1]}.${parts[0]}`;
}

export function formatDateRange(startIso: string, endIso: string): string {
  const start = parseIsoDate(startIso);
  const end = parseIsoDate(endIso);

  const sDay = start.getDate();
  const eDay = end.getDate();
  const sMonth = start.getMonth();
  const eMonth = end.getMonth();
  const sYear = start.getFullYear();

  if (startIso === endIso) {
    return `${sDay} ${MONTHS_GENITIVE[sMonth]} ${sYear}`;
  }
  if (sMonth === eMonth) {
    return `${sDay}–${eDay} ${MONTHS_GENITIVE[sMonth]} ${sYear}`;
  }
  return `${sDay} ${MONTHS_GENITIVE[sMonth]} – ${eDay} ${MONTHS_GENITIVE[eMonth]} ${sYear}`;
}

export function formatCalendarBadge(startIso: string, endIso: string): {
  dayText: string;
  monthText: string;
  monthShortLabel: string;
  durationText: string;
} {
  const start = parseIsoDate(startIso);
  const end = parseIsoDate(endIso);
  const sDay = start.getDate();
  const eDay = end.getDate();
  const monthText = MONTHS_SHORT_UPPER[start.getMonth()] || "НОЯ";
  const monthShortLabel = MONTHS_SHORT_LOWER[start.getMonth()] || "нояб.";

  const diffDays = Math.max(
    1,
    Math.round((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24)) + 1
  );

  const dayText =
    startIso === endIso || start.getMonth() !== end.getMonth()
      ? `${sDay}`
      : `${sDay}–${eDay}`;

  let durationText = `${diffDays} дн.`;
  if (diffDays === 1) durationText = "1 день";
  else if (diffDays >= 2 && diffDays <= 4) durationText = `${diffDays} дня`;
  else durationText = `${diffDays} дней`;

  return { dayText, monthText, monthShortLabel, durationText };
}

export function getDaysUntil(deadlineIso: string | null | undefined): number | null {
  if (!deadlineIso) return null;
  const target = parseIsoDate(deadlineIso);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.round((target.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
}

export interface DateSpanItem {
  event_id: number;
  canonical_title: string;
  start_date: string;
  end_date: string;
  is_online: boolean;
}

/**
 * Детерминированная проверка отсутствия пересечений дат между очными мероприятиями
 * (Слайд 02, 03, 04 и Шаг 06 «Календарь без накладок»).
 */
export function checkDateConflicts(items: DateSpanItem[]): {
  hasConflict: boolean;
  conflictDescription: string | null;
} {
  const offline = items.filter((i) => !i.is_online);
  for (let i = 0; i < offline.length; i++) {
    for (let j = i + 1; j < offline.length; j++) {
      const a = offline[i];
      const b = offline[j];
      if (a.start_date <= b.end_date && b.start_date <= a.end_date) {
        return {
          hasConflict: true,
          conflictDescription: `Пересечение дат: «${a.canonical_title}» и «${b.canonical_title}»`,
        };
      }
    }
  }
  return { hasConflict: false, conflictDescription: null };
}

export function getFormatLabel(fmt: EventFormat | string): string {
  return FORMAT_LABELS[fmt] || "Деловое мероприятие";
}

