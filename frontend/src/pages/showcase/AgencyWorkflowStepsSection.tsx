import {
  CheckCircle2,
  Users,
  Mic,
  Gamepad2,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";

/**
 * Нижний информационный блок витрины клиента, раскрывающий ценность коммуникационного агентства
 * по Слайдам 05, 06, 07, 08 («Путь совместной работы» и «Подготовка под задачи клиента»)
 * в обсидианово-золотом архитектурном стиле.
 */
export function AgencyWorkflowStepsSection() {
  const pillars = [
    {
      step: "01",
      icon: CheckCircle2,
      title: "Организация участия и партнёрские условия",
      description:
        "Согласовываем формат, условия и программу участия с организаторами. Фиксируем скидки раннего бронирования и партнёрские преференции.",
    },
    {
      step: "02",
      icon: Users,
      title: "Деловые знакомства и выход на ключевых игроков",
      description:
        "Определяем целевые компании среди участников форума, помогаем выйти на ЛПР и готовим график личных деловых встреч на площадке.",
    },
    {
      step: "03",
      icon: Mic,
      title: "Подготовка экспертного выступления спикера",
      description:
        "Подбираем целевую сессию, прорабатываем тему, ключевые смыслы и структуру презентации, готовим спикера к выступлению и вопросам зала.",
    },
    {
      step: "04",
      icon: Gamepad2,
      title: "Вовлечение аудитории и интерактив на стенде",
      description:
        "Создаём интерактивные программы и деловые игры для стенда или деловой зоны, формирующие повод для знакомства и продолжения контакта.",
    },
  ];

  return (
    <section className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <div className="rounded-2xl border border-[#262D35] bg-[#161B22] p-6 shadow-2xl">
        <div className="flex flex-col justify-between gap-2 border-b border-[#262D35] pb-4 md:flex-row md:items-end">
          <div>
            <Badge variant="ebGold" className="text-[10px] tracking-wider uppercase">
              ЭКСПЕРТНОЕ СОПРОВОЖДЕНИЕ
            </Badge>
            <h2 className="mt-2 font-serif text-lg font-bold text-white sm:text-xl">
              Как мы превращаем участие в мероприятиях в деловой результат
            </h2>
          </div>
          <p className="text-xs text-neutral-400">
            Форматы сопровождения можно сочетать под каждую выбранную площадку
          </p>
        </div>

        <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {pillars.map((item) => {
            const Icon = item.icon;
            return (
              <div
                key={item.step}
                className="group flex flex-col justify-between rounded-xl border border-[#262D35] bg-[#12161A] p-4 transition-all duration-200 hover:border-[#7C5A20]/60 hover:shadow-lg"
              >
                <div>
                  <div className="flex items-center justify-between">
                    <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-[#7C5A20]/40 bg-[#161B22] text-[#E5C378] transition-transform duration-200 group-hover:scale-105">
                      <Icon className="h-4 w-4" strokeWidth={1.75} />
                    </span>
                    <span className="font-serif italic text-base text-[#E5C378]/70 tabular-nums">
                      {item.step}
                    </span>
                  </div>
                  <h3 className="mt-3 text-xs font-bold leading-snug text-white transition-colors group-hover:text-[#E5C378]">
                    {item.title}
                  </h3>
                  <p className="mt-1.5 text-xs leading-relaxed text-neutral-400">
                    {item.description}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
