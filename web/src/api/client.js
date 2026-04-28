/**
 * API client with JWT token management, auto-refresh, and 401 redirect.
 * Drop-in replacement for @base44/sdk HTTP layer.
 */

import { config } from "@/config";

const API_URL = config.apiUrl;

let _accessToken = localStorage.getItem("t911_token");
let _refreshToken = localStorage.getItem("t911_refresh");
let _refreshPromise = null;
let _actAsTenantId = null;

export function setActAsTenant(tenantId) {
  _actAsTenantId = tenantId || null;
}

export function getActAsTenant() {
  return _actAsTenantId;
}

export function setTokens(access, refresh) {
  _accessToken = access;
  _refreshToken = refresh;
  if (access) localStorage.setItem("t911_token", access);
  else localStorage.removeItem("t911_token");
  if (refresh) localStorage.setItem("t911_refresh", refresh);
  else localStorage.removeItem("t911_refresh");
}

export function clearTokens() {
  _accessToken = null;
  _refreshToken = null;
  _actAsTenantId = null;
  localStorage.removeItem("t911_token");
  localStorage.removeItem("t911_refresh");
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
    window.location.href = "/login";
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
  if (_actAsTenantId) headers["X-Act-As-Tenant"] = _actAsTenantId;
  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = headers["Content-Type"] || "application/json";
  }

  let res;
  try {
    res = await fetch(url, { ...options, headers });
  } catch (networkErr) {
    // fetch() itself throws on network failures (DNS, CORS block, offline).
    // Wrap with actionable context instead of bare "Failed to fetch".
    const msg =
      "Network error — unable to reach the API server. " +
      "This may be a CORS restriction, a DNS issue, or the server may be down.";
    const err = new Error(msg);
    err.cause = networkErr;
    throw err;
  }

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
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const err = new Error(extractDetailMessage(body, res));
    err.status = res.status;
    err.body = body;
    throw err;
  }

  return res.json();
}

/**
 * Build a user-readable error message from a FastAPI/Pydantic error body.
 *
 * FastAPI's `HTTPException(detail=…)` can hand us a string, an object, or
 * an array (Pydantic validation).  This helper produces a single string
 * for `new Error(...)` so the UI doesn't end up showing "[object Object]"
 * or stringified arrays.
 *
 * 401 responses do NOT use this — that path keeps its existing message
 * and still redirects to /login.
 */
function extractDetailMessage(body, res) {
  const detail = body && body.detail;

  // Plain string detail — most common shape.
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }

  // Pydantic validation errors: array of { loc, msg, type, ... }.
  if (Array.isArray(detail) && detail.length > 0) {
    const lines = detail.map((item) => {
      if (!item || typeof item !== "object") return String(item);
      const loc = Array.isArray(item.loc)
        ? item.loc.filter((p) => p !== "body").join(".")
        : "";
      const msg = item.msg || item.message || "Invalid value";
      return loc ? `${loc}: ${msg}` : msg;
    });
    return lines.join("\n");
  }

  // Structured object detail (e.g. our 409 conflict payloads:
  // { field, value, conflicting_*_id, message }).  Prefer an
  // explicit message field; otherwise fall back to a JSON dump so the
  // user at least sees the real fields instead of "[object Object]".
  if (detail && typeof detail === "object") {
    if (typeof detail.message === "string" && detail.message.trim()) {
      return detail.message;
    }
    try {
      return JSON.stringify(detail);
    } catch {
      // fall through to status-based fallback
    }
  }

  // Some routes return { message } at the top level instead of detail.
  if (typeof body?.message === "string" && body.message.trim()) {
    return body.message;
  }

  // Final fallback — prefer the HTTP status text (e.g. "Unprocessable
  // Entity") over our old generic "API error 422".
  return res.statusText || `Request failed (${res.status})`;
}
