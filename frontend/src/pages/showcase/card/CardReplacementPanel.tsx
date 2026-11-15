import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { REPLACEMENT_QUICK_REASONS } from "@/lib/formatters";

interface CardReplacementPanelProps {
  replaceComment: string;
  isReacting: boolean;
  onChangeReplaceComment: (comment: string) => void;
  onSelectQuickReason: (reason: string) => void;
  onSubmit: () => void;
  onClose: () => void;
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
          Укажите причину или напишите комментарий для куратора:
        </p>

        <div className="mt-2.5 flex flex-wrap gap-1.5">
          {REPLACEMENT_QUICK_REASONS.map((reason) => (
            <button
              key={reason}
              type="button"
              disabled={isReacting}
              onClick={() => onSelectQuickReason(reason)}
              className="rounded-[6px] border border-[#262D35] bg-[#161B22] px-2.5 py-1 text-[11px] font-medium text-[#D1D5DB] transition-colors hover:border-[#5E2242] hover:bg-[#28131E] hover:text-[#F472B6] disabled:opacity-50 cursor-pointer"
            >
              {reason}
            </button>
          ))}
        </div>

        <div className="mt-2.5 flex gap-1.5">
          <input
            type="text"
            value={replaceComment}
            onChange={(e) => onChangeReplaceComment(e.target.value)}
            placeholder="Ваш комментарий (например, другие даты)..."
            className="h-8 flex-1 rounded-[6px] border border-[#262D35] bg-[#161B22] px-2.5 text-xs text-white placeholder:text-[#727985] focus:border-[#F472B6] focus:outline-none"
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={isReacting}
            onClick={onSubmit}
            className="border-[#5E2242] bg-[#28131E] text-[#F472B6] hover:bg-[#381a2b] cursor-pointer"
          >
            Отправить
          </Button>
        </div>
      </div>
    </motion.div>
  );
}
