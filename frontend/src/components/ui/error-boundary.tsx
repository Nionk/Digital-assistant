import * as React from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";

interface AppErrorBoundaryProps {
  children: React.ReactNode;
}

interface AppErrorBoundaryState {
  hasError: boolean;
  errorMessage: string | null;
}

/**
 * Корневой предохранитель рендеринга SPA в визуальном стиле платформы.
 */
export class AppErrorBoundary extends React.Component<
  AppErrorBoundaryProps,
  AppErrorBoundaryState
> {
  constructor(props: AppErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, errorMessage: null };
  }

  static getDerivedStateFromError(error: Error): AppErrorBoundaryState {
    return {
      hasError: true,
      errorMessage: error.message || "Непредвиденная ошибка интерфейса",
    };
  }

  override componentDidCatch(error: Error, info: React.ErrorInfo): void {
    console.error("AppErrorBoundary caught error:", error, info);
  }

  private handleReload = (): void => {
    window.location.reload();
  };

  override render(): React.ReactNode {
    if (!this.state.hasError) {
      return this.props.children;
    }

    return (
      <div className="min-h-screen bg-[#0B0E12] text-[#F3F4F6] flex items-center justify-center p-4">
        <div className="w-full max-w-md rounded-[12px] border border-[#262D35] bg-[#161B22] p-6 shadow-2xl">
          <div className="flex items-center gap-3 border-b border-[#21262F] pb-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[8px] border border-[#7C5A20]/60 bg-[#261E0F] text-[#E5C378]">
              <AlertTriangle className="h-4 w-4" strokeWidth={2} />
            </div>
            <div>
              <h1 className="font-serif italic text-base font-semibold text-[#E5C378]">
                Ошибка отображения интерфейса
              </h1>
              <p className="text-xs text-[#8E95A0]">
                Работа модуля приостановлена для защиты данных
              </p>
            </div>
          </div>

          <p className="mt-4 rounded-[8px] border border-[#21262F] bg-[#12161A] p-3 text-xs text-[#D1D5DB] break-words">
            {this.state.errorMessage}
          </p>

          <button
            type="button"
            onClick={this.handleReload}
            className="btn-monolith mt-5 w-full h-10 rounded-[8px] inline-flex items-center justify-center gap-2 text-xs font-semibold cursor-pointer"
          >
            <RotateCcw className="h-3.5 w-3.5" strokeWidth={2} />
            <span>Обновить страницу</span>
          </button>
        </div>
      </div>
    );
  }
}
