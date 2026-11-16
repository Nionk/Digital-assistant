import { MessageSquareText } from "lucide-react";
import type { ShowcaseEventItemOut } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { FORMAT_LABELS } from "@/lib/formatters";

interface EventBenefitsTabProps {
  activeEvent: ShowcaseEventItemOut;
  onSwitchToRegulationTab: () => void;
}

/** Вкладка условий тарифа, программы, тематических треков и обоснования подборки. */
export function EventBenefitsTab({
  activeEvent,
  onSwitchToRegulationTab,
}: EventBenefitsTabProps) {
  return (
    <div className="space-y-4">
      <div className="rounded-[12px] border border-[#262D35] bg-[#12161A] p-4 space-y-3">
        <div className="flex items-center justify-between gap-2 border-b border-[#21262F] pb-2.5">
          <span className="font-serif italic text-xs font-semibold text-[#E5C378]">
            Программа и фокус площадки
          </span>
          <Badge variant="darkSubtle" asSlanted={false} className="text-[11px]">
            {FORMAT_LABELS[activeEvent.event_format] ||
              activeEvent.event_format}
          </Badge>
        </div>

        <p className="text-xs leading-relaxed text-[#E5E7EB]">
          {activeEvent.summary}
        </p>

        {activeEvent.themes.length > 0 && (
          <div className="pt-1">
            <span className="block text-[11px] font-medium text-[#8E95A0] mb-1.5">
              Ключевые тематические треки:
            </span>
            <div className="flex flex-wrap gap-1.5">
              {activeEvent.themes.map((theme) => (
                <span
                  key={theme}
                  className="rounded-[4px] border border-[#262D35] bg-[#161B22] px-2 py-0.5 text-[11px] font-serif italic text-[#D1D5DB]"
                >
                  {theme}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {activeEvent.included_benefits && (
        <div className="rounded-[12px] border border-[#262D35] bg-[#12161A] p-4">
          <span className="block font-serif italic text-xs font-semibold text-[#E5C378]">
            Что входит в пакет «{activeEvent.tariff_name}»
          </span>
          <p className="mt-2 whitespace-pre-line text-xs leading-relaxed text-[#D1D5DB]">
            {activeEvent.included_benefits}
          </p>
        </div>
      )}

      {activeEvent.ai_rationale && (
        <div className="rounded-[12px] border border-[#262D35] border-l-2 border-l-[#E5C378] bg-[#12161A] p-4">
          <span className="block font-serif italic text-xs font-semibold text-[#E5C378]">
            Почему мероприятие включено в подборку
          </span>
          <p className="mt-1.5 text-xs leading-relaxed text-[#D1D5DB]">
            {activeEvent.ai_rationale}
          </p>
        </div>
      )}

      <Button
        type="button"
        variant="outline"
        size="md"
        onClick={onSwitchToRegulationTab}
        className="w-full border-[#7C5A20]/50 bg-[#12161A] text-xs font-semibold text-[#E5C378] hover:border-[#E5C378] hover:bg-[#1A2128] hover:text-white cursor-pointer"
      >
        <MessageSquareText className="h-3.5 w-3.5" strokeWidth={1.75} />
        <span>Задать вопрос консультанту по регламенту</span>
      </Button>
    </div>
  );
}
