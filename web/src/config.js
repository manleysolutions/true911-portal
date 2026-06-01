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
  /** Feature flag: show AI / Samantha nav item. */
  featureSamantha: import.meta.env.VITE_FEATURE_SAMANTHA === "true",
  /** Feature flag: enable carrier write operations (activate/suspend/resume SIMs via carrier API).
   *  Default OFF — these actions only update local DB status until carrier APIs are wired. */
  featureCarrierWriteOps: import.meta.env.VITE_FEATURE_CARRIER_WRITE_OPS === "true",
  /** Feature flag: LLLM Phase 1 "AI Health Summary".  Default OFF — when
   *  off the AI nav item is hidden and the Command Center card is not
   *  rendered, so the portal behaves exactly as before Phase 1. */
  featureLllm: import.meta.env.VITE_FEATURE_LLLM === "true",
  /** Feature flag: hardware-agnostic Device/Property Health page.  Default
   *  OFF — when off the "Property Health" nav item is hidden and the page
   *  shows a friendly "not enabled" state (the backend also returns 404).
   *  Mirrors the backend FEATURE_DEVICE_HEALTH gate. */
  featureDeviceHealth: import.meta.env.VITE_FEATURE_DEVICE_HEALTH === "true",
};

export const isDemo = config.appMode === "demo";
