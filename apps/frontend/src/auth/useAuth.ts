import { useContext } from "react";

import { AuthContext, type AuthValue } from "./context";

export function useAuth(): AuthValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("AuthProvider is missing");
  return context;
}
