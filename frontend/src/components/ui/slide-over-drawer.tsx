import * as React from "react";
import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";

interface SlideOverDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  headerSelector?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
}

/**
 * Выдвижная панель справа (Slide-over Drawer 480px) с поддержкой клавиши Esc и плавной физикой.
 */
export function SlideOverDrawer({
  isOpen,
  onClose,
  title,
  subtitle,
  headerSelector,
  children,
  footer,
}: SlideOverDrawerProps) {
  React.useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={onClose}
            className="fixed inset-0 z-40 bg-ink/35 backdrop-blur-[1px]"
          />

          <motion.aside
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", stiffness: 320, damping: 32 }}
            className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[480px] flex-col border-l border-border bg-surface shadow-drawer"
          >
            <div className="border-b border-border bg-canvas/70 px-5 py-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  {subtitle && (
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-sage">
                      {subtitle}
                    </p>
                  )}
                  <h2 className="mt-0.5 text-base font-semibold leading-snug text-ink">
                    {title}
                  </h2>
                </div>
                <button
                  type="button"
                  onClick={onClose}
                  aria-label="Закрыть панель"
                  className="rounded-control p-1.5 text-ink-muted transition-colors hover:bg-surface-muted hover:text-ink"
                >
                  <X className="h-4 w-4" strokeWidth={1.75} />
                </button>
              </div>
              {headerSelector && <div className="mt-3">{headerSelector}</div>}
            </div>

            <div className="flex-1 overflow-y-auto px-5 py-4 scrollbar-thin">
              {children}
            </div>

            {footer && (
              <div className="border-t border-border bg-surface px-5 py-3.5">
                {footer}
              </div>
            )}
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

