import { type ReactNode, useMemo, useState } from "react";

import { api } from "../api/client";
import { AuthContext, type AuthSession, type AuthValue } from "./context";

export function AuthProvider({ children, initialSession = null }: { children: ReactNode; initialSession?: AuthSession | null }) {
  const [session, setSession] = useState<AuthSession | null>(initialSession);
  const value = useMemo<AuthValue>(
    () => ({
      session,
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
    [session],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
