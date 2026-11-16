import * as React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Check, ChevronDown } from "lucide-react";
import type { ShowcaseEventItemOut } from "@/api/types";
import { formatDateRange } from "@/lib/formatters";
import { cn } from "@/lib/utils";

interface EventSelectorDropdownProps {
  isDrawerOpen: boolean;
  events: ShowcaseEventItemOut[];
  activeEvent: ShowcaseEventItemOut;
  onSelectEvent: (eventId: number) => void;
}

/** Выпадающий переключатель мероприятий в шапке шторки ИИ-консультанта. */
export function EventSelectorDropdown({
  isDrawerOpen,
  events,
  activeEvent,
  onSelectEvent,
}: EventSelectorDropdownProps) {
  const [isEventSelectorOpen, setIsEventSelectorOpen] = React.useState(false);
  const selectorRef = React.useRef<HTMLDivElement>(null);

  // Закрытие кастомного выпадающего списка при клике вне
  React.useEffect(() => {
    if (!isEventSelectorOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (
        selectorRef.current &&
        !selectorRef.current.contains(e.target as Node)
      ) {
        setIsEventSelectorOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isEventSelectorOpen]);

  // Закрываем дропдаун при закрытии шторки
  React.useEffect(() => {
    if (!isDrawerOpen) setIsEventSelectorOpen(false);
  }, [isDrawerOpen]);

  return (
    <div className="relative" ref={selectorRef}>
      <button
        type="button"
        onClick={() => setIsEventSelectorOpen((prev) => !prev)}
        className={cn(
          "flex w-full items-center justify-between gap-2 rounded-[8px] border bg-[#161B22] px-3 py-2 text-left text-xs transition-colors duration-150 cursor-pointer",
          isEventSelectorOpen
            ? "border-[#E5C378] text-white"
            : "border-[#262D35] text-[#E5E7EB] hover:border-[#7C5A20]"
        )}
      >
        <div className="min-w-0 flex-1">
          <span className="block text-[11px] text-[#8E95A0]">Мероприятие:</span>
          <span className="mt-0.5 block truncate font-medium text-white">
            {activeEvent.canonical_title}{" "}
            <span className="text-[#8E95A0]">
              ({activeEvent.is_online ? "Онлайн" : activeEvent.city})
            </span>
          </span>
        </div>
        <ChevronDown
          className={cn(
            "h-4 w-4 shrink-0 text-[#E5C378] transition-transform duration-200",
            isEventSelectorOpen && "rotate-180"
          )}
          strokeWidth={1.75}
        />
      </button>

      <AnimatePresence>
        {isEventSelectorOpen && (
          <motion.div
            initial={{ opacity: 0, y: -4, scale: 0.99 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.99 }}
            transition={{ duration: 0.16, ease: "easeOut" }}
            className="absolute left-0 right-0 z-50 mt-1.5 max-h-60 overflow-y-auto rounded-[10px] border border-[#262D35] bg-[#0E1216] p-1.5 shadow-2xl scrollbar-thin"
          >
            {events.map((ev) => {
              const isSelected = ev.event_id === activeEvent.event_id;
              return (
                <button
                  key={ev.event_id}
                  type="button"
                  onClick={() => {
                    onSelectEvent(ev.event_id);
                    setIsEventSelectorOpen(false);
                  }}
                  className={cn(
                    "flex w-full items-center justify-between gap-2 rounded-[6px] px-3 py-2 text-left text-xs transition-colors cursor-pointer",
                    isSelected
                      ? "bg-[#1A2128] text-white font-semibold"
                      : "text-[#D1D5DB] hover:bg-[#161B22] hover:text-white"
                  )}
                >
                  <div className="min-w-0 flex-1">
                    <span className="block truncate">{ev.canonical_title}</span>
                    <span className="mt-0.5 block text-[11px] text-[#8E95A0]">
                      {ev.is_online ? "Онлайн" : ev.city} ·{" "}
                      {formatDateRange(ev.start_date, ev.end_date)}
                    </span>
                  </div>
                  {isSelected && (
                    <Check
                      className="h-3.5 w-3.5 shrink-0 text-[#E5C378]"
                      strokeWidth={2.25}
                    />
                  )}
                </button>
              );
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
