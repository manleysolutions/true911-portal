/**
 * API client with JWT token management, auto-refresh, and 401 redirect.
 * Drop-in replacement for @base44/sdk HTTP layer.
 */

import { config } from "@/config";

const API_URL = config.apiUrl;

let _accessToken = localStorage.getItem("t911_token");
let _refreshToken = localStorage.getItem("t911_refresh");
let _refreshPromise = null;

export function setTokens(access, refresh) {
  _accessToken = access;
  _refreshToken = refresh;
  if (access) localStorage.setItem("t911_token", access);
  else localStorage.removeItem("t911_token");
  if (refresh) localStorage.setItem("t911_refresh", refresh);
  else localStorage.removeItem("t911_refresh");
}

export function clearTokens() {
  setTokens(null, null);
}

export function getAccessToken() {
  return _accessToken;
}

async function refreshAccessToken() {
  if (!_refreshToken) throw new Error("No refresh token");
  const res = await fetch(`${API_URL}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: _refreshToken }),
  });
  if (!res.ok) {
    clearTokens();
    window.location.href = "/AuthGate";
    throw new Error("Session expired");
  }
  const data = await res.json();
  setTokens(data.access_token, data.refresh_token || _refreshToken);
  return data.access_token;
}

/**
 * Fetch wrapper that injects JWT and handles 401 refresh.
 */
export async function apiFetch(path, options = {}) {
  const url = path.startsWith("http") ? path : `${API_URL}${path}`;

  const headers = { ...options.headers };
  if (_accessToken) headers["Authorization"] = `Bearer ${_accessToken}`;
  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = headers["Content-Type"] || "application/json";
  }

  let res = await fetch(url, { ...options, headers });

  // On 401, try refreshing the token once
  if (res.status === 401 && _refreshToken) {
    if (!_refreshPromise) {
      _refreshPromise = refreshAccessToken().finally(() => { _refreshPromise = null; });
    }
    try {
      const newToken = await _refreshPromise;
      headers["Authorization"] = `Bearer ${newToken}`;
      res = await fetch(url, { ...options, headers });
    } catch {
      // refresh failed — redirect handled in refreshAccessToken
      throw new Error("Session expired");
    }
  }

  if (res.status === 401) {
    clearTokens();
    window.location.href = "/AuthGate";
    throw new Error("Unauthorized");
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const err = new Error(body.detail || `API error ${res.status}`);
    err.status = res.status;
    err.body = body;
    throw err;
  }

  return res.json();
}
