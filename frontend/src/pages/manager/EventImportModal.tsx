import * as React from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  X,
  Upload,
  FileText,
  Link2,
  Loader2,
  CheckCircle2,
  AlertCircle,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";
import { useUploadEventPdfMutation } from "@/api/queries";
import type { EventUploadOut } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { pluralizeRu } from "@/lib/formatters";
import { cn } from "@/lib/utils";

interface EventImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialSourceUrl?: string | null;
  initialEventTitle?: string | null;
  onSuccess?: (result: EventUploadOut) => void;
}

function isValidHttpUrl(raw: string): boolean {
  try {
    const parsed = new URL(raw);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} Б`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} КБ`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`;
}

export function EventImportModal({
  isOpen,
  onClose,
  initialSourceUrl = null,
  initialEventTitle = null,
  onSuccess,
}: EventImportModalProps) {
  const uploadMutation = useUploadEventPdfMutation();

  const [mounted, setMounted] = React.useState(false);
  const [selectedFile, setSelectedFile] = React.useState<File | null>(null);
  const [sourceUrl, setSourceUrl] = React.useState("");
  const [rawText, setRawText] = React.useState("");
  const [isDragging, setIsDragging] = React.useState(false);
  const [formError, setFormError] = React.useState<string | null>(null);
  const [uploadResult, setUploadResult] = React.useState<EventUploadOut | null>(
    null
  );

  const fileInputRef = React.useRef<HTMLInputElement>(null);

  React.useEffect(() => {
    setMounted(true);
  }, []);

  React.useEffect(() => {
    if (!isOpen) return;
    setSelectedFile(null);
    setSourceUrl(initialSourceUrl?.trim() || "");
    setRawText("");
    setFormError(null);
    setUploadResult(null);
    setIsDragging(false);
  }, [isOpen, initialSourceUrl]);

  React.useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !uploadMutation.isPending) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose, uploadMutation.isPending]);

  if (!mounted || typeof document === "undefined") return null;

  const acceptFile = (file: File | null | undefined) => {
    if (!file) return;
    setFormError(null);
    setUploadResult(null);
    const isPdf =
      file.type === "application/pdf" ||
      file.name.toLowerCase().endsWith(".pdf");
    if (!isPdf) {
      setFormError("Поддерживаются только файлы формата PDF (.pdf).");
      return;
    }
    if (file.size === 0) {
      setFormError("Выбранный PDF-файл пуст.");
      return;
    }
    setSelectedFile(file);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    if (uploadMutation.isPending) return;
    acceptFile(e.dataTransfer.files?.[0]);
  };

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setFormError(null);
    setUploadResult(null);

    const trimmedUrl = sourceUrl.trim();
    const trimmedText = rawText.trim();

    if (!selectedFile && !trimmedUrl && !trimmedText) {
      setFormError(
        "Прикрепите PDF-брошюру, укажите URL страницы или вставьте текстовый регламент."
      );
      return;
    }

    if (trimmedUrl && !isValidHttpUrl(trimmedUrl)) {
      setFormError("Укажите корректный URL с протоколом http:// или https://.");
      return;
    }

    try {
      const result = await uploadMutation.mutateAsync({
        file: selectedFile,
        source_url: trimmedUrl || null,
        raw_text: trimmedText || null,
      });
      setUploadResult(result);
      toast.success(
        `Площадка «${result.canonical_title}» сохранена (${result.tariffs_count} ${pluralizeRu(result.tariffs_count, ["тариф", "тарифа", "тарифов"])})`
      );
      onSuccess?.(result);
    } catch (err) {
      const message =
        err instanceof Error
          ? err.message
          : "Не удалось импортировать материалы мероприятия.";
      setFormError(message);
      toast.error(message);
    }
  };

  return createPortal(
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-[10000] flex items-center justify-center p-4">
          <motion.div
            key="import-modal-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18, ease: "easeOut" }}
            className="fixed inset-0 bg-black/75 backdrop-blur-md"
            onClick={() => {
              if (!uploadMutation.isPending) onClose();
            }}
          />

          <motion.div
            key="import-modal-content"
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 8 }}
            transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
            className="relative z-10 w-full max-w-lg overflow-hidden rounded-[10px] border border-[#7C5A20] bg-[#161B22] text-white shadow-[0_25px_60px_-15px_rgba(0,0,0,0.9),0_0_20px_rgba(229,195,120,0.1)]"
          >
            <div className="p-4 sm:p-5">
              <div className="flex items-start justify-between gap-3 border-b border-[#21262F] pb-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-[#E5C378] text-xs select-none">✦</span>
                    <h2 className="font-serif italic text-base font-semibold tracking-tight text-[#E5C378]">
                      {initialEventTitle
                        ? "Обогащение площадки из PDF / ссылки"
                        : "Импорт площадки из PDF, ссылки или текста"}
                    </h2>
                  </div>
                  {initialEventTitle && (
                    <p className="mt-1 truncate text-xs text-[#8E95A0]">
                      Целевое событие: <span className="text-white">{initialEventTitle}</span>
                    </p>
                  )}
                </div>

                <button
                  type="button"
                  disabled={uploadMutation.isPending}
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

                {uploadResult && (
                  <div className="rounded-[8px] border border-[#1E5241] bg-[#0E241E]/90 p-3 text-xs space-y-2">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-1.5 font-semibold text-[#34D399]">
                        <CheckCircle2 className="h-4 w-4 shrink-0" />
                        <span>{uploadResult.canonical_title}</span>
                      </div>
                      <Badge
                        variant={
                          uploadResult.data_status === "ready"
                            ? "ebEmerald"
                            : "ebAmber"
                        }
                        asSlanted={false}
                        className="text-[11px] shrink-0"
                      >
                        {uploadResult.data_status === "ready"
                          ? "Готово к подбору"
                          : "Требует обогащения"}
                      </Badge>
                    </div>
                    <p className="text-[#D1D5DB] leading-relaxed">
                      {uploadResult.message} Извлечено тарифов:{" "}
                      <strong className="text-white tabular-nums">
                        {uploadResult.tariffs_count}
                      </strong>
                      .
                    </p>
                  </div>
                )}

                {/* Загрузка PDF-брошюры */}
                <div>
                  <label
                    htmlFor="event-import-file"
                    className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-[#8E95A0]"
                  >
                    PDF-брошюра / регламент (опционально)
                  </label>
                  <input
                    ref={fileInputRef}
                    id="event-import-file"
                    name="file"
                    type="file"
                    accept=".pdf,application/pdf"
                    disabled={uploadMutation.isPending}
                    onChange={(e) => {
                      acceptFile(e.target.files?.[0]);
                      e.target.value = "";
                    }}
                    className="hidden"
                  />

                  {selectedFile ? (
                    <div className="flex items-center justify-between gap-2 rounded-[6px] border border-[#7C5A20] bg-[#1E190E] px-3 py-2 text-xs">
                      <div className="flex items-center gap-2 min-w-0">
                        <FileText className="h-4 w-4 shrink-0 text-[#E5C378]" />
                        <span className="truncate font-medium text-white">
                          {selectedFile.name}
                        </span>
                        <span className="shrink-0 text-[11px] text-[#8E95A0] tabular-nums">
                          ({formatFileSize(selectedFile.size)})
                        </span>
                      </div>
                      <button
                        type="button"
                        disabled={uploadMutation.isPending}
                        onClick={() => setSelectedFile(null)}
                        className="rounded p-1 text-[#8E95A0] hover:text-[#EF4444] transition-colors"
                        title="Убрать файл"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ) : (
                    <div
                      onDragOver={(e) => {
                        e.preventDefault();
                        if (!uploadMutation.isPending) setIsDragging(true);
                      }}
                      onDragLeave={() => setIsDragging(false)}
                      onDrop={handleDrop}
                      onClick={() => {
                        if (!uploadMutation.isPending) {
                          fileInputRef.current?.click();
                        }
                      }}
                      className={cn(
                        "flex cursor-pointer flex-col items-center justify-center rounded-[8px] border border-dashed px-4 py-4 text-center transition-colors",
                        isDragging
                          ? "border-[#E5C378] bg-[#1E190E]"
                          : "border-[#38414F] bg-[#12161A] hover:border-[#E5C378] hover:bg-[#161B21]"
                      )}
                    >
                      <Upload className="h-5 w-5 text-[#E5C378]" strokeWidth={1.75} />
                      <p className="mt-1.5 text-xs font-medium text-[#D1D5DB]">
                        Перетащите PDF сюда или{" "}
                        <span className="text-[#E5C378] underline underline-offset-2">
                          выберите файл
                        </span>
                      </p>
                      <p className="mt-0.5 text-[11px] text-[#8E95A0]">
                        ИИ извлечет даты, описание, тарифы организатора и Early Bird
                      </p>
                    </div>
                  )}
                </div>

                {/* Внешний URL */}
                <div>
                  <label
                    htmlFor="event-import-url"
                    className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-[#8E95A0]"
                  >
                    Ссылка на страницу события (URL)
                  </label>
                  <div className="relative">
                    <Link2 className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[#8E95A0]" />
                    <input
                      id="event-import-url"
                      name="source_url"
                      type="url"
                      value={sourceUrl}
                      disabled={uploadMutation.isPending}
                      onChange={(e) => setSourceUrl(e.target.value)}
                      placeholder="https://forum-example.ru/program"
                      className="h-9 w-full rounded-[6px] border border-[#262D35] bg-[#12161A] pl-8 pr-3 text-xs text-white placeholder:text-[#8E95A0] [color-scheme:dark] outline-none focus:border-[#E5C378] focus:shadow-[0_0_0_1px_rgba(229,195,120,0.25)] transition-colors"
                    />
                  </div>
                </div>

                {/* Сырой текст */}
                <div>
                  <label
                    htmlFor="event-import-text"
                    className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-[#8E95A0]"
                  >
                    Текстовый конспект, программа или условия тарифов
                  </label>
                  <textarea
                    id="event-import-text"
                    name="raw_text"
                    rows={4}
                    value={rawText}
                    disabled={uploadMutation.isPending}
                    onChange={(e) => setRawText(e.target.value)}
                    placeholder="Вставьте описание площадки, расценки участия (делегат/спикер/стенд) и дедлайны скидок..."
                    className="w-full rounded-[6px] border border-[#262D35] bg-[#12161A] p-2.5 text-xs leading-relaxed text-white placeholder:text-[#8E95A0] [color-scheme:dark] outline-none focus:border-[#E5C378] focus:shadow-[0_0_0_1px_rgba(229,195,120,0.25)] transition-colors scrollbar-thin"
                  />
                </div>

                <div className="flex items-center justify-end gap-2 border-t border-[#21262F] pt-3">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={uploadMutation.isPending}
                    onClick={onClose}
                    className="border-[#262D35] bg-[#12161A] text-xs text-[#D1D5DB] hover:border-[#E5C378] hover:text-white"
                  >
                    {uploadResult ? "Закрыть" : "Отмена"}
                  </Button>
                  <Button
                    type="submit"
                    variant="monolith"
                    size="sm"
                    disabled={uploadMutation.isPending}
                    className="text-xs font-semibold px-4"
                  >
                    {uploadMutation.isPending ? (
                      <>
                        <Loader2 className="h-3.5 w-3.5 animate-spin text-[#E5C378]" />
                        <span>Структурирование через ИИ...</span>
                      </>
                    ) : (
                      <>
                        <Upload className="h-3.5 w-3.5 text-[#E5C378] monolith-icon" />
                        <span>Распознать и сохранить</span>
                      </>
                    )}
                  </Button>
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
