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
 * Выдвижная панель справа (Slide-over Drawer 480px) в обсидианово-золотом дизайне
 * с поддержкой клавиши Esc и плавной кинематикой.
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
            className="fixed inset-0 z-40 bg-black/80 backdrop-blur-sm"
          />

          <motion.aside
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ duration: 0.26, ease: [0.22, 1, 0.36, 1] }}
            className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[500px] flex-col border-l border-[#262D35] bg-[#161B22] text-white shadow-[0_0_50px_rgba(0,0,0,0.8)]"
          >
            <div className="border-b border-[#262D35] bg-[#12161A]/95 backdrop-blur-md px-6 py-4.5">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  {subtitle && (
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-[#E5C378]">
                      {subtitle}
                    </p>
                  )}
                  <h2 className="mt-1 font-serif text-lg font-bold leading-snug text-white">
                    {title}
                  </h2>
                </div>
                <button
                  type="button"
                  onClick={onClose}
                  aria-label="Закрыть панель"
                  className="rounded-lg p-1.5 text-neutral-400 transition-colors hover:bg-[#1E2530] hover:text-white"
                >
                  <X className="h-4 w-4" strokeWidth={1.75} />
                </button>
              </div>
              {headerSelector && <div className="mt-3">{headerSelector}</div>}
            </div>

            <div className="flex-1 overflow-y-auto px-6 py-5 text-neutral-200 scrollbar-thin">
              {children}
            </div>

            {footer && (
              <div className="border-t border-[#262D35] bg-[#12161A]/95 px-6 py-4">
                {footer}
              </div>
            )}
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
