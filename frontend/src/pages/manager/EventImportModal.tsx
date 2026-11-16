import * as React from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  X,
  Upload,
  FileText,
  Link2,
  AlignLeft,
  Layers,
  Loader2,
  CheckCircle2,
  Check,
  AlertCircle,
  Trash2,
  ArrowRight,
  RefreshCw,
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
  initialFile?: File | null;
  onSuccess?: (result: EventUploadOut) => void;
  onOpenEventDetails?: (eventId: number) => void;
}

type SourceTab = "pdf" | "url" | "text" | "all";

interface TextTemplate {
  id: string;
  label: string;
  snippet: string;
}

const TEXT_TEMPLATES: TextTemplate[] = [
  {
    id: "tariffs",
    label: "+ Тарифы / Early Bird",
    snippet:
      "Тарифы участия:\n- Делегат (Standard): ___ руб. (Early Bird до __.__.2026: ___ руб.)\n- Спикер / Партнёр: ___ руб.\n- Выставочный стенд: ___ руб.\nЧто включено: ",
  },
  {
    id: "program",
    label: "+ Даты и площадка",
    snippet:
      "Мероприятие: \nДаты проведения: __–__.__.2026\nГород и площадка: \nКлючевые темы и аудитория: ",
  },
  {
    id: "terms",
    label: "+ Условия спикера / стенда",
    snippet:
      "Условия для спикера / экспонента:\n- Длительность слота: ___ мин\n- Требования к заявке / дедлайн: \n- Бонусы и проходки для команды: ",
  },
];

const PIPELINE_STEPS = [
  { id: 1, label: "Подготовка и чтение материалов" },
  { id: 2, label: "Извлечение структуры и тарифов через ИИ" },
  { id: 3, label: "Проверка дублей и сохранение в базу" },
];

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

