// Public acquisition client contract (D-031): a prospect is told "received" ONLY
// when the server returns a receipt naming a durable record.  404, timeouts,
// network errors, 5xx, validation errors and malformed responses all FAIL.
//
// Pure module (no apiFetch import) so node tests can exercise it; callers inject
// the poster.  Also the analytics event boundary — no vendor is installed (D-032).

export const EVENTS = Object.freeze([
  "page_view", "cta_click", "assessment_started", "assessment_step", "assessment_submitted",
  "lead_created", "lead_qualified", "customer_created", "subscriber_activated",
]);
// Only the server may confirm these; the client emits them solely from a real receipt.
export const SERVER_CONFIRMED = Object.freeze(["lead_created", "lead_qualified", "customer_created",
  "subscriber_activated"]);

let sink = null;
/** Install an analytics sink later (none today).  Returns the previous sink. */
export function setSink(fn) {
  const prev = sink;
  sink = typeof fn === "function" ? fn : null;
  return prev;
}

/** Emit a vocabulary event.  No-op without a sink; never throws into the UI. */
export function track(name, props = {}) {
  if (!EVENTS.includes(name)) return false;
  try { if (sink) sink(name, props); } catch { /* analytics must never break a form */ }
  return true;
}

// ── attribution (first touch, this browser session) ─────────────────
const ATTR_KEY = "t911.attribution";
const UTM = ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"];

function store() {
  try { return typeof sessionStorage !== "undefined" ? sessionStorage : null; } catch { return null; }
}

/** Capture first-touch provenance once per session.  Server re-normalises it;
 *  it is never used for security. */
export function captureAttribution(loc = typeof window !== "undefined" ? window.location : null,
  referrer = typeof document !== "undefined" ? document.referrer : "", st = store()) {
  let current = null;
  try { current = st && JSON.parse(st.getItem(ATTR_KEY) || "null"); } catch { current = null; }
  if (current) return current;
  const out = {};
  if (loc) {
    out.landing_path = String(loc.pathname || "/").slice(0, 300);
    const q = new URLSearchParams(loc.search || "");
    for (const k of UTM) { const v = q.get(k); if (v) out[k] = v.slice(0, 150); }
  }
  if (referrer) out.referrer = String(referrer).split("?")[0].slice(0, 300);
  try { st && st.setItem(ATTR_KEY, JSON.stringify(out)); } catch { /* private mode */ }
  return out;
}

export function rememberCta(cta, st = store()) {
  try {
    const a = JSON.parse(st?.getItem(ATTR_KEY) || "{}");
    if (!a.initial_cta) { a.initial_cta = String(cta).slice(0, 60); st?.setItem(ATTR_KEY, JSON.stringify(a)); }
  } catch { /* ignore */ }
  track("cta_click", { cta });
}

export function getAttribution(st = store()) {
  try { return JSON.parse(st?.getItem(ATTR_KEY) || "{}"); } catch { return {}; }
}

/** One key per form attempt; reused on retry so the server never duplicates. */
export function newIdempotencyKey() {
  const c = typeof crypto !== "undefined" ? crypto : null;
  if (c?.randomUUID) return c.randomUUID();
  return `k-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`.padEnd(20, "0");
}

export function isReceipt(r) {
  return !!r && r.received === true && typeof r.record_ref === "string" && r.record_ref.length > 0;
}

/** Submit and resolve ONLY with a durable receipt; anything else throws. */
export async function submitAcquisition(post, path, body) {
  let res;
  try {
    res = await post(path, body);
  } catch (err) {
    const e = new Error(err?.status === 422
      ? "Please check the highlighted information and try again."
      : err?.status === 429
        ? "Too many attempts from this connection. Please wait a few minutes and try again."
        : "We couldn't confirm your request was received. Nothing was lost on your side — please try again.");
    e.status = err?.status ?? null;
    e.cause = err;
    throw e;
  }
  if (!isReceipt(res)) {
    const e = new Error("We couldn't confirm your request was received. Please try again.");
    e.status = null;
    throw e;
  }
  track("lead_created", { record_ref: res.record_ref });
  return res;
}
