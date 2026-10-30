import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-control text-sm font-medium transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pine/30 disabled:pointer-events-none disabled:opacity-50 active:scale-[0.99]",
  {
    variants: {
      variant: {
        primary:
          "bg-pine text-white shadow-sm hover:bg-pine-hover",
        secondary:
          "bg-surface-muted text-ink hover:bg-border/60 border border-border",
        outline:
          "bg-surface text-ink border border-border hover:bg-surface-hover hover:border-border-strong",
        ghost:
          "text-ink-secondary hover:bg-surface-muted hover:text-ink",
        sage:
          "bg-sage text-white shadow-sm hover:bg-pine",
        sageTint:
          "bg-sage-tint text-sage border border-sage-border hover:bg-sage/15",
        terracotta:
          "bg-terracotta text-white shadow-sm hover:bg-terracotta-hover",
        terracottaTint:
          "bg-terracotta-tint text-terracotta border border-terracotta-border hover:bg-terracotta/15",
        gold:
          "btn-gold-ingot text-[#0E1215]",
      },
      size: {
        xs: "h-7 px-2.5 text-xs",
        sm: "h-8 px-3 text-xs",
        md: "h-9 px-4 text-sm",
        lg: "h-11 px-5 text-sm font-semibold",
        icon: "h-8 w-8 p-0",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "md",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";

