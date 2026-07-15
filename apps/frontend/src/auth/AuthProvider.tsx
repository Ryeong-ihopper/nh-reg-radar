import { type ReactNode, useCallback, useEffect, useLayoutEffect, useMemo, useState } from "react";

import { api, setAuthRefreshHandler } from "../api/client";
import { AuthContext, type AuthSession, type AuthValue } from "./context";

export function AuthProvider({ children, initialSession }: { children: ReactNode; initialSession?: AuthSession | null }) {
  const [session, setSession] = useState<AuthSession | null>(initialSession ?? null);
  const [isInitializing, setIsInitializing] = useState(initialSession === undefined);
  const refresh = useCallback(async () => {
    try {
      const response = await api.refresh();
      setSession({ accessToken: response.accessToken, user: response.user });
      return response;
    } catch {
      setSession(null);
      return null;
    } finally {
      setIsInitializing(false);
    }
  }, []);

  useLayoutEffect(() => {
    setAuthRefreshHandler(refresh);
    return () => setAuthRefreshHandler(null);
  }, [refresh]);

  useEffect(() => {
    if (initialSession === undefined) void refresh();
  }, [initialSession, refresh]);

  const value = useMemo<AuthValue>(
    () => ({
      session,
      isInitializing,
      async login(email, password) {
        const response = await api.login(email, password);
        // Access tokens intentionally remain in memory; refresh is protected by an httpOnly cookie.
        setSession({ accessToken: response.accessToken, user: response.user });
      },
      async logout() {
        try {
          await api.logout();
        } finally {
          setSession(null);
        }
      },
    }),
    [isInitializing, session],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
