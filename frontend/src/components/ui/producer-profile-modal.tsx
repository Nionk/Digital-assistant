import * as React from "react";
import { X, Check } from "lucide-react";
import {
  PRODUCER_PROFILES,
  type ProducerProfile,
  useManagerStore,
} from "@/store/useManagerStore";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
      {/* Затемняющий матовый фон */}
      <div
        className="fixed inset-0 bg-ink/70 backdrop-blur-sm transition-opacity"
        onClick={onClose}
      />

      {/* Окно профиля в эстетике Novel.AI: глубокий графитовый/матовый фон, антиква в заголовках, строгие плашки */}
      <div className="relative z-10 w-full max-w-xl overflow-hidden rounded-card border border-novel-border bg-novel-dark text-white shadow-2xl">
        {/* Декоративная тонкая золотистая линия сверху */}
        <div className="h-1 w-full bg-gradient-to-r from-novel-gold via-novel-sand to-novel-gold opacity-80" />

        <div className="p-6 sm:p-7">
          {/* Верхняя строка: Логотип + заголовок + кнопка закрытия */}
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2">
                <Badge variant="novelSand" className="text-[10px]">
                  TERMINAL ACCESS
                </Badge>
                <span className="text-[11px] font-mono tracking-wider text-white/50">
                  SYS_VER 2.4 · READY
                </span>
              </div>
              <h2 className="mt-2.5 font-serif text-2xl font-bold tracking-tight text-white sm:text-[26px]">
                Рабочее место продюсера
              </h2>
              <p className="mt-1 text-xs text-white/70 leading-relaxed">
                Интеллектуальная система селекции площадок, расчета Early Bird тарифов
                и сборки персональных клиентских витрин.
              </p>
            </div>

            <button
              type="button"
              onClick={onClose}
              className="rounded-tag border border-white/10 bg-white/5 p-1.5 text-white/60 transition-colors hover:bg-white/10 hover:text-white"
            >
              <X className="h-4 w-4" strokeWidth={1.75} />
            </button>
          </div>

          {/* Карточки продюсеров для быстрого переключения в 1 клик */}
          <div className="mt-6 space-y-3">
            <span className="text-[10px] font-bold uppercase tracking-widest text-white/60">
              Выберите активный профиль куратора
            </span>

            {PRODUCER_PROFILES.map((profile) => {
              const isCurrent = profile.id === selectedId;

              return (
                <div
                  key={profile.id}
                  onClick={() => handleSelect(profile)}
                  className={cn(
                    "group relative flex cursor-pointer items-center justify-between rounded-control border p-3.5 transition-all",
                    isCurrent
                      ? "border-novel-sand bg-novel-charcoal shadow-md ring-1 ring-novel-sand/30"
                      : "border-white/10 bg-novel-charcoal/60 hover:border-white/20 hover:bg-novel-charcoal"
                  )}
                >
                  <div className="flex items-center gap-3.5">
                    {/* Аватар-плашка с инициалами */}
                    <div
                      className={cn(
                        "flex h-11 w-11 shrink-0 items-center justify-center rounded-tag border text-xs font-bold tracking-wider",
                        isCurrent
                          ? "border-novel-sand bg-novel-sand text-[#1F1808]"
                          : "border-white/15 bg-white/10 text-white"
                      )}
                    >
                      {profile.avatarText}
                    </div>

                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-serif text-base font-semibold text-white group-hover:text-novel-sand transition-colors">
                          {profile.name}
                        </span>
                        <Badge
                          variant={isCurrent ? "novelSand" : "neutral"}
                          className="text-[9px]"
                        >
                          {profile.role}
                        </Badge>
                      </div>
                      <p className="mt-0.5 text-xs text-white/65">
                        {profile.department} · {profile.dealsCount} активных сделок
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    {isCurrent ? (
                      <span className="inline-flex items-center gap-1 rounded-tag bg-novel-sand px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-[#1F1808]">
                        <Check className="h-3 w-3" strokeWidth={2.5} />
                        Активен
                      </span>
                    ) : (
                      <span className="text-xs text-white/40 group-hover:text-white/80 transition-colors">
                        Переключить →
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Информационный подвал системы */}
          <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-white/10 pt-4 text-xs text-white/60">
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
              <span>База данных актуальна: 2026</span>
            </div>

            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={onClose}
                className="border-white/20 bg-transparent text-white hover:bg-white/10"
              >
                Закрыть окно
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
