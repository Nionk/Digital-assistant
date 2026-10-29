import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/**
 * Строгие матовые ячейки-плашки в эстетике Novel.AI и Early Bird:
 * Прямоугольная строгая форма (rounded-[4px]), плотный контрастный фон,
 * чёткая тонкая граница и моноширинный трекинг без размытых нейросетевых пилюль.
 */
const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-[4px] px-2 py-0.5 text-[10px] font-serif italic font-bold tracking-wider uppercase transition-colors select-none tabular-nums",
  {
    variants: {
      variant: {
        // Ряды стилей Early Bird / Novel.AI (четкие матовые ячейки с границами)
        ebEmerald:
          "bg-[#0E241E] text-[#34D399] border border-[#1E5241]",
        ebAmber:
          "bg-[#22160C] text-[#E59837] border border-[#7C4A19]",
        ebTeal:
          "bg-[#0B2528] text-[#2DD4BF] border border-[#165057]",
        ebGold:
          "bg-[#261E0F] text-[#E5C378] border border-[#6B531E]",
        ebBlue:
          "bg-[#101D2C] text-[#60A5FA] border border-[#1E3B5C]",
        ebRose:
          "bg-[#28131E] text-[#F472B6] border border-[#5E2242]",
        ebSlate:
          "bg-[#161B22] text-[#D1D5DB] border border-[#2B3545]",

        // Novel.AI классика
        novelWhite:
          "bg-white text-[#0E1215] border border-white/20 font-semibold shadow-xs",
        novelSand:
          "bg-[#261E0F] text-[#E5C378] border border-[#6B531E]",
        novelGold:
          "bg-[#261E0F] text-[#E5C378] border border-[#7C5A20]",
        novelDark:
          "bg-[#161B22] text-white border border-[#2B3545]",
        novelEmerald:
          "bg-[#0E241E] text-[#34D399] border border-[#1E5241]",
        novelWine:
          "bg-[#28131E] text-[#F472B6] border border-[#5E2242]",

        // Совместимость с системными темами
        neutral:
          "bg-[#161B22] text-[#D1D5DB] border border-[#262D35]",
        surface:
          "bg-[#1A1E24] text-[#D1D5DB] border border-[#262D35]",
        pine:
          "bg-[#0E241E] text-[#34D399] border border-[#1E5241]",
        sage:
          "bg-[#0B2528] text-[#2DD4BF] border border-[#165057]",
        terracotta:
          "bg-[#22160C] text-[#E59837] border border-[#7C4A19]",
        darkSubtle:
          "bg-[#161B22] text-[#8E95A0] border border-[#2A313C]",
      },
    },
    defaultVariants: {
      variant: "neutral",
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}


