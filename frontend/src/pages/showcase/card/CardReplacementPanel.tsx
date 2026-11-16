import * as React from "react";
import { motion } from "framer-motion";
import { Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { REPLACEMENT_QUICK_REASONS } from "@/lib/formatters";
import { cn } from "@/lib/utils";

interface CardReplacementPanelProps {
  replaceComment: string;
  isReacting: boolean;
  onChangeReplaceComment: (comment: string) => void;
  onSelectQuickReason: (reason: string) => void;
  onSubmit: () => void;
  onClose: () => void;
}

/** Добавляет или переключает быструю причину замены в текстовом комментарии. */
export function mergeReplaceQuickReason(
  current: string,
  reason: string
): string {
  const trimmed = current.trim();
  if (!trimmed || trimmed === "Запрошена замена площадки") {
    return reason;
  }
  const parts = trimmed
    .split(/\s*;\s*/)
    .map((part) => part.trim())
    .filter(Boolean);
  const existingIdx = parts.findIndex(
    (part) => part.toLowerCase() === reason.toLowerCase()
  );
  if (existingIdx !== -1) {
    parts.splice(existingIdx, 1);
    return parts.join("; ");
  }
  if (trimmed.toLowerCase().includes(reason.toLowerCase())) {
    return current;
  }
  return `${parts.join("; ")}; ${reason}`;
}

function isQuickReasonSelected(comment: string, reason: string): boolean {
  const trimmed = comment.trim().toLowerCase();
  if (!trimmed) return false;
  return trimmed.includes(reason.trim().toLowerCase());
}

/** Раскрываемая панель пожеланий и быстрых причин замены мероприятия на карточке витрины. */
export function CardReplacementPanel({
  replaceComment,
  isReacting,
  onChangeReplaceComment,
  onSelectQuickReason,
  onSubmit,
  onClose,
}: CardReplacementPanelProps) {
  const inputRef = React.useRef<HTMLInputElement>(null);

  const handleChipClick = (reason: string) => {
    onSelectQuickReason(reason);
    window.requestAnimationFrame(() => {
      const input = inputRef.current;
      if (!input) return;
      input.focus();
      const len = input.value.length;
      input.setSelectionRange(len, len);
    });
  };

  const hasComment = replaceComment.trim().length > 0;

  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: "auto" }}
      exit={{ opacity: 0, height: 0 }}
      transition={{ duration: 0.2, ease: "easeOut" }}
      className="overflow-hidden"
    >
      <div className="mt-3 rounded-[10px] border border-[#5E2242]/70 bg-[#12161A] p-3.5 shadow-lg">
        <div className="flex items-center justify-between">
          <span className="font-serif italic text-xs font-semibold text-[#F472B6]">
            Пожелания для замены мероприятия
          </span>
          <button
            type="button"
            onClick={onClose}
            className="text-[11px] text-[#8E95A0] hover:text-white transition-colors cursor-pointer"
          >
            Отмена
          </button>
        </div>
        <p className="mt-1 text-[11px] text-[#8E95A0]">
          Выберите одну или несколько причин, при необходимости уточните детали и нажмите «Отправить»:
        </p>

        <div className="mt-2.5 flex flex-wrap gap-1.5">
          {REPLACEMENT_QUICK_REASONS.map((reason) => {
            const isActive = isQuickReasonSelected(replaceComment, reason);
            return (
              <button
                key={reason}
                type="button"
                aria-pressed={isActive}
                disabled={isReacting}
                onClick={() => handleChipClick(reason)}
                className={cn(
                  "inline-flex items-center gap-1 rounded-[6px] border px-2.5 py-1 text-[11px] font-medium transition-colors disabled:opacity-50 cursor-pointer",
                  isActive
                    ? "border-[#F472B6] bg-[#381A2B] text-white shadow-[0_0_10px_rgba(244,114,182,0.2)]"
                    : "border-[#262D35] bg-[#161B22] text-[#D1D5DB] hover:border-[#5E2242] hover:bg-[#28131E] hover:text-[#F472B6]"
                )}
              >
                {isActive && (
                  <Check className="h-3 w-3 shrink-0 text-[#F472B6]" strokeWidth={2.25} />
                )}
                <span>{reason}</span>
              </button>
            );
          })}
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!isReacting) onSubmit();
          }}
          className="mt-2.5 flex gap-1.5"
        >
          <input
            ref={inputRef}
            type="text"
            value={replaceComment}
            onChange={(e) => onChangeReplaceComment(e.target.value)}
            placeholder="Ваш комментарий (например, другие даты)..."
            className="h-8 flex-1 rounded-[6px] border border-[#262D35] bg-[#161B22] px-2.5 text-xs text-white placeholder:text-[#727985] focus:border-[#F472B6] focus:outline-none"
          />
          <Button
            type="submit"
            variant="outline"
            size="sm"
            disabled={isReacting}
            className={cn(
              "border-[#5E2242] bg-[#28131E] text-[#F472B6] hover:bg-[#381a2b] cursor-pointer transition-all",
              hasComment &&
                "border-[#F472B6] bg-[#381A2B] text-white shadow-[0_0_10px_rgba(244,114,182,0.22)]"
            )}
          >
            Отправить
          </Button>
        </form>
      </div>
    </motion.div>
  );
}
