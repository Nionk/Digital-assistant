import { Compass, PanelLeftOpen, Pencil, Plus } from "lucide-react";
import { motion } from "framer-motion";

export function WorkspaceLoadingState() {
  return (
    <div className="flex h-64 items-center justify-center rounded-[12px] border border-[#262D35] bg-[#161B22] text-sm text-[#8E95A0]">
      Загрузка рабочего пространства менеджера...
    </div>
  );
}

interface WorkspaceEmptyClientStateProps {
  hasClients?: boolean;
  onOpenClientsDropdown: () => void;
  onCreateClient?: () => void;
}

export function WorkspaceEmptyClientState({
  hasClients = true,
  onOpenClientsDropdown,
  onCreateClient,
}: WorkspaceEmptyClientStateProps) {
  return (
    <div className="flex h-64 flex-col items-center justify-center gap-3 rounded-[12px] border border-[#262D35] bg-[#161B22] p-6 text-center shadow-card">
      <p className="text-sm font-medium text-white">
        {hasClients ? "Клиент не выбран" : "В портфеле пока нет активных клиентов"}
      </p>
      <div className="flex flex-wrap items-center justify-center gap-2.5">
        {hasClients && (
          <button
            type="button"
            onClick={onOpenClientsDropdown}
            className="inline-flex items-center gap-2 rounded-[8px] border border-[#262D35] bg-[#12161A] px-4 py-2 text-xs font-semibold text-white transition-all duration-150 hover:border-[#E5C378] hover:bg-[#1A2128] hover:text-[#E5C378] hover:shadow-[0_0_10px_rgba(229,195,120,0.2)] cursor-pointer"
          >
            <PanelLeftOpen className="h-4 w-4" />
            <span>Выбрать компанию из списка</span>
          </button>
        )}
        {onCreateClient && (
          <button
            type="button"
            onClick={onCreateClient}
            className="inline-flex items-center gap-2 rounded-[8px] border border-[#7C5A20]/70 bg-[#1E190E] px-4 py-2 text-xs font-semibold text-[#E5C378] transition-all duration-150 hover:border-[#E5C378] hover:bg-[#261E0F] hover:text-white cursor-pointer"
          >
            <Plus className="h-4 w-4" />
            <span>Новый клиент</span>
          </button>
        )}
      </div>
    </div>
  );
}

interface ActiveClientHeaderProps {
  companyName: string;
  contactPerson: string | null;
  onEditClient?: () => void;
}

export function ActiveClientHeader({
  companyName,
  contactPerson,
  onEditClient,
}: ActiveClientHeaderProps) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-[12px] border border-[#262D35] bg-[#161B22] px-5 py-3.5 shadow-sm">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-base sm:text-lg font-semibold tracking-tight text-white">
          {companyName}
        </h1>
        {contactPerson && (
          <>
            <div className="hidden h-4 w-[1px] bg-[#2D3540] sm:block" />
            <span className="text-xs font-normal text-[#8E95A0]">
              {contactPerson}
            </span>
          </>
        )}
      </div>

      {onEditClient && (
        <button
          type="button"
          onClick={onEditClient}
          className="inline-flex items-center gap-1.5 rounded-[6px] border border-[#262D35] bg-[#12161A] px-2.5 py-1 text-xs font-medium text-[#D1D5DB] transition-colors hover:border-[#E5C378] hover:bg-[#1E252E] hover:text-[#E5C378] cursor-pointer"
        >
          <Pencil className="h-3 w-3" strokeWidth={1.75} />
          <span>Редактировать</span>
        </button>
      )}
    </div>
  );
}

export function BundleOnboardingEmptyState() {
  return (
    <motion.div
      key="bundle-empty"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.2 }}
      className="rounded-[12px] border border-[#21262F] bg-[#0E1116] p-8 text-center shadow-sm"
    >
      <Compass className="mx-auto h-9 w-9 text-[#E5C378]" strokeWidth={1.5} />
      <h3 className="mt-3 font-serif italic text-sm font-semibold text-[#E5C378]">
        Готово к формированию пакетов участия
      </h3>
      <p className="mx-auto mt-1.5 max-w-lg text-xs leading-relaxed text-[#8E95A0]">
        Проверьте конспект установочной встречи выше и нажмите{" "}
        <strong className="font-semibold text-white">
          «Подобрать варианты пакетов»
        </strong>
        . Система извлечет критерии отбора, сверит календарь без накладок и сформирует 2 пакета с расчетом выгоды Early Bird.
      </p>
    </motion.div>
  );
}

export function PitchWaitingEmptyState() {
  return (
    <motion.div
      key="pitch-empty"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.2 }}
      className="rounded-[12px] border border-[#21262F] bg-[#0E1116] p-5 shadow-sm"
    >
      <span className="font-serif italic font-semibold text-xs tracking-wide text-[#E5C378]">
        Сводка и публикация КП
      </span>
      <h3 className="mt-1 font-serif italic text-sm font-semibold text-white">
        Ожидание расчёта подборки
      </h3>
      <p className="mt-1.5 font-serif italic text-xs leading-relaxed text-white/90">
        После запуска подбора здесь появится финансовая сводка пакета (внешние взносы организаторов и выгода Early Bird), редактор персонального письма и выпуск ссылки на витрину клиента.
      </p>
    </motion.div>
  );
}
