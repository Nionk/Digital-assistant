import * as React from "react";
import { Search, X, Check, ChevronDown, Plus } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { cn } from "@/lib/utils";

export interface MultiSelectOption {
  value: string;
  label: string;
  count?: number;
}

export interface SearchableMultiSelectPopoverProps {
  label: string;
  placeholder?: string;
  options: MultiSelectOption[];
  selectedValues: string[];
  onChange: (values: string[]) => void;
  allowCustomCreation?: boolean;
  onCreateCustom?: (newValue: string) => void;
  align?: "left" | "right";
  triggerClassName?: string;
  popoverClassName?: string;
  popoverWidthClass?: string;
  allSelectedLabel?: string;
  emptyMessage?: string;
  renderTriggerContent?: (props: {
    selectedValues: string[];
    options: MultiSelectOption[];
    isOpen: boolean;
  }) => React.ReactNode;
}

/**
 * Выдвижная панель с живым поиском и мультивыбором:
 * - Позволяет пролистывать все варианты и одновременно фильтровать поиском.
 * - Показывает выбранные варианты прямо в шапке окна в виде чипсов с крестиками.
 * - Позволяет выбирать варианты кликом без закрытия окна.
 * - Опционально позволяет добавлять свои кастомные метки.
 */
export function SearchableMultiSelectPopover({
  label,
  placeholder = "Поиск...",
  options,
  selectedValues,
  onChange,
  allowCustomCreation = false,
  onCreateCustom,
  align = "left",
  triggerClassName,
  popoverClassName,
  popoverWidthClass = "w-80",
  allSelectedLabel = "Все",
  emptyMessage = "Ничего не найдено",
  renderTriggerContent,
}: SearchableMultiSelectPopoverProps) {
  const [isOpen, setIsOpen] = React.useState(false);
  const [searchQuery, setSearchQuery] = React.useState("");
  const containerRef = React.useRef<HTMLDivElement>(null);
  const searchInputRef = React.useRef<HTMLInputElement>(null);

  // Карта значений для быстрого поиска меток
  const optionMap = React.useMemo(() => {
    const map = new Map<string, MultiSelectOption>();
    for (const opt of options) {
      map.set(opt.value, opt);
    }
    return map;
  }, [options]);

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

  // Автофокус на поле поиска при открытии
  React.useEffect(() => {
    if (isOpen) {
      setTimeout(() => {
        searchInputRef.current?.focus();
      }, 50);
    } else {
      setSearchQuery("");
    }
  }, [isOpen]);

  const toggleValue = (val: string) => {
    if (selectedValues.includes(val)) {
      onChange(selectedValues.filter((v) => v !== val));
    } else {
      onChange([...selectedValues, val]);
    }
  };

  const removeValue = (val: string) => {
    onChange(selectedValues.filter((v) => v !== val));
  };

  const clearAll = () => {
    onChange([]);
  };

  const handleCreateCustom = () => {
    const trimmed = searchQuery.trim();
    if (!trimmed) return;
    if (onCreateCustom) {
      onCreateCustom(trimmed);
    } else if (!selectedValues.includes(trimmed)) {
      onChange([...selectedValues, trimmed]);
    }
    setSearchQuery("");
  };

  // Фильтрация опций по поисковому запросу
  const filteredOptions = React.useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return options;
    return options.filter(
      (opt) =>
        opt.label.toLowerCase().includes(q) ||
        opt.value.toLowerCase().includes(q)
    );
  }, [options, searchQuery]);

  const canCreateNew =
    allowCustomCreation &&
    searchQuery.trim().length > 0 &&
    !options.some(
      (o) => o.label.toLowerCase() === searchQuery.trim().toLowerCase()
    ) &&
    !selectedValues.some(
      (v) => v.toLowerCase() === searchQuery.trim().toLowerCase()
    );

  // Формирование текста триггера по умолчанию
  const defaultTriggerText = React.useMemo(() => {
    if (selectedValues.length === 0) {
      return `${label}: ${allSelectedLabel}`;
    }
    if (selectedValues.length === 1) {
      const first = optionMap.get(selectedValues[0])?.label || selectedValues[0];
      return `${label}: ${first}`;
    }
    const first = optionMap.get(selectedValues[0])?.label || selectedValues[0];
    return `${label} (${selectedValues.length}): ${first}, ...`;
  }, [label, allSelectedLabel, selectedValues, optionMap]);

  return (
    <div ref={containerRef} className="relative inline-block text-left">
      {/* Кнопка-триггер */}
      {renderTriggerContent ? (
        <div onClick={() => setIsOpen((prev) => !prev)}>
          {renderTriggerContent({ selectedValues, options, isOpen })}
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setIsOpen((prev) => !prev)}
          className={cn(
            "flex h-7 items-center justify-between gap-1.5 rounded-[6px] border border-[#262D35] bg-[#12161A] px-2.5 py-1 text-xs font-medium text-[#D1D5DB] transition-all hover:border-[#E5C378] hover:text-[#E5C378]",
            isOpen && "border-[#E5C378] bg-[#161B21] text-[#E5C378] shadow-[0_0_8px_rgba(229,195,120,0.25)]",
            selectedValues.length > 0 && "border-[#7C5A20] text-[#E5C378] bg-[#161510]",
            triggerClassName
          )}
        >
          <span className="truncate max-w-[190px]">{defaultTriggerText}</span>
          <ChevronDown
            className={cn(
              "h-3.5 w-3.5 shrink-0 text-[#8E95A0] transition-transform duration-200",
              isOpen && "rotate-180 text-[#E5C378]"
            )}
            strokeWidth={1.75}
          />
        </button>
      )}

      {/* Выдвижная панель */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: -4, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -3, scale: 0.98 }}
            transition={{ duration: 0.15, ease: "easeOut" }}
            className={cn(
              "absolute z-50 mt-1.5 rounded-[8px] border border-[#7C5A20]/80 bg-[#12161A] shadow-[0_12px_32px_rgba(0,0,0,0.65)] backdrop-blur-md overflow-hidden flex flex-col",
              align === "right" ? "right-0" : "left-0",
              popoverWidthClass,
              popoverClassName
            )}
          >
            {/* 1. Поисковая строка */}
            <div className="p-2 border-b border-[#21262F] bg-[#161B22]/90">
              <div className="relative flex items-center">
                <Search className="absolute left-2.5 h-3.5 w-3.5 text-[#8E95A0]" />
                <input
                  ref={searchInputRef}
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder={placeholder}
                  className="h-7 w-full rounded-[4px] border border-[#262D35] bg-[#0E1215] pl-8 pr-7 text-xs text-white placeholder:text-[#6B7280] outline-none focus:border-[#E5C378] focus:shadow-[0_0_0_1px_rgba(229,195,120,0.25)] transition-colors"
                />
                {searchQuery && (
                  <button
                    type="button"
                    onClick={() => setSearchQuery("")}
                    className="absolute right-2 text-[#8E95A0] hover:text-white"
                  >
                    <X className="h-3 w-3" />
                  </button>
                )}
              </div>
            </div>

            {/* 2. Секция выбранных меток (чипсы с крестиками) */}
            {selectedValues.length > 0 && (
              <div className="px-2.5 py-1.5 border-b border-[#21262F] bg-[#161510]/80">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-serif italic text-[10px] text-[#8E95A0]">
                    Выбрано ({selectedValues.length}):
                  </span>
                  <button
                    type="button"
                    onClick={clearAll}
                    className="text-[10px] text-[#8E95A0] hover:text-[#EF4444] transition-colors"
                  >
                    Сбросить все
                  </button>
                </div>
                <div className="flex flex-wrap gap-1 max-h-20 overflow-y-auto scrollbar-thin py-0.5">
                  {selectedValues.map((val) => {
                    const opt = optionMap.get(val);
                    const title = opt ? opt.label : val;
                    return (
                      <span
                        key={val}
                        className="inline-flex items-center gap-1 rounded-[4px] border border-[#7C5A20]/50 bg-[#1E190E] px-1.5 py-0.5 text-[10px] font-medium text-[#E5C378]"
                      >
                        <span className="truncate max-w-[140px]">{title}</span>
                        <button
                          type="button"
                          onClick={() => removeValue(val)}
                          className="text-[#8E95A0] hover:text-[#EF4444] transition-colors"
                        >
                          <X className="h-2.5 w-2.5" />
                        </button>
                      </span>
                    );
                  })}
                </div>
              </div>
            )}

            {/* 3. Кнопка создания новой темы (если включено) */}
            {canCreateNew && (
              <div className="p-1.5 border-b border-[#21262F] bg-[#161E28]/60">
                <button
                  type="button"
                  onClick={handleCreateCustom}
                  className="flex w-full items-center gap-1.5 rounded-[4px] border border-dashed border-[#E5C378]/50 bg-[#1B232D] px-2 py-1 text-left text-xs text-[#E5C378] hover:border-[#E5C378] hover:bg-[#202936] transition-colors"
                >
                  <Plus className="h-3 w-3 shrink-0" />
                  <span className="truncate">
                    Добавить новую: <strong className="font-semibold text-white">«{searchQuery.trim()}»</strong>
                  </span>
                </button>
              </div>
            )}

            {/* 4. Прокручиваемый список доступных вариантов */}
            <div className="max-h-56 overflow-y-auto p-1 scrollbar-thin space-y-0.5">
              {filteredOptions.length === 0 && !canCreateNew ? (
                <div className="py-4 text-center text-xs text-[#6B7280]">
                  {emptyMessage}
                </div>
              ) : (
                filteredOptions.map((opt) => {
                  const isSelected = selectedValues.includes(opt.value);
                  return (
                    <div
                      key={opt.value}
                      onClick={() => toggleValue(opt.value)}
                      className={cn(
                        "flex items-center justify-between gap-2 rounded-[4px] px-2 py-1.5 text-xs cursor-pointer select-none transition-colors",
                        isSelected
                          ? "bg-[#1E190E] text-[#E5C378] font-medium"
                          : "text-[#D1D5DB] hover:bg-[#1E252E] hover:text-[#E5C378]"
                      )}
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        {/* Кастомный индикатор-чекбокс */}
                        <div
                          className={cn(
                            "flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-[3px] border transition-colors",
                            isSelected
                              ? "border-[#E5C378] bg-[#E5C378] text-[#0E1215]"
                              : "border-[#3A424D] bg-[#12161A]"
                          )}
                        >
                          {isSelected && <Check className="h-2.5 w-2.5 stroke-[3]" />}
                        </div>
                        <span className="truncate text-inherit">{opt.label}</span>
                      </div>

                      {opt.count !== undefined && (
                        <span
                          className={cn(
                            "shrink-0 font-serif italic text-[10px] tabular-nums",
                            isSelected ? "text-[#E5C378]/80" : "text-[#8E95A0]"
                          )}
                        >
                          {opt.count}
                        </span>
                      )}
                    </div>
                  );
                })
              )}
            </div>

            {/* 5. Подвал панели */}
            <div className="border-t border-[#21262F] bg-[#12161A] px-2.5 py-1.5 flex items-center justify-between text-[10px] text-[#8E95A0]">
              <span className="font-serif italic text-[#727985]">
                Esc для закрытия
              </span>
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                className="rounded-[4px] border border-[#262D35] bg-[#161B21] px-2.5 py-0.5 text-xs font-serif italic text-[#E5C378] hover:border-[#E5C378] hover:bg-[#201B11] hover:text-white transition-colors"
              >
                Готово
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
