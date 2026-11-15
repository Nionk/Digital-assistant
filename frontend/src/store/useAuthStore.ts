import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import { configureApiAuth } from "@/api/client";
import type { ManagerUser, TokenOut } from "@/api/types";

interface AuthState {
  accessToken: string | null;
  user: ManagerUser | null;
  setSession: (tokenOut: TokenOut) => void;
  logout: () => void;
}

export interface ManagerDisplayInfo {
  displayName: string;
  roleLabel: string;
  initials: string;
  email: string;
  telegramChatId: number | null;
}

/**
 * Разбирает ФИО и должность из ManagerUser.full_name (например, "Анна Соколова (Ведущий менеджер)").
 */
export function parseManagerDisplayInfo(
  user: ManagerUser | null
): ManagerDisplayInfo {
  const rawName = user?.full_name?.trim() || "Персональный куратор";
  const openParen = rawName.indexOf("(");
  const closeParen = rawName.lastIndexOf(")");

  let displayName = rawName;
  let roleLabel = "Менеджер сопровождения";

  if (openParen !== -1 && closeParen > openParen) {
    displayName = rawName.slice(0, openParen).trim() || rawName;
    const extractedRole = rawName.slice(openParen + 1, closeParen).trim();
    if (extractedRole) {
      roleLabel = extractedRole;
    }
  }

  const initials =
    displayName
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase() || "")
      .join("") || "МК";

  return {
    displayName,
    roleLabel,
    initials,
    email: user?.email || "",
    telegramChatId: user?.telegram_chat_id ?? null,
  };
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      user: null,

      setSession: (tokenOut) =>
        set({
          accessToken: tokenOut.access_token,
          user: tokenOut.user,
        }),

      logout: () =>
        set({
          accessToken: null,
          user: null,
        }),
    }),
    {
      name: "skart_auth_session_v1",
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        accessToken: state.accessToken,
        user: state.user,
      }),
    }
  )
);

// Связываем транспортный клиент с JWT-сессией сразу при загрузке модуля
configureApiAuth({
  getAccessToken: () => useAuthStore.getState().accessToken,
  onUnauthorized: () => {
    if (useAuthStore.getState().accessToken !== null) {
      useAuthStore.getState().logout();
    }
  },
});
