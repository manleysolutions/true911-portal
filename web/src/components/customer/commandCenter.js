// ════════════════════════════════════════════════════════════════════
// Life-Safety Command Center — pure presentation rules (no React, no "@/").
//
// Everything the Command Center SAYS or COLOURS is decided here so it can be
// unit-tested with `node --test`.  It only re-presents what the API returns:
//   * UNKNOWN is never GOOD and never FAILED (D-022).
//   * Green only for evidence-backed good — never for E911 until the API carries
//     authoritative, provider-backed verification (today "Verified" can be derived
//     from legacy validated/confirmed values).
//   * No life-safety service or connection totals until the canonical inventory
//     is certified (D-023) — never derived from numbers, devices or legacy units.
//   * Customer action and True911 work are always labelled by owner (D-028).
// ════════════════════════════════════════════════════════════════════

import { portfolioHero } from "./selfService.js";

// ── Semantic status tokens (the ONLY place status colours are defined) ──
// Classes are literal strings so Tailwind's JIT sees them.  `hex` is for the
// map (Leaflet draws outside Tailwind).  Every token also carries an icon key
// and a text word — colour is never the only signal.
export const STATUS_TOKENS = {
  good: {
    word: "Good", icon: "good", hex: "#059669",
    chip: "bg-emerald-50 text-emerald-800 ring-1 ring-inset ring-emerald-200",
    text: "text-emerald-800", accent: "bg-emerald-600", tile: "ring-emerald-200",
  },
  attention: {
    word: "Attention", icon: "attention", hex: "#d97706",
    chip: "bg-amber-50 text-amber-900 ring-1 ring-inset ring-amber-300",
    text: "text-amber-900", accent: "bg-amber-500", tile: "ring-amber-300",
  },
  critical: {
    word: "Critical", icon: "critical", hex: "#dc2626",
    chip: "bg-red-50 text-red-800 ring-1 ring-inset ring-red-200",
    text: "text-red-800", accent: "bg-red-600", tile: "ring-red-300",
  },
  working: {
    word: "True911 working", icon: "working", hex: "#2563eb",
    chip: "bg-blue-50 text-blue-800 ring-1 ring-inset ring-blue-200",
    text: "text-blue-800", accent: "bg-blue-500", tile: "ring-blue-200",
  },
  unknown: {
    word: "Being confirmed", icon: "unknown", hex: "#94a3b8",
    chip: "bg-slate-50 text-slate-700 ring-1 ring-inset ring-slate-300",
    text: "text-slate-700", accent: "bg-slate-400", tile: "ring-slate-200",
  },
  neutral: {
    word: "", icon: null, hex: "#64748b",
    chip: "bg-white text-slate-700 ring-1 ring-inset ring-slate-200",
    text: "text-slate-900", accent: "bg-slate-300", tile: "ring-slate-200",
  },
};
// E911 has its own IDENTITY (the chip), separate from its status colour.
export const E911_IDENTITY = "bg-indigo-50 text-indigo-800 ring-1 ring-inset ring-indigo-300";

// Location operational tone (selfService `op.tone`) -> semantic token.
export const OP_TOKEN = { good: "good", problem: "attention", urgent: "critical", neutral: "unknown" };
export function tokenFor(opTone) {
  return STATUS_TOKENS[OP_TOKEN[opTone] || "unknown"];
}

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

// ── E911 display policy ─────────────────────────────────────────────
// Provider-backed verification is not yet available through the customer API,
// so NO E911 value is ever rendered as authoritative green "Verified".  Legacy
// "Verified" (from validated / confirmed) reads "Record on file" in neutral.
export const E911_PROVIDER_VERIFICATION_AVAILABLE = false;
const E911_DISPLAY = {
  // workspace states (self_service.e911_state)
  verified: { label: "Record on file", token: "unknown" },
  customer_confirmation_required: { label: "Your confirmation needed", token: "attention" },
  customer_submitted: { label: "Awaiting verification", token: "unknown" },
  verification_pending: { label: "Awaiting verification", token: "unknown" },
  not_verified: { label: "Being prepared by True911", token: "working" },
  failed: { label: "Needs attention", token: "attention" },
  // list-level labels (emergency_address_state)
  "Verified": { label: "Record on file", token: "unknown" },
  "Verification Pending": { label: "Awaiting verification", token: "unknown" },
  "Not yet verified": { label: "Awaiting verification", token: "unknown" },
  "Setup needed": { label: "Being prepared by True911", token: "working" },
};
export function e911Display(state) {
  return E911_DISPLAY[state] || { label: "Awaiting verification", token: "unknown" };
}

