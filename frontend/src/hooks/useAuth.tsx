/**
 * useAuth — React context + hook for OILTRACE authentication.
 *
 * Provides:
 *   user            — AuthUser | null (null = not authenticated)
 *   isAuthenticated — derived boolean
 *   isLoading       — true while the initial session check is in flight
 *   login()         — POST /api/auth/login, sets HTTP-only cookie server-side
 *   logout()        — POST /api/auth/logout, clears cookies server-side
 *   refreshAuth()   — POST /api/auth/refresh (called automatically by api.ts on 401)
 */

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { AuthContextValue, AuthUser } from "../types/auth";
import { loginUser, logoutUser, getCurrentUser } from "../services/api";

// ──────────────────────────────────────────────────────────────────────────────
// Context
// ──────────────────────────────────────────────────────────────────────────────

const AuthContext = createContext<AuthContextValue | null>(null);

// ──────────────────────────────────────────────────────────────────────────────
// Provider
// ──────────────────────────────────────────────────────────────────────────────

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Restore session from cookie on mount
  useEffect(() => {
    getCurrentUser()
      .then((u) => setUser(u))
      .catch(() => setUser(null))
      .finally(() => setIsLoading(false));
  }, []);

  const login = useCallback(async (identifier: string, password: string) => {
    const u = await loginUser(identifier, password);
    setUser(u);
  }, []);

  const logout = useCallback(async () => {
    try {
      await logoutUser();
    } catch {
      // Best-effort: clear local state even if network fails
    }
    setUser(null);
  }, []);

  const refreshAuth = useCallback(async () => {
    const u = await getCurrentUser();
    setUser(u);
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: user !== null,
        isLoading,
        login,
        logout,
        refreshAuth,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// Hook
// ──────────────────────────────────────────────────────────────────────────────

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an <AuthProvider>.");
  }
  return ctx;
}
