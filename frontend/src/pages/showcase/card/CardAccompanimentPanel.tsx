import { motion } from "framer-motion";
import { Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { AGENCY_SERVICES_STAGE_09 } from "@/lib/formatters";
import { cn } from "@/lib/utils";

interface CardAccompanimentPanelProps {
  effectiveAgencyServices: string[];
  interestedNote: string;
  isReacting: boolean;
  onToggleService: (serviceTag: string) => void;
  onChangeInterestedNote: (note: string) => void;
  onClose: () => void;
  onSubmit: () => void;
}

/** Раскрываемая панель выбора задач сопровождения агентства (Этап 09) на карточке витрины. */
export function CardAccompanimentPanel({
  effectiveAgencyServices,
  interestedNote,
  isReacting,
  onToggleService,
  onChangeInterestedNote,
  onClose,
  onSubmit,
}: CardAccompanimentPanelProps) {
  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: "auto" }}
      exit={{ opacity: 0, height: 0 }}
      transition={{ duration: 0.2, ease: "easeOut" }}
      className="overflow-hidden"
    >
      <div className="mt-3 rounded-[10px] border border-[#1E5241] bg-[#0D211B] p-3.5 shadow-lg">
        <div className="flex items-center justify-between gap-2">
          <span className="font-serif italic text-xs font-semibold text-[#34D399]">
            Подготовка и сопровождение от агентства
          </span>
          <button
            type="button"
            onClick={onClose}
            className="text-[11px] text-[#8E95A0] hover:text-white transition-colors cursor-pointer"
          >
            Свернуть
          </button>
        </div>
        <p className="mt-1 text-[11px] text-[#A7F3D0]/80">
          Отметьте задачи, которые вы хотите поручить нашей команде:
        </p>

        <div className="mt-2.5 space-y-1.5">
          {AGENCY_SERVICES_STAGE_09.map((srv) => {
            const checked = effectiveAgencyServices.includes(srv.shortTag);
            return (
              <label
                key={srv.id}
                className={cn(
                  "flex cursor-pointer items-start gap-2.5 rounded-[8px] border p-2.5 text-xs transition-colors",
                  checked
                    ? "border-[#2B6E58] bg-[#133329] text-white"
                    : "border-[#1E5241]/60 bg-[#0A1914] text-[#D1D5DB] hover:border-[#2B6E58]"
                )}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => onToggleService(srv.shortTag)}
                  className="mt-0.5 h-3.5 w-3.5 rounded accent-[#34D399]"
                />
                <div className="min-w-0 flex-1">
                  <span className="block font-semibold text-white">
                    {srv.title}
                  </span>
                  <span className="mt-0.5 block text-[11px] text-[#8E95A0] leading-snug">
                    {srv.subtitle}
                  </span>
                </div>
              </label>
            );
          })}
        </div>

        <input
          type="text"
          value={interestedNote}
          onChange={(e) => onChangeInterestedNote(e.target.value)}
          placeholder="Комментарий куратору (необязательно)..."
          className="mt-2.5 h-8 w-full rounded-[6px] border border-[#1E5241]/70 bg-[#0A1914] px-2.5 text-xs text-white placeholder:text-[#6B8F82] focus:border-[#34D399] focus:outline-none"
        />

        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={isReacting}
          onClick={onSubmit}
          className="mt-2.5 w-full border-[#2B6E58] bg-[#14382D] text-xs font-semibold text-[#34D399] hover:bg-[#194638] hover:text-white cursor-pointer"
        >
          <Check className="h-3.5 w-3.5" strokeWidth={2.25} />
          <span>Сохранить выбранные опции</span>
        </Button>
      </div>
    </motion.div>
  );
}