// ── The one operational statement (no score, no synthesis) ──────────
export function statusStatement(summary, ac, locations = []) {
  const m = summary || {};
  const ops = m.operational_states || {};
  const total = m.locations_total || 0;
  const attention = ops.attention_required || 0;
  const monitored = ops.monitored || 0;
  const reconciling = ops.being_reconciled || 0;
  const confirming = ops.not_yet_confirmed || 0;
  const urgent = (locations || []).filter((l) => l?.op?.tone === "urgent").length;
  const hero = portfolioHero(summary, ac);
  let tone, title;
  if (total === 0) {
    tone = "unknown"; title = "Your locations are being set up";
  } else if (urgent > 0) {
    tone = "critical"; title = `${plural(urgent, "location needs", "locations need")} attention now`;
  } else if (attention > 0) {
    tone = "attention"; title = `${plural(attention, "location needs", "locations need")} attention`;
  } else {
    title = "No known service issues";
    // green only when EVERY location is evidence-backed monitored
    tone = monitored === total ? "good" : "unknown";
  }
  const working = [
    reconciling && `True911 is confirming monitoring information at ${plural(reconciling, "location", "locations")}`,
    confirming && `True911 is confirming the status of ${plural(confirming, "location", "locations")}`,
  ].filter(Boolean);
  return {
    tone, title, total, monitored, attention, urgent,
    detail: attention ? "True911 is working on it." : working.join(" · ") || "Based on current monitoring evidence.",
    customerActions: hero.customerActions,
    true911Work: hero.operationsActions,
  };
}

// ── The four operational tiles ──────────────────────────────────────
export function opTiles(summary, ac, locations = []) {
  const m = summary || {};
  const ops = m.operational_states || {};
  const c = ac?.counts || {};
  const total = m.locations_total || 0;
  const attention = ops.attention_required || 0;
  const urgent = (locations || []).filter((l) => l?.op?.tone === "urgent").length;
  const being = (ops.being_reconciled || 0) + (ops.not_yet_confirmed || 0);
  const confirm = c.e911_confirmation_required || 0;
  const notReady = c.e911_not_ready || 0;
  return [
    { key: "locations", title: "Locations", icon: "locations", token: "neutral",
      value: total, numeric: true, target: "locations",
      detail: [`${ops.monitored || 0} monitored`, being && `${being} being confirmed by True911`].filter(Boolean).join(" · ") },
    { key: "attention", title: "Needs attention", icon: "attention",
      token: urgent ? "critical" : attention ? "attention" : "neutral",
      value: attention, numeric: true, target: "attention",
      detail: attention ? "True911 is working on it" : "No known service issues" },
    { key: "e911", title: "E911 readiness", icon: "e911", e911: true,
      token: confirm ? "attention" : "neutral", target: "actions",
      ...(ac
        ? (confirm
          ? { value: confirm, numeric: true, caption: confirm === 1 ? "needs your confirmation" : "need your confirmation" }
          : { value: "Nothing waiting on you", numeric: false })
        : { value: "Verification by the verification team", numeric: false }),
      detail: ac
        ? [notReady && `${notReady} being prepared by True911`, "Verified status appears only after official E911 verification"].filter(Boolean).join(" · ")
        : "Verified status appears only after official E911 verification" },
    { key: "services", title: "Life-safety services", icon: "services", token: "working",
      value: "Being finalized by True911", numeric: false, target: null,
      detail: "Service and connection totals appear once your inventory is certified" },
  ];
}

// ── Map markers: shape + glyph + text, never colour alone ───────────
const MARKER = {
  good: { shape: "circle", glyph: "check" },
  attention: { shape: "diamond", glyph: "!" },
  critical: { shape: "diamond", glyph: "!", large: true },
  unknown: { shape: "ring", glyph: "" },
};
export function markerView(loc, actionRefs = new Set()) {
  const key = OP_TOKEN[loc?.op?.tone] || "unknown";
  const action = actionRefs.has(loc?.location_ref);
  const label = loc?.op?.label || "Status being confirmed";
  return {
    token: key, ...MARKER[key], label, action,
    ariaLabel: `${loc?.location || "Location"}: ${label}${action ? ". Your action needed" : ""}`,
  };
}
export const MAP_LEGEND_ITEMS = [
  { token: "good", shape: "circle", label: "Monitored" },
  { token: "attention", shape: "diamond", label: "Needs attention" },
  { token: "unknown", shape: "ring", label: "Being confirmed by True911" },
  { token: "action", shape: "badge", label: "Your action needed" },
];

// ── Ownership line for every Action Center row ──────────────────────
const OWNER = {
  awaiting_your_response: { text: "Your response needed", token: "attention", owner: "customer" },
  e911_confirmation_required: { text: "Your confirmation needed", token: "attention", owner: "customer" },
  needs_attention: { text: "True911 is working on this", token: "working", owner: "true911" },
  being_reconciled: { text: "True911 is working on this", token: "working", owner: "true911" },
  e911_not_ready: { text: "True911 is preparing this", token: "working", owner: "true911" },
  service_change_requests: { text: "Submitted by you", token: "working", owner: "true911" },
  open_problems: { text: "Reported by you", token: "working", owner: "true911" },
  missing_contact_information: { text: "Optional", token: "neutral", owner: "customer" },
  recently_updated: { text: "Done", token: "neutral", owner: "none" },
};
export function ownership(sectionKey, item) {
  const o = OWNER[sectionKey] || { text: "", token: "neutral", owner: "none" };
  // a submitted request shows who acted AND who owns the next step
  if ((sectionKey === "service_change_requests" || sectionKey === "open_problems") && item?.status_label) {
    return { ...o, text: `${o.text} · ${item.status_label} · True911 owns the next step` };
  }
  return o;
}

// ── Freshness ───────────────────────────────────────────────────────
export function freshnessText(date) {
  if (!date) return "Loading…";
  const t = date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  return `Updated ${t}`;
}
