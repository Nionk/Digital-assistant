const EXACT_KEY_LABELS: Record<string, string> = {
  accreditation: "Порядок аккредитации и прохода",
  accreditation_badge_rules: "Правила аккредитации и выдачи бейджей",
  accreditation_rules: "Правила аккредитации и регистрации",
  cancellation_policy: "Условия отмены участия и возврата",
  dress_code: "Требования к дресс-коду",
  early_bird_deadline: "Дедлайн раннего бронирования (Early Bird)",
  early_bird_price: "Стоимость по спецтарифу Early Bird",
  early_bird_terms: "Условия раннего бронирования (Early Bird)",
  end_date: "Дата окончания мероприятия",
  event_format: "Формат мероприятия",
  exact_end_time: "Точное время окончания мероприятия",
  exact_speaker_time_limit: "Регламент времени выступления спикера",
  exact_start_time: "Точное время начала мероприятия",
  faq_cache: "Ответы по условиям Early Bird и требованиям к спикеру",
  full_program: "Полная программа мероприятия",
  "full_program.afternoon_sessions": "Расписание дневных сессий программы",
  full_regulation: "Подробный регламент мероприятия",
  "full_regulation.accreditation_rules": "Регламент: порядок аккредитации и прохода",
  "full_regulation.parking_and_transfer": "Регламент: парковка и трансфер",
  "full_regulation.speaker_technical_requirements":
    "Регламент: технические требования к спикерам",
  full_regulation_markdown: "Подробный регламент мероприятия",
  "full_regulation_markdown.accreditation":
    "Регламент: порядок аккредитации и прохода",
  "full_regulation_markdown.logistics_dress_code":
    "Регламент: логистика и дресс-код",
  "full_regulation_markdown.logistics_parking_catering_dresscode":
    "Регламент: парковка, питание и дресс-код",
  "full_regulation_markdown.logistics_parking_food_dress_code":
    "Регламент: парковка, питание и дресс-код",
  "full_regulation_markdown.program_sessions":
    "Регламент: программа деловых сессий",
  "full_regulation_markdown.return_policy":
    "Регламент: правила отмены и возврата",
  "full_regulation_markdown.speaker_requirements":
    "Регламент: требования к спикерам",
  is_vat_included: "Условия по НДС",
  logistics: "Логистика площадки",
  "logistics.parking_transfer_dresscode":
    "Логистика: парковка, трансфер и дресс-код",
  meal_details: "Информация о питании и кофе-брейках",
  parking_and_transfer_details: "Информация о парковке и трансфере",
  parking_details: "Информация о парковке",
  policy_registration_terms: "Условия регистрации и оплаты",
  program_schedule: "Подробное расписание программы",
  refund_policy: "Условия возврата и отмены",
  speaker_deadline_before_event: "Дедлайн подачи материалов спикером",
  speaker_presentation_deadline: "Дедлайн сдачи презентации спикера",
  speaker_presentation_format: "Требования к формату презентации спикера",
  speaker_requirements: "Требования к спикерам",
  speakers: "Состав и биографии спикеров",
  tariffs: "Тарифы и условия участия",
  "tariffs.base_price": "Базовая стоимость тарифов",
  "tariffs.early_bird_deadline": "Дедлайн раннего бронирования (Early Bird)",
  "tariffs.early_bird_price": "Стоимость по спецтарифу Early Bird",
  "tariffs.included_benefits": "Состав опций, включённых в тарифы",
  "tariffs.is_vat_included": "Условия по НДС в тарифах",
  "tariffs.participation_role": "Тарифы по ролям участия",
  "tariffs.sponsor.base_price": "Стоимость спонсорского тарифа",
  "tariffs.sponsor_price_missing": "Стоимость спонсорского тарифа",
  transfer_details: "Информация о трансфере",
  vat_terms: "Условия по НДС",
  venue: "Площадка проведения",
  "venue.exact_address": "Точный адрес площадки проведения",
  "venue.parking_details": "Информация о парковке на площадке",

  // Системные коды полноты карточки (ingestion.py)
  summary_too_short: "Неполное описание концепции мероприятия",
  regulation_markdown_too_short: "Недостаточно подробный регламент мероприятия",
  no_tariffs_extracted: "Не извлечены тарифы участия",
  missing_city_for_offline_event: "Не указан город для очного мероприятия",
  dossier_truncated_before_llm:
    "Исходный документ был сокращён при обработке — требуется проверка полноты",
  pdf_scanned_pages_not_recognized: "Часть страниц PDF-скана не распознана",
};

