import { toast } from "sonner";

export interface CopyToClipboardOptions {
  successMessage?: string;
  errorMessage?: string;
}

/**
 * Безопасное копирование текста в буфер обмена с честной обработкой отказов
 * (включая HTTP-контексты без navigator.clipboard или запрет разрешений браузера).
 */
export async function copyTextToClipboard(
  text: string,
  options?: CopyToClipboardOptions
): Promise<boolean> {
  if (!text) return false;

  if (
    typeof navigator === "undefined" ||
    !navigator.clipboard ||
    typeof navigator.clipboard.writeText !== "function"
  ) {
    toast.error(
      options?.errorMessage ??
        "Буфер обмена недоступен в текущем контексте (требуется HTTPS или разрешение браузера)."
    );
    return false;
  }

  try {
    await navigator.clipboard.writeText(text);
    if (options?.successMessage) {
      toast.success(options.successMessage);
    }
    return true;
  } catch (err) {
    const reason =
      err instanceof Error && err.message ? ` (${err.message})` : "";
    toast.error(
      options?.errorMessage ??
        `Не удалось скопировать в буфер обмена${reason}. Скопируйте текст вручную.`
    );
    return false;
  }
}
