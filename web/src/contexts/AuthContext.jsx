/**
 * Unified AuthContext with SuperAdmin impersonation support.
 *
 * On mount: checks stored JWT via GET /api/auth/me.
 * Exposes: user, ready, login, logout, can, isLoadingAuth,
 *          isSuperAdmin, impersonation, startImpersonation, stopImpersonation
 *
 * Impersonation:
 *   When a SuperAdmin activates "View As", the context overrides `user.role`
 *   and `user.tenant_id` for all downstream consumers.  The real user is
 *   preserved in `impersonation.realUser`.  The `can()` function respects
 *   the impersonated role.  The API client sends X-Act-As-Tenant so the
 *   backend scopes data to the target tenant.
 */

import { createContext, useContext, useState, useEffect, useCallback } from "react";
import { apiFetch, setTokens, clearTokens, getAccessToken, setActAsTenant } from "@/api/client";
// Single source of truth — the backend reads the same JSON via
// api/app/services/rbac.py.  See permissions.json at the repo root.
import PERMISSIONS from "@permissions";

const AuthContext = createContext(null);

// Normalize role strings from backend to PascalCase
const ROLE_MAP = {
  superadmin: "SuperAdmin",
  admin: "Admin",
  manager: "Manager",
  user: "User",
  dataentry: "DataEntry",
  "data entry": "DataEntry",
};
function normalizeRole(role) {
  if (!role) return "User";
  return ROLE_MAP[role.toLowerCase()] || role;
}

// PERMISSIONS comes from the shared @permissions JSON import above.
// To change a role's grant, edit /permissions.json — both the
// frontend (here) and the backend (api/app/services/rbac.py) read
// from the same file.

// Storage key for persisting impersonation across refreshes
const IMPERSONATION_KEY = "t911_impersonation";

function loadSavedImpersonation() {
  try {
    const raw = sessionStorage.getItem(IMPERSONATION_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

function saveImpersonation(data) {
  if (data) sessionStorage.setItem(IMPERSONATION_KEY, JSON.stringify(data));
  else sessionStorage.removeItem(IMPERSONATION_KEY);
}


export function AuthProvider({ children }) {
  const [realUser, setRealUser] = useState(null);
  const [ready, setReady] = useState(false);
  const [isLoadingAuth, setIsLoadingAuth] = useState(true);
  const [impersonation, setImpersonation] = useState(loadSavedImpersonation);

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
        setRealUser({ ...u, role: normalizeRole(u.role) });
        // Restore tenant impersonation header if session was persisted
        const saved = loadSavedImpersonation();
        if (saved?.tenantId) setActAsTenant(saved.tenantId);
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
    const normalized = { ...u, role: normalizeRole(u.role) };
    setRealUser(normalized);
    return normalized;
  }, []);

  const register = useCallback(async (email, password, name) => {
    const data = await apiFetch("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, name }),
    });
    setTokens(data.access_token, data.refresh_token);
    const u = await apiFetch("/auth/me");
    const normalized = { ...u, role: normalizeRole(u.role) };
    setRealUser(normalized);
    return normalized;
  }, []);

  const logout = useCallback(() => {
    stopImpersonation();
    clearTokens();
    setRealUser(null);
    window.location.href = "/login";
  }, []);

  // ── Impersonation ──────────────────────────────────────────────
  const isRealSuperAdmin = realUser?.role === "SuperAdmin";

  const startImpersonation = useCallback((tenantId, tenantName, role) => {
    if (!isRealSuperAdmin) return;
    const imp = { tenantId, tenantName, role: normalizeRole(role) };
    setImpersonation(imp);
    saveImpersonation(imp);
    setActAsTenant(tenantId);
  }, [isRealSuperAdmin]);

  const stopImpersonation = useCallback(() => {
    setImpersonation(null);
    saveImpersonation(null);
    setActAsTenant(null);
  }, []);

  // ── Effective user (impersonated or real) ──────────────────────
  const user = realUser ? (
    impersonation ? {
      ...realUser,
      role: impersonation.role,
      tenant_id: impersonation.tenantId,
      _impersonating: true,
    } : realUser
  ) : null;

  const isSuperAdmin = impersonation ? false : isRealSuperAdmin;

  const can = useCallback(
    (action) => {
      if (!user) return false;
      // When NOT impersonating, SuperAdmin has implicit access to everything
      if (!impersonation && user.role === "SuperAdmin") return true;
      // When impersonating, use the impersonated role strictly
      const allowed = PERMISSIONS[action];
      return allowed ? allowed.includes(user.role) : false;
    },
    [user, impersonation]
  );

  return (
    <AuthContext.Provider value={{
      user,
      realUser,
      ready,
      isLoadingAuth,
      login,
      register,
      logout,
      can,
      isSuperAdmin,
      isRealSuperAdmin,
      impersonation,
      startImpersonation,
      stopImpersonation,
    }}>
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
