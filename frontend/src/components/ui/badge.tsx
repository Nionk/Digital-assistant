import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/**
 * Авторские скошенные ячейки-плашки (Italic Slanted Ribbon) в эстетике Novel.AI:
 * Геометрия параллелограмма со скосом -9° (точно в сторону наклона серифа Lora Italic),
 * оптическая компенсация внутреннего контента (+9°) для безупречной читаемости и резкости,
 * плотный книжный фон и тонкая деликатная окантовка без шаблонного нейросетевого дефолта.
 */
const badgeVariants = cva(
  "inline-flex items-center justify-center text-[10px] sm:text-[11px] font-serif italic font-bold tracking-normal transition-colors select-none tabular-nums",
  {
    variants: {
      variant: {
        // Однотонный плотный книжный фон с четким тёмным текстом (раннее бронирование, выгода)
        ebEmerald:
          "bg-[#34D399] text-[#02291D] border border-[#2BB883]/60",
        ebAmber:
          "bg-[#E59837] text-[#261502] border border-[#D98223]/60",
        ebTeal:
          "bg-[#2DD4BF] text-[#042824] border border-[#14B8A6]/60",
        ebGold:
          "bg-[#E5C378] text-[#241A04] border border-[#D4AF37]/60",
        ebBlue:
          "bg-[#60A5FA] text-[#082242] border border-[#3B82F6]/60",
        ebRose:
          "bg-[#F472B6] text-[#3B0716] border border-[#EC4899]/60",
        ebSlate:
          "bg-[#94A3B8] text-[#0F172A] border border-[#64748B]/60",

        // Novel.AI классика
        novelWhite:
          "bg-white text-[#0E1215] border border-white/20 font-semibold shadow-xs",
        novelSand:
          "bg-[#E5C378] text-[#241A04] border border-[#D4AF37]/60",
        novelGold:
          "bg-[#E5C378] text-[#241A04] border border-[#D4AF37]/60",
        novelDark:
          "bg-[#161B22] text-[#E5C378] border border-[#7C5A20]/50",
        novelEmerald:
          "bg-[#34D399] text-[#02291D] border border-[#2BB883]/60",
        novelWine:
          "bg-[#F472B6] text-[#3B0716] border border-[#EC4899]/60",

        // Совместимость с системными темами
        neutral:
          "bg-[#94A3B8] text-[#0F172A] border border-[#64748B]/60",
        surface:
          "bg-[#1A1E24] text-[#D1D5DB] border border-[#262D35]",
        pine:
          "bg-[#34D399] text-[#02291D] border border-[#2BB883]/60",
        sage:
          "bg-[#2DD4BF] text-[#042824] border border-[#14B8A6]/60",
        terracotta:
          "bg-[#E59837] text-[#261502] border border-[#D98223]/60",
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
    VariantProps<typeof badgeVariants> {
  asSlanted?: boolean;
}

export function Badge({
  className,
  variant,
  asSlanted = true,
  children,
  ...props
}: BadgeProps) {
  if (!asSlanted) {
    return (
      <span
        className={cn(
          badgeVariants({ variant }),
          "rounded-[4px] px-2 py-0.5 gap-1.5",
          className
        )}
        {...props}
      >
        {children}
      </span>
    );
  }

  return (
    <span
      className={cn(
        badgeVariants({ variant }),
        "-skew-x-[9deg] rounded-[2px] px-2.5 py-0.5",
        className
      )}
      {...props}
    >
      <span className="inline-flex items-center gap-1.5 skew-x-[9deg]">
        {children}
      </span>
    </span>
  );
}
