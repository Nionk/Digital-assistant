import * as React from "react";
import { X, Play } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import {
  PRODUCER_PROFILES,
  type ProducerProfile,
  useManagerStore,
} from "@/store/useManagerStore";
import { cn } from "@/lib/utils";

interface ProducerProfileModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function ProducerProfileModal({
  isOpen,
  onClose,
}: ProducerProfileModalProps) {
  const currentProducer = useManagerStore((s) => s.currentProducer);
  const setProducer = useManagerStore((s) => s.setProducer);

  const [selectedId, setSelectedId] = React.useState(currentProducer.id);

  React.useEffect(() => {
    setSelectedId(currentProducer.id);
  }, [currentProducer.id]);

  const handleSelect = (profile: ProducerProfile) => {
    setSelectedId(profile.id);
    setProducer(profile);
    setTimeout(() => {
      onClose();
    }, 180);
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          {/* Матовый затемняющий фон с плавным проявлением */}
          <motion.div
            key="modal-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18, ease: "easeOut" }}
            className="fixed inset-0 bg-black/75 backdrop-blur-md"
            onClick={onClose}
          />

          {/* Карточка окна: благородный матовый фон, золотистый кант, плавная анимация раскрытия */}
          <motion.div
            key="modal-content"
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 8 }}
            transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
            className="relative z-10 w-full max-w-md overflow-hidden rounded-[10px] border border-[#7C5A20] bg-[#161B22] text-white shadow-[0_25px_60px_-15px_rgba(0,0,0,0.9),0_0_20px_rgba(229,195,120,0.1)]"
          >
            <div className="p-4 sm:p-5">
              {/* Шапка окна: лаконичный заголовок + выразительный золотой крестик */}
              <div className="flex items-center justify-between border-b border-[#21262F] pb-3">
                <div className="flex items-center gap-2">
                  <span className="text-[#E5C378] text-xs select-none">✦</span>
                  <h2 className="font-serif italic text-base font-semibold tracking-tight text-[#E5C378]">
                    Выбор куратора
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

              {/* Список кураторов в строгом книжном стиле */}
              <div className="mt-3 space-y-2">
                {PRODUCER_PROFILES.map((profile) => {
                  const isCurrent = profile.id === selectedId;

                  return (
                    <div
                      key={profile.id}
                      onClick={() => handleSelect(profile)}
                      className={cn(
                        "group flex cursor-pointer items-center justify-between gap-3 rounded-[6px] border p-2.5 transition-colors duration-150 select-none",
                        isCurrent
                          ? "border-[#E5C378] bg-[#1E190E] shadow-[0_0_10px_rgba(229,195,120,0.12)]"
                          : "border-[#262D35] bg-[#12161A] hover:border-[#7C5A20] hover:bg-[#181D23]"
                      )}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        {/* Компактная плашка с инициалами */}
                        <div
                          className={cn(
                            "flex h-9 w-9 shrink-0 items-center justify-center rounded-[4px] border text-xs font-bold tabular-nums font-sans",
                            isCurrent
                              ? "border-[#E5C378] bg-[#E5C378] text-[#1A1405]"
                              : "border-[#262D35] bg-[#161B21] text-[#E5C378]"
                          )}
                        >
                          {profile.avatarText}
                        </div>

                        <div className="min-w-0">
                          <div className="flex items-center gap-2 truncate">
                            <span className="font-serif text-sm font-semibold text-white group-hover:text-[#E5C378] transition-colors truncate">
                              {profile.name}
                            </span>
                            <span className="shrink-0 rounded-[2px] border border-[#262D35] bg-[#161B21] px-1.5 py-0.2 text-[10px] font-serif italic text-[#8E95A0]">
                              {profile.role}
                            </span>
                          </div>
                          <p className="mt-0.5 text-xs text-[#727985] truncate tabular-nums">
                            {profile.department} · {profile.dealsCount} активных сделок
                          </p>
                        </div>
                      </div>

                      {/* Статус активности либо золотой треугольник перехода (без переносов) */}
                      <div className="shrink-0 flex items-center">
                        {isCurrent ? (
                          <span className="inline-flex items-center gap-1 rounded-[3px] border border-[#7C5A20]/60 bg-[#261E0F] px-2 py-0.5 text-[10px] font-serif italic text-[#E5C378]">
                            ✦ Активен
                          </span>
                        ) : (
                          <span className="flex h-6 w-6 items-center justify-center rounded-[3px] border border-[#262D35] bg-[#12161A] text-[#E5C378] transition-all duration-150 group-hover:border-[#E5C378] group-hover:bg-[#261E0F] group-hover:translate-x-0.5">
                            <Play className="h-2.5 w-2.5 fill-[#E5C378] text-[#E5C378]" />
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
