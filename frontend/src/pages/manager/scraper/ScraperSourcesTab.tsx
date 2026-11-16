import * as React from "react";
import {
  AlertCircle,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  Loader2,
  Pencil,
  Play,
  Plus,
  Power,
  Search,
  Trash2,
  X,
} from "lucide-react";
import { toast } from "sonner";
import { ApiError } from "@/api/client";
import {
  useCreateScraperSourceMutation,
  useDeleteScraperSourceMutation,
  usePreviewScraperSourceMutation,
  useUpdateScraperSourceMutation,
} from "@/api/queries";
import type {
  ScraperAdapterType,
  ScraperSourceOut,
  ScraperSourcePreviewOut,
} from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CustomSelect } from "@/components/ui/custom-select";
import { cn } from "@/lib/utils";
import {
  ADAPTER_LABELS,
  ADAPTER_OPTIONS,
  parseMultilineValues,
} from "./scraperFormatters";

interface ScraperSourcesTabProps {
  sources: ScraperSourceOut[];
  isLoading: boolean;
  onQuickRunSource: (sourceKey: string) => void;
}

interface SourceFormState {
  mode: "create" | "edit";
  editingKey: string | null;
  displayName: string;
  catalogUrlsText: string;
  adapterType: ScraperAdapterType;
  b2bFilterEnabled: boolean;
  russiaOnlineOnly: boolean;
  sourceKey: string;
  cardPatternsText: string;
  excludePatternsText: string;
  useJinaReader: boolean;
  encoding: string;
  maxUrlsPerRun: string;
  isEnabled: boolean;
}

function createInitialFormState(source?: ScraperSourceOut): SourceFormState {
  if (!source) {
    return {
      mode: "create",
      editingKey: null,
      displayName: "",
      catalogUrlsText: "",
      adapterType: "html_list",
      b2bFilterEnabled: false,
      russiaOnlineOnly: true,
      sourceKey: "",
      cardPatternsText: "",
      excludePatternsText: "",
      useJinaReader: false,
      encoding: "utf-8",
      maxUrlsPerRun: "10",
      isEnabled: true,
    };
  }
  return {
    mode: "edit",
    editingKey: source.source_key,
    displayName: source.display_name,
    catalogUrlsText: source.catalog_urls.join("\n"),
    adapterType: source.adapter_type,
    b2bFilterEnabled: source.b2b_filter_enabled,
    russiaOnlineOnly: source.russia_online_only,
    sourceKey: source.source_key,
    cardPatternsText: source.card_url_patterns.join("\n"),
    excludePatternsText: source.exclude_url_patterns.join("\n"),
    useJinaReader: source.use_jina_reader,
    encoding: source.encoding || "utf-8",
    maxUrlsPerRun: String(source.max_urls_per_run ?? 10),
    isEnabled: source.is_enabled,
  };
}

