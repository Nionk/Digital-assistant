import { AGENCY_SERVICES_STAGE_09 } from "@/lib/formatters";

export const ACCOMPANIMENT_PREFIX_RE =
  /^(?:Сопровождение агентства \(Этап 09\)|Опции сопровождения):\s*(.+)$/i;

const KNOWN_STAGE_09_TAGS = new Set<string>(
  AGENCY_SERVICES_STAGE_09.map((srv) => srv.shortTag)
);

export interface ParsedClientComment {
  freeNote: string;
  parsedServices: string[];
}

/**
 * Разбирает комментарий клиента на свободный текст и теги услуг сопровождения (Этап 09).
 */
export function parseClientComment(
  raw: string | null | undefined
): ParsedClientComment {
  if (!raw) return { freeNote: "", parsedServices: [] };
  const freeLines: string[] = [];
  const parsedServices: string[] = [];

  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    const match = trimmed.match(ACCOMPANIMENT_PREFIX_RE);
    if (match) {
      const rawTags = match[1]
        .split(/[;,]\s*/)
        .map((s) => s.trim())
        .filter(Boolean);
      for (const tok of rawTags) {
        const canonicalTag = KNOWN_STAGE_09_TAGS.has(tok) ? tok : tok;
        if (!parsedServices.includes(canonicalTag)) {
          parsedServices.push(canonicalTag);
        }
      }
    } else if (!/^Участие по базовому тарифу$/i.test(trimmed)) {
      freeLines.push(trimmed);
    }
  }

  return {
    freeNote: freeLines.join("\n"),
    parsedServices,
  };
}

/**
 * Сериализует выбранные услуги сопровождения и текстовый комментарий для сохранения реакции клиента.
 */
export function formatReactionComment(
  services: string[],
  freeNote?: string | null
): string | undefined {
  const parts: string[] = [];
  const cleanedNote = (freeNote || "").trim();
  if (cleanedNote) {
    parts.push(cleanedNote);
  }
  if (services.length > 0) {
    parts.push(`Опции сопровождения: ${services.join("; ")}`);
  }
  return parts.length > 0 ? parts.join("\n") : undefined;
}
