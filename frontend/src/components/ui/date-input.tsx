import * as React from "react";
import * as Popover from "@radix-ui/react-popover";
import { Calendar, ChevronLeft, ChevronRight, X } from "lucide-react";
import { cn } from "@/lib/utils";

const MONTHS_NOMINATIVE = [
  "Январь",
  "Февраль",
  "Март",
  "Апрель",
  "Май",
  "Июнь",
  "Июль",
  "Август",
  "Сентябрь",
  "Октябрь",
  "Ноябрь",
  "Декабрь",
] as const;

const WEEKDAYS_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"] as const;

const ISO_DATE_RE = /^(\d{4})-(\d{2})-(\d{2})$/;
const RU_DATE_RE = /^(\d{2})\.(\d{2})\.(\d{4})$/;

function isValidCalendarParts(year: number, month: number, day: number): boolean {
  if (year < 1900 || year > 2100 || month < 1 || month > 12 || day < 1 || day > 31) {
    return false;
  }
  const probe = new Date(year, month - 1, day);
  return (
    probe.getFullYear() === year &&
    probe.getMonth() === month - 1 &&
    probe.getDate() === day
  );
}

function toIsoDate(year: number, month: number, day: number): string {
  const y = String(year).padStart(4, "0");
  const m = String(month).padStart(2, "0");
  const d = String(day).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function parseIsoParts(iso: string): { year: number; month: number; day: number } | null {
  const match = ISO_DATE_RE.exec(iso.trim());
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  if (!isValidCalendarParts(year, month, day)) return null;
  return { year, month, day };
}

function formatIsoToRu(iso: string): string {
  const parts = parseIsoParts(iso);
  if (!parts) return "";
  return `${String(parts.day).padStart(2, "0")}.${String(parts.month).padStart(2, "0")}.${String(parts.year).padStart(4, "0")}`;
}

function parseRuToIso(ruText: string): string | null {
  const match = RU_DATE_RE.exec(ruText.trim());
  if (!match) return null;
  const day = Number(match[1]);
  const month = Number(match[2]);
  const year = Number(match[3]);
  if (!isValidCalendarParts(year, month, day)) return null;
  return toIsoDate(year, month, day);
}

function formatDigitsForward(digits: string): string {
  const clean = digits.slice(0, 8);
  if (clean.length <= 2) return clean.length === 2 ? `${clean}.` : clean;
  if (clean.length <= 4) {
    const base = `${clean.slice(0, 2)}.${clean.slice(2)}`;
    return clean.length === 4 ? `${base}.` : base;
  }
  return `${clean.slice(0, 2)}.${clean.slice(2, 4)}.${clean.slice(4)}`;
}

function getTodayIso(): string {
  const now = new Date();
  return toIsoDate(now.getFullYear(), now.getMonth() + 1, now.getDate());
}

interface CalendarDayCell {
  iso: string;
  day: number;
  inCurrentMonth: boolean;
}

function buildCalendarGrid(viewYear: number, viewMonth: number): CalendarDayCell[] {
  const firstDayOfMonth = new Date(viewYear, viewMonth - 1, 1);
  // Преобразуем JS-день (0=Вс..6=Сб) к понедельнику первым (0=Пн..6=Вс)
  const leadingEmpty = (firstDayOfMonth.getDay() + 6) % 7;
  const gridStart = new Date(viewYear, viewMonth - 1, 1 - leadingEmpty);

  const cells: CalendarDayCell[] = [];
  for (let i = 0; i < 42; i++) {
    const cellDate = new Date(
      gridStart.getFullYear(),
      gridStart.getMonth(),
      gridStart.getDate() + i
    );
    const y = cellDate.getFullYear();
    const m = cellDate.getMonth() + 1;
    const d = cellDate.getDate();
    cells.push({
      iso: toIsoDate(y, m, d),
      day: d,
      inCurrentMonth: y === viewYear && m === viewMonth,
    });
  }
  return cells;
}

export interface DateInputProps {
  value: string;
  onChange: (value: string) => void;
  id?: string;
  name?: string;
  ariaLabel?: string;
  ariaInvalid?: boolean;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  inputClassName?: string;
  align?: "start" | "center" | "end";
}

/**
 * Переиспользуемый тёмный date-input + календарный popover в формате ДД.ММ.ГГГГ.
 * Наружу всегда принимает и отдаёт строгий ISO YYYY-MM-DD (или ""),
 * не зависит от локали браузера и поддерживает клавиатурный ввод и быструю очистку.
 */
export function DateInput({
  value,
  onChange,
  id,
  name,
  ariaLabel,
  ariaInvalid = false,
  placeholder = "ДД.ММ.ГГГГ",
  disabled = false,
  className,
  inputClassName,
  align = "start",
}: DateInputProps) {
  const [open, setOpen] = React.useState(false);
  const [text, setText] = React.useState(() => formatIsoToRu(value));

  const todayIso = React.useMemo(() => getTodayIso(), []);
  const initialParts = parseIsoParts(value) ?? parseIsoParts(todayIso)!;
  const [viewYear, setViewYear] = React.useState(initialParts.year);
  const [viewMonth, setViewMonth] = React.useState(initialParts.month);

  React.useEffect(() => {
    setText(formatIsoToRu(value));
    const parts = parseIsoParts(value);
    if (parts) {
      setViewYear(parts.year);
      setViewMonth(parts.month);
    }
  }, [value]);

  const handleOpenChange = (nextOpen: boolean) => {
    if (disabled) return;
    if (nextOpen) {
      const parts = parseIsoParts(value) ?? parseIsoParts(todayIso)!;
      setViewYear(parts.year);
      setViewMonth(parts.month);
    }
    setOpen(nextOpen);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const raw = e.target.value;
    if (raw.trim() === "") {
      setText("");
      if (value !== "") onChange("");
      return;
    }

    const isDeleting = raw.length < text.length;
    const nextText = isDeleting
      ? raw.replace(/[^\d.]/g, "").slice(0, 10)
      : formatDigitsForward(raw.replace(/\D/g, ""));

    setText(nextText);

    const parsedIso = parseRuToIso(nextText);
    if (parsedIso) {
      const parts = parseIsoParts(parsedIso);
      if (parts) {
        setViewYear(parts.year);
        setViewMonth(parts.month);
      }
      if (parsedIso !== value) {
        onChange(parsedIso);
      }
    }
  };

  const handleInputBlur = () => {
    const trimmed = text.trim();
    if (!trimmed) {
      if (value !== "") onChange("");
      setText("");
      return;
    }
    const parsedIso = parseRuToIso(trimmed);
    if (parsedIso) {
      setText(formatIsoToRu(parsedIso));
      if (parsedIso !== value) onChange(parsedIso);
    } else {
      setText(formatIsoToRu(value));
    }
  };

  const handleClear = (e: React.MouseEvent) => {
    e.stopPropagation();
    setText("");
    if (value !== "") onChange("");
  };

  const handleSelectDay = (iso: string) => {
    setText(formatIsoToRu(iso));
    onChange(iso);
    setOpen(false);
  };

  const shiftMonth = (delta: number) => {
    const shifted = new Date(viewYear, viewMonth - 1 + delta, 1);
    setViewYear(shifted.getFullYear());
    setViewMonth(shifted.getMonth() + 1);
  };

  const calendarCells = React.useMemo(
    () => buildCalendarGrid(viewYear, viewMonth),
    [viewYear, viewMonth]
  );

  const hasContent = text.length > 0 || value.length > 0;

  return (
    <Popover.Root open={open} onOpenChange={handleOpenChange}>
      <div className={cn("relative flex items-center", className)}>
        <input
          id={id}
          name={name}
          type="text"
          inputMode="numeric"
          autoComplete="off"
          disabled={disabled}
          value={text}
          onChange={handleInputChange}
          onBlur={handleInputBlur}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown" && (e.altKey || !open)) {
              e.preventDefault();
              handleOpenChange(true);
            }
          }}
          placeholder={placeholder}
          aria-label={ariaLabel}
          aria-invalid={ariaInvalid}
          maxLength={10}
          className={cn(
            "h-7 w-[124px] rounded-[4px] border bg-[#12161A] pl-2 text-[11px] text-white placeholder:text-[#8E95A0] tabular-nums outline-none transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-50",
            hasContent ? "pr-11" : "pr-7",
            ariaInvalid
              ? "border-[#EF4444] focus:border-[#EF4444]"
              : "border-[#262D35] focus:border-[#E5C378] focus:shadow-[0_0_0_1px_rgba(229,195,120,0.25)]",
            inputClassName
          )}
        />

        {hasContent && !disabled && (
          <button
            type="button"
            onClick={handleClear}
            aria-label="Очистить дату"
            title="Очистить дату"
            className="absolute right-6 flex h-4 w-4 items-center justify-center rounded text-[#8E95A0] transition-colors hover:text-[#EF4444] cursor-pointer"
          >
            <X className="h-3 w-3" strokeWidth={2} />
          </button>
        )}

        <Popover.Trigger asChild>
          <button
            type="button"
            disabled={disabled}
            aria-label="Открыть календарь"
            title="Выбрать дату в календаре"
            className={cn(
              "absolute right-1.5 flex h-5 w-5 items-center justify-center rounded text-[#E5C378]/85 transition-colors hover:text-[#E5C378] disabled:opacity-50 cursor-pointer",
              open && "text-[#E5C378]"
            )}
          >
            <Calendar className="h-3.5 w-3.5" strokeWidth={1.75} />
          </button>
        </Popover.Trigger>
      </div>

      <Popover.Portal>
        <Popover.Content
          align={align}
          sideOffset={6}
          collisionPadding={12}
          className="z-[10050] w-[264px] rounded-[8px] border border-[#7C5A20]/80 bg-[#12161A] p-3 text-white shadow-[0_18px_40px_rgba(0,0,0,0.85)] outline-none"
        >
          <div className="flex items-center justify-between gap-2 pb-2.5 border-b border-[#21262F]">
            <button
              type="button"
              onClick={() => shiftMonth(-1)}
              aria-label="Предыдущий месяц"
              className="flex h-6 w-6 items-center justify-center rounded-[4px] border border-[#262D35] bg-[#161B22] text-[#D1D5DB] transition-colors hover:border-[#E5C378] hover:text-[#E5C378] cursor-pointer"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
            </button>

            <span className="font-serif italic text-xs font-semibold text-[#E5C378] select-none">
              {MONTHS_NOMINATIVE[viewMonth - 1]} {viewYear}
            </span>

            <button
              type="button"
              onClick={() => shiftMonth(1)}
              aria-label="Следующий месяц"
              className="flex h-6 w-6 items-center justify-center rounded-[4px] border border-[#262D35] bg-[#161B22] text-[#D1D5DB] transition-colors hover:border-[#E5C378] hover:text-[#E5C378] cursor-pointer"
            >
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
          </div>

          <div className="mt-2 grid grid-cols-7 gap-1 text-center">
            {WEEKDAYS_SHORT.map((wd) => (
              <span
                key={wd}
                className="py-1 text-[11px] font-medium text-[#8E95A0] select-none"
              >
                {wd}
              </span>
            ))}

            {calendarCells.map((cell) => {
              const isSelected = cell.iso === value;
              const isToday = cell.iso === todayIso;
              return (
                <button
                  key={cell.iso}
                  type="button"
                  onClick={() => handleSelectDay(cell.iso)}
                  aria-label={formatIsoToRu(cell.iso)}
                  aria-pressed={isSelected}
                  className={cn(
                    "flex h-7 w-full items-center justify-center rounded-[4px] text-xs tabular-nums transition-colors cursor-pointer",
                    isSelected
                      ? "bg-[#E5C378] font-bold text-[#1A1405]"
                      : isToday
                        ? "border border-[#7C5A20] bg-[#1E190E] font-semibold text-[#E5C378] hover:border-[#E5C378]"
                        : cell.inCurrentMonth
                          ? "text-[#F3F4F6] hover:bg-[#1E252E] hover:text-[#E5C378]"
                          : "text-[#8E95A0]/55 hover:bg-[#161B22] hover:text-[#D1D5DB]"
                  )}
                >
                  {cell.day}
                </button>
              );
            })}
          </div>

          <div className="mt-2.5 flex items-center justify-between border-t border-[#21262F] pt-2">
            <button
              type="button"
              onClick={() => handleSelectDay(todayIso)}
              className="rounded-[4px] border border-[#262D35] bg-[#161B22] px-2 py-1 text-[11px] font-medium text-[#E5C378] transition-colors hover:border-[#E5C378] hover:bg-[#201B11] cursor-pointer"
            >
              Сегодня
            </button>
            <button
              type="button"
              onClick={() => {
                setText("");
                if (value !== "") onChange("");
                setOpen(false);
              }}
              className="rounded-[4px] px-2 py-1 text-[11px] font-medium text-[#8E95A0] transition-colors hover:text-[#EF4444] cursor-pointer"
            >
              Очистить
            </button>
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
