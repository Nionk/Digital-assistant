import * as React from "react";
import { ChevronDown } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { cn } from "@/lib/utils";

export interface CustomSelectOption<T extends number | string = number | string> {
  value: T;
  label: string;
  subLabel?: string;
}

interface CustomSelectProps<T extends number | string = number | string> {
  value: T;
  onChange: (val: T) => void;
  options: CustomSelectOption<T>[];
  placeholder?: string;
  className?: string;
  buttonClassName?: string;
  menuClassName?: string;
  disabled?: boolean;
}

export function CustomSelect<T extends number | string = number | string>({
  value,
  onChange,
  options,
  placeholder = "Выберите значение...",
  className,
  buttonClassName,
  menuClassName,
  disabled = false,
}: CustomSelectProps<T>) {
  const [isOpen, setIsOpen] = React.useState(false);
  const [highlightedIndex, setHighlightedIndex] = React.useState<number>(-1);
  const containerRef = React.useRef<HTMLDivElement>(null);
  const buttonRef = React.useRef<HTMLButtonElement>(null);
  const optionRefs = React.useRef<(HTMLDivElement | null)[]>([]);
  const listboxId = React.useId();

  const selectedIndex = options.findIndex((o) => o.value === value);
  const selectedOption = selectedIndex >= 0 ? options[selectedIndex] : undefined;

  // Закрытие при клике снаружи
  React.useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    }
    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isOpen]);

  // Синхронизация подсвеченного индекса при открытии меню
  React.useEffect(() => {
    if (isOpen) {
      setHighlightedIndex(
        selectedIndex >= 0 ? selectedIndex : options.length > 0 ? 0 : -1
      );
    } else {
      setHighlightedIndex(-1);
    }
  }, [isOpen, selectedIndex, options.length]);

  // Прокрутка активной опции в область видимости при навигации стрелками
  React.useEffect(() => {
    if (!isOpen || highlightedIndex < 0) return;
    optionRefs.current[highlightedIndex]?.scrollIntoView({ block: "nearest" });
  }, [isOpen, highlightedIndex]);

  // Закрытие по Escape (если кликнули вне фокуса кнопки)
  React.useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsOpen(false);
        buttonRef.current?.focus();
      }
    }
    if (isOpen) {
      document.addEventListener("keydown", handleKeyDown);
    }
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen]);

  const handleSelectOption = (optionValue: T) => {
    onChange(optionValue);
    setIsOpen(false);
    buttonRef.current?.focus();
  };

  const handleButtonKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>) => {
    if (disabled || options.length === 0) return;

    if (!isOpen) {
      if (
        event.key === "ArrowDown" ||
        event.key === "ArrowUp" ||
        event.key === "Enter" ||
        event.key === " "
      ) {
        event.preventDefault();
        setIsOpen(true);
      }
      return;
    }

    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        setHighlightedIndex((prev) =>
          prev < 0 ? 0 : (prev + 1) % options.length
        );
        break;
      case "ArrowUp":
        event.preventDefault();
        setHighlightedIndex((prev) =>
          prev <= 0 ? options.length - 1 : prev - 1
        );
        break;
      case "Home":
        event.preventDefault();
        setHighlightedIndex(0);
        break;
      case "End":
        event.preventDefault();
        setHighlightedIndex(options.length - 1);
        break;
      case "Enter":
      case " ":
        event.preventDefault();
        if (highlightedIndex >= 0 && options[highlightedIndex]) {
          handleSelectOption(options[highlightedIndex].value);
        }
        break;
      case "Escape":
        event.preventDefault();
        event.stopPropagation();
        setIsOpen(false);
        break;
      case "Tab":
        setIsOpen(false);
        break;
    }
  };

  return (
    <div ref={containerRef} className={cn("relative", className)}>
      <button
        ref={buttonRef}
        type="button"
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-controls={isOpen ? listboxId : undefined}
        aria-activedescendant={
          isOpen && highlightedIndex >= 0
            ? `${listboxId}-opt-${highlightedIndex}`
            : undefined
        }
        onClick={() => setIsOpen((prev) => !prev)}
        onKeyDown={handleButtonKeyDown}
        className={cn(
          "flex items-center justify-between gap-1.5 rounded-[6px] border border-[#262D35] bg-[#12161A] px-2 py-1 text-xs font-medium text-white tabular-nums select-none cursor-pointer outline-none transition-colors duration-150",
          "hover:border-[#E5C378] focus-visible:border-[#E5C378]",
          isOpen && "border-[#E5C378] shadow-[0_0_8px_rgba(229,195,120,0.25)]",
          disabled && "cursor-not-allowed opacity-50",
          buttonClassName
        )}
      >
        <span className="truncate">
          {selectedOption ? selectedOption.label : placeholder}
        </span>
        <ChevronDown
          className={cn(
            "h-3.5 w-3.5 shrink-0 text-[#8E95A0] transition-transform duration-200",
            isOpen && "rotate-180 text-[#E5C378]"
          )}
          strokeWidth={1.75}
        />
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            id={listboxId}
            role="listbox"
            aria-label={placeholder}
            initial={{ opacity: 0, y: -4, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -3, scale: 0.98 }}
            transition={{ duration: 0.12, ease: "easeOut" }}
            className={cn(
              "absolute left-0 z-50 mt-1 max-h-56 min-w-full overflow-y-auto rounded-[6px] border border-[#262D35] bg-[#12161A] p-1 shadow-2xl scrollbar-thin",
              menuClassName
            )}
          >
            {options.map((option, idx) => {
              const isSelected = option.value === value;
              const isHighlighted = idx === highlightedIndex;
              return (
                <div
                  key={String(option.value)}
                  ref={(el) => {
                    optionRefs.current[idx] = el;
                  }}
                  id={`${listboxId}-opt-${idx}`}
                  role="option"
                  aria-selected={isSelected}
                  onMouseEnter={() => setHighlightedIndex(idx)}
                  onClick={() => handleSelectOption(option.value)}
                  className={cn(
                    "flex items-center justify-between gap-2 rounded-[4px] px-2.5 py-1.5 text-xs font-medium cursor-pointer select-none transition-colors duration-100",
                    isSelected || isHighlighted
                      ? "bg-[#1E252E] text-[#E5C378]"
                      : "text-[#D1D5DB] hover:bg-[#1E252E] hover:text-[#E5C378]"
                  )}
                >
                  <span className="truncate text-inherit">
                    {option.label}
                  </span>
                  {option.subLabel && (
                    <span className="shrink-0 text-[10px] text-inherit opacity-80 tabular-nums">
                      {option.subLabel}
                    </span>
                  )}
                </div>
              );
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