const PREFIX_SHORT_LABELS: Record<string, string> = {
  full_regulation_markdown: "Регламент",
  full_regulation: "Регламент",
  full_program: "Программа",
  tariffs: "Тарифы",
  logistics: "Логистика",
  venue: "Площадка проведения",
  speakers: "Спикеры",
  faq_cache: "Частые вопросы",
  event_format: "Формат мероприятия",
};

const TOKEN_LABELS: Record<string, string> = {
  accreditation: "аккредитация",
  afternoon: "дневные",
  base: "базовая",
  benefits: "опции",
  catering: "питание",
  deadline: "дедлайн",
  details: "детали",
  dress: "дресс",
  dresscode: "дресс-код",
  early_bird: "Early Bird",
  end: "окончания",
  exact: "точное",
  food: "питание",
  included: "включённые",
  logistics: "логистика",
  parking: "парковка",
  policy: "правила",
  price: "стоимость",
  program: "программа",
  refund: "возврат",
  requirements: "требования",
  return: "возврат",
  rules: "правила",
  schedule: "расписание",
  sessions: "сессии",
  speaker: "спикера",
  speakers: "спикеров",
  sponsor: "спонсора",
  start: "начала",
  technical: "технические",
  terms: "условия",
  time: "время",
  transfer: "трансфер",
  vat: "НДС",
};

function capitalizeFirst(text: string): string {
  if (!text) return "";
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function cleanClarificationText(rawClarification: string): string {
  const trimmed = rawClarification.trim();
  if (!trimmed) return "";
  // Смягчаем технические формулировки про значения БД/схем внутри скобок
  if (/проставлено\s+true\s+по\s+умолчанию/i.test(trimmed)) {
    return "не указано явно, требует подтверждения";
  }
  return trimmed.replace(/\s+/g, " ");
}

function humanizeTechnicalTokens(rawKey: string): string {
  const normalized = rawKey
    .replace(/\[\d+\.\.\d+\]/g, "")
    .replace(/\.\d+\b/g, "")
    .replace(/_markdown\b/g, "")
    .trim();

  const segments = normalized
    .split(/[._]+/)
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);

  if (segments.length === 0) return rawKey.trim();

  const translated = segments.map((seg) => TOKEN_LABELS[seg] ?? seg);
  return capitalizeFirst(translated.join(" "));
}

function lookupKeyLabel(key: string): string | null {
  const normalized = key.trim().toLowerCase().replace(/\[\d+\.\.\d+\]/g, "");
  return EXACT_KEY_LABELS[normalized] ?? null;
}

/**
 * Преобразует технический ключ/путь из missing_data_warnings в аккуратную русскую формулировку
 * без имён полей БД/JSON.
 */
