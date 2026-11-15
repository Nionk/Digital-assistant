import { useEffect, useRef, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useAuthStore } from "@/store/useAuthStore";

interface AuthGuardProps {
  children: ReactNode;
}

/**
 * Защищает приватные маршруты `/admin/*`: без действующей JWT-сессии
 * очищает клиентский кэш запросов и перенаправляет на `/login`.
 */
export function AuthGuard({ children }: AuthGuardProps) {
  const accessToken = useAuthStore((s) => s.accessToken);
  const user = useAuthStore((s) => s.user);
  const location = useLocation();
  const queryClient = useQueryClient();
  const prevUserIdRef = useRef<number | null>(user?.id ?? null);

  const isAuthenticated = Boolean(accessToken && user);

  useEffect(() => {
    const currentUserId = isAuthenticated ? (user?.id ?? null) : null;
    if (prevUserIdRef.current !== currentUserId) {
      queryClient.clear();
      prevUserIdRef.current = currentUserId;
    }
  }, [isAuthenticated, user?.id, queryClient]);

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <>{children}</>;
}
