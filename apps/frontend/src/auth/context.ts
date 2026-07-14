import { createContext } from "react";

import type { UserContext } from "../api/client";

export interface AuthSession {
  accessToken: string;
  user: UserContext;
}

export interface AuthValue {
  session: AuthSession | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

export const AuthContext = createContext<AuthValue | null>(null);
