import {
  CheckCircle2,
  Users,
  Mic,
  Gamepad2,
} from "lucide-react";

/**
 * Нижний информационный блок витрины клиента, раскрывающий ценность коммуникационного агентства
 * по Слайдам 05, 06, 07, 08 («Путь совместной работы» и «Подготовка под задачи клиента»).
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
      <div className="rounded-card border border-border bg-surface p-6 shadow-card">
        <div className="flex flex-col justify-between gap-2 border-b border-border/80 pb-4 md:flex-row md:items-end">
          <div>
            <span className="text-[11px] font-semibold uppercase tracking-wider text-sage">
              Этапы совместной работы · Подготовка под ваши бизнес-задачи
            </span>
            <h2 className="mt-1 text-lg font-bold text-ink">
              Как мы превращаем участие в мероприятиях в деловой результат
            </h2>
          </div>
          <p className="text-xs text-ink-muted">
            Форматы сопровождения можно сочетать под каждую выбранную площадку
          </p>
        </div>

        <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {pillars.map((item) => {
            const Icon = item.icon;
            return (
              <div
                key={item.step}
                className="flex flex-col justify-between rounded-control border border-border/80 bg-canvas/55 p-4"
              >
                <div>
                  <div className="flex items-center justify-between">
                    <span className="flex h-7 w-7 items-center justify-center rounded-badge bg-pine/10 text-pine">
                      <Icon className="h-4 w-4" strokeWidth={1.75} />
                    </span>
                    <span className="text-xs font-bold text-ink-faint tabular-nums">
                      {item.step}
                    </span>
                  </div>
                  <h3 className="mt-3 text-xs font-bold leading-snug text-ink">
                    {item.title}
                  </h3>
                  <p className="mt-1.5 text-xs leading-relaxed text-ink-secondary">
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