export function ScraperSourcesTab({
  sources,
  isLoading,
  onQuickRunSource,
}: ScraperSourcesTabProps) {
  const createMutation = useCreateScraperSourceMutation();
  const updateMutation = useUpdateScraperSourceMutation();
  const deleteMutation = useDeleteScraperSourceMutation();
  const previewMutation = usePreviewScraperSourceMutation();

  const [formState, setFormState] = React.useState<SourceFormState | null>(
    null
  );
  const [showAdvanced, setShowAdvanced] = React.useState(false);
  const [formError, setFormError] = React.useState<string | null>(null);
  const [previewResult, setPreviewResult] =
    React.useState<ScraperSourcePreviewOut | null>(null);
  const [togglingKey, setTogglingKey] = React.useState<string | null>(null);
  const [confirmDeleteKey, setConfirmDeleteKey] = React.useState<string | null>(
    null
  );

  const isFormSubmitting =
    createMutation.isPending || updateMutation.isPending;

  const openCreateForm = () => {
    setFormState(createInitialFormState());
    setShowAdvanced(false);
    setFormError(null);
    setPreviewResult(null);
  };

  const openEditForm = (source: ScraperSourceOut) => {
    const nextState = createInitialFormState(source);
    setFormState(nextState);
    const hasCustomAdvanced =
      source.card_url_patterns.length > 0 ||
      source.exclude_url_patterns.length > 0 ||
      source.use_jina_reader ||
      source.encoding !== "utf-8" ||
      source.max_urls_per_run !== 10;
    setShowAdvanced(hasCustomAdvanced);
    setFormError(null);
    setPreviewResult(null);
  };

  const closeForm = () => {
    if (isFormSubmitting || previewMutation.isPending) return;
    setFormState(null);
    setFormError(null);
    setPreviewResult(null);
  };

  const handleToggleEnabled = async (source: ScraperSourceOut) => {
    setTogglingKey(source.source_key);
    try {
      const updated = await updateMutation.mutateAsync({
        sourceKey: source.source_key,
        payload: { is_enabled: !source.is_enabled },
      });
      toast.success(
        updated.is_enabled
          ? `Площадка «${updated.display_name}» включена.`
          : `Площадка «${updated.display_name}» отключена.`
      );
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.detail
          : "Не удалось обновить статус площадки.";
      toast.error(msg);
    } finally {
      setTogglingKey(null);
    }
  };

  const handleConfirmDelete = async (source: ScraperSourceOut) => {
    try {
      await deleteMutation.mutateAsync(source.source_key);
      toast.success(`Площадка «${source.display_name}» удалена.`);
      setConfirmDeleteKey(null);
      if (formState?.editingKey === source.source_key) {
        setFormState(null);
      }
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.detail : "Не удалось удалить площадку.";
      toast.error(msg);
    }
  };

  const handlePreview = async () => {
    if (!formState) return;
    setFormError(null);
    setPreviewResult(null);

    const catalogUrls = parseMultilineValues(formState.catalogUrlsText);
    if (catalogUrls.length === 0) {
      const msg = "Укажите хотя бы один URL каталога или RSS для проверки.";
      setFormError(msg);
      toast.error(msg);
      return;
    }

    try {
      const res = await previewMutation.mutateAsync({
        catalog_urls: catalogUrls,
        adapter_type: formState.adapterType,
        card_url_patterns: parseMultilineValues(formState.cardPatternsText),
        exclude_url_patterns: parseMultilineValues(
          formState.excludePatternsText
        ),
        b2b_filter_enabled: formState.b2bFilterEnabled,
        russia_online_only: formState.russiaOnlineOnly,
        use_jina_reader: formState.useJinaReader,
        encoding: formState.encoding.trim() || "utf-8",
      });
      setPreviewResult(res);
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.detail
          : err instanceof Error
            ? err.message
            : "Не удалось выполнить предпросмотр ссылок.";
      setFormError(msg);
      toast.error(msg);
    }
  };

  const handleSaveForm = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formState) return;
    setFormError(null);

    const displayName = formState.displayName.trim();
    if (displayName.length < 2) {
      setFormError("Название площадки должно содержать минимум 2 символа.");
      return;
    }

    const catalogUrls = parseMultilineValues(formState.catalogUrlsText);
    if (catalogUrls.length === 0) {
      setFormError("Укажите хотя бы один URL каталога или RSS.");
      return;
    }

    const maxUrlsNum = Number(formState.maxUrlsPerRun.trim() || "10");
    if (
      !Number.isInteger(maxUrlsNum) ||
      maxUrlsNum < 1 ||
      maxUrlsNum > 50
    ) {
      setFormError("Лимит новых URL за запуск должен быть целым числом от 1 до 50.");
      return;
    }

    const cardPatterns = parseMultilineValues(formState.cardPatternsText);
    const excludePatterns = parseMultilineValues(formState.excludePatternsText);
    const encodingVal = formState.encoding.trim() || "utf-8";

    try {
      if (formState.mode === "create") {
        const created = await createMutation.mutateAsync({
          display_name: displayName,
          catalog_urls: catalogUrls,
          adapter_type: formState.adapterType,
          b2b_filter_enabled: formState.b2bFilterEnabled,
          russia_online_only: formState.russiaOnlineOnly,
          source_key: formState.sourceKey.trim() || null,
          card_url_patterns: cardPatterns,
          exclude_url_patterns: excludePatterns,
          use_jina_reader: formState.useJinaReader,
          encoding: encodingVal,
          max_urls_per_run: maxUrlsNum,
          is_enabled:
            formState.adapterType === "manual_only"
              ? false
              : formState.isEnabled,
        });
        toast.success(`Площадка «${created.display_name}» добавлена.`);
        setFormState(null);
        setPreviewResult(null);
      } else if (formState.editingKey) {
        const isArchdialog = formState.editingKey === "archdialog";
        const updated = await updateMutation.mutateAsync({
          sourceKey: formState.editingKey,
          payload: {
            display_name: displayName,
            catalog_urls: catalogUrls,
            ...(isArchdialog ? {} : { adapter_type: formState.adapterType }),
            b2b_filter_enabled: formState.b2bFilterEnabled,
            russia_online_only: formState.russiaOnlineOnly,
            card_url_patterns: cardPatterns,
            exclude_url_patterns: excludePatterns,
            use_jina_reader: formState.useJinaReader,
            encoding: encodingVal,
            max_urls_per_run: maxUrlsNum,
            is_enabled:
              formState.adapterType === "manual_only"
                ? false
                : formState.isEnabled,
          },
        });
        toast.success(`Настройки площадки «${updated.display_name}» сохранены.`);
        setFormState(null);
        setPreviewResult(null);
      }
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.detail
          : err instanceof Error
            ? err.message
            : "Не удалось сохранить настройки площадки.";
      setFormError(msg);
      toast.error(msg);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-xs text-[#8E95A0]">
          Всего площадок в базе:{" "}
          <strong className="text-white tabular-nums">{sources.length}</strong>
        </div>

        <Button
          type="button"
          variant="monolith"
          size="sm"
          onClick={openCreateForm}
          className="h-8 px-3 text-xs font-semibold cursor-pointer"
        >
          <Plus className="h-3.5 w-3.5 text-[#E5C378] monolith-icon" />
          <span>Добавить площадку</span>
        </Button>
      </div>

      {/* Форма создания / редактирования */}
      {formState && (
        <form
          onSubmit={handleSaveForm}
          className="rounded-[8px] border border-[#7C5A20] bg-[#12161A] p-4 space-y-3.5 shadow-[0_12px_30px_rgba(0,0,0,0.45)]"
        >
          <div className="flex items-center justify-between border-b border-[#21262F] pb-2.5">
            <h3 className="font-serif italic text-sm font-semibold text-[#E5C378]">
              {formState.mode === "create"
                ? "Новая площадка мониторинга"
                : `Редактирование: ${formState.displayName || formState.editingKey}`}
            </h3>
            <button
              type="button"
              onClick={closeForm}
              disabled={isFormSubmitting || previewMutation.isPending}
              aria-label="Закрыть форму"
              className="rounded-[4px] p-1 text-[#8E95A0] hover:bg-[#1E252E] hover:text-white transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-[1fr_220px] gap-3">
            <div>
              <label
                htmlFor="source-form-display-name"
                className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-[#8E95A0]"
              >
                Название площадки *
              </label>
              <input
                id="source-form-display-name"
                type="text"
                required
                value={formState.displayName}
                onChange={(e) =>
                  setFormState((prev) =>
                    prev ? { ...prev, displayName: e.target.value } : prev
                  )
                }
                placeholder="Например, СтройФорум Урал"
                className="h-9 w-full rounded-[6px] border border-[#262D35] bg-[#0E1116] px-3 text-xs text-white placeholder:text-[#6B7280] outline-none focus:border-[#E5C378]"
              />
            </div>

            <div>
              <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-[#8E95A0]">
                Тип адаптера
              </span>
              <CustomSelect<ScraperAdapterType>
                value={formState.adapterType}
                onChange={(val) =>
                  setFormState((prev) =>
                    prev
                      ? {
                          ...prev,
                          adapterType: val,
                          isEnabled:
                            val === "manual_only" ? false : prev.isEnabled,
                        }
                      : prev
                  )
                }
                options={ADAPTER_OPTIONS}
                disabled={
                  isFormSubmitting || formState.editingKey === "archdialog"
                }
                className="w-full"
                buttonClassName="w-full h-9 px-3 text-xs"
                menuClassName="w-full"
              />
              {formState.editingKey === "archdialog" && (
                <p className="mt-1 text-[10px] text-[#E59837]">
                  Для АрхДиалог (Timepad) тип адаптера заблокирован.
                </p>
              )}
            </div>
          </div>

          <div>
            <label
              htmlFor="source-form-catalog-urls"
              className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-[#8E95A0]"
            >
              URL каталога или RSS (по одному в строке) *
            </label>
            <textarea
              id="source-form-catalog-urls"
              rows={2}
              required
              value={formState.catalogUrlsText}
              onChange={(e) =>
                setFormState((prev) =>
                  prev ? { ...prev, catalogUrlsText: e.target.value } : prev
                )
              }
              placeholder="https://example.ru/events/"
              className="w-full rounded-[6px] border border-[#262D35] bg-[#0E1116] px-3 py-2 text-xs text-white font-mono placeholder:text-[#6B7280] outline-none focus:border-[#E5C378]"
            />
          </div>

          <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
            <label className="inline-flex items-center gap-2 text-xs text-[#D1D5DB] cursor-pointer select-none">
              <input
                type="checkbox"
                checked={formState.b2bFilterEnabled}
                onChange={(e) =>
                  setFormState((prev) =>
                    prev
                      ? { ...prev, b2bFilterEnabled: e.target.checked }
                      : prev
                  )
                }
                className="h-4 w-4 rounded border-[#7C5A20] bg-[#0E1116] accent-[#E5C378]"
              />
              <span>Фильтр B2C</span>
            </label>

            <label className="inline-flex items-center gap-2 text-xs text-[#D1D5DB] cursor-pointer select-none">
              <input
                type="checkbox"
                checked={formState.russiaOnlineOnly}
                onChange={(e) =>
                  setFormState((prev) =>
                    prev
                      ? { ...prev, russiaOnlineOnly: e.target.checked }
                      : prev
                  )
                }
                className="h-4 w-4 rounded border-[#7C5A20] bg-[#0E1116] accent-[#E5C378]"
              />
              <span>Только РФ и онлайн</span>
            </label>

            {formState.adapterType !== "manual_only" && (
              <label className="inline-flex items-center gap-2 text-xs text-[#D1D5DB] cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={formState.isEnabled}
                  onChange={(e) =>
                    setFormState((prev) =>
                      prev ? { ...prev, isEnabled: e.target.checked } : prev
                    )
                  }
                  className="h-4 w-4 rounded border-[#7C5A20] bg-[#0E1116] accent-[#E5C378]"
                />
                <span>Активна в мониторинге</span>
              </label>
            )}
          </div>

          {/* Сворачиваемые расширенные настройки */}
          <div className="rounded-[6px] border border-[#21262F] bg-[#0E1116]">
            <button
              type="button"
              onClick={() => setShowAdvanced((prev) => !prev)}
              className="flex w-full items-center justify-between px-3 py-2 text-xs font-medium text-[#D1D5DB] hover:text-[#E5C378] transition-colors cursor-pointer"
            >
              <span>Расширенные настройки (regex, Jina Reader, лимиты)</span>
              {showAdvanced ? (
                <ChevronUp className="h-4 w-4" />
              ) : (
                <ChevronDown className="h-4 w-4" />
              )}
            </button>

            {showAdvanced && (
              <div className="border-t border-[#21262F] p-3 space-y-3">
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div>
                    <label
                      htmlFor="source-form-key"
                      className="mb-1 block text-[11px] font-medium text-[#8E95A0]"
                    >
                      Ключ площадки (source_key)
                    </label>
                    <input
                      id="source-form-key"
                      type="text"
                      value={formState.sourceKey}
                      disabled={formState.mode === "edit"}
                      onChange={(e) =>
                        setFormState((prev) =>
                          prev ? { ...prev, sourceKey: e.target.value } : prev
                        )
                      }
                      placeholder="Авто из названия"
                      className="h-8 w-full rounded-[6px] border border-[#262D35] bg-[#12161A] px-2.5 text-xs font-mono text-white placeholder:text-[#6B7280] disabled:opacity-50 outline-none focus:border-[#E5C378]"
                    />
                  </div>

                  <div>
                    <label
                      htmlFor="source-form-encoding"
                      className="mb-1 block text-[11px] font-medium text-[#8E95A0]"
                    >
                      Кодировка (encoding)
                    </label>
                    <input
                      id="source-form-encoding"
                      type="text"
                      value={formState.encoding}
                      onChange={(e) =>
                        setFormState((prev) =>
                          prev ? { ...prev, encoding: e.target.value } : prev
                        )
                      }
                      placeholder="utf-8"
                      className="h-8 w-full rounded-[6px] border border-[#262D35] bg-[#12161A] px-2.5 text-xs font-mono text-white outline-none focus:border-[#E5C378]"
                    />
                  </div>

                  <div>
                    <label
                      htmlFor="source-form-max-urls"
                      className="mb-1 block text-[11px] font-medium text-[#8E95A0]"
                    >
                      Макс. новых URL за прогон (1–50)
                    </label>
                    <input
                      id="source-form-max-urls"
                      type="number"
                      min={1}
                      max={50}
                      value={formState.maxUrlsPerRun}
                      onChange={(e) =>
                        setFormState((prev) =>
                          prev
                            ? { ...prev, maxUrlsPerRun: e.target.value }
                            : prev
                        )
                      }
                      className="h-8 w-full rounded-[6px] border border-[#262D35] bg-[#12161A] px-2.5 text-xs tabular-nums text-white outline-none focus:border-[#E5C378]"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label
                      htmlFor="source-form-card-patterns"
                      className="mb-1 block text-[11px] font-medium text-[#8E95A0]"
                    >
                      Regex-паттерны карточек (1 на строку)
                    </label>
                    <textarea
                      id="source-form-card-patterns"
                      rows={2}
                      value={formState.cardPatternsText}
                      onChange={(e) =>
                        setFormState((prev) =>
                          prev
                            ? { ...prev, cardPatternsText: e.target.value }
                            : prev
                        )
                      }
                      placeholder="/events/\d+"
                      className="w-full rounded-[6px] border border-[#262D35] bg-[#12161A] px-2.5 py-1.5 text-xs font-mono text-white placeholder:text-[#6B7280] outline-none focus:border-[#E5C378]"
                    />
                  </div>

                  <div>
                    <label
                      htmlFor="source-form-exclude-patterns"
                      className="mb-1 block text-[11px] font-medium text-[#8E95A0]"
                    >
                      Regex-исключения (1 на строку)
                    </label>
                    <textarea
                      id="source-form-exclude-patterns"
                      rows={2}
                      value={formState.excludePatternsText}
                      onChange={(e) =>
                        setFormState((prev) =>
                          prev
                            ? { ...prev, excludePatternsText: e.target.value }
                            : prev
                        )
                      }
                      placeholder="/archive/"
                      className="w-full rounded-[6px] border border-[#262D35] bg-[#12161A] px-2.5 py-1.5 text-xs font-mono text-white placeholder:text-[#6B7280] outline-none focus:border-[#E5C378]"
                    />
                  </div>
                </div>

                <label className="inline-flex items-center gap-2 text-xs text-[#D1D5DB] cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={formState.useJinaReader}
                    onChange={(e) =>
                      setFormState((prev) =>
                        prev
                          ? { ...prev, useJinaReader: e.target.checked }
                          : prev
                      )
                    }
                    className="h-4 w-4 rounded border-[#7C5A20] bg-[#12161A] accent-[#E5C378]"
                  />
                  <span>Обход через Jina Reader (r.jina.ai)</span>
                </label>
              </div>
            )}
          </div>

          {formError && (
            <div className="flex items-start gap-2 rounded-[6px] border border-[#EA4335]/50 bg-[#EA4335]/10 p-2.5 text-xs text-[#FCA5A5]">
              <AlertCircle className="h-4 w-4 shrink-0 mt-0.5 text-[#F87171]" />
              <span>{formError}</span>
            </div>
          )}

          {/* Результат Preview */}
          {previewResult && (
            <div className="rounded-[6px] border border-[#262D35] bg-[#0E1116] p-3 space-y-2.5">
              {previewResult.total_catalog_urls > 1 && (
                <div className="rounded-[4px] border border-[#7C5A20]/50 bg-[#1E190E] px-2.5 py-1.5 text-[11px] text-[#E5C378]">
                  Проверен 1-й URL из {previewResult.total_catalog_urls}:{" "}
                  <span className="font-mono break-all">
                    {previewResult.checked_url}
                  </span>
                </div>
              )}

              {previewResult.error ? (
                <div className="flex items-start gap-2 text-xs text-[#FCA5A5]">
                  <AlertCircle className="h-4 w-4 shrink-0 mt-0.5 text-[#F87171]" />
                  <span>{previewResult.error}</span>
                </div>
              ) : (
                <>
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    <Badge
                      variant="ebEmerald"
                      asSlanted={false}
                      className="text-[11px] font-sans not-italic"
                    >
                      Найдено: {previewResult.discovered_count}
                    </Badge>
                    <Badge
                      variant="surface"
                      asSlanted={false}
                      className="text-[11px] font-sans not-italic"
                    >
                      Отсеяно B2C: {previewResult.rejected_b2c}
                    </Badge>
                    <Badge
                      variant="surface"
                      asSlanted={false}
                      className="text-[11px] font-sans not-italic"
                    >
                      Не РФ/онлайн: {previewResult.rejected_geo}
                    </Badge>
                  </div>

                  {previewResult.sample_candidates.length === 0 ? (
                    <p className="text-xs text-[#8E95A0]">
                      Подходящих ссылок на первой странице не обнаружено.
                      Проверьте URL каталога или regex-фильтры.
                    </p>
                  ) : (
                    <ul className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
                      {previewResult.sample_candidates.map((cand, idx) => (
                        <li
                          key={`${cand.url}-${idx}`}
                          className="rounded-[4px] border border-[#21262F] bg-[#12161A] px-2.5 py-1.5 text-xs"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <a
                              href={cand.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1 font-medium text-[#E5C378] hover:underline truncate"
                            >
                              <span className="truncate">
                                {cand.title || cand.url}
                              </span>
                              <ExternalLink className="h-3 w-3 shrink-0" />
                            </a>
                            {cand.is_digest && (
                              <Badge
                                variant="ebGold"
                                asSlanted={false}
                                className="text-[10px] shrink-0 font-sans not-italic"
                              >
                                Дайджест
                              </Badge>
                            )}
                          </div>
                          <div className="text-[10px] font-mono text-[#8E95A0] truncate">
                            {cand.url}
                          </div>
                          {cand.snippet && (
                            <p className="mt-0.5 text-[11px] text-[#D1D5DB] line-clamp-2">
                              {cand.snippet}
                            </p>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </>
              )}
            </div>
          )}

          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-[#21262F] pt-3">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={previewMutation.isPending || isFormSubmitting}
              onClick={handlePreview}
              className="border-[#7C5A20]/60 bg-[#1E190E] text-xs text-[#E5C378] hover:border-[#E5C378] hover:bg-[#261E0F] hover:text-white cursor-pointer"
            >
              {previewMutation.isPending ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  <span>Проверка...</span>
                </>
              ) : (
                <>
                  <Search className="h-3.5 w-3.5" />
                  <span>Проверить ссылки (0 токенов)</span>
                </>
              )}
            </Button>

            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={closeForm}
                disabled={isFormSubmitting}
                className="border-[#262D35] bg-[#0E1116] text-xs text-[#D1D5DB] hover:border-[#E5C378] hover:text-white"
              >
                Отмена
              </Button>
              <Button
                type="submit"
                variant="monolith"
                size="sm"
                disabled={isFormSubmitting}
                className="text-xs font-semibold px-4 cursor-pointer"
              >
                {isFormSubmitting ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-[#E5C378]" />
                    <span>Сохранение...</span>
                  </>
                ) : formState.mode === "create" ? (
                  "Создать площадку"
                ) : (
                  "Сохранить изменения"
                )}
              </Button>
            </div>
          </div>
        </form>
      )}

      {/* Список всех площадок */}
      {isLoading ? (
        <div className="flex items-center justify-center gap-2 py-8 text-xs text-[#8E95A0]">
          <Loader2 className="h-4 w-4 animate-spin text-[#E5C378]" />
          <span>Загрузка площадок...</span>
        </div>
      ) : sources.length === 0 ? (
        <div className="rounded-[8px] border border-[#21262F] bg-[#12161A] p-6 text-center text-xs text-[#8E95A0]">
          Список площадок пуст. Добавьте первую площадку мониторинга.
        </div>
      ) : (
        <div className="space-y-2.5">
          {sources.map((src) => {
            const isManual = src.adapter_type === "manual_only";
            const extraUrlsCount = Math.max(0, src.catalog_urls.length - 1);
            const isConfirmingDelete = confirmDeleteKey === src.source_key;

            return (
              <div
                key={src.source_key}
                className={cn(
                  "rounded-[8px] border bg-[#12161A] p-3 transition-colors",
                  src.is_enabled || isManual
                    ? "border-[#21262F]"
                    : "border-[#21262F]/70 opacity-80"
                )}
              >
                <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2.5">
                  <div className="min-w-0 space-y-1.5">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="text-sm font-semibold text-white">
                        {src.display_name}
                      </span>
                      <span className="text-[11px] font-mono text-[#8E95A0]">
                        ({src.source_key})
                      </span>
                      <Badge
                        variant={src.is_builtin ? "ebGold" : "ebBlue"}
                        asSlanted={false}
                        className="text-[10px] font-sans not-italic"
                      >
                        {src.is_builtin ? "Встроенная" : "Пользовательская"}
                      </Badge>
                      <Badge
                        variant="surface"
                        asSlanted={false}
                        className="text-[10px] font-sans not-italic"
                      >
                        {ADAPTER_LABELS[src.adapter_type]}
                      </Badge>
                      {!isManual && !src.is_enabled && (
                        <Badge
                          variant="ebRose"
                          asSlanted={false}
                          className="text-[10px] font-sans not-italic"
                        >
                          Отключена
                        </Badge>
                      )}
                    </div>

                    <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
                      {src.b2b_filter_enabled && (
                        <span className="rounded-[4px] border border-[#262D35] bg-[#0E1116] px-1.5 py-0.5 text-[#D1D5DB]">
                          B2C-фильтр
                        </span>
                      )}
                      {src.russia_online_only && (
                        <span className="rounded-[4px] border border-[#262D35] bg-[#0E1116] px-1.5 py-0.5 text-[#D1D5DB]">
                          РФ/онлайн
                        </span>
                      )}
                      {src.use_jina_reader && (
                        <span className="rounded-[4px] border border-[#262D35] bg-[#0E1116] px-1.5 py-0.5 text-[#D1D5DB]">
                          Jina Reader
                        </span>
                      )}
                      <span className="rounded-[4px] border border-[#262D35] bg-[#0E1116] px-1.5 py-0.5 text-[#8E95A0] tabular-nums">
                        лимит: {src.max_urls_per_run} URL
                      </span>
                    </div>

                    {src.catalog_urls[0] && (
                      <div className="flex flex-wrap items-center gap-1.5 text-xs">
                        <a
                          href={src.catalog_urls[0]}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-[#E5C378] hover:underline truncate max-w-[420px]"
                        >
                          <span className="truncate">{src.catalog_urls[0]}</span>
                          <ExternalLink className="h-3 w-3 shrink-0" />
                        </a>
                        {extraUrlsCount > 0 && (
                          <span
                            title={src.catalog_urls.slice(1).join("\n")}
                            className="rounded-[4px] border border-[#7C5A20]/50 bg-[#1E190E] px-1.5 py-0.5 text-[10px] font-semibold text-[#E5C378] tabular-nums"
                          >
                            +{extraUrlsCount}
                          </span>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Действия по площадке */}
                  <div className="flex flex-wrap items-center gap-1.5 shrink-0">
                    {!isManual && (
                      <>
                        <button
                          type="button"
                          disabled={togglingKey === src.source_key}
                          onClick={() => handleToggleEnabled(src)}
                          className={cn(
                            "inline-flex items-center gap-1 rounded-[6px] border px-2.5 py-1 text-[11px] font-medium transition-colors cursor-pointer disabled:opacity-50",
                            src.is_enabled
                              ? "border-[#1E5241] bg-[#0E241E] text-[#34D399] hover:border-[#34D399]"
                              : "border-[#262D35] bg-[#0E1116] text-[#8E95A0] hover:border-[#E5C378] hover:text-white"
                          )}
                        >
                          {togglingKey === src.source_key ? (
                            <Loader2 className="h-3 w-3 animate-spin" />
                          ) : (
                            <Power className="h-3 w-3" />
                          )}
                          <span>{src.is_enabled ? "Вкл" : "Выкл"}</span>
                        </button>

                        <button
                          type="button"
                          disabled={!src.is_enabled}
                          onClick={() => onQuickRunSource(src.source_key)}
                          title={
                            src.is_enabled
                              ? "Перейти к запуску этой площадки"
                              : "Сначала включите площадку"
                          }
                          className="inline-flex items-center gap-1 rounded-[6px] border border-[#7C5A20]/60 bg-[#1E190E] px-2.5 py-1 text-[11px] font-medium text-[#E5C378] hover:border-[#E5C378] hover:bg-[#261E0F] hover:text-white transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                          <Play className="h-3 w-3" />
                          <span>Запустить</span>
                        </button>
                      </>
                    )}

                    <button
                      type="button"
                      onClick={() => openEditForm(src)}
                      className="inline-flex items-center gap-1 rounded-[6px] border border-[#262D35] bg-[#0E1116] px-2.5 py-1 text-[11px] font-medium text-[#D1D5DB] hover:border-[#E5C378] hover:text-white transition-colors cursor-pointer"
                    >
                      <Pencil className="h-3 w-3" />
                      <span>Изменить</span>
                    </button>

                    {!src.is_builtin && !isConfirmingDelete && (
                      <button
                        type="button"
                        onClick={() => setConfirmDeleteKey(src.source_key)}
                        className="inline-flex items-center gap-1 rounded-[6px] border border-[#EA4335]/40 bg-[#EA4335]/10 px-2.5 py-1 text-[11px] font-medium text-[#FCA5A5] hover:border-[#F87171] hover:text-white transition-colors cursor-pointer"
                      >
                        <Trash2 className="h-3 w-3" />
                        <span>Удалить</span>
                      </button>
                    )}

                    {!src.is_builtin && isConfirmingDelete && (
                      <div className="inline-flex items-center gap-1 rounded-[6px] border border-[#EA4335]/60 bg-[#2A1215] px-2 py-1">
                        <span className="text-[11px] text-[#FCA5A5]">
                          Удалить?
                        </span>
                        <button
                          type="button"
                          disabled={deleteMutation.isPending}
                          onClick={() => handleConfirmDelete(src)}
                          className="rounded-[4px] bg-[#DC2626] px-2 py-0.5 text-[10px] font-semibold text-white hover:bg-[#EF4444] cursor-pointer disabled:opacity-50"
                        >
                          Да
                        </button>
                        <button
                          type="button"
                          disabled={deleteMutation.isPending}
                          onClick={() => setConfirmDeleteKey(null)}
                          className="rounded-[4px] border border-[#262D35] bg-[#12161A] px-2 py-0.5 text-[10px] text-[#D1D5DB] hover:text-white cursor-pointer"
                        >
                          Нет
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
