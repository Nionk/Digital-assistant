import * as React from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { X, LogOut, Mail, Briefcase, MessageSquare } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { useManagerDashboard } from "@/api/queries";
import { parseManagerDisplayInfo, useAuthStore } from "@/store/useAuthStore";

interface ProducerProfileModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function ProducerProfileModal({
  isOpen,
  onClose,
}: ProducerProfileModalProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const { data: dashboardData } = useManagerDashboard();

  const [mounted, setMounted] = React.useState(false);

  React.useEffect(() => {
    setMounted(true);
  }, []);

  React.useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!mounted || typeof document === "undefined") return null;

  const profile = parseManagerDisplayInfo(user);
  const activeClientsCount = dashboardData?.clients.length ?? 0;

  const handleLogout = () => {
    onClose();
    logout();
    queryClient.clear();
    navigate("/login", { replace: true });
  };

  return createPortal(
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4">
          <motion.div
            key="modal-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18, ease: "easeOut" }}
            className="fixed inset-0 bg-black/75 backdrop-blur-md"
            onClick={onClose}
          />

          <motion.div
            key="modal-content"
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 8 }}
            transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
            className="relative z-10 w-full max-w-md overflow-hidden rounded-[10px] border border-[#7C5A20] bg-[#161B22] text-white shadow-[0_25px_60px_-15px_rgba(0,0,0,0.9),0_0_20px_rgba(229,195,120,0.1)]"
          >
            <div className="p-4 sm:p-5">
              <div className="flex items-center justify-between border-b border-[#21262F] pb-3">
                <div className="flex items-center gap-2">
                  <span className="text-[#E5C378] text-xs select-none">✦</span>
                  <h2 className="font-serif italic text-base font-semibold tracking-tight text-[#E5C378]">
                    Профиль куратора
                  </h2>
                </div>

                <button
                  type="button"
                  onClick={onClose}
                  aria-label="Закрыть окно"
                  className="rounded-[6px] border border-[#7C5A20]/40 bg-[#12161A] p-1.5 text-[#E5C378] transition-all duration-150 hover:border-[#E5C378] hover:bg-[#261E0F] hover:text-white hover:shadow-[0_0_8px_rgba(229,195,120,0.25)] outline-none"
                >
                  <X className="h-4 w-4 stroke-[2]" />
                </button>
              </div>

              <div className="mt-4 space-y-3">
                <div className="flex items-center justify-between gap-3 rounded-[6px] border border-[#E5C378] bg-[#1E190E] p-3 shadow-[0_0_10px_rgba(229,195,120,0.12)]">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[4px] border border-[#E5C378] bg-[#E5C378] text-xs font-bold tabular-nums font-sans text-[#1A1405]">
                      {profile.initials}
                    </div>
                    <div className="min-w-0">
                      <span className="block font-serif text-sm font-semibold text-white truncate">
                        {profile.displayName}
                      </span>
                      <span className="mt-0.5 inline-block rounded-[2px] border border-[#7C5A20]/50 bg-[#161B21] px-1.5 py-0.5 text-[10px] font-serif italic text-[#E5C378]">
                        {profile.roleLabel}
                      </span>
                    </div>
                  </div>

                  <span className="shrink-0 inline-flex items-center gap-1 rounded-[3px] border border-[#7C5A20]/60 bg-[#261E0F] px-2 py-0.5 text-[10px] font-serif italic text-[#E5C378]">
                    ✦ Активен
                  </span>
                </div>

                <div className="space-y-2 rounded-[6px] border border-[#262D35] bg-[#12161A] p-3 text-xs">
                  <div className="flex items-center justify-between gap-3">
                    <span className="flex items-center gap-2 text-[#8E95A0]">
                      <Mail className="h-3.5 w-3.5 text-[#E5C378]/80" />
                      Email сессии
                    </span>
                    <span className="font-medium text-[#F1F5F9] truncate">
                      {profile.email || "—"}
                    </span>
                  </div>

                  <div className="flex items-center justify-between gap-3">
                    <span className="flex items-center gap-2 text-[#8E95A0]">
                      <Briefcase className="h-3.5 w-3.5 text-[#E5C378]/80" />
                      Компаний в портфеле
                    </span>
                    <span className="font-semibold tabular-nums text-[#F1F5F9]">
                      {activeClientsCount}
                    </span>
                  </div>

                  <div className="flex items-center justify-between gap-3">
                    <span className="flex items-center gap-2 text-[#8E95A0]">
                      <MessageSquare className="h-3.5 w-3.5 text-[#E5C378]/80" />
                      Telegram-уведомления
                    </span>
                    <span className="tabular-nums text-[#CBD5E1]">
                      {profile.telegramChatId !== null
                        ? `ID ${profile.telegramChatId}`
                        : "Не привязан"}
                    </span>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={handleLogout}
                  className="flex w-full items-center justify-center gap-2 rounded-[6px] border border-[#7C5A20]/70 bg-[#1A150B] px-3.5 py-2.5 text-xs font-semibold text-[#E5C378] transition-all duration-150 hover:border-[#E5C378] hover:bg-[#261E0F] hover:text-white"
                >
                  <LogOut className="h-3.5 w-3.5" />
                  <span>Выйти / Сменить аккаунт</span>
                </button>
              </div>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>,
    document.body
  );
}
