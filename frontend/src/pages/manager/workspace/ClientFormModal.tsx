import * as React from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  X,
  Building2,
  UserCheck,
  FileText,
  Archive,
  AlertTriangle,
  AlertCircle,
  Loader2,
  Check,
  Plus,
} from "lucide-react";
import { toast } from "sonner";
import {
  useCreateClientMutation,
  useUpdateClientMutation,
} from "@/api/queries";
import type { ClientSummaryOut } from "@/api/types";
import { Button } from "@/components/ui/button";

interface ClientFormModalProps {
  isOpen: boolean;
  mode: "create" | "edit";
  client?: ClientSummaryOut | null;
  onClose: () => void;
  onCreated?: (client: ClientSummaryOut) => void;
  onUpdated?: (client: ClientSummaryOut) => void;
  onArchived?: (client: ClientSummaryOut) => void;
}

export function ClientFormModal({
  isOpen,
  mode,
  client = null,
  onClose,
  onCreated,
  onUpdated,
  onArchived,
}: ClientFormModalProps) {
  const createMutation = useCreateClientMutation();
  const updateMutation = useUpdateClientMutation();

  const [mounted, setMounted] = React.useState(false);
  const [companyName, setCompanyName] = React.useState("");
  const [contactPerson, setContactPerson] = React.useState("");
  const [rawNotes, setRawNotes] = React.useState("");
  const [formError, setFormError] = React.useState<string | null>(null);
  const [isArchiveConfirmOpen, setIsArchiveConfirmOpen] = React.useState(false);

  const isBusy = createMutation.isPending || updateMutation.isPending;

  React.useEffect(() => {
    setMounted(true);
  }, []);

  React.useEffect(() => {
    if (!isOpen) return;
    if (mode === "edit" && client) {
      setCompanyName(client.company_name);
      setContactPerson(client.contact_person ?? "");
      setRawNotes(client.raw_manager_notes ?? "");
    } else {
      setCompanyName("");
      setContactPerson("");
      setRawNotes("");
    }
    setFormError(null);
    setIsArchiveConfirmOpen(false);
  }, [isOpen, mode, client]);

  React.useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !isBusy) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, isBusy, onClose]);

  if (!mounted || typeof document === "undefined") return null;

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setFormError(null);

    const trimmedName = companyName.trim();
    if (!trimmedName) {
      setFormError("Укажите название компании клиента.");
      return;
    }

    const trimmedContact = contactPerson.trim();
    const trimmedNotes = rawNotes.trim();

    try {
      if (mode === "create") {
        const created = await createMutation.mutateAsync({
          company_name: trimmedName,
          contact_person: trimmedContact || null,
          raw_manager_notes: trimmedNotes,
        });
        toast.success(`Клиент «${created.company_name}» создан и выбран активным`);
        onCreated?.(created);
        onClose();
      } else if (client) {
        const updated = await updateMutation.mutateAsync({
          clientId: client.id,
          payload: {
            company_name: trimmedName,
            contact_person: trimmedContact || null,
            raw_manager_notes: trimmedNotes,
          },
        });
        toast.success(`Карточка «${updated.company_name}» обновлена`);
        onUpdated?.(updated);
        onClose();
      }
    } catch (err) {
      const message =
        err instanceof Error
          ? err.message
          : "Не удалось сохранить карточку клиента.";
      setFormError(message);
      toast.error(message);
    }
  };

  const handleArchiveConfirm = async () => {
    if (!client || isBusy) return;
    setFormError(null);
    try {
      const archived = await updateMutation.mutateAsync({
        clientId: client.id,
        payload: { is_active: false },
      });
      toast.success(`Клиент «${archived.company_name}» перенесён в архив`);
      onArchived?.(archived);
      onClose();
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Не удалось архивировать клиента.";
      setFormError(message);
      toast.error(message);
    }
  };

  return createPortal(
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-[10000] flex items-center justify-center p-4">
          <motion.div
            key="client-modal-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18, ease: "easeOut" }}
            className="fixed inset-0 bg-black/75 backdrop-blur-md"
            onClick={() => {
              if (!isBusy) onClose();
            }}
          />

          <motion.div
            key="client-modal-content"
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 8 }}
            transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
            className="relative z-10 w-full max-w-lg overflow-hidden rounded-[10px] border border-[#7C5A20] bg-[#161B22] text-white shadow-[0_25px_60px_-15px_rgba(0,0,0,0.9),0_0_20px_rgba(229,195,120,0.1)]"
          >
            <div className="p-4 sm:p-5">
              <div className="flex items-start justify-between gap-3 border-b border-[#21262F] pb-3">
                <div className="flex items-center gap-2">
                  <span className="text-[#E5C378] text-xs select-none">✦</span>
                  <h2 className="font-serif italic text-base font-semibold tracking-tight text-[#E5C378]">
                    {mode === "create"
                      ? "Новый клиент в портфеле"
                      : `Редактирование: ${client?.company_name ?? "клиент"}`}
                  </h2>
                </div>

                <button
                  type="button"
                  disabled={isBusy}
                  onClick={onClose}
                  aria-label="Закрыть окно"
                  className="shrink-0 rounded-[6px] border border-[#7C5A20]/40 bg-[#12161A] p-1.5 text-[#E5C378] transition-all duration-150 hover:border-[#E5C378] hover:bg-[#261E0F] hover:text-white disabled:opacity-50 outline-none"
                >
                  <X className="h-4 w-4 stroke-[2]" />
                </button>
              </div>

              <form onSubmit={handleSubmit} className="mt-4 space-y-3.5" noValidate>
                {formError && (
                  <div
                    role="alert"
                    className="flex items-start gap-2 rounded-[6px] border border-[#EA4335]/40 bg-[#EA4335]/10 px-3 py-2 text-xs text-[#FCA5A5]"
                  >
                    <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#F87171]" />
                    <span>{formError}</span>
                  </div>
                )}

                <div>
                  <label
                    htmlFor="client-form-company"
                    className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-[#8E95A0]"
                  >
                    <Building2 className="h-3.5 w-3.5 text-[#E5C378]" />
                    <span>Название компании *</span>
                  </label>
                  <input
                    id="client-form-company"
                    name="company_name"
                    type="text"
                    required
                    value={companyName}
                    disabled={isBusy}
                    onChange={(e) => setCompanyName(e.target.value)}
                    placeholder="Например: ГК «Эталон»"
                    className="h-9 w-full rounded-[6px] border border-[#262D35] bg-[#12161A] px-3 text-xs text-white placeholder:text-[#8E95A0] [color-scheme:dark] outline-none focus:border-[#E5C378] focus:shadow-[0_0_0_1px_rgba(229,195,120,0.25)] transition-colors"
                  />
                </div>

                <div>
                  <label
                    htmlFor="client-form-contact"
                    className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-[#8E95A0]"
                  >
                    <UserCheck className="h-3.5 w-3.5 text-[#E5C378]" />
                    <span>Контактное лицо (опционально)</span>
                  </label>
                  <input
                    id="client-form-contact"
                    name="contact_person"
                    type="text"
                    value={contactPerson}
                    disabled={isBusy}
                    onChange={(e) => setContactPerson(e.target.value)}
                    placeholder="Например: Мария Соколова (Директор по маркетингу)"
                    className="h-9 w-full rounded-[6px] border border-[#262D35] bg-[#12161A] px-3 text-xs text-white placeholder:text-[#8E95A0] [color-scheme:dark] outline-none focus:border-[#E5C378] focus:shadow-[0_0_0_1px_rgba(229,195,120,0.25)] transition-colors"
                  />
                </div>

                <div>
                  <label
                    htmlFor="client-form-notes"
                    className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-[#8E95A0]"
                  >
                    <FileText className="h-3.5 w-3.5 text-[#E5C378]" />
                    <span>Конспект встречи / вводные (опционально)</span>
                  </label>
                  <textarea
                    id="client-form-notes"
                    name="raw_manager_notes"
                    rows={3}
                    value={rawNotes}
                    disabled={isBusy}
                    onChange={(e) => setRawNotes(e.target.value)}
                    placeholder="Задачи участия, города, бюджет, желаемые роли (спикер/делегат/стенд)..."
                    className="w-full rounded-[6px] border border-[#262D35] bg-[#12161A] p-2.5 text-xs leading-relaxed text-white placeholder:text-[#8E95A0] [color-scheme:dark] outline-none focus:border-[#E5C378] focus:shadow-[0_0_0_1px_rgba(229,195,120,0.25)] transition-colors scrollbar-thin"
                  />
                </div>

                {mode === "edit" && client && isArchiveConfirmOpen && (
                  <div className="rounded-[8px] border border-[#7C4A19] bg-[#22160C] p-3 text-xs space-y-2.5">
                    <div className="flex items-start gap-2 text-[#FDE68A]">
                      <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5 text-[#E59837]" />
                      <p className="leading-relaxed">
                        Перенести клиента{" "}
                        <strong className="text-white">«{client.company_name}»</strong>{" "}
                        в архив? Компания исчезнет из рабочего списка, но история
                        подборок и опубликованные витрины сохранятся в базе.
                      </p>
                    </div>
                    <div className="flex items-center justify-end gap-2">
                      <Button
                        type="button"
                        variant="outline"
                        size="xs"
                        disabled={isBusy}
                        onClick={() => setIsArchiveConfirmOpen(false)}
                        className="border-[#262D35] bg-[#12161A] text-[#D1D5DB] hover:border-[#E5C378] hover:text-white"
                      >
                        Отмена
                      </Button>
                      <Button
                        type="button"
                        variant="terracotta"
                        size="xs"
                        disabled={isBusy}
                        onClick={handleArchiveConfirm}
                        className="font-semibold"
                      >
                        {updateMutation.isPending ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Archive className="h-3.5 w-3.5" />
                        )}
                        <span>Подтвердить архивацию</span>
                      </Button>
                    </div>
                  </div>
                )}

                <div className="flex flex-wrap items-center justify-between gap-2 border-t border-[#21262F] pt-3">
                  <div>
                    {mode === "edit" && client && !isArchiveConfirmOpen && (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        disabled={isBusy}
                        onClick={() => setIsArchiveConfirmOpen(true)}
                        className="border-[#7C4A19]/70 bg-[#1B120A] text-xs text-[#E59837] hover:border-[#E59837] hover:bg-[#2A1B0E] hover:text-[#FDE68A]"
                      >
                        <Archive className="h-3.5 w-3.5" />
                        <span>В архив</span>
                      </Button>
                    )}
                  </div>

                  <div className="flex items-center gap-2 ml-auto">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={isBusy}
                      onClick={onClose}
                      className="border-[#262D35] bg-[#12161A] text-xs text-[#D1D5DB] hover:border-[#E5C378] hover:text-white"
                    >
                      Отмена
                    </Button>
                    <Button
                      type="submit"
                      variant="monolith"
                      size="sm"
                      disabled={isBusy || companyName.trim().length === 0}
                      className="text-xs font-semibold px-4"
                    >
                      {isBusy ? (
                        <>
                          <Loader2 className="h-3.5 w-3.5 animate-spin text-[#E5C378]" />
                          <span>Сохранение...</span>
                        </>
                      ) : mode === "create" ? (
                        <>
                          <Plus className="h-3.5 w-3.5 text-[#E5C378] monolith-icon" />
                          <span>Создать клиента</span>
                        </>
                      ) : (
                        <>
                          <Check className="h-3.5 w-3.5 text-[#E5C378] monolith-icon" />
                          <span>Сохранить</span>
                        </>
                      )}
                    </Button>
                  </div>
                </div>
              </form>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>,
    document.body
  );
}
