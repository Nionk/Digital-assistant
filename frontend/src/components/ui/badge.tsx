import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/**
 * Строгие матовые ячейки-плашки в эстетике Novel.AI и Early Bird:
 * Прямоугольная строгая форма (rounded-[4px]), плотный контрастный фон,
 * чёткая тонкая граница и моноширинный трекинг без размытых нейросетевых пилюль.
 */
const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-[4px] px-2 py-0.5 text-[10px] font-serif italic font-bold tracking-normal transition-colors select-none tabular-nums",
  {
    variants: {
      variant: {
        // Однотонный плотный фон с четким тёмным текстом того же цветового тона (без CAPS LOCK)
        ebEmerald:
          "bg-[#34D399] text-[#02291D] border-transparent font-bold",
        ebAmber:
          "bg-[#E59837] text-[#261502] border-transparent font-bold",
        ebTeal:
          "bg-[#2DD4BF] text-[#042824] border-transparent font-bold",
        ebGold:
          "bg-[#E5C378] text-[#241A04] border-transparent font-bold",
        ebBlue:
          "bg-[#60A5FA] text-[#082242] border-transparent font-bold",
        ebRose:
          "bg-[#F472B6] text-[#3B0716] border-transparent font-bold",
        ebSlate:
          "bg-[#94A3B8] text-[#0F172A] border-transparent font-bold",

        // Novel.AI классика
        novelWhite:
          "bg-white text-[#0E1215] border border-white/20 font-semibold shadow-xs",
        novelSand:
          "bg-[#E5C378] text-[#241A04] border-transparent font-bold",
        novelGold:
          "bg-[#E5C378] text-[#241A04] border-transparent font-bold",
        novelDark:
          "bg-[#161B22] text-white border border-[#2B3545]",
        novelEmerald:
          "bg-[#34D399] text-[#02291D] border-transparent font-bold",
        novelWine:
          "bg-[#F472B6] text-[#3B0716] border-transparent font-bold",

        // Совместимость с системными темами
        neutral:
          "bg-[#94A3B8] text-[#0F172A] border-transparent font-bold",
        surface:
          "bg-[#1A1E24] text-[#D1D5DB] border border-[#262D35]",
        pine:
          "bg-[#34D399] text-[#02291D] border-transparent font-bold",
        sage:
          "bg-[#2DD4BF] text-[#042824] border-transparent font-bold",
        terracotta:
          "bg-[#E59837] text-[#261502] border-transparent font-bold",
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