function formatElapsed(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

export function EventImportModal({
  isOpen,
  onClose,
  initialSourceUrl = null,
  initialEventTitle = null,
  initialFile = null,
  onSuccess,
  onOpenEventDetails,
}: EventImportModalProps) {
  const uploadMutation = useUploadEventPdfMutation();

  const [mounted, setMounted] = React.useState(false);
  const [activeTab, setActiveTab] = React.useState<SourceTab>("pdf");
  const [selectedFile, setSelectedFile] = React.useState<File | null>(null);
  const [sourceUrl, setSourceUrl] = React.useState("");
  const [rawText, setRawText] = React.useState("");
  const [isDragging, setIsDragging] = React.useState(false);
  const [formError, setFormError] = React.useState<string | null>(null);
  const [uploadResult, setUploadResult] = React.useState<EventUploadOut | null>(
    null
  );
  const [elapsedSeconds, setElapsedSeconds] = React.useState(0);

  const fileInputRef = React.useRef<HTMLInputElement>(null);
  const textAreaRef = React.useRef<HTMLTextAreaElement>(null);

  React.useEffect(() => {
    setMounted(true);
  }, []);

  React.useEffect(() => {
    if (!isOpen) return;
    const trimmedInitialUrl = initialSourceUrl?.trim() || "";
    setSelectedFile(initialFile ?? null);
    setSourceUrl(trimmedInitialUrl);
    setRawText("");
    setFormError(null);
    setUploadResult(null);
    setIsDragging(false);
    setElapsedSeconds(0);

    if (initialFile) {
      setActiveTab("pdf");
    } else if (trimmedInitialUrl) {
      setActiveTab("url");
    } else {
      setActiveTab("pdf");
    }
  }, [isOpen, initialSourceUrl, initialFile]);

  React.useEffect(() => {
    if (!uploadMutation.isPending) {
      setElapsedSeconds(0);
      return;
    }
    const timer = window.setInterval(() => {
      setElapsedSeconds((prev) => prev + 1);
    }, 1000);
    return () => window.clearInterval(timer);
  }, [uploadMutation.isPending]);

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

  const trimmedUrl = sourceUrl.trim();
  const trimmedText = rawText.trim();
  const hasPdf = Boolean(selectedFile);
  const hasUrl = trimmedUrl.length > 0;
  const isUrlValid = hasUrl && isValidHttpUrl(trimmedUrl);
  const hasText = trimmedText.length > 0;
  const filledSourcesCount = [hasPdf, hasUrl, hasText].filter(Boolean).length;

  const activePipelineStep = !uploadMutation.isPending
    ? 0
    : elapsedSeconds < 2
      ? 1
      : elapsedSeconds < 8
        ? 2
        : 3;

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
    e.stopPropagation();
    setIsDragging(false);
    if (uploadMutation.isPending) return;
    acceptFile(e.dataTransfer.files?.[0]);
  };

  const handleInsertTemplate = (snippet: string) => {
    setFormError(null);
    setRawText((prev) => {
      const cleanPrev = prev.trimEnd();
      return cleanPrev ? `${cleanPrev}\n\n${snippet}` : snippet;
    });
    window.requestAnimationFrame(() => {
      textAreaRef.current?.focus();
    });
  };

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setFormError(null);
    setUploadResult(null);

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

  const tabs: Array<{
    id: SourceTab;
    label: string;
    icon: React.ReactNode;
    isFilled: boolean;
    badgeText?: string;
  }> = [
    {
      id: "pdf",
      label: "PDF-документ",
      icon: <FileText className="h-3.5 w-3.5" />,
      isFilled: hasPdf,
    },
    {
      id: "url",
      label: "По ссылке (URL)",
      icon: <Link2 className="h-3.5 w-3.5" />,
      isFilled: isUrlValid,
    },
    {
      id: "text",
      label: "Из текста",
      icon: <AlignLeft className="h-3.5 w-3.5" />,
      isFilled: hasText,
    },
    {
      id: "all",
      label: "Всё вместе",
      icon: <Layers className="h-3.5 w-3.5" />,
      isFilled: filledSourcesCount > 0,
      badgeText: filledSourcesCount > 0 ? `${filledSourcesCount}/3` : undefined,
    },
  ];

  const renderPdfField = (compact: boolean) => (
    <div>
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <label
          htmlFor="event-import-file"
          className="block text-[11px] font-semibold uppercase tracking-wider text-[#8E95A0]"
        >
          PDF-брошюра / регламент
        </label>
        {selectedFile && (
          <span className="text-[11px] text-[#34D399] font-medium">
            ✓ Прикреплён
          </span>
        )}
      </div>

      {selectedFile ? (
        <div className="rounded-[8px] border border-[#7C5A20] bg-[#1E190E] p-3 text-xs">
          <div className="flex items-start justify-between gap-2.5">
            <div className="flex items-start gap-2.5 min-w-0">
              <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-[6px] border border-[#7C5A20]/60 bg-[#12161A]">
                <FileText className="h-4 w-4 text-[#E5C378]" />
              </div>
              <div className="min-w-0">
                <p className="truncate font-medium text-white">
                  {selectedFile.name}
                </p>
                <p className="mt-0.5 text-[11px] text-[#8E95A0] tabular-nums">
                  PDF-документ · {formatFileSize(selectedFile.size)}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-1 shrink-0">
              <button
                type="button"
                disabled={uploadMutation.isPending}
                onClick={() => fileInputRef.current?.click()}
                className="inline-flex items-center gap-1 rounded-[5px] border border-[#7C5A20]/50 bg-[#12161A] px-2 py-1 text-[11px] text-[#E5C378] hover:border-[#E5C378] hover:text-white transition-colors disabled:opacity-50"
                title="Заменить PDF-файл"
              >
                <RefreshCw className="h-3 w-3" />
                <span>Заменить</span>
              </button>
              <button
                type="button"
                disabled={uploadMutation.isPending}
                onClick={() => setSelectedFile(null)}
                aria-label="Убрать PDF-файл"
                className="rounded-[5px] border border-[#262D35] bg-[#12161A] p-1.5 text-[#8E95A0] hover:border-[#EF4444]/50 hover:text-[#EF4444] transition-colors disabled:opacity-50"
                title="Убрать файл"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
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
            "flex cursor-pointer flex-col items-center justify-center rounded-[8px] border border-dashed px-4 text-center transition-colors",
            compact ? "py-4" : "py-8",
            isDragging
              ? "border-[#E5C378] bg-[#1E190E]"
              : "border-[#38414F] bg-[#12161A] hover:border-[#E5C378] hover:bg-[#161B21]"
          )}
        >
          <div className="flex h-10 w-10 items-center justify-center rounded-full border border-[#7C5A20]/50 bg-[#1E190E]">
            <Upload className="h-5 w-5 text-[#E5C378]" strokeWidth={1.75} />
          </div>
          <p className="mt-2.5 text-xs font-medium text-[#D1D5DB]">
            Перетащите PDF сюда или{" "}
            <span className="text-[#E5C378] underline underline-offset-2">
              выберите файл
            </span>
          </p>
          <p className="mt-1 text-[11px] text-[#8E95A0]">
            Брошюры, медиакиты, прайс-листы и регламенты участия (.pdf)
          </p>
        </div>
      )}
    </div>
  );

  const renderUrlField = () => (
    <div>
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <label
          htmlFor="event-import-url"
          className="block text-[11px] font-semibold uppercase tracking-wider text-[#8E95A0]"
        >
          Ссылка на страницу события (URL)
        </label>
        {hasUrl && (
          <span
            className={cn(
              "text-[11px] font-medium",
              isUrlValid ? "text-[#34D399]" : "text-[#E59837]"
            )}
          >
            {isUrlValid ? "✓ Протокол корректен" : "Требуется http:// или https://"}
          </span>
        )}
      </div>
      <div className="relative">
        <Link2 className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[#8E95A0]" />
        <input
          id="event-import-url"
          name="source_url"
          type="url"
          aria-label="Ссылка на страницу события (URL)"
          value={sourceUrl}
          disabled={uploadMutation.isPending}
          onChange={(e) => {
            setSourceUrl(e.target.value);
            setFormError(null);
          }}
          placeholder="https://forum-example.ru/program"
          className={cn(
            "h-9 w-full rounded-[6px] border bg-[#12161A] pl-8 pr-8 text-xs text-white placeholder:text-[#8E95A0] [color-scheme:dark] outline-none transition-colors",
            hasUrl && !isUrlValid
              ? "border-[#E59837]/70 focus:border-[#E59837]"
              : "border-[#262D35] focus:border-[#E5C378] focus:shadow-[0_0_0_1px_rgba(229,195,120,0.25)]"
          )}
        />
        {hasUrl && (
          <button
            type="button"
            disabled={uploadMutation.isPending}
            onClick={() => setSourceUrl("")}
            aria-label="Очистить URL"
            className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-[#8E95A0] hover:text-white transition-colors"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
    </div>
  );

  const renderTextField = (rows: number) => (
    <div>
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <label
          htmlFor="event-import-text"
          className="block text-[11px] font-semibold uppercase tracking-wider text-[#8E95A0]"
        >
          Текстовый конспект, программа или прайс
        </label>
        {hasText && (
          <span className="text-[11px] text-[#8E95A0] tabular-nums">
            {trimmedText.length} симв.
          </span>
        )}
      </div>

      <div className="mb-2 flex flex-wrap gap-1.5">
        {TEXT_TEMPLATES.map((tpl) => (
          <button
            key={tpl.id}
            type="button"
            disabled={uploadMutation.isPending}
            onClick={() => handleInsertTemplate(tpl.snippet)}
            className="rounded-[5px] border border-[#7C5A20]/50 bg-[#1E190E] px-2 py-1 text-[11px] font-medium text-[#E5C378] hover:border-[#E5C378] hover:bg-[#261E0F] hover:text-white transition-colors disabled:opacity-50 cursor-pointer"
          >
            {tpl.label}
          </button>
        ))}
      </div>

      <textarea
        ref={textAreaRef}
        id="event-import-text"
        name="raw_text"
        aria-label="Текстовый конспект, программа или прайс"
        rows={rows}
        value={rawText}
        disabled={uploadMutation.isPending}
        onChange={(e) => {
          setRawText(e.target.value);
          setFormError(null);
        }}
        placeholder="Вставьте переписку с организатором, прайс-лист (делегат/спикер/стенд), дедлайны Early Bird и условия..."
        className="w-full rounded-[6px] border border-[#262D35] bg-[#12161A] p-2.5 text-xs leading-relaxed text-white placeholder:text-[#8E95A0] [color-scheme:dark] outline-none focus:border-[#E5C378] focus:shadow-[0_0_0_1px_rgba(229,195,120,0.25)] transition-colors scrollbar-thin"
      />
    </div>
  );

  return createPortal(
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-[10000] flex items-center justify-center p-3 sm:p-4">
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
            initial={{ opacity: 0, scale: 0.96, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 8 }}
            transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
            className="relative z-10 w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-[10px] border border-[#7C5A20] bg-[#161B22] text-white shadow-[0_25px_60px_-15px_rgba(0,0,0,0.9),0_0_24px_rgba(229,195,120,0.12)] scrollbar-thin"
          >
            {/* Шапка модалки */}
            <div className="sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-[#21262F] bg-[#12161A] px-4 py-3 sm:px-5">
              <div className="flex items-center gap-2 min-w-0">
                <span
                  className="text-[#E5C378] text-xs not-italic leading-none select-none shrink-0"
                  aria-hidden="true"
                >
                  ✦
                </span>
                <h2 className="truncate font-serif italic text-base font-semibold tracking-tight text-[#E5C378]">
                  {initialEventTitle
                    ? "Сборщик досье · Обогащение площадки"
                    : "Сборщик досье · Импорт площадки"}
                </h2>
              </div>

              <button
                type="button"
                disabled={uploadMutation.isPending}
                onClick={onClose}
                aria-label="Закрыть окно"
                className="shrink-0 rounded-[6px] border border-[#7C5A20]/40 bg-[#161B22] p-1.5 text-[#E5C378] transition-all duration-150 hover:border-[#E5C378] hover:bg-[#261E0F] hover:text-white disabled:opacity-50 outline-none"
              >
                <X className="h-4 w-4 stroke-[2]" />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="space-y-3.5 p-4 sm:p-5" noValidate>
              {/* Скрытый input для выбора PDF-файла, доступный из любой вкладки */}
              <input
                ref={fileInputRef}
                id="event-import-file"
                name="file"
                type="file"
                accept=".pdf,application/pdf"
                aria-label="Загрузить PDF-брошюру"
                disabled={uploadMutation.isPending}
                onChange={(e) => {
                  acceptFile(e.target.files?.[0]);
                  e.target.value = "";
                }}
                className="hidden"
              />

              {initialEventTitle && (
                <div className="flex items-center justify-between gap-2 rounded-[6px] border border-[#7C5A20]/50 bg-[#1E190E] px-3 py-2 text-xs">
                  <span className="shrink-0 text-[11px] uppercase tracking-wider text-[#E5C378]/80">
                    Целевое событие
                  </span>
                  <span className="truncate font-medium text-white">
                    {initialEventTitle}
                  </span>
                </div>
              )}

              {formError && (
                <div
                  role="alert"
                  className="flex items-start gap-2 rounded-[6px] border border-[#EA4335]/40 bg-[#EA4335]/10 px-3 py-2 text-xs text-[#FCA5A5]"
                >
                  <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#F87171]" />
                  <span>{formError}</span>
                </div>
              )}

              {/* Переключатель вкладок */}
              <div
                role="tablist"
                aria-label="Источники импорта площадки"
                className="grid grid-cols-2 gap-1.5 rounded-[8px] border border-[#262D35] bg-[#0B0E12] p-1 sm:grid-cols-4"
              >
                {tabs.map((tab) => {
                  const isActive = activeTab === tab.id;
                  return (
                    <button
                      key={tab.id}
                      type="button"
                      role="tab"
                      aria-selected={isActive}
                      disabled={uploadMutation.isPending}
                      onClick={() => setActiveTab(tab.id)}
                      className={cn(
                        "flex items-center justify-center gap-1.5 rounded-[6px] px-2 py-1.5 text-[11px] font-medium transition-all cursor-pointer disabled:opacity-60",
                        isActive
                          ? "border border-[#7C5A20] bg-[#1E190E] text-[#E5C378] shadow-xs"
                          : "border border-transparent text-[#8E95A0] hover:bg-[#161B22] hover:text-white"
                      )}
                    >
                      {tab.icon}
                      <span className="truncate">{tab.label}</span>
                      {tab.isFilled && (
                        <span
                          className={cn(
                            "inline-flex items-center justify-center text-[11px] font-semibold",
                            tab.badgeText
                              ? "rounded bg-[#34D399]/15 px-1 text-[#34D399] tabular-nums"
                              : "text-[#34D399]"
                          )}
                          title="Источник заполнен"
                        >
                          {tab.badgeText ?? "✓"}
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>

              {/* Блок ввода активной вкладки */}
              <div className="rounded-[8px] border border-[#262D35] bg-[#0B0E12]/60 p-3.5">
                {activeTab === "pdf" && renderPdfField(false)}
                {activeTab === "url" && renderUrlField()}
                {activeTab === "text" && renderTextField(6)}
                {activeTab === "all" && (
                  <div className="space-y-4">
                    {renderPdfField(true)}
                    <div className="border-t border-[#21262F] pt-3.5">
                      {renderUrlField()}
                    </div>
                    <div className="border-t border-[#21262F] pt-3.5">
                      {renderTextField(4)}
                    </div>
                  </div>
                )}
              </div>

              {/* Компактная горизонтальная строка статуса источников */}
              <div className="flex flex-wrap items-center justify-between gap-2 rounded-[8px] border border-[#21262F] bg-[#12161A] px-3 py-2">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-[#8E95A0] tabular-nums">
                  Источники · {filledSourcesCount}/3
                </span>

                <div className="flex flex-wrap items-center gap-1.5">
                  <button
                    type="button"
                    disabled={uploadMutation.isPending}
                    onClick={() => setActiveTab("pdf")}
                    className={cn(
                      "inline-flex max-w-[220px] items-center gap-1.5 rounded-[6px] border px-2.5 py-1 text-[11px] font-medium transition-colors cursor-pointer disabled:opacity-60",
                      hasPdf
                        ? "border-[#34D399]/50 bg-[#0E241E] text-[#34D399]"
                        : activeTab === "pdf"
                          ? "border-[#7C5A20] bg-[#1E190E] text-[#E5C378]"
                          : "border-[#262D35] bg-[#0B0E12] text-[#8E95A0] hover:border-[#38414F] hover:text-white"
                    )}
                    title={selectedFile ? `${selectedFile.name} · ${formatFileSize(selectedFile.size)}` : "Перейти к загрузке PDF"}
                  >
                    {hasPdf ? (
                      <Check className="h-3 w-3 shrink-0 stroke-[2.5]" />
                    ) : (
                      <FileText className="h-3 w-3 shrink-0" />
                    )}
                    <span className="truncate tabular-nums">
                      {selectedFile
                        ? `${selectedFile.name} (${formatFileSize(selectedFile.size)})`
                        : "PDF-файл"}
                    </span>
                  </button>

                  <button
                    type="button"
                    disabled={uploadMutation.isPending}
                    onClick={() => setActiveTab("url")}
                    className={cn(
                      "inline-flex items-center gap-1.5 rounded-[6px] border px-2.5 py-1 text-[11px] font-medium transition-colors cursor-pointer disabled:opacity-60",
                      isUrlValid
                        ? "border-[#34D399]/50 bg-[#0E241E] text-[#34D399]"
                        : hasUrl
                          ? "border-[#E59837]/60 bg-[#22160C] text-[#E59837]"
                          : activeTab === "url"
                            ? "border-[#7C5A20] bg-[#1E190E] text-[#E5C378]"
                            : "border-[#262D35] bg-[#0B0E12] text-[#8E95A0] hover:border-[#38414F] hover:text-white"
                    )}
                    title={hasUrl ? trimmedUrl : "Перейти к вводу URL"}
                  >
                    {isUrlValid ? (
                      <Check className="h-3 w-3 shrink-0 stroke-[2.5]" />
                    ) : (
                      <Link2 className="h-3 w-3 shrink-0" />
                    )}
                    <span>URL</span>
                  </button>

                  <button
                    type="button"
                    disabled={uploadMutation.isPending}
                    onClick={() => setActiveTab("text")}
                    className={cn(
                      "inline-flex items-center gap-1.5 rounded-[6px] border px-2.5 py-1 text-[11px] font-medium transition-colors cursor-pointer disabled:opacity-60",
                      hasText
                        ? "border-[#34D399]/50 bg-[#0E241E] text-[#34D399]"
                        : activeTab === "text"
                          ? "border-[#7C5A20] bg-[#1E190E] text-[#E5C378]"
                          : "border-[#262D35] bg-[#0B0E12] text-[#8E95A0] hover:border-[#38414F] hover:text-white"
                    )}
                    title="Перейти к текстовому конспекту"
                  >
                    {hasText ? (
                      <Check className="h-3 w-3 shrink-0 stroke-[2.5]" />
                    ) : (
                      <AlignLeft className="h-3 w-3 shrink-0" />
                    )}
                    <span className="tabular-nums">
                      {hasText ? `Текст (${trimmedText.length})` : "Текст"}
                    </span>
                  </button>
                </div>
              </div>

              {/* Условный блок: шаги обработки ИИ или карточка результата */}
              {uploadMutation.isPending ? (
                <div className="rounded-[8px] border border-[#7C5A20]/60 bg-[#1E190E]/70 p-3 space-y-2.5">
                  <div className="flex items-center justify-between gap-2">
                    <span className="flex items-center gap-1.5 text-xs font-semibold text-[#E5C378]">
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      <span>Обработка досье...</span>
                    </span>
                    <span className="text-[11px] font-mono text-[#E5C378] tabular-nums">
                      {formatElapsed(elapsedSeconds)}
                    </span>
                  </div>
                  <ol className="space-y-1.5 text-[11px]">
                    {PIPELINE_STEPS.map((step) => {
                      const isDone = activePipelineStep > step.id;
                      const isCurrent = activePipelineStep === step.id;
                      return (
                        <li
                          key={step.id}
                          className={cn(
                            "flex items-center gap-2 transition-colors",
                            isDone
                              ? "text-[#34D399]"
                              : isCurrent
                                ? "text-white font-medium"
                                : "text-[#8E95A0]"
                          )}
                        >
                          <span
                            className={cn(
                              "flex h-4 w-4 shrink-0 items-center justify-center rounded-full border text-[11px] tabular-nums",
                              isDone
                                ? "border-[#34D399]/60 bg-[#34D399]/15 text-[#34D399]"
                                : isCurrent
                                  ? "border-[#E5C378] bg-[#E5C378]/15 text-[#E5C378]"
                                  : "border-[#262D35] text-[#8E95A0]"
                            )}
                          >
                            {isDone ? (
                              <Check className="h-2.5 w-2.5 stroke-[2.5]" />
                            ) : (
                              step.id
                            )}
                          </span>
                          <span>{step.label}</span>
                        </li>
                      );
                    })}
                  </ol>
                </div>
              ) : uploadResult ? (
                <div className="rounded-[8px] border border-[#1E5241] bg-[#0E241E]/90 p-3 text-xs space-y-2.5">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-start gap-1.5 font-semibold text-[#34D399] min-w-0">
                      <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
                      <span className="leading-snug">
                        {uploadResult.canonical_title}
                      </span>
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
                        ? "Готово к КП"
                        : "Требует обогащения"}
                    </Badge>
                  </div>

                  <p className="text-[11px] text-[#D1D5DB] leading-relaxed">
                    {uploadResult.message}
                  </p>

                  <div className="flex items-center justify-between rounded-[6px] border border-[#1E5241]/80 bg-[#0B0E12]/60 px-2.5 py-1.5 text-[11px]">
                    <span className="text-[#8E95A0]">Извлечено тарифов:</span>
                    <strong className="text-white font-semibold tabular-nums">
                      {uploadResult.tariffs_count}{" "}
                      {pluralizeRu(uploadResult.tariffs_count, [
                        "тариф",
                        "тарифа",
                        "тарифов",
                      ])}
                    </strong>
                  </div>

                  {onOpenEventDetails && (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        const eventId = uploadResult.event_id;
                        onClose();
                        onOpenEventDetails(eventId);
                      }}
                      className="w-full h-8 border-[#34D399]/50 bg-[#12161A] text-xs font-semibold text-[#34D399] hover:border-[#34D399] hover:bg-[#1E5241]/40 hover:text-white"
                    >
                      <span>Открыть паспорт площадки</span>
                      <ArrowRight className="h-3.5 w-3.5" />
                    </Button>
                  )}
                </div>
              ) : null}

              {/* Компактный футер */}
              <div className="flex flex-col-reverse gap-2 border-t border-[#21262F] pt-3 sm:flex-row sm:items-center sm:justify-end">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={uploadMutation.isPending}
                  onClick={onClose}
                  className="border-[#262D35] bg-[#161B22] text-xs text-[#D1D5DB] hover:border-[#E5C378] hover:text-white"
                >
                  {uploadResult ? "Закрыть" : "Отмена"}
                </Button>
                <Button
                  type="submit"
                  variant="monolith"
                  size="sm"
                  disabled={uploadMutation.isPending || filledSourcesCount === 0}
                  className="text-xs font-semibold px-4"
                >
                  {uploadMutation.isPending ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 animate-spin text-[#E5C378]" />
                      <span>Распознаём...</span>
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
          </motion.div>
        </div>
      )}
    </AnimatePresence>,
    document.body
  );
}
