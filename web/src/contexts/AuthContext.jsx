/**
 * Unified AuthContext — replaces both lib/AuthContext.jsx and components/AuthContext.jsx.
 *
 * On mount: checks stored JWT via GET /api/auth/me.
 * Exposes: user, ready, login, logout, can, isLoadingAuth
 */

import { createContext, useContext, useState, useEffect, useCallback } from "react";
import { apiFetch, setTokens, clearTokens, getAccessToken } from "@/api/client";

const AuthContext = createContext(null);

// RBAC permission matrix — identical to the original components/AuthContext.jsx
const PERMISSIONS = {
  PING: ["Admin", "Manager"],
  REBOOT: ["Admin"],
  GENERATE_REPORT: ["Admin", "Manager"],
  UPDATE_E911: ["Admin"],
  UPDATE_HEARTBEAT: ["Admin"],
  VIEW_ADMIN: ["Admin"],
  RESTART_CONTAINER: ["Admin"],
  PULL_LOGS: ["Admin"],
  SWITCH_CHANNEL: ["Admin"],
  ACK_INCIDENT: ["Admin", "Manager"],
  CLOSE_INCIDENT: ["Admin", "Manager"],
  MANAGE_NOTIFICATIONS: ["Admin"],
};

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);
  const [isLoadingAuth, setIsLoadingAuth] = useState(true);

  // Check existing token on mount
  useEffect(() => {
    const token = getAccessToken();
    if (!token) {
      setReady(true);
      setIsLoadingAuth(false);
      return;
    }
    apiFetch("/auth/me")
      .then((u) => {
        setUser(u);
      })
      .catch(() => {
        clearTokens();
      })
      .finally(() => {
        setReady(true);
        setIsLoadingAuth(false);
      });
  }, []);

  const login = useCallback(async (email, password) => {
    const data = await apiFetch("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setTokens(data.access_token, data.refresh_token);
    const u = await apiFetch("/auth/me");
    setUser(u);
    return u;
  }, []);

  const register = useCallback(async (email, password, name) => {
    const data = await apiFetch("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, name }),
    });
    setTokens(data.access_token, data.refresh_token);
    const u = await apiFetch("/auth/me");
    setUser(u);
    return u;
  }, []);

  const logout = useCallback(() => {
    clearTokens();
    setUser(null);
    window.location.href = "/AuthGate";
  }, []);

  const can = useCallback(
    (action) => {
      if (!user) return false;
      const allowed = PERMISSIONS[action];
      return allowed ? allowed.includes(user.role) : false;
    },
    [user]
  );

  return (
    <AuthContext.Provider value={{ user, ready, isLoadingAuth, login, register, logout, can }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be inside AuthProvider");
  return ctx;
}

export default AuthContext;
