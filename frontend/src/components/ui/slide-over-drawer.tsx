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
 * Выдвижная панель справа (Slide-over Drawer 520px) в обсидианово-золотом дизайне
 * с поддержкой клавиши Esc, правильными отступами и плавной кинематикой.
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
            transition={{ duration: 0.22, ease: "easeOut" }}
            onClick={onClose}
            className="fixed inset-0 z-40 bg-black/75 backdrop-blur-sm"
          />

          <motion.aside
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ duration: 0.26, ease: [0.22, 1, 0.36, 1] }}
            className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[520px] flex-col border-l border-[#7C5A20]/50 bg-[#161B22] text-white shadow-[0_0_50px_rgba(0,0,0,0.85)]"
          >
            {/* Шапка шторки с выверенными отступами p-5 */}
            <div className="shrink-0 border-b border-[#21262F] bg-[#12161A] p-5">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  {subtitle && (
                    <p className="font-serif italic text-xs font-medium text-[#E5C378]">
                      ✦ {subtitle}
                    </p>
                  )}
                  <AnimatePresence mode="wait" initial={false}>
                    <motion.h2
                      key={title}
                      initial={{ opacity: 0, y: 3 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -3 }}
                      transition={{ duration: 0.16, ease: "easeOut" }}
                      className="mt-1 font-serif text-base sm:text-lg font-bold leading-snug text-white"
                    >
                      {title}
                    </motion.h2>
                  </AnimatePresence>
                </div>

                <button
                  type="button"
                  onClick={onClose}
                  aria-label="Закрыть панель"
                  className="shrink-0 rounded-[6px] border border-[#7C5A20]/40 bg-[#161B21] p-1.5 text-[#E5C378] transition-all duration-150 hover:border-[#E5C378] hover:bg-[#261E0F] hover:text-white outline-none cursor-pointer"
                >
                  <X className="h-4 w-4 stroke-[2]" />
                </button>
              </div>

              {headerSelector && <div className="mt-3.5">{headerSelector}</div>}
            </div>

            {/* Основная прокручиваемая область с ровными полями p-5 */}
            <div className="flex-1 overflow-y-auto p-5 text-[#E5E7EB] scrollbar-thin">
              {children}
            </div>

            {/* Нижняя панель ввода */}
            {footer && (
              <div className="shrink-0 border-t border-[#21262F] bg-[#12161A] px-5 py-4">
                {footer}
              </div>
            )}
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
