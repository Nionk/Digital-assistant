import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/**
 * Строгие матовые плашки в эстетике Novel.AI:
 * Прямоугольная форма (rounded-[2px]-3px), плотный непрозрачный цвет,
 * чёткий трекинг и акцентный контраст без размытых нейросетевых пилюль.
 */
const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-badge px-2 py-0.5 text-[10px] font-bold tracking-wider uppercase transition-colors select-none",
  {
    variants: {
      variant: {
        // Novel.AI стили (высокий контраст, плотная матовая заливка)
        novelWhite:
          "bg-white text-ink border border-ink/20 shadow-[0_1px_2px_rgba(0,0,0,0.06)]",
        novelSand:
          "bg-novel-sand text-[#2C2416] border border-novel-sandBorder shadow-[0_1px_2px_rgba(0,0,0,0.04)]",
        novelGold:
          "bg-novel-gold text-[#1F1808] border border-[#CCA75A]",
        novelDark:
          "bg-novel-dark text-white border border-novel-border",
        novelEmerald:
          "bg-novel-emerald text-white border border-[#144A39]",
        novelWine:
          "bg-novel-wine text-white border border-[#7A2430]",

        // Семантические B2B-роли
        neutral:
          "bg-surface-muted text-ink-secondary border border-border",
        surface:
          "bg-surface text-ink-secondary border border-border shadow-xs",
        pine:
          "bg-pine text-white border border-pine-hover",
        sage:
          "bg-sage-tint text-sage border border-sage-border",
        terracotta:
          "bg-terracotta-tint text-terracotta border border-terracotta-border",
        darkSubtle:
          "bg-surface-muted/80 text-ink-muted border border-border/80",
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


