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
  const containerRef = React.useRef<HTMLDivElement>(null);

  const selectedOption = options.find((o) => o.value === value);

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

  // Закрытие по Escape
  React.useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsOpen(false);
      }
    }
    if (isOpen) {
      document.addEventListener("keydown", handleKeyDown);
    }
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen]);

  return (
    <div ref={containerRef} className={cn("relative", className)}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setIsOpen((prev) => !prev)}
        className={cn(
          "flex items-center justify-between gap-1.5 rounded-[6px] border border-[#262D35] bg-[#12161A] px-2 py-1 text-xs font-medium text-white tabular-nums transition-all duration-150 ease-out select-none cursor-pointer",
          "hover:border-[#E5C378] focus:border-[#E5C378] focus:outline-none focus:ring-1 focus:ring-[#E5C378]/30",
          isOpen && "border-[#E5C378] ring-1 ring-[#E5C378]/30",
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
            initial={{ opacity: 0, y: -4, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -3, scale: 0.98 }}
            transition={{ duration: 0.12, ease: "easeOut" }}
            className={cn(
              "absolute left-0 z-50 mt-1 max-h-56 min-w-full overflow-y-auto rounded-[6px] border border-[#262D35] bg-[#12161A] p-1 shadow-2xl backdrop-blur-md scrollbar-thin",
              menuClassName
            )}
          >
            {options.map((option) => {
              const isSelected = option.value === value;
              return (
                <div
                  key={String(option.value)}
                  onClick={() => {
                    onChange(option.value);
                    setIsOpen(false);
                  }}
                  className={cn(
                    "group flex items-center justify-between gap-2 rounded-[4px] px-2.5 py-1.5 text-xs cursor-pointer select-none transition-colors duration-100",
                    // При наведении — сплошной золотой фон и чёрный текст
                    "hover:bg-[#E5C378] hover:text-[#0E1215] hover:font-semibold",
                    isSelected
                      ? "bg-[#1E252E] text-white font-medium"
                      : "text-[#D1D5DB]"
                  )}
                >
                  <span className="truncate group-hover:text-[#0E1215]">
                    {option.label}
                  </span>
                  {option.subLabel && (
                    <span className="shrink-0 text-[10px] text-[#8E95A0] group-hover:text-[#0E1215]/80 tabular-nums">
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

