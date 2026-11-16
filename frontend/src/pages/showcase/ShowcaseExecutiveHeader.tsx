import * as React from "react";
import { Layers, Check, Mail, Copy, ArrowDown } from "lucide-react";
import type { ShowcaseViewOut } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { copyTextToClipboard } from "@/lib/clipboard";
import { formatDateShort, formatRub, pluralizeRu } from "@/lib/formatters";
import logoImage from "@/assets/images/logo.png";

interface ShowcaseExecutiveHeaderProps {
  showcase: ShowcaseViewOut;
}

export function ShowcaseExecutiveHeader({
  showcase,
}: ShowcaseExecutiveHeaderProps) {
  const [emailCopied, setEmailCopied] = React.useState(false);
  const copyTimerRef = React.useRef<number | null>(null);

  React.useEffect(() => {
    return () => {
      if (copyTimerRef.current !== null) {
        window.clearTimeout(copyTimerRef.current);
      }
    };
  }, []);

  const handleCopyManagerEmail = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!showcase.manager_email) return;
    const ok = await copyTextToClipboard(showcase.manager_email, {
      successMessage: "Email куратора скопирован в буфер обмена",
    });
    if (!ok) return;
    setEmailCopied(true);
    if (copyTimerRef.current !== null) {
      window.clearTimeout(copyTimerRef.current);
    }
    copyTimerRef.current = window.setTimeout(() => {
      setEmailCopied(false);
      copyTimerRef.current = null;
    }, 2000);
  };

  const approvedItems = showcase.items.filter(
    (i) => i.client_reaction === "interested"
  );
  const approvedCount = approvedItems.length;
  const approvedOnRequestCount = approvedItems.filter(
    (item) => item.actual_price === null
  ).length;
  const approvedTotalPrice = approvedItems.reduce((acc, item) => {
    if (item.actual_price === null) return acc;
    return acc + item.actual_price;
  }, 0);
  const approvedOnlyOnRequest =
    approvedCount > 0 && approvedOnRequestCount === approvedCount;

  const onRequestCount = showcase.items.filter(
    (item) => item.actual_price === null
  ).length;
  const onlyOnRequest =
    onRequestCount > 0 &&
    onRequestCount === showcase.items.length &&
    showcase.total_actual_price === 0;

  const totalBasePrice = showcase.items.reduce((acc, item) => {
    if (item.actual_price === null) return acc;
    return acc + (item.base_price ?? item.actual_price);
  }, 0);

  // Извлекаем чистое имя куратора и инициалы для персонального бейджа
  const rawName = showcase.manager_full_name || "Анна Соколова";
  const parenIndex = rawName.indexOf("(");
  const cleanName = (
    parenIndex !== -1 ? rawName.slice(0, parenIndex) : rawName
  ).trim();
  const initials =
    cleanName
      .split(/\s+/)
      .slice(0, 2)
      .map((word) => word[0]?.toUpperCase() || "")
      .join("") || "АС";

  return (
    <header className="relative border-b border-[#1A2026] bg-[#0E1215]/95 backdrop-blur-md text-white">
      {/* Деликатная бронзово-золотая нить переплёта внизу хедера */}
      <div className="pointer-events-none absolute bottom-0 left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-[#7C5A20]/35 to-transparent" />

      {/* Верхняя навигационная полоса: Логотип слева + Персональный куратор справа */}
      <div className="mx-auto flex h-[67px] max-w-7xl items-center justify-between gap-3 border-b border-[#1A2026] px-4 sm:px-6">
        <div className="flex items-center">
          <img
            src={logoImage}
            alt="EXEDRA"
            className="h-8 sm:h-[34px] w-auto object-contain shrink-0"
          />
        </div>

        {/* Персональная карточка куратора, работающего с клиентом */}
        <div className="flex items-center gap-2.5 rounded-[8px] border border-[#262D35] bg-[#12161A] px-3 py-1.5 shadow-sm">
          <div className="relative flex h-7 w-7 shrink-0 items-center justify-center rounded-[6px] border border-[#7C5A20]/60 bg-[#161B21] text-[11px] font-bold text-[#E5C378] tabular-nums">
            {initials}
            <span
              className="absolute -bottom-0.5 -right-0.5 h-2 w-2 rounded-full bg-[#34D399] ring-2 ring-[#12161A]"
              title="На связи"
            />
          </div>
          <div className="text-left leading-tight">
            <span className="block font-serif italic text-[11px] text-[#8E95A0]">
              С вами работает персональный куратор
            </span>
            <span className="mt-0.5 block text-xs font-semibold text-white">
              {cleanName}
            </span>
            {showcase.manager_email && (
              <div className="mt-0.5 flex items-center gap-1.5">
                <a
                  href={`mailto:${showcase.manager_email}`}
                  title={`Написать куратору на ${showcase.manager_email}`}
                  className="inline-flex items-center gap-1 text-[11px] text-[#E5C378] transition-colors hover:text-white hover:underline underline-offset-2"
                >
                  <Mail className="h-3 w-3 shrink-0" strokeWidth={1.75} />
                  <span>{showcase.manager_email}</span>
                </a>
                <button
                  type="button"
                  onClick={handleCopyManagerEmail}
                  title="Скопировать email куратора"
                  aria-label="Скопировать email куратора"
                  className="inline-flex h-4 w-4 items-center justify-center rounded text-[#8E95A0] transition-colors hover:text-[#E5C378] cursor-pointer"
                >
                  {emailCopied ? (
                    <Check className="h-3 w-3 text-[#34D399]" strokeWidth={2.25} />
                  ) : (
                    <Copy className="h-2.5 w-2.5" strokeWidth={1.75} />
                  )}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Основной двухколоночный блок: План участия и Сводный бюджет */}
      <div className="mx-auto max-w-7xl px-4 py-5 sm:px-6">
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-12 items-stretch">
          {/* Левая колонка (7 из 12): План участия и обращение куратора */}
          <div className="flex flex-col justify-between rounded-[12px] border border-[#262D35] bg-[#161B22] p-5 sm:p-6 lg:col-span-7 shadow-sm">
            <div className="flex flex-col h-full">
              <div>
                <span className="font-serif italic text-xs font-semibold tracking-wide text-[#E5C378]">
                  Подготовлено для {showcase.company_name}
                </span>
                <h1 className="mt-1 font-serif text-xl font-bold tracking-tight text-white sm:text-2xl leading-snug">
                  План участия в профильных мероприятиях
                </h1>
              </div>

              {/* Текст сопроводительного письма от куратора */}
              <div className="mt-4 flex-1 rounded-[8px] border border-[#262D35] border-l-2 border-l-[#E5C378] bg-[#12161A] p-4 shadow-inner">
                <p className="whitespace-pre-line text-xs sm:text-[13px] leading-relaxed text-[#D1D5DB] font-sans">
                  {showcase.pitch_text}
                </p>
              </div>
            </div>
          </div>

          {/* Правая колонка (5 из 12): Сводный бюджет участия (в стиле панели менеджера) */}
          <div className="flex flex-col gap-3.5 rounded-[12px] border border-[#262D35] bg-[#161B22] p-5 text-white shadow-sm sm:p-6 lg:col-span-5">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#21262F] pb-3">
              <div>
                <span className="font-serif italic font-semibold text-xs tracking-wide text-[#E5C378]">
                  Сводный бюджет участия
                </span>
                <h2 className="mt-0.5 font-serif text-base font-semibold text-white">
                  {showcase.company_name}
                </h2>
              </div>

              {/* Интуитивные счетчики площадок (как в кабинете менеджера) */}
              <div className="flex items-center gap-2">
                <div className="inline-flex items-center gap-1.5 rounded-[6px] border border-[#262D35] bg-[#12161A] px-2.5 py-1 select-none">
                  <Layers
                    className="h-3.5 w-3.5 text-[#E5C378] shrink-0"
                    strokeWidth={1.5}
                  />
                  <span className="font-serif italic text-[11px] leading-none text-[#8E95A0]">
                    Площадок:
                  </span>
                  <span className="inline-flex min-w-[22px] h-[18px] items-center justify-center rounded-[4px] bg-[#1E252E] px-1.5 font-sans font-bold text-xs text-white tabular-nums leading-none">
                    {showcase.total_events_count}
                  </span>
                </div>

                {approvedCount > 0 && (
                  <div className="inline-flex items-center gap-1.5 rounded-[6px] border border-[#1E5241] bg-[#0E241E] px-2.5 py-1 select-none">
                    <Check
                      className="h-3 w-3 text-[#34D399] shrink-0"
                      strokeWidth={2.25}
                    />
                    <span className="font-serif italic text-[11px] leading-none text-[#A7F3D0]">
                      В плане:
                    </span>
                    <span className="inline-flex min-w-[22px] h-[18px] items-center justify-center rounded-[4px] bg-[#14352B] px-1.5 font-sans font-bold text-xs text-[#34D399] tabular-nums leading-none">
                      {approvedCount}
                    </span>
                  </div>
                )}
              </div>
            </div>

            {/* Сумма организационных взносов и выгода */}
            <div className="flex-1 flex flex-col justify-center gap-3">
              <div>
                <div className="flex items-baseline justify-between text-xs text-[#8E95A0]">
                  <span>Организационные взносы площадок:</span>
                  {showcase.total_savings > 0 &&
                    totalBasePrice > showcase.total_actual_price && (
                      <span className="text-[#8E95A0] line-through tabular-nums">
                        {formatRub(totalBasePrice)}
                      </span>
                    )}
                </div>

                <div className="mt-1 flex flex-wrap items-baseline gap-2.5 tabular-nums">
                  {onlyOnRequest ? (
                    <span className="text-2xl sm:text-3xl font-bold tracking-tight text-white">
                      По запросу
                    </span>
                  ) : (
                    <>
                      <span className="text-2xl sm:text-3xl font-bold tracking-tight text-white">
                        {formatRub(showcase.total_actual_price)}
                      </span>
                      <span className="text-xs text-[#8E95A0]">с НДС</span>
                    </>
                  )}

                  {onRequestCount > 0 && (
                    <Badge variant="ebAmber" asSlanted={false} className="text-[11px]">
                      + {onRequestCount}{" "}
                      {pluralizeRu(onRequestCount, [
                        "спецпроект",
                        "спецпроекта",
                        "спецпроектов",
                      ])}{" "}
                      по запросу
                    </Badge>
                  )}
                </div>

                {approvedCount > 0 && (
                  <div className="mt-2.5 flex flex-wrap items-center justify-between gap-2 rounded-[8px] border border-[#1E5241]/80 bg-[#0E241E]/75 px-3 py-2 text-xs tabular-nums">
                    <div className="flex items-center gap-1.5 text-[#A7F3D0]">
                      <Check
                        className="h-3.5 w-3.5 shrink-0 text-[#34D399]"
                        strokeWidth={2.25}
                      />
                      <span className="font-serif italic">В плане клиента:</span>
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5 font-semibold text-white">
                      {approvedOnlyOnRequest ? (
                        <span className="text-[#E5C378]">
                          {approvedOnRequestCount} по запросу
                        </span>
                      ) : (
                        <>
                          <span>{formatRub(approvedTotalPrice)}</span>
                          {approvedOnRequestCount > 0 && (
                            <span className="text-[11px] font-medium text-[#E5C378]">
                              + {approvedOnRequestCount} по запросу
                            </span>
                          )}
                        </>
                      )}
                    </div>
                  </div>
                )}
              </div>

              {/* Выгода по спецтарифам Early Bird */}
              {showcase.total_savings > 0 && (
                <div className="rounded-[8px] border border-[#1E5241] bg-[#0E241E]/90 p-3">
                  <div className="flex items-center justify-between gap-2 tabular-nums">
                    <span className="font-serif italic text-xs font-semibold text-[#D1D5DB]">
                      Выгода по спецтарифам:
                    </span>
                    <Badge variant="ebEmerald" asSlanted={false} className="text-[11px]">
                      −{formatRub(showcase.total_savings)}
                    </Badge>
                  </div>
                  {showcase.min_early_bird_deadline && (
                    <p className="mt-1.5 text-[11px] text-[#8E95A0] tabular-nums">
                      Фиксация льготных условий при бронировании до{" "}
                      <strong className="font-semibold text-white">
                        {formatDateShort(showcase.min_early_bird_deadline)}
                      </strong>
                    </p>
                  )}
                </div>
              )}
            </div>

            {/* Нижняя сноска и быстрый переход к выбору площадок */}
            <div className="border-t border-[#21262F] pt-3 flex flex-col gap-2.5 sm:flex-row sm:items-end sm:justify-between">
              <p className="text-[11px] leading-relaxed text-[#8E95A0]">
                Расчет включает официальные взносы организаторов. Опции подготовки спикера и стенда выбираются индивидуально на карточках.
              </p>

              {showcase.items.length > 0 && (
                <a
                  href="#showcase-events"
                  onClick={(e) => {
                    e.preventDefault();
                    document
                      .getElementById("showcase-events")
                      ?.scrollIntoView({ behavior: "smooth", block: "start" });
                  }}
                  className="inline-flex shrink-0 items-center justify-center gap-1.5 rounded-[7px] border border-[#7C5A20]/70 bg-[#1E190E] px-3 py-1.5 text-xs font-semibold text-[#E5C378] transition-colors hover:border-[#E5C378] hover:bg-[#261E0F] hover:text-white whitespace-nowrap tabular-nums"
                >
                  <span>К мероприятиям ({showcase.items.length})</span>
                  <ArrowDown className="h-3.5 w-3.5 shrink-0" strokeWidth={2} />
                </a>
              )}
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}