export function humanizeMissingDataWarning(raw: string): string {
  const trimmed = raw.trim();
  if (!trimmed) return "";

  const exact = lookupKeyLabel(trimmed);
  if (exact) return exact;

  const low = trimmed.toLowerCase();

  // Специальные составные выражения с несколькими ключами или БД-примечаниями
  if (low === "early_bird_price и early_bird_deadline") {
    return "Стоимость и дедлайн спецтарифа Early Bird";
  }
  if (low.startsWith("exact_start_time / exact_end_time")) {
    return "Точное время начала и окончания мероприятия";
  }
  if (low.startsWith("is_vat_included")) {
    const rest = trimmed.slice("is_vat_included".length).trim();
    return rest ? `Условия по НДС ${rest}` : "Условия по НДС";
  }
  if (low.startsWith("event_format:")) {
    if (low.includes("выставка") || low.includes("exhibition")) {
      return "Формат мероприятия: в источнике указана выставка (в каталоге отображается как форум)";
    }
    const rest = trimmed.slice("event_format:".length).trim();
    return rest ? `Формат мероприятия: ${rest}` : "Формат мероприятия";
  }

  // Нумерованные разделы регламента вида "full_regulation_markdown.4 (технические требования...)"
  const numberedSectionMatch = trimmed.match(
    /^([a-z0-9_]+)\.\d+\s*\((.+)\)$/i
  );
  if (numberedSectionMatch) {
    const prefixKey = numberedSectionMatch[1].toLowerCase();
    const prefixLabel = PREFIX_SHORT_LABELS[prefixKey];
    const details = cleanClarificationText(numberedSectionMatch[2]);
    if (prefixLabel) {
      return `${prefixLabel}: ${details}`;
    }
    return capitalizeFirst(details);
  }

  // Путь/ключ + пояснение в скобках: "key.subkey (детали)" или "key (детали)"
  const parenMatch = trimmed.match(/^([a-z0-9_.[\]]+)\s*\((.+)\)$/i);
  if (parenMatch) {
    const keyPart = parenMatch[1].trim();
    const details = cleanClarificationText(parenMatch[2]);
    const keyLow = keyPart.toLowerCase();

    if (
      keyLow === "full_regulation_markdown" ||
      keyLow === "full_regulation"
    ) {
      return `Регламент: ${details}`;
    }
    const mappedKey = lookupKeyLabel(keyPart);
    if (mappedKey) {
      if (!details) return mappedKey;
      const baseLabel = mappedKey.replace(/\s*\(Early Bird\)$/i, "");
      return `${baseLabel} (${details})`;
    }
    const prefixLabel = PREFIX_SHORT_LABELS[keyLow];
    if (prefixLabel) {
      return `${prefixLabel}: ${details}`;
    }
    return `${humanizeTechnicalTokens(keyPart)} (${details})`;
  }

  // Префикс + разделитель (: или —) + описание: "full_regulation_markdown: ..." / "faq_cache: ..."
  const sepMatch = trimmed.match(/^([a-z0-9_.[\]]+)\s*(?::|—)\s*(.+)$/i);
  if (sepMatch) {
    const keyPart = sepMatch[1].trim();
    const keyLow = keyPart.toLowerCase();
    let rest = sepMatch[2].trim();

    if (keyLow === "full_regulation_markdown" || keyLow === "full_regulation") {
      rest = rest.replace(/^детальные\s+разделы\s*:\s*/i, "");
      return `Регламент: ${rest}`;
    }
    if (keyLow === "faq_cache") {
      rest = rest.replace(/\s*—\s*нет исходных данных.*$/i, " — нет данных в источнике");
      return capitalizeFirst(rest);
    }
    const prefixLabel =
      PREFIX_SHORT_LABELS[keyLow] ?? lookupKeyLabel(keyPart);
    if (prefixLabel) {
      return `${prefixLabel}: ${rest}`;
    }
    return `${humanizeTechnicalTokens(keyPart)}: ${rest}`;
  }

  // Префикс с пробельным русским продолжением: "tariffs для ...", "tariffs[0..1].participation_role для ..."
  const spaceKeyMatch = trimmed.match(/^([a-z0-9_.[\]]+)\s+(.+)$/i);
  if (spaceKeyMatch && /[a-z]_[a-z]|^[a-z]+\.|^tariffs/i.test(spaceKeyMatch[1])) {
    const keyPart = spaceKeyMatch[1].trim();
    const rest = spaceKeyMatch[2].trim();
    const mapped = lookupKeyLabel(keyPart);
    if (mapped) {
      if (keyPart.toLowerCase().startsWith("tariffs")) {
        return `Тарифы ${rest}`;
      }
      return `${mapped} ${rest}`;
    }
    return `${humanizeTechnicalTokens(keyPart)} ${rest}`;
  }

  // Неизвестный snake_case / dot-path ключ
  if (/^[a-z0-9_.[\]]+$/i.test(trimmed) && (trimmed.includes("_") || trimmed.includes("."))) {
    return humanizeTechnicalTokens(trimmed);
  }

  // Обычная русская фраза без технических префиксов
  return capitalizeFirst(trimmed);
}

/**
 * Нормализует массив предупреждений с удалением пустых значений и дубликатов.
 */
export function humanizeMissingDataWarnings(
  warnings: readonly string[] | null | undefined
): string[] {
  if (!warnings || warnings.length === 0) return [];
  const seen = new Set<string>();
  const result: string[] = [];
  for (const w of warnings) {
    const label = humanizeMissingDataWarning(w);
    if (!label) continue;
    const dedupKey = label.toLowerCase();
    if (!seen.has(dedupKey)) {
      seen.add(dedupKey);
      result.push(label);
    }
  }
  return result;
}
