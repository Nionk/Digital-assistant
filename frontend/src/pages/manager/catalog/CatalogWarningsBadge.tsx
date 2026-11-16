import { AlertTriangle } from "lucide-react";
import { humanizeMissingDataWarnings } from "@/lib/warnings";
import { cn } from "@/lib/utils";

interface CatalogWarningsBadgeProps {
  warnings: readonly string[];
  className?: string;
}

/** Компактный бейдж недостающих данных площадки со списком подсказок в tooltip. */
export function CatalogWarningsBadge({
  warnings,
  className,
}: CatalogWarningsBadgeProps) {
  const humanized = humanizeMissingDataWarnings(warnings);
  if (humanized.length === 0) return null;

  const tooltip = `Уточнить данные:\n${humanized.map((w) => `• ${w}`).join("\n")}`;

  return (
    <span
      title={tooltip}
      className={cn(
        "inline-flex items-center gap-1 rounded-[4px] border border-[#7C4A19]/70 bg-[#22160C]/80 px-1.5 py-0.5 text-[11px] font-medium text-[#E59837] cursor-help",
        className
      )}
    >
      <AlertTriangle className="h-3 w-3 shrink-0" strokeWidth={1.75} />
      <span>Недостаёт: {humanized.length}</span>
    </span>
  );
}
