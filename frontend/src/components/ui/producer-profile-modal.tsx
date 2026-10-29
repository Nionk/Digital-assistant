import * as React from "react";
import { X, Check, Play } from "lucide-react";
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

  if (!isOpen) return null;

  const handleSelect = (profile: ProducerProfile) => {
    setSelectedId(profile.id);
    setProducer(profile);
    setTimeout(() => {
      onClose();
    }, 180);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Затемняющий матовый фон с размытием */}
      <div
        className="fixed inset-0 bg-black/75 backdrop-blur-md transition-opacity"
        onClick={onClose}
      />

      {/* Окно профиля: матовый тёмный фон блоков, благородный золотой кант */}
      <div className="relative z-10 w-full max-w-lg overflow-hidden rounded-[14px] border border-[#7C5A20] bg-[#161B22] text-white shadow-[0_25px_60px_-15px_rgba(0,0,0,0.9),0_0_25px_rgba(229,195,120,0.12)]">
        <div className="p-5 sm:p-6">
          {/* Верхняя строка: заголовок + выразительный золотой крестик справа */}
          <div className="flex items-start justify-between gap-4 border-b border-[#21262F] pb-4">
            <div>
              <h2 className="font-serif italic text-lg sm:text-xl font-semibold tracking-tight text-[#E5C378]">
                Выбор куратора
              </h2>
              <p className="mt-1 text-xs text-[#8E95A0] leading-relaxed">
                Переключение активного профиля менеджера для формирования пакетов и витрин
              </p>
            </div>

            <button
              type="button"
              onClick={onClose}
              aria-label="Закрыть окно"
              className="shrink-0 rounded-[6px] border border-[#7C5A20]/40 bg-[#12161A] p-2 text-[#E5C378] transition-all duration-150 hover:border-[#E5C378] hover:bg-[#261E0F] hover:text-white hover:shadow-[0_0_10px_rgba(229,195,120,0.25)] outline-none"
            >
              <X className="h-4 w-4 stroke-[2]" />
            </button>
          </div>

          {/* Карточки продюсеров для быстрого переключения в 1 клик */}
          <div className="mt-4 space-y-2.5">
            {PRODUCER_PROFILES.map((profile) => {
              const isCurrent = profile.id === selectedId;

              return (
                <div
                  key={profile.id}
                  onClick={() => handleSelect(profile)}
                  className={cn(
                    "group flex cursor-pointer items-center justify-between gap-3 rounded-[8px] border p-3 transition-colors duration-150 select-none",
                    isCurrent
                      ? "border-[#E5C378] bg-[#1E190E] shadow-[0_0_12px_rgba(229,195,120,0.12)]"
                      : "border-[#262D35] bg-[#12161A] hover:border-[#7C5A20] hover:bg-[#1A1E24]"
                  )}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    {/* Аватар-плашка с инициалами */}
                    <div
                      className={cn(
                        "flex h-10 w-10 shrink-0 items-center justify-center rounded-[6px] border text-xs font-bold tracking-wider",
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
                        <span className="shrink-0 rounded-[3px] border border-[#262D35] bg-[#161B21] px-1.5 py-0.2 text-[10px] font-serif italic text-[#8E95A0]">
                          {profile.role}
                        </span>
                      </div>
                      <p className="mt-0.5 text-xs text-[#727985] truncate tabular-nums">
                        {profile.department} · {profile.dealsCount} активных сделок
                      </p>
                    </div>
                  </div>

                  {/* Кнопка статуса или золотой треугольник перехода, без переносов */}
                  <div className="shrink-0 flex items-center">
                    {isCurrent ? (
                      <span className="inline-flex items-center gap-1 rounded-[4px] border border-[#7C5A20]/60 bg-[#261E0F] px-2 py-0.5 text-[10px] font-serif italic text-[#E5C378]">
                        <Check className="h-3 w-3 text-[#E5C378]" strokeWidth={2.5} />
                        <span>Активен</span>
                      </span>
                    ) : (
                      <span className="flex h-7 w-7 items-center justify-center rounded-[4px] border border-[#262D35] bg-[#12161A] text-[#E5C378] transition-all duration-150 group-hover:border-[#E5C378] group-hover:bg-[#261E0F] group-hover:translate-x-0.5">
                        <Play className="h-2.5 w-2.5 fill-[#E5C378] text-[#E5C378]" />
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
