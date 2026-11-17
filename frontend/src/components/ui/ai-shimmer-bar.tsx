import * as React from "react";
import { AnimatePresence, motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface GoldShimmerBarProps {
  /** Процент прогресса (0–100) или null для непрерывного сканирующего режима. */
  progressPercent?: number | null;
  /** Активна ли анимация свечения и бегущего луча. */
  active?: boolean;
  /** Тонкая полоса (для ИИ-генерации) или стандартная (для прогресса парсера). */
  size?: "thin" | "md";
  /** Цветовой акцент: золотой (ИИ/общий) или изумрудно-золотой (live-парсер). */
  tone?: "gold" | "emerald-gold";
  className?: string;
}

/**
 * Плавный прогресс-бар и сканирующий шиммер в эстетике тёмного обсидиана и золота.
 */
export function GoldShimmerBar({
  progressPercent = null,
  active = true,
  size = "md",
  tone = "gold",
  className,
}: GoldShimmerBarProps) {
  const isDeterminate = progressPercent !== null && progressPercent !== undefined;
  const clamped = isDeterminate ? Math.max(0, Math.min(100, progressPercent)) : 0;
  // При 0% в активном состоянии оставляем минимальную «искру», чтобы полоса не выглядела пустой
  const visualWidth = isDeterminate
    ? active && clamped < 6
      ? 6
      : clamped
    : 100;

  const fillGradient =
    tone === "emerald-gold"
      ? "bg-gradient-to-r from-[#1E5241] via-[#34D399]/80 to-[#E5C378]"
      : "bg-gradient-to-r from-[#7C5A20] via-[#C8A961] to-[#E5C378]";

  const beamGradient =
    tone === "emerald-gold"
      ? "bg-gradient-to-r from-transparent via-[#E5C378]/90 to-transparent"
      : "bg-gradient-to-r from-transparent via-[#F6E2A8]/90 to-transparent";

  return (
    <div
      className={cn(
        "relative w-full overflow-hidden rounded-full bg-[#181E27]",
        size === "thin" ? "h-[3px]" : "h-2 border border-[#262D35]/80",
        className
      )}
    >
      {isDeterminate ? (
        <motion.div
          className={cn("relative h-full rounded-full", fillGradient)}
          initial={false}
          animate={{ width: `${visualWidth}%` }}
          transition={{ type: "spring", stiffness: 85, damping: 20, mass: 0.8 }}
        >
          {active && (
            <motion.div
              aria-hidden="true"
              className="absolute inset-0 bg-gradient-to-r from-transparent via-white/35 to-transparent"
              animate={{ x: ["-100%", "150%"] }}
              transition={{
                duration: 1.6,
                repeat: Infinity,
                ease: "easeInOut",
              }}
            />
          )}
        </motion.div>
      ) : null}

      {active && (
        <motion.div
          aria-hidden="true"
          className={cn(
            "pointer-events-none absolute inset-y-0 w-2/5 rounded-full opacity-75",
            beamGradient
          )}
          animate={{ x: ["-110%", "260%"] }}
          transition={{
            duration: isDeterminate ? 2.2 : 1.7,
            repeat: Infinity,
            ease: [0.4, 0, 0.2, 1],
          }}
        />
      )}
    </div>
  );
}

interface RotatingStatusTextProps {
  steps: readonly string[];
  active: boolean;
  intervalMs?: number;
  className?: string;
}

/**
 * Плавная смена статусных фраз с пульсирующей золотой искрой ✦.
 */
export function RotatingStatusText({
  steps,
  active,
  intervalMs = 2800,
  className,
}: RotatingStatusTextProps) {
  const [stepIndex, setStepIndex] = React.useState(0);

  React.useEffect(() => {
    if (!active || steps.length <= 1) {
      setStepIndex(0);
      return;
    }
    setStepIndex(0);
    const id = window.setInterval(() => {
      setStepIndex((prev) => (prev + 1) % steps.length);
    }, intervalMs);
    return () => window.clearInterval(id);
  }, [active, steps, intervalMs]);

  const currentText = steps[stepIndex] ?? steps[0] ?? "";

  return (
    <div className={cn("flex items-center gap-2 min-w-0", className)}>
      <motion.span
        aria-hidden="true"
        className="inline-block shrink-0 text-xs leading-none text-[#E5C378]"
        animate={
          active
            ? { opacity: [0.45, 1, 0.45], scale: [0.9, 1.15, 0.9] }
            : { opacity: 1, scale: 1 }
        }
        transition={{ duration: 1.8, repeat: Infinity, ease: "easeInOut" }}
      >
        ✦
      </motion.span>
      <div className="min-w-0 flex-1 overflow-hidden">
        <AnimatePresence mode="wait">
          <motion.span
            key={currentText}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.25, ease: "easeInOut" }}
            className="block truncate font-serif italic text-xs font-medium text-[#E5C378]"
          >
            {currentText}
          </motion.span>
        </AnimatePresence>
      </div>
    </div>
  );
}
