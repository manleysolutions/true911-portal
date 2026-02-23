/**
 * Runtime-safe app configuration.
 *
 * Reads VITE_API_URL (or VITE_API_BASE_URL) at build time (baked by Vite).
 * If the env var was never set, `apiUrl` will be the fallback "/api".
 *
 * For local dev this is fine (Vite proxy handles /api -> localhost:8000).
 * For Render static sites, VITE_API_URL must be set to the full API URL.
 */

export const config = {
  /** Base URL for all API calls (no trailing slash). Prefer VITE_API_URL, fall back to VITE_API_BASE_URL. */
  apiUrl: import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE_URL || "/api",
  /** "demo" | "production" — controls demo banners, role picker, etc. Default is production-safe. */
  appMode: import.meta.env.VITE_APP_MODE || "production",
};

export const isDemo = config.appMode === "demo";
