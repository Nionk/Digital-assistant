import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/**
 * Строгие прямоугольные бейджи (6px скругление вместо нейросетевых овалов rounded-full).
 */
const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-badge px-2 py-0.5 text-xs font-medium tracking-tight transition-colors",
  {
    variants: {
      variant: {
        neutral: "bg-surface-muted text-ink-secondary border border-border",
        surface: "bg-surface text-ink-secondary border border-border",
        pine: "bg-pine text-white",
        sage: "bg-sage-tint text-sage border border-sage-border",
        terracotta:
          "bg-terracotta-tint text-terracotta border border-terracotta-border",
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

