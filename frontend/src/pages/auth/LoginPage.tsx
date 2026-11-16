import * as React from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff, Loader2, Lock, Mail, AlertCircle } from "lucide-react";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { ApiError } from "@/api/client";
import { useLoginMutation } from "@/api/queries";
import { useAuthStore } from "@/store/useAuthStore";
import { Button } from "@/components/ui/button";
import logoImage from "@/assets/images/logo.png";

interface LocationState {
  from?: {
    pathname?: string;
    search?: string;
  };
}

function getSafeRedirectTarget(state: LocationState | null): string {
  const pathname = state?.from?.pathname;
  if (!pathname || !pathname.startsWith("/admin")) {
    return "/admin";
  }
  return `${pathname}${state?.from?.search || ""}`;
}

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();

  const accessToken = useAuthStore((s) => s.accessToken);
  const user = useAuthStore((s) => s.user);
  const setSession = useAuthStore((s) => s.setSession);

  const loginMutation = useLoginMutation();

  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [showPassword, setShowPassword] = React.useState(false);
  const [formError, setFormError] = React.useState<string | null>(null);

  const redirectTarget = getSafeRedirectTarget(
    (location.state as LocationState | null) ?? null
  );

  if (accessToken && user) {
    return <Navigate to={redirectTarget} replace />;
  }

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setFormError(null);

    const normalizedEmail = email.trim();
    if (!normalizedEmail) {
      setFormError("Введите корпоративный email менеджера.");
      return;
    }
    if (!password) {
      setFormError("Введите пароль для входа.");
      return;
    }

    try {
      const tokenOut = await loginMutation.mutateAsync({
        email: normalizedEmail,
        password,
      });

      queryClient.clear();
      setSession(tokenOut);
      toast.success(`Добро пожаловать, ${tokenOut.user.full_name}`);
      navigate(redirectTarget, { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401 || err.status === 403) {
          setFormError("Неверный email или пароль. Проверьте учетные данные.");
          return;
        }
        setFormError(err.message);
        return;
      }
      setFormError("Не удалось выполнить вход. Проверьте подключение к серверу.");
    }
  };

  return (
    <div className="min-h-screen bg-[#0B0E12] text-[#F1F5F9] flex flex-col items-center justify-center px-4 py-8">
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.22, ease: "easeOut" }}
        className="w-full max-w-[420px] overflow-hidden rounded-[12px] border border-[#262D35] bg-[#161B22] shadow-[0_24px_60px_rgba(0,0,0,0.65)]"
      >
        <div className="border-b border-[#262D35] bg-[#0E1215]/80 px-6 py-5">
          <div className="flex items-center gap-3">
            <img
              src={logoImage}
              alt="EXEDRA"
              className="h-8 w-auto object-contain"
            />
            <div className="h-5 w-[1px] bg-[#262D35]" />
            <div>
              <span className="block text-[11px] font-semibold uppercase tracking-[0.14em] text-[#94A3B8]">
                Менеджерский терминал
              </span>
              <h1 className="font-serif italic text-[18px] leading-tight text-[#E5C378]">
                Вход в рабочую среду
              </h1>
            </div>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 p-6" noValidate>
          {formError && (
            <div
              role="alert"
              className="flex items-start gap-2.5 rounded-[8px] border border-[#EA4335]/40 bg-[#EA4335]/10 px-3.5 py-2.5 text-xs text-[#FCA5A5]"
            >
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-[#F87171]" />
              <span>{formError}</span>
            </div>
          )}

          <div className="space-y-1.5">
            <label
              htmlFor="login-email"
              className="block text-[11px] font-semibold uppercase tracking-[0.08em] text-[#94A3B8]"
            >
              Email куратора
            </label>
            <div className="relative">
              <Mail className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#8E95A0]" />
              <input
                id="login-email"
                name="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@exedra.ru"
                disabled={loginMutation.isPending}
                className="h-10 w-full rounded-[8px] border border-[#38414F] bg-[#12161A] pl-9 pr-3.5 text-sm text-[#F1F5F9] placeholder:text-[#8E95A0] transition-colors focus:border-[#E5C378] focus:shadow-[0_0_0_1px_rgba(229,195,120,0.25)] focus:outline-none disabled:opacity-60"
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <label
              htmlFor="login-password"
              className="block text-[11px] font-semibold uppercase tracking-[0.08em] text-[#94A3B8]"
            >
              Пароль
            </label>
            <div className="relative">
              <Lock className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#8E95A0]" />
              <input
                id="login-password"
                name="password"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Введите пароль"
                disabled={loginMutation.isPending}
                className="h-10 w-full rounded-[8px] border border-[#38414F] bg-[#12161A] pl-9 pr-10 text-sm text-[#F1F5F9] placeholder:text-[#8E95A0] transition-colors focus:border-[#E5C378] focus:shadow-[0_0_0_1px_rgba(229,195,120,0.25)] focus:outline-none disabled:opacity-60"
              />
              <button
                type="button"
                onClick={() => setShowPassword((prev) => !prev)}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded p-1 text-[#94A3B8] transition-colors hover:text-[#CBD5E1]"
                aria-label={showPassword ? "Скрыть пароль" : "Показать пароль"}
              >
                {showPassword ? (
                  <EyeOff className="h-4 w-4" />
                ) : (
                  <Eye className="h-4 w-4" />
                )}
              </button>
            </div>
          </div>

          <div className="pt-2">
            <Button
              type="submit"
              variant="monolith"
              size="lg"
              disabled={loginMutation.isPending}
              className="w-full"
            >
              {loginMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span>Выполняется вход...</span>
                </>
              ) : (
                <span>Войти в систему</span>
              )}
            </Button>
          </div>
        </form>
      </motion.div>
    </div>
  );
}
